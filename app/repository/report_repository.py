import uuid

from app.config.config import get_settings
from app.repository.mongodb import get_mongodb_database
from app.repository.report_storage import get_report_object_storage
from app.schemas import LatestReportResponse, ReportSource, utc_now

COLLECTION_NAME = "report_versions"


def _get_collection():
    return get_mongodb_database()[COLLECTION_NAME]


async def save_report_version(
    project_id: str,
    title: str,
    html: str,
    sources: list[dict],
) -> LatestReportResponse:
    """保存研究报告版本。

    自动递增版本号，将 HTML 内容写入对象存储，
    MongoDB 只保存元数据（含 html_uri）。
    """
    storage = get_report_object_storage()

    # 计算下一个版本号
    latest = await _get_collection().find_one(
        {"project_id": project_id},
        sort=[("version", -1)],
        projection={"version": 1},
    )
    next_version = latest["version"] + 1 if latest else 1

    report_id = str(uuid.uuid4())
    created_at = utc_now()

    # HTML 写入对象存储
    stored = await storage.save_html(
        project_id=project_id,
        report_id=report_id,
        version=next_version,
        html=html,
    )

    # MongoDB 只存元数据
    document = {
        "_id": report_id,
        "project_id": project_id,
        "report_id": report_id,
        "version": next_version,
        "title": title,
        "html_uri": stored.uri,
        "html_path": stored.path,
        "html_size": stored.size,
        "sources": sources,
        "created_at": created_at,
    }
    await _get_collection().insert_one(document)

    return LatestReportResponse(
        project_id=project_id,
        report_id=report_id,
        version=next_version,
        title=title,
        html=html,
        sources=[ReportSource(**s) if isinstance(s, dict) else s for s in sources],
        created_at=created_at,
    )


async def get_latest_report(project_id: str) -> LatestReportResponse | None:
    """读取项目的最新报告版本。"""
    doc = await _get_collection().find_one(
        {"project_id": project_id},
        sort=[("version", -1)],
    )
    if doc is None:
        return None

    # 从对象存储读取 HTML
    html = await _load_report_html(doc)
    sources_data = doc.get("sources", [])

    return LatestReportResponse(
        project_id=str(doc["project_id"]),
        report_id=str(doc["report_id"]),
        version=int(doc["version"]),
        title=str(doc.get("title", "")),
        html=html,
        sources=[ReportSource(**s) if isinstance(s, dict) else s for s in sources_data],
        created_at=doc["created_at"],
    )


async def _load_report_html(document: dict) -> str:
    """从对象存储或文档内嵌字段读取报告 HTML。"""
    html_uri = document.get("html_uri")
    if isinstance(html_uri, str) and html_uri.strip():
        storage = get_report_object_storage()
        return await storage.read_html(uri=html_uri)
    # 兼容旧格式：HTML 直接内嵌在文档中
    return str(document.get("html") or "")


# ---- 兼容旧接口，避免 research_tasks.py 报错 ----

async def save_html_result(html_result, project_id):
    """兼容旧接口，内部转为 save_report_version 调用。"""
    return await save_report_version(
        project_id=project_id,
        title=html_result.get("title", ""),
        html=html_result.get("html", ""),
        sources=html_result.get("sources", []),
    )
