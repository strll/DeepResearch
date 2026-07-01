"""后台研究任务的业务逻辑实现。

该模块提供四个 run_* 函数供 celery_tasks.py 中的 Celery 任务调用，
每个函数负责完整的任务生命周期：标记运行 → 执行业务 → 标记成功 / 失败。
"""
import json
import time
from typing import Any

from loguru import logger

from app.agents.research_agent import get_research_agent
from app.repository import report_repository, research_project_repository, research_task_repository
from app.schemas import ProjectStatus, TaskStatus
from app.tools.render_html import write_html


# ============================================================================
#  Celery 任务投递
# ============================================================================

def _send_task(task_path: str, args: tuple) -> None:
    """把后台任务投递到 Celery 队列。"""
    from app.celery_app import celery_app
    celery_app.send_task(task_path, args=args)
    logger.info("后台任务已投递，task_path={}，args={}", task_path, args)


# ---- 对外入口：供 routers 层调用 ----

def start_generate_research_brief_task(project_id: str, task_id: str) -> None:
    """投递大纲生成任务到 Celery。"""
    _send_task("research.generate_research_brief", (project_id, task_id))


def start_revise_outline_task(project_id: str, task_id: str, revision_instruction: str) -> None:
    """投递大纲修改任务到 Celery。"""
    _send_task("research.revise_outline", (project_id, task_id, revision_instruction))


def start_generate_report_task(project_id: str, task_id: str, user_instruction: str | None) -> None:
    """投递报告生成任务到 Celery。"""
    _send_task("research.generate_report", (project_id, task_id, user_instruction))


def start_render_report_task(project_id: str, task_id: str, user_instruction: str | None) -> None:
    """投递独立报告渲染任务到 Celery。"""
    _send_task("research.render_report", (project_id, task_id, user_instruction))


# ============================================================================
#  任务执行逻辑（由 Celery Worker 调用）
# ============================================================================

async def run_generate_research_brief_task(project_id: str, task_id: str) -> None:
    """执行研究任务书和大纲生成任务。"""
    try:
        await research_task_repository.mark_task_running(task_id, "正在生成研究任务书和大纲")
        await research_project_repository.update_project_status(project_id, ProjectStatus.BRIEF_GENERATING)
        logger.info("[STEP 1/4] 开始生成研究任务书和大纲，project_id={}，task_id={}", project_id, task_id)

        logger.info("[STEP 2/4] 初始化研究智能体...")
        agent = get_research_agent()
        logger.info("[STEP 2/4] 研究智能体初始化完成")

        logger.info("[STEP 3/4] 读取项目信息，project_id={}", project_id)
        project = await research_project_repository.get_project(project_id)
        if project is None:
            raise ValueError(f"项目不存在: {project_id}")
        logger.info("[STEP 3/4] 项目信息读取完成，topic={}", project.get("topic", "未知"))

        safe_project_for_agent = json.loads(json.dumps(project, default=str))

        logger.info("[STEP 4/4] 调用 Agent 生成大纲，thread_id={}_{}", project_id, task_id)
        result = await agent.generate_outline(
            project_id=project_id,
            research_project=safe_project_for_agent,
            task_id=task_id,
        )
        logger.info("[STEP 4/4] Agent 返回结果，has_outline={}", bool(result.get("outline")))

        await research_project_repository.save_research_brief_and_outline(
            project_id=project_id,
            research_brief=result.get("research_brief"),
            outline=result.get("outline", []),
        )
        await research_project_repository.update_project_status(project_id, ProjectStatus.OUTLINE_READY)
        await research_task_repository.mark_task_succeeded(task_id, "研究任务书和大纲已生成，等待用户确认")
        logger.info("[完成] 研究任务书和大纲生成完成，project_id={}，task_id={}", project_id, task_id)

    except Exception as exc:
        logger.error("[失败] 步骤失败，错误类型={}，详情={}", type(exc).__name__, str(exc))
        await _mark_task_failed(project_id, task_id, "研究任务书和大纲生成失败", exc)
        raise


async def run_revise_outline_task(project_id: str, task_id: str, revision_instruction: str) -> None:
    """执行研究大纲修改任务。"""
    try:
        await research_task_repository.mark_task_running(task_id, "正在根据用户要求修改研究大纲")
        await research_project_repository.update_project_status(project_id, ProjectStatus.OUTLINE_REVISING)
        logger.info("开始修改研究大纲，project_id={}，task_id={}", project_id, task_id)

        agent = get_research_agent()
        project = await research_project_repository.get_project(project_id)
        revised = await agent.revise_outline(
            project_id=project_id,
            research_project=project,
            revision_instruction=revision_instruction,
            task_id=task_id,
        )

        await research_project_repository.save_outline(project_id=project_id, outline=revised)
        await research_project_repository.update_project_status(project_id, ProjectStatus.OUTLINE_READY)
        await research_task_repository.mark_task_succeeded(task_id, "研究大纲已修改，等待用户确认")
        logger.info("研究大纲修改完成，project_id={}，task_id={}", project_id, task_id)

    except Exception as exc:
        await _mark_task_failed(project_id, task_id, "研究大纲修改失败", exc)
        raise


