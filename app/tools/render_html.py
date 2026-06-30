import markdown
from datetime import datetime, timezone


def write_html_report(research_result: dict) -> dict:
    """
    入口函数：把研究结果渲染为完整 HTML 报告。
    输入: {"title": str, "sections": [...], "sources": [...], "fact_cards": [...], "insight_cards": [...]}
    输出: {"title": str, "html": str, "sources": list, "fact_cards": list, "insight_cards": list}
    """
    title = research_result.get("title", "研究报告")
    sections = research_result.get("sections", [])
    sources = research_result.get("sources", [])
    fact_cards = research_result.get("fact_cards", [])
    insight_cards = research_result.get("insight_cards", [])

    # 逐个渲染章节
    sections_html = _render_sections(sections, sources)

    # 拼装完整页面
    html = _assemble_page(title, sections_html, sources, fact_cards, insight_cards)

    return {
        "title": title,
        "html": html,
        "sources": sources,
        "fact_cards": fact_cards,
        "insight_cards": insight_cards,
    }


def _render_sections(sections: list[dict], sources: list[dict]) -> str:
    """渲染所有章节正文（Markdown → HTML），处理引用标注。"""
    md = markdown.Markdown(extensions=['tables', 'fenced_code'])
    parts = []

    for sec in sections:
        sec_title = sec.get("title", "")
        sec_id = str(sec.get("section_id", ""))
        body = sec.get("body", "")  # ← 这就是 Markdown 正文

        # 第一步：把 [source:xxx] 替换为角标
        body = _replace_citations(body, sources)

        # 第二步：Markdown → HTML
        md.reset()  # 重置解析器状态，复用同一个实例
        body_html = md.convert(body)

        parts.append(f'<section id="section-{sec_id}"><h2>{sec_title}</h2>{body_html}</section>')

    return "\n".join(parts)


def _replace_citations(body: str, sources: list[dict]) -> str:
    """把正文中的 [source:src_01] 替换为可点击上标角标。"""
    import re

    # 建立 source_id → 编号 的映射
    index = {}
    for i, src in enumerate(sources, 1):
        sid = src.get("source_id", "")
        if sid:
            index[sid] = i

    def _replace(match):
        sid = match.group(1)
        num = index.get(sid)
        if num:
            return f'<sup><a href="#ref-{num}">[{num}]</a></sup>'
        return match.group(0)

    return re.sub(r'\[source:(\w+)\]', _replace, body)


def _assemble_page(title, sections_html, sources, fact_cards, insight_cards):
    """拼装完整的 HTML 页面，包含 CSS 样式、目录、来源列表。"""
    import html as _html
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{_html.escape(title)}</title>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 900px; margin: 0 auto; padding: 40px 24px; line-height: 1.8; }}
    h1 {{ border-bottom: 2px solid #4f46e5; padding-bottom: 12px; }}
    h2 {{ color: #4f46e5; margin-top: 40px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 10px 14px; }}
    th {{ background: #f8fafc; }}
    pre {{ background: #f8fafc; padding: 16px; border-radius: 8px; overflow-x: auto; }}
    code {{ background: #f8fafc; padding: 2px 6px; border-radius: 4px; }}
    blockquote {{ border-left: 4px solid #4f46e5; padding: 8px 16px; background: #f8fafc; }}
    sup a {{ text-decoration: none; color: #4f46e5; font-weight: 600; }}
    .sources-list {{ font-size: 14px; }}
    .sources-list li {{ margin-bottom: 8px; }}
</style>
</head>
<body>
<h1>{_html.escape(title)}</h1>
<p style="color:#94a3b8">{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</p>
{sections_html}
<hr>
<h2>参考来源</h2>
{_render_sources_list(sources)}
{_render_fact_cards(fact_cards)}
{_render_insight_cards(insight_cards)}
</body>
</html>"""


def _render_sources_list(sources):
    """渲染来源列表。"""
    import html as _html
    items = []
    for i, src in enumerate(sources, 1):
        title = _html.escape(src.get("title", ""))
        url = src.get("url", "")
        stype = src.get("source_type", "")
        if url:
            items.append(f'<li id="ref-{i}"><a href="{_html.escape(url)}" target="_blank">{title}</a> <span style="color:#94a3b8">({stype})</span></li>')
        else:
            items.append(f'<li id="ref-{i}">{title} <span style="color:#94a3b8">({stype})</span></li>')
    return '<ol class="sources-list">' + "".join(items) + '</ol>'


def _render_fact_cards(fact_cards):
    """渲染事实卡片附录。"""
    if not fact_cards:
        return ""
    import html as _html
    items = []
    for fc in fact_cards:
        fid = _html.escape(str(fc.get("fact_id", "")))
        stmt = _html.escape(str(fc.get("statement", "")))
        items.append(f'<li><strong>[{fid}]</strong> {stmt}</li>')
    return '<h2>关键事实</h2><ul>' + "".join(items) + '</ul>'


def _render_insight_cards(insight_cards):
    """渲染洞察卡片附录。"""
    if not insight_cards:
        return ""
    import html as _html
    items = []
    for ic in insight_cards:
        t = _html.escape(str(ic.get("title", "")))
        c = _html.escape(str(ic.get("content", "")))
        items.append(f'<li><strong>{t}</strong>: {c}</li>')
    return '<h2>分析洞察</h2><ul>' + "".join(items) + '</ul>'


# 兼容旧函数名，让现有的 research_tasks.py 调用不报错
def write_html(research_result):
    return write_html_report(research_result)
