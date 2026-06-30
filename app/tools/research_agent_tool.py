from app.config.config import get_settings
from app.repository import research_project_repository


def _validate_section(section: dict) -> list:
    errors: list = []

    _section = section.get("section", None)
    project_id = section["project_id"]

    if not _section or not project_id:
        errors.append("section参数中必须要有section键和project_id")
        return errors
    section_id = section["section_id"]
    expected_section_ids = research_project_repository.get_expected_section_ids(project_id=project_id)

    if not section_id or not expected_section_ids or not section_id in expected_section_ids:
        errors.append("section_id不在expected_section_ids中 需要重新生成大纲")
    title = section.get("title", None)
    if not title:
        errors.append("section参数中必须要有title键")

    summary = section.get("summary", None)
    if not summary:
        errors.append("section参数中必须要有summary键")

    body = section.get("body", None)

    if not body or len(body) < 200:
        errors.append("section参数中必须要有body键 或body总字数小于200 需要重新生成")

    evidence_chain: list | None = section.get("evidence_chain")

    sources: list | None = section.get("source")

    # BUG: 应该是 if not evidence_chain or not sources: (缺少两个 not)
    if not evidence_chain or not sources:
        errors.append("section参数中必须要有evidence_chain键和source键")

    source_ids = [source.get("source_id") for source in sources]

    for evidence in evidence_chain:
        source_id = evidence.get("source_ids")
        if not source_id or not source_id in source_ids:
            errors.append("evidence_chain中的source_id不在source_ids中")

    # TODO: 补充校验:
    #   - 每个 source 必须含 source_id 和 url
    #   - body 不能为空字符串
    #   - section_id 不能为空字符串

    return errors


async def save_research_sections(project_id: str, section: dict) -> dict:
    """
    模型调用 并且把section保存到mongodb里面  返回保存是否成功 失败要报错
    :param project_id:
    :param section:
    :return:
    """
    # TODO: 先调 _validate_section() 校验
    errors: list = _validate_section(section)

    if errors:
        return {"status": "error",
                "errors": errors
                }

    await research_project_repository.upsert_section(section)

    # TODO: 返回实际值而非硬编码
    return {
        "status": "ok",
        "project_id": project_id,  # 实际值
        "section_id": section.get("section", {}).get("section_id"),  # 实际值
        "sources_saved": section,  # 实际值
        "message": "research section saved"
    }
