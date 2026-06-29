import asyncio

from app.agents import research_agent
from app.agents.research_agent import get_research_agent
from app.repository import research_project_repository, report_repository
from app.repository.research_project_repository import update_project_status, save_outline
from app.repository.research_task_repository import update_status
from app.schemas import TaskStatus, ProjectStatus
from app.tools.render_html import write_html


async def _start_report_generation(task_id: str, project_id: str):
    try:
        await update_status(task_id=task_id, status=TaskStatus.RUNNING)



    except Exception as e:
        await update_status(task_id=task_id, status=TaskStatus.FAILED)
        print(f"当前任务出现异常 {task_id} 报错是 {str(e)}")


def start_report_generation(task_id: str, project_id: str, user_instruction):
    start_report_generation_res = _start_report_generation(task_id=task_id, project_id=project_id)
    asyncio.create_task(start_report_generation_res)


# 进行研究 保存报告的协程
async def _start_report_generate(task_id: str, project_id: str, user_instruction):
    try:
        await update_status(task_id=task_id, status=TaskStatus.RUNNING)
        research_agent_res = research_agent.get_research_agent()

        await research_agent_res.generate_research_result(project_id=project_id,
                                                          user_instruction=user_instruction
                                                          , task_id=task_id
                                                          )

        research_result = await research_project_repository.get_research_result(project_id=project_id)

        html_result = write_html(research_result)

        await report_repository.save_html_result(html_result, project_id)

        await update_project_status(project_id=project_id, status=ProjectStatus.REPORT_READY)

        await update_status(task_id=task_id, status=TaskStatus.SUCCEEDED)

    except Exception as e:
        await update_status(task_id=task_id, status=TaskStatus.FAILED)
        print(f"当前任务出现异常 {task_id} 报错是 {str(e)}")
    pass


def start_report_generate(task_id: str, project_id: str, user_instruction):
    task_coroutline = _start_report_generate(task_id=task_id, project_id=project_id, user_instruction=user_instruction)

    asyncio.create_task(task_coroutline)


# 启动生成大纲的任务
def start_outline_generation(research_project, task_id, project_id):
    task_coroutline = _start_outline_generation(research_project=research_project, task_id=task_id,
                                                project_id=project_id)
    asyncio.create_task(task_coroutline)


async def _start_outline_generation(research_project, task_id, project_id):
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
