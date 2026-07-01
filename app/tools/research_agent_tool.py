from app.config.config import get_settings
from app.repository import research_project_repository


async def _validate_section(section: dict) -> list:
    errors: list = []

    _section = section.get("section", None)
    project_id = section["project_id"]

    if not _section or not project_id:
        errors.append("section参数中必须要有section键和project_id")
        return errors
    section_id = _section.get("section_id", None)
    expected_section_ids = await research_project_repository.get_expected_section_ids(project_id=project_id)

    if not section_id or not expected_section_ids or not section_id in expected_section_ids:
        errors.append("section_id不在expected_section_ids中 需要重新生成大纲")
    title = _section.get("title", None)
    if not title:
        errors.append("section参数中必须要有title键")

    summary = _section.get("summary", None)
    if not summary:
        errors.append("section参数中必须要有summary键")

    body = _section.get("body", None)

    if not body or len(body) < 200:
        errors.append("section参数中必须要有body键 或body总字数小于200 需要重新生成")

    evidence_chain: list | None = _section.get("evidence_chain")
    sources: list | None = _section.get("sources")

    if evidence_chain is None or sources is None:
        errors.append("section参数中必须要有evidence_chain键和sources键")
        return errors

    if not isinstance(sources, list):
        sources = []

    source_ids = [s.get("source_id") for s in sources if isinstance(s, dict)]

    for evidence in evidence_chain:
        if not isinstance(evidence, dict):
            continue
        ev_source_ids = evidence.get("source_ids", [])
        if not isinstance(ev_source_ids, list):
            ev_source_ids = [ev_source_ids] if ev_source_ids else []
        for sid in ev_source_ids:
            if sid not in source_ids:
                errors.append(f"evidence_chain中的source_id {sid} 不在source_ids中")

    for source in sources:
        if not source.get("source_id"):
            errors.append("source参数中必须要有source_id键")
        if not source.get("url"):
            errors.append("source参数中必须要有url键")

    # 补充校验: body 不能为空字符串
    if isinstance(body, str) and body.strip() == "":
        errors.append("body不能为空字符串")

    # 补充校验: section_id 不能为空字符串
    if isinstance(section_id, str) and section_id.strip() == "":
        errors.append("section_id不能为空字符串")

    return errors


async def save_research_sections(project_id: str, section: dict) -> dict:
    """
    模型调用 并且把section保存到mongodb里面  返回保存是否成功 失败要报错
    :param project_id:
    :param section:
    :return:
    """
    wrapped = {
        "project_id": project_id,
        "section": section,
    }

    errors: list = await _validate_section(wrapped)

    if errors:
        return {"status": "error",
                "errors": errors
                }

    await research_project_repository.upsert_section(wrapped)

    return {
        "status": "ok",
        "project_id": project_id,
        "section_id": section.get("section_id"),
        "sources_saved": len(section.get("sources", [])),
        "message": "research section saved"
    }
