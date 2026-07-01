"""
报告生成核心方法独立测试（不依赖 FastAPI API）

用法:
    uv run python app/test/test_research_agent.py

前置条件:
    - MongoDB + Redis 已启动
    - .env 中 DEEPSEEK_API_KEY 已配置
    - 可选: Celery Worker 不需要（脚本直接调 Agent）
"""

import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger

from app.agents.research_agent import get_research_agent
from app.repository import research_project_repository
from app.repository.mongodb import get_mongodb_database

# ---------------------------------------------------------------------------
# 测试参数
# ---------------------------------------------------------------------------
TEST_OUTLINE = [
    {
        "node_id": "1",
        "title": "AI医疗影像诊断技术概述",
        "question": "AI医疗影像诊断的核心技术原理是什么",
        "description": "简要介绍深度学习在医疗影像中的技术基础和应用场景",
        "children": [],
    },
]


def utc_now():
    return datetime.now(timezone.utc)


async def setup_test_project() -> str:
    """在 MongoDB 写入带已确认大纲的测试项目。"""
    project_id = f"test-agent-{uuid.uuid4().hex[:8]}"
    now = utc_now()

    document = {
        "_id": project_id,
        "project_id": project_id,
        "topic": "AI医疗影像诊断技术",
        "request": {},
        "status": "outline_confirmed",
        "outline": TEST_OUTLINE,
        "confirmed_outline": TEST_OUTLINE,
        "sections": [],
        "sources": [],
        "research_result": None,
        "created_at": now,
        "updated_at": now,
    }

    await get_mongodb_database()["research_projects"].insert_one(document)
    logger.info("测试项目已创建: {}", project_id)
    return project_id


async def cleanup(project_id: str):
    await get_mongodb_database()["research_projects"].delete_one({"project_id": project_id})
    await get_mongodb_database()["research_tasks"].delete_many({"project_id": project_id})


async def main():
    project_id = None
    cache_path = Path(__file__).resolve().parent / "test_sections_dump.json"

    # 如果有缓存，直接用
    if cache_path.exists():
        logger.info("发现缓存文件，跳过 LLM 调用 → {}", cache_path)

        from app.tools.render_html import write_html_report

        sections = json.loads(cache_path.read_text(encoding="utf-8"))
        for s in sections:
            if isinstance(s, dict):
                print(f"  [{s.get('section_id')}] {s.get('title')} — {len(s.get('body',''))} 字")

        result_data = {
            "title": sections[0].get("title", "AI医疗影像诊断技术概述") if sections else "测试报告",
            "sections": sections,
            "sources": sections[0].get("sources", []) if sections else [],
            "fact_cards": [],
            "insight_cards": [],
        }
        html_result = write_html_report(result_data)
        html = html_result.get("html", "")

        output_path = Path(__file__).resolve().parent / "test_report_output.html"
        output_path.write_text(html, encoding="utf-8")
        logger.success("HTML 报告已生成 → {} ({} 字)", output_path, len(html))
        print(f"\n📄 用浏览器打开: {output_path}")
        return 0

    # 无缓存：正常走 LLM 流程
    try:
        # 1. 准备数据
        project_id = await setup_test_project()
        task_id = "test-task-001"

        # 2. 初始化 Agent
        logger.info("初始化研究 Agent...")
        agent = get_research_agent()

        # 3. 直接调用核心方法
        logger.info("开始执行 generate_research_result...")
        t0 = time.perf_counter()

        await agent.generate_research_result(
            project_id=project_id,
            user_instruction="请重点关注临床应用场景",
            task_id=task_id,
        )

        elapsed = time.perf_counter() - t0
        logger.success("方法执行完成！耗时={:.1f}s", elapsed)

        # 4. 验证结果
        sections = await research_project_repository.get_saved_sections(project_id)
        logger.info("已保存 {} 个章节", len(sections))

        # 从 MongoDB 读取完整章节数据
        project = await research_project_repository.get_project(project_id)
        full_sections = (project or {}).get("sections", [])

        # 保存到本地文件
        if full_sections:
            dump_path = Path(__file__).resolve().parent / "test_sections_dump.json"
            dump_path.write_text(
                json.dumps(full_sections, ensure_ascii=False, default=str, indent=2),
                encoding="utf-8"
            )
            logger.info("章节数据已导出到 {} ({} 个章节)", dump_path, len(full_sections))

            for s in full_sections:
                if isinstance(s, dict):
                    print(f"  [{s.get('section_id')}] {s.get('title')} — {len(s.get('body',''))} 字")

        print(f"\n📄 HTML 报告: {Path(__file__).resolve().parent / 'test_report_output.html'}")

        if len(full_sections) == 0:
            logger.error("❌ 失败：没有章节被保存")
            return 1
        else:
            logger.success("✅ 成功：{} 个章节已生成 (下次运行将使用缓存)", len(full_sections))

        # 渲染 HTML
        logger.info("渲染 HTML 报告...")
        from app.tools.render_html import write_html_report

        result_data = {
            "title": full_sections[0].get("title", "AI医疗影像诊断技术概述"),
            "sections": full_sections,
            "sources": full_sections[0].get("sources", []),
            "fact_cards": [],
            "insight_cards": [],
        }
        html_result = write_html_report(result_data)
        html = html_result.get("html", "")

        output_path = Path(__file__).resolve().parent / "test_report_output.html"
        output_path.write_text(html, encoding="utf-8")
        logger.info("HTML 报告已保存到 {} ({} 字)", output_path, len(html))

        return 0

    except Exception as exc:
        logger.exception("异常: {}", exc)
        return 1

    finally:
        if project_id:
            await cleanup(project_id)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
