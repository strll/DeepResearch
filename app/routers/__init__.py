"""
API 路由模块

该模块定义了研究工作台的全部 REST 接口，包括项目管理、大纲操作、
后台任务查询和报告获取。所有接口均通过 repository 层与 MongoDB 交互。
"""
from uuid import uuid4

from fastapi import FastAPI, HTTPException, APIRouter
from starlette import status

from app.background.research_tasks import (
    start_generate_research_brief_task,
    start_generate_report_task,
    start_outline_generation,
    start_report_generation,
    start_revise_outline_task,
)

from app.repository import research_task_repository, research_project_repository, report_repository
from app.schemas import (
    LatestReportResponse,
    NextStep,
    OutlineAction,
    OutlineConfirmResponse,
    OutlineResponse,
    OutlineRevisionResponse,
    OutlineUpdateRequest,
    ProjectStatus,
    ReportSource,
    ReportTaskCreate,
    ReportTaskCreateResponse,
    ResearchProjectCreate,
    ResearchProjectCreateResponse,
    TaskStatus,
    TaskStatusResponse,
    TaskType,
    utc_now,
)

app = APIRouter(tags=["研究项目"])


async def _create_task(
        project_id: str,
        task_type: TaskType,
        message: str,
) -> str:
    """创建后台任务记录并返回任务编号。

    输入为项目编号、任务类型和状态说明；输出为新生成的任务编号。
    该函数只负责任务元数据持久化，不触发后台任务的实际执行。
    """

    now = utc_now()
    task_id = str(uuid4())
    await research_task_repository.create_task(
        task_id=task_id,
        project_id=project_id,
        task_type=task_type,
        status=TaskStatus.QUEUED,
        message=message,
        created_at=now,
        updated_at=now,
    )

    return task_id


# ---------------------------------------------------------------------------
#  1. 服务健康检查
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> dict[str, str]:
    """服务健康检查接口，供负载均衡和监控探针使用。"""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
#  2. 创建研究项目
# ---------------------------------------------------------------------------
@app.post(
    "/research-projects",
    response_model=ResearchProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(request: ResearchProjectCreate):
    """创建新的研究项目。

    输入为用户提交的研究主题、目标受众、地域和时间范围；
    流程分为三步：
    1. 将项目基础信息持久化到 MongoDB；
    2. 创建后台任务记录用于跟踪大纲生成；
    3. 返回项目编号和初始状态，后续由 background 模块接管异步任务调度。
    """

    project_id = str(uuid4())
    created_at = utc_now()

   # 1. 持久化项目记录到 MongoDB
    await research_project_repository.create_project(
        project_id=project_id,
        request=request,
        topic=request.topic,
        status=ProjectStatus.BRIEF_GENERATING,
        created_at=created_at,
    )

    # 2. 创建后台任务记录，用于前端轮询大纲生成进度
    task_id = await _create_task(
        project_id=project_id,
        task_type=TaskType.GENERATE_RESEARCH_BRIEF,
        message="研究任务书和大纲生成任务已创建",
    )

    start_outline_generation(research_project=request, task_id=task_id,project_id=project_id)



    # 3. 组装响应，告知前端当前处于 BRIEF_GENERATING 阶段，需等待大纲
    response = ResearchProjectCreateResponse(
        project_id=project_id,
        initial_task_id=task_id,
        initial_task_type=TaskType.GENERATE_RESEARCH_BRIEF,
        topic=request.topic,
        status=ProjectStatus.BRIEF_GENERATING,
        next_step=NextStep.WAIT_FOR_OUTLINE,
        created_at=created_at,
    )

    return response


# ---------------------------------------------------------------------------
#  3. 获取大纲草案
# ---------------------------------------------------------------------------
@app.get(
    "/research-projects/{project_id}/outline",
    response_model=OutlineResponse,
)
async def get_outline(project_id: str):
    """获取指定项目的当前大纲草案。

    输入为项目编号；输出为大纲节点列表及项目状态。
    如果大纲尚未生成则返回空列表，前端可根据状态字段判断是否需要轮询等待。
    """

    # 从 MongoDB 查询项目文档
    project = await research_project_repository.get_project(project_id)

    # 项目不存在时返回 404，防止空指针错误
    if project is None:
        raise HTTPException(status_code=404, detail="当前查询的项目不存在")

    # 兼容 outline 字段不存在或为空的情况，避免 KeyError
    outline = project.get("outline", [])

    return OutlineResponse(
        outline=outline if isinstance(outline, list) else [],
        project_id=project_id,
        status=project["status"],
    )


# ---------------------------------------------------------------------------
#  4. 确认大纲或提交大纲修改意见
# ---------------------------------------------------------------------------
@app.put(
    "/research-projects/{project_id}/outline",
    response_model=OutlineConfirmResponse | OutlineRevisionResponse,
)
async def update_outline(project_id: str, request: OutlineUpdateRequest):
    """确认大纲或提交修改意见。

    输入为项目编号和大纲操作请求；根据 action 类型分为两个分支：
    - CONFIRM：将当前大纲草案保存为已确认大纲，项目状态切换为 OUTLINE_CONFIRMED，
      前端之后可以提交报告生成任务；
    - REVISE：将项目状态切换为 OUTLINE_REVISING，创建大纲修改后台任务，
      前端需要轮询任务状态等待新大纲生成。
    """

    # 校验项目是否存在
    project = await research_project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="当前查询的项目不存在")

    if request.action == OutlineAction.CONFIRM:
        # ---- 确认大纲 ----
        # 将当前大纲草案写入 confirmed_outline 字段作为快照
        outline = project.get("outline", [])
        await research_project_repository.save_confirmed_outline(project_id, outline)
        # 更新项目主流程状态
        await research_project_repository.update_project_status(
            project_id, ProjectStatus.OUTLINE_CONFIRMED,
        )

        return OutlineConfirmResponse(
            project_id=project_id,
            status=ProjectStatus.OUTLINE_CONFIRMED,
            next_step=NextStep.GENERATE_REPORT,
        )
    elif request.action == OutlineAction.REVISE:
        # ---- 修改大纲 ----
        # 更新项目状态为 OUTLINE_REVISING，表示大纲正在被 AI 重新生成
        task_id = await _create_task(
            project_id=project_id,
            task_type=TaskType.REVISE_OUTLINE,
            message="研究大纲修改任务已创建",
        )

        # 投递大纲修改任务到 Celery，由 info_search_agent 根据用户指令修订大纲
        start_revise_outline_task(
            project_id=project_id,
            task_id=task_id,
            revision_instruction=request.revision_instruction or "",
        )

        return OutlineRevisionResponse(
            project_id=project_id,
            revision_task_id=task_id,
            status=ProjectStatus.OUTLINE_REVISING,
            next_step=NextStep.WAIT_FOR_OUTLINE,
        )
    else:
        raise HTTPException(status_code=400, detail="无效的大纲操作")

