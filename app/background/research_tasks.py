"""
TODO: 【高优先级】接入 Celery 后台任务系统，完善任务实现
参照: app/background/research_tasks.py (参考项目) - 完整的 Celery 桥接 + 异步任务

当前状态: 直接使用 asyncio.create_task() 在 API 进程中执行，不具备:
- 任务持久化（进程重启丢失）
- 失败自动重试
- 多 worker 并发
- 任务进度追踪

需要修改的内容:

1. 【架构变更】从 asyncio.create_task() 改为 Celery 投递:
   - start_* 函数改为调用 _send_task() 投递到 Celery 队列
   - 独立的 celery worker 进程消费任务
   - 参考: app/background/research_tasks.py (参考项目)

2. 【缺失】start_generate_research_brief_task(project_id, task_id):
   - 调用 _send_task("research.generate_research_brief", ...)

3. 【缺失】start_revise_outline_task(project_id, task_id, revision_instruction):
   - 调用 _send_task("research.revise_outline", ...)

4. 【缺失】start_render_report_task(project_id, task_id, user_instruction):
   - 调用 _send_task("research.render_report", ...)
   - 独立报告渲染：只读已落库 research_result，重新渲染 HTML

5. 【需重写】start_report_generation -> start_generate_report_task():
   - 改为 Celery 投递，而非 asyncio.create_task()

6. 【需重写】_start_report_generate() 任务实现:
   - 拆分为 run_generate_report_task() + run_render_report_task()
   - 研究过程 -> 调用 agent.generate_research_result()
   - 渲染过程 -> 调用 agent.generate_report()

7. 【缺失】_send_task() 投递函数:
   - from app.celery_app import celery_app
   - celery_app.send_task(task_path, args=args)

8. 【缺失】run_* 函数: 实际任务执行逻辑
   - run_generate_research_brief_task(project_id, task_id)
   - run_revise_outline_task(project_id, task_id, revision_instruction)
   - run_generate_report_task(project_id, task_id, user_instruction)
   - run_render_report_task(project_id, task_id, user_instruction)

9. 【缺失】_mark_task_failed() 统一错误处理:
   - 更新任务状态为 FAILED
   - 记录错误日志（不泄露 API Key）

10.【缺失】错误详情提取: _build_task_error_message(), _extract_exception_attrs()
"""

import asyncio

from app.agents import research_agent
from app.agents.research_agent import get_research_agent
from app.repository import research_project_repository, report_repository
from app.repository.research_project_repository import update_project_status, save_outline
from app.repository.research_task_repository import update_status
from app.schemas import TaskStatus, ProjectStatus
from app.tools.render_html import write_html


async def _start_report_generation(task_id: str, project_id: str):
    # TODO: 此函数为空壳，需要实现完整的报告生成逻辑
    # 应该拆分为 run_generate_report_task() 和 run_render_report_task()
    try:
        await update_status(task_id=task_id, status=TaskStatus.RUNNING)



    except Exception as e:
        await update_status(task_id=task_id, status=TaskStatus.FAILED)
        print(f"当前任务出现异常 {task_id} 报错是 {str(e)}")


def start_report_generation(task_id: str, project_id: str, user_instruction):
    # TODO: 改为 Celery 投递 _send_task("research.generate_report", ...)
    start_report_generation_res = _start_report_generation(task_id=task_id, project_id=project_id)
    asyncio.create_task(start_report_generation_res)


# 进行研究 保存报告的协程
async def _start_report_generate(task_id: str, project_id: str, user_instruction):
    # TODO: 重命名为 run_generate_report_task()
    # TODO: 拆分为两步:
    #   1. agent.generate_research_result() -> 保存 research_result
    #   2. agent.generate_report() -> write_html_report() -> 保存报告版本
    # TODO: 增加 _mark_task_failed() 统一错误处理
    try:
        await update_status(task_id=task_id, status=TaskStatus.RUNNING)
        research_agent_res = research_agent.get_research_agent()

        await research_agent_res.generate_research_result(project_id=project_id,
                                                          user_instruction=user_instruction
                                                          , task_id=task_id
                                                          )

        research_result = await research_project_repository.get_research_result(project_id=project_id)

        # TODO: 步骤2 - 调用 write_html_report() 确定性渲染
        # 参照: from app.tools.render_html import write_html_report
        # result = await write_html_report(research_result=research_result, layout_plan=...)
        html_result = write_html(research_result)

        # TODO: 步骤3 - 保存报告版本到 report_versions 集合 + 对象存储
        # await report_repository.save_report_version(project_id, title, html, sources)
        await report_repository.save_html_result(html_result, project_id)

        await update_project_status(project_id=project_id, status=ProjectStatus.REPORT_READY)

        await update_status(task_id=task_id, status=TaskStatus.SUCCEEDED)

    except Exception as e:
        await update_status(task_id=task_id, status=TaskStatus.FAILED)
        print(f"当前任务出现异常 {task_id} 报错是 {str(e)}")
    pass


def start_report_generate(task_id: str, project_id: str, user_instruction):
    # TODO: 改为 Celery 投递 _send_task("research.generate_report", ...)
    task_coroutline = _start_report_generate(task_id=task_id, project_id=project_id, user_instruction=user_instruction)

    asyncio.create_task(task_coroutline)


# 启动生成大纲的任务
def start_outline_generation(research_project, task_id, project_id):
    # TODO: 改为 Celery 投递 _send_task("research.generate_research_brief", ...)
    task_coroutline = _start_outline_generation(research_project=research_project, task_id=task_id,
                                                project_id=project_id)
    asyncio.create_task(task_coroutline)


async def _start_outline_generation(research_project, task_id, project_id):
    # TODO: 重命名为 run_generate_research_brief_task()
    # TODO: 改为由 celery_tasks.py 中的 generate_research_brief_task() 通过 _run_async() 调用
    # TODO: 增加 _mark_task_failed() 统一错误处理
    try:
        await update_status(task_id=task_id, status=TaskStatus.RUNNING)
        research_agent = get_research_agent()
        outline = await research_agent.generate_outline(project_id=project_id, research_project=research_project,
                                                        task_id=task_id)

        await research_project_repository.save_outline(outline=outline, project_id=project_id)

        await research_project_repository.update_project_status(project_id=project_id,
                                                                status=ProjectStatus.OUTLINE_READY)

        await update_status(task_id=task_id, status=TaskStatus.SUCCEEDED)


    except Exception as e:
        await update_status(task_id=task_id, status=TaskStatus.FAILED)
        print(f"当前任务出现异常 {task_id} 报错是 {str(e)}")
