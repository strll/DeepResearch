"""后台研究任务的业务逻辑实现。

该模块提供四个 run_* 函数供 celery_tasks.py 中的 Celery 任务调用，
每个函数负责完整的任务生命周期：标记运行 → 执行业务 → 标记成功 / 失败。
"""

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
        logger.info("开始生成研究任务书和大纲，project_id={}，task_id={}", project_id, task_id)

        agent = get_research_agent()
        project = await research_project_repository.get_project(project_id)
        result = await agent.generate_outline(
            project_id=project_id,
            research_project=project,
            task_id=task_id,
        )

        await research_project_repository.save_research_brief_and_outline(
            project_id=project_id,
            research_brief=result.get("research_brief"),
            outline=result.get("outline", []),
        )
        await research_project_repository.update_project_status(project_id, ProjectStatus.OUTLINE_READY)
        await research_task_repository.mark_task_succeeded(task_id, "研究任务书和大纲已生成，等待用户确认")
        logger.info("研究任务书和大纲生成完成，project_id={}，task_id={}", project_id, task_id)

    except Exception as exc:
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
        logger.info("开始执行研究和报告渲染，project_id={}，task_id={}", project_id, task_id)

        agent = get_research_agent()

        # 第一步：执行研究
        await agent.generate_research_result(
            project_id=project_id,
            user_instruction=user_instruction,
            task_id=task_id,
        )
        research_result = await research_project_repository.get_research_result(project_id=project_id)
        logger.info("研究结果已保存，project_id={}，task_id={}", project_id, task_id)

        # 第二步：渲染 HTML 报告
        html_result = write_html(research_result)
        await report_repository.save_report_version(
            project_id=project_id,
            title=html_result.get("title", ""),
            html=html_result.get("html", ""),
            sources=html_result.get("sources", []),
        )

        await research_project_repository.update_project_status(project_id, ProjectStatus.REPORT_READY)
        await research_task_repository.mark_task_succeeded(task_id, "研究报告已生成")
        logger.info("研究和报告渲染完成，project_id={}，task_id={}", project_id, task_id)

    except Exception as exc:
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