# ---------------------------------------------------------------------------
#  5. 提交报告生成任务
# ---------------------------------------------------------------------------
@app.post(
    "/research-projects/{project_id}/report-tasks",
    response_model=ReportTaskCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_report_task(project_id: str, request: ReportTaskCreate):
    """提交报告生成后台任务。

    输入为项目编号和可选的用户补充说明；输出为新创建的任务编号。
    该接口有状态校验：只有 OUTLINE_CONFIRMED 或 REPORT_READY 状态的项目
    才允许创建报告生成任务，否则返回 409 冲突错误。
    """

    # 校验项目是否存在及当前状态是否允许生成报告
    project = await research_project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="当前查询的项目不存在")

    if project["status"] not in (ProjectStatus.OUTLINE_CONFIRMED, ProjectStatus.REPORT_READY):
        raise HTTPException(
            status_code=409,
            detail="当前项目状态不允许生成报告，请先确认大纲",
        )

    # 创建 GENERATE_REPORT 类型的后台任务
    task_id = await _create_task(
        project_id=project_id,
        task_type=TaskType.GENERATE_REPORT,
        message=request.user_instruction or "报告生成任务已创建",
    )

    # 更新项目状态，标记研究正在进行中
    await research_project_repository.update_project_status(
        project_id, ProjectStatus.RESEARCH_RUNNING,
    )

    start_report_generation(task_id,project_id,user_instruction=request.user_instruction )

    return ReportTaskCreateResponse(
        task_id=task_id,
        project_id=project_id,
        task_type=TaskType.GENERATE_REPORT,
        status=TaskStatus.QUEUED,
    )


# ---------------------------------------------------------------------------
#  6. 查询后台任务状态
# ---------------------------------------------------------------------------
@app.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
)
async def get_task_status(task_id: str):
    """查询后台任务的当前状态和描述信息。

    输入为任务编号；输出为完整的任务状态结构（含类型、状态、时间戳）。
    前端通过轮询此接口来判断大纲生成、大纲修改、报告生成等异步任务是否完成。
    """

    task = await research_task_repository.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="当前查询的任务不存在")
    return task


# ---------------------------------------------------------------------------
#  7. 获取最新报告
# ---------------------------------------------------------------------------
@app.get(
    "/research-projects/{project_id}/reports/latest",
    response_model=LatestReportResponse,
)
async def get_latest_report(project_id: str):
    """获取项目的最新研究报告。

    优先从 report_versions 集合读取已保存的正式报告版本，
    如不存在则回退到项目文档中的 research_result 字段做兜底展示。
    """
    # 优先使用正式报告版本
    report = await report_repository.get_latest_report(project_id)
    if report is not None:
        return report

    # ---- 兜底方案：从项目文档 research_result 提取 ----
    project = await research_project_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="当前查询的项目不存在")

    research_result = project.get("research_result")
    if research_result is None:
        raise HTTPException(status_code=404, detail="当前项目尚未生成报告")

    # ---- 提取来源列表 ----
    # sources 在 MongoDB 中存储为 dict 列表，需转换为 ReportSource 模型列表
    sources_data = project.get("sources", [])
    sources: list[ReportSource] = []
    for s in sources_data:
        if isinstance(s, ReportSource):
            sources.append(s)
        elif isinstance(s, dict):
            sources.append(ReportSource(**s))

    # ---- 提取报告标题和 HTML 内容 ----
    title = project.get("topic", "")
    updated_at = project.get("updated_at", utc_now())
    html = ""

    if isinstance(research_result, dict):
        # 优先使用 research_result 中的标题
        title = research_result.get("title") or title
        # 按优先级获取 HTML：已渲染 HTML > 原始内容 > sections 拼装
        html = research_result.get("html") or research_result.get("content") or ""
        if not html:
            # 兜底方案：将各章节拼接为简易 HTML，保证前端有内容可展示
            sections = research_result.get("sections", [])
            html_parts: list[str] = []
            for sec in sections:
                if isinstance(sec, dict):
                    sec_title = sec.get("title", "")
                    sec_content = sec.get("content", "")
                    html_parts.append(f"<h2>{sec_title}</h2><div>{sec_content}</div>")
            html = "\n".join(html_parts)

    return LatestReportResponse(
        project_id=project_id,
        report_id=f"{project_id}-v1",
        version=1,
        title=str(title),
        html=str(html) if html else "",
        sources=sources,
        created_at=updated_at,
    )