async def run_generate_report_task(project_id: str, task_id: str, user_instruction: str | None) -> None:
    """执行研究报告生成任务。

    分为两步：1) 执行研究过程并保存研究结果  2) 渲染 HTML 报告并保存版本。
    """
    try:
        await research_task_repository.mark_task_running(task_id, "正在执行研究并生成报告")
        await research_project_repository.update_project_status(project_id, ProjectStatus.RESEARCH_RUNNING)
        logger.info("[STEP 1/4] 开始执行研究和报告渲染，project_id={}，task_id={}", project_id, task_id)

        agent = get_research_agent()

        logger.info("[STEP 2/4] 执行研究（Agent 逐章节检索+撰写）...")
        t0 = time.perf_counter()
        research_result = await agent.generate_research_result(
            project_id=project_id,
            user_instruction=user_instruction,
            task_id=task_id,
        )
        logger.info("[STEP 2/4] 研究执行完成，耗时={:.1f}s", time.perf_counter() - t0)

        # generate_research_result 返回了 research_result，直接使用
        sections = research_result.get("sections", []) if isinstance(research_result, dict) else []
        if not sections:
            logger.warning("generate_research_result 返回的 research_result 没有章节数据，"
                           "回退到从 MongoDB 读取")
            research_result = await research_project_repository.get_research_result(project_id=project_id)
            if isinstance(research_result, str):
                try:
                    research_result = json.loads(research_result)
                except Exception:
                    research_result = None
            elif not isinstance(research_result, dict):
                research_result = None
            if research_result is None:
                project_doc = await research_project_repository.get_project(project_id=project_id)
                if not project_doc:
                    raise ValueError(f"项目不存在: {project_id}")
                sections = await research_project_repository.get_research_sections(project_id)
                sources = project_doc.get("sources", [])
                fact_cards = project_doc.get("fact_cards", [])
                insight_cards = project_doc.get("insight_cards", [])
                research_result = {
                    "title": project_doc.get("topic", "研究报告"),
                    "sections": sections,
                    "sources": sources,
                    "fact_cards": fact_cards,
                    "insight_cards": insight_cards,
                }
            sections = research_result.get("sections", []) if isinstance(research_result, dict) else []
        if not sections:
            raise ValueError(
                f"研究结果中没有章节数据（project_id={project_id}）。"
                f"可能原因：LLM 未调用 save_research_sections 工具，"
                f"或工具调用被校验逻辑拒绝。请查看 Celery 日志确认 Agent 输出。"
            )
        logger.info("[STEP 3/4] 研究结果已保存，project_id={}，sections={}", project_id, len(sections))

        logger.info("[STEP 4/4] 渲染 HTML 报告...")
        html_result = write_html(research_result)
        await report_repository.save_report_version(
            project_id=project_id,
            title=html_result.get("title", ""),
            html=html_result.get("html", ""),
            sources=html_result.get("sources", []),
        )

        await research_project_repository.update_project_status(project_id, ProjectStatus.REPORT_READY)
        await research_task_repository.mark_task_succeeded(task_id, "研究报告已生成")
        logger.info("[完成] 研究和报告渲染完成，project_id={}，task_id={}", project_id, task_id)

    except Exception as exc:
        logger.error("[失败] 报告生成失败，错误类型={}，详情={}", type(exc).__name__, str(exc))
        await _mark_task_failed(project_id, task_id, "研究报告生成失败", exc)
        raise


async def run_render_report_task(project_id: str, task_id: str, user_instruction: str | None) -> None:
    """执行独立报告渲染任务。

    只读取已落库的 research_result 并重新渲染 HTML，不重新执行研究。
    """
    try:
        await research_task_repository.mark_task_running(task_id, "正在基于已有研究结果渲染报告")
        logger.info("开始独立渲染报告，project_id={}，task_id={}", project_id, task_id)

        research_result = await research_project_repository.get_research_result(project_id=project_id)
        if research_result is None:
            raise ValueError("项目缺少已落库的 research_result，无法直接渲染报告")

        html_result = write_html(research_result)
        await report_repository.save_report_version(
            project_id=project_id,
            title=html_result.get("title", ""),
            html=html_result.get("html", ""),
            sources=html_result.get("sources", []),
        )

        await research_project_repository.update_project_status(project_id, ProjectStatus.REPORT_READY)
        await research_task_repository.mark_task_succeeded(task_id, "报告已基于已有研究结果生成")
        logger.info("独立报告渲染完成，project_id={}，task_id={}", project_id, task_id)

    except Exception as exc:
        await _mark_task_failed(project_id, task_id, "独立报告渲染失败", exc)
        raise


# ============================================================================
#  错误处理
# ============================================================================

async def _mark_task_failed(project_id: str, task_id: str, message: str, exc: Exception) -> None:
    """统一记录后台任务失败状态。"""
    error_message = _build_task_error_message(message, exc)
    logger.exception(
        "后台任务执行失败，project_id={}，task_id={}，error={}",
        project_id,
        task_id,
        error_message,
    )
    await research_task_repository.mark_task_failed(task_id, error_message)


def _build_task_error_message(message: str, exc: Exception) -> str:
    """构建写入任务状态的短错误摘要。"""
    detail = str(exc).strip()
    if detail:
        return f"{message}: {type(exc).__name__}: {detail[:500]}"
    return f"{message}: {type(exc).__name__}"


# ============================================================================
#  兼容旧接口（逐步迁移中）
# ============================================================================

import asyncio


def start_report_generation(task_id: str, project_id: str, user_instruction: str | None = None):
    """兼容旧接口，内部转为 Celery 投递。"""
    start_generate_report_task(project_id, task_id, user_instruction)


def start_report_generate(task_id: str, project_id: str, user_instruction: str | None = None):
    """兼容旧接口，内部转为 Celery 投递。"""
    start_generate_report_task(project_id, task_id, user_instruction)


def start_outline_generation(research_project, task_id: str, project_id: str):
    """兼容旧接口，内部转为 Celery 投递。"""
    start_generate_research_brief_task(project_id, task_id)
