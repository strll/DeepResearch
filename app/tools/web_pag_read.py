import re
from html.parser import HTMLParser
from typing import Any

import httpx
from loguru import logger

from app.config.config import get_settings

# 单次研究任务中的网页读取计数器
_page_read_count = 0


def reset_page_read_counter():
    """重置网页读取计数器（每次新研究任务开始时调用）。"""
    global _page_read_count
    _page_read_count = 0


async def read_web_page(url: str, max_chars: int | None = None) -> dict[str, Any]:
    """读取网页正文和基础元数据。

    输入为 URL 和可选的字符上限；输出为标题、发布时间线索、正文摘要和读取状态。
    读取前先通过 HEAD 探测可达性，不可达则直接返回错误，避免长时间等待。
    """

    global _page_read_count
    limit = get_settings().web_read_max_pages_per_section
    if _page_read_count >= limit:
        return {
            "status": "skipped",
            "url": url,
            "title": None,
            "published_at": None,
            "content": "",
            "source_type": "public_web",
            "error": f"已达单次研究网页读取上限（{limit} 页），跳过 {url}",
        }
    _page_read_count += 1
