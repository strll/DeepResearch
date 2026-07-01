"""
HTML 报告渲染独立测试（不调 LLM，用本地保存的章节数据）

用法:
    uv run python app/test/test_render_only.py

前置条件:
    - 先跑过 tempfile_1782874222787.py 生成 test_sections_dump.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger


def main():
    dump_file = Path(__file__).resolve().parent / "test_sections_dump.json"

    if not dump_file.exists():
        logger.error("未找到章节数据，请先运行 tempfile_1782874222787.py 生成")
        return 1

    sections = json.loads(dump_file.read_text(encoding="utf-8"))

    # 组装 research_result 结构（render_html 期望的格式）
    result_data = {
        "title": "AI医疗影像诊断技术概述（测试渲染）",
        "sections": sections,
        "sources": [],
        "fact_cards": [],
        "insight_cards": [],
    }

    from app.tools.render_html import write_html_report

    html_result = write_html_report(result_data)
    html = html_result.get("html", "")

    output_path = Path(__file__).resolve().parent / "test_report_output.html"
    output_path.write_text(html, encoding="utf-8")
    logger.success("HTML 报告渲染完成 → {} ({} 字)", output_path, len(html))

    print(f"\n📄 用浏览器打开: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
