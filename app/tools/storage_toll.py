from app.repository.report_storage import get_report_object_storage


async def save_report_html_to_file(html: str, project_id: str = "", report_id: str = "", version: int = 1) -> str:
    """兼容旧接口，委托到 report_storage 实现。

    新代码请直接使用:
        from app.repository.report_storage import get_report_object_storage
        storage = get_report_object_storage()
        stored = await storage.save_html(project_id, report_id, version, html)
        return stored.uri
    """
    storage = get_report_object_storage()
    stored = await storage.save_html(
        project_id=project_id or "_",
        report_id=report_id or "_",
        version=version,
        html=html,
    )
    return stored.uri
