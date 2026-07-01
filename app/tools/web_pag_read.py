import re
from html.parser import HTMLParser
from typing import Any

import httpx
from loguru import logger

from app.config.config import get_settings

# 默认值保留为兜底（当 Settings 未加载时使用）
FALLBACK_TIMEOUT = 15
FALLBACK_MAX_CHARS = 8000
PING_TIMEOUT = 5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def _get_web_read_config():
    """优先从 Settings 读取配置，加载失败时回退到模块级默认值。"""
    try:
        s = get_settings()
        return s.web_read_timeout, s.web_read_max_chars
    except Exception:
        return FALLBACK_TIMEOUT, FALLBACK_MAX_CHARS


async def _check_url_reachable(url: str) -> tuple[bool, str]:
    """用 HEAD 请求快速探测 URL 是否可达。

    输入为标准化 URL；返回 (是否可达, 失败原因)。
    5 秒超时，2xx/3xx 视为可达，405 视为服务器不支持 HEAD 也放行，
    连接失败/超时/4xx/5xx 视为不可达。
    """
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(PING_TIMEOUT),
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
            follow_redirects=False,
        ) as client:
            response = await client.head(url)
            if response.status_code < 400:
                return True, ""
            if response.status_code == 405:
                return True, ""
            return False, f"HTTP {response.status_code}"
    except httpx.TimeoutException:
        return False, f"超时（{PING_TIMEOUT}s）"
    except httpx.HTTPError as exc:
        return False, str(exc)


async def read_web_page(url: str, max_chars: int | None = None) -> dict[str, Any]:
    """读取网页正文和基础元数据。

    输入为 URL 和可选的字符上限；输出为标题、发布时间线索、正文摘要和读取状态。
    读取前先通过 HEAD 探测可达性，不可达则直接返回错误，避免长时间等待。
    """

    timeout_secs, default_max_chars = _get_web_read_config()
    effective_max = max_chars if max_chars is not None else default_max_chars

    normalized_url = url.strip()
    if not normalized_url.startswith(("http://", "https://")):
        return {
            "status": "error",
            "url": url,
            "title": None,
            "published_at": None,
            "content": "",
            "source_type": "public_web",
            "error": "仅支持 http 或 https URL",
        }

    # ---- 预检：HEAD 探测可达性 ----
    reachable, reason = await _check_url_reachable(normalized_url)
    if not reachable:
        logger.info("网页不可达，跳过读取，url={}，原因={}", normalized_url, reason)
        return {
            "status": "skipped",
            "url": normalized_url,
            "title": None,
            "published_at": None,
            "content": "",
            "source_type": "public_web",
            "error": f"URL 不可达: {reason}",
        }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_secs),
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
            follow_redirects=True,
        ) as client:
            response = await client.get(normalized_url)
            response.raise_for_status()
            html = response.text
            final_url = str(response.url)
            content_type = response.headers.get("Content-Type")
    except (httpx.HTTPError, httpx.TimeoutException, UnicodeDecodeError) as exc:
        logger.warning("网页读取失败，url={}, error={}", normalized_url, exc)
        return {
            "status": "error",
            "url": normalized_url,
            "title": None,
            "published_at": None,
            "content": "",
            "source_type": "public_web",
            "error": str(exc),
        }

    parser = _ReadableHtmlParser()
    parser.feed(html)
    content = _normalize_space(" ".join(parser.text_parts))
    limited_content = content[: max(500, min(effective_max, 30000))]
    title = parser.title or _extract_title(html)
    published_at = parser.published_at or _extract_published_at(html)

    logger.info("网页读取完成，url={}, chars={}", final_url, len(limited_content))
    return {
        "status": "ok",
        "url": final_url,
        "title": title,
        "published_at": published_at,
        "content_type": content_type,
        "content": limited_content,
        "truncated": len(content) > len(limited_content),
        "source_type": "public_web",
    }


class _ReadableHtmlParser(HTMLParser):
    """轻量级 HTML 正文提取器，跳过脚本、样式、导航等噪音标签。"""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside"}

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.title: str | None = None
        self.published_at: str | None = None
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            self._handle_meta(attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title:
            cleaned = data.strip()
            if cleaned:
                self.title = cleaned
            return
        text = data.strip()
        if text:
            self.text_parts.append(text)

    def _handle_meta(self, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value for name, value in attrs if value}
        name = (attr_map.get("name") or attr_map.get("property") or "").lower()
        content = attr_map.get("content")
        if not content:
            return
        if name in {"article:published_time", "date", "pubdate", "dc.date", "citation_date"}:
            self.published_at = content
        elif name == "og:title":
            if not self.title:
                self.title = content


def _normalize_space(value: str) -> str:
    """将连续空白字符合并为单个空格，并去除首尾空白。"""
    return re.sub(r"\s+", " ", value).strip()


def _extract_title(html: str) -> str | None:
    """从 HTML 中通过 <title> 标签提取标题。"""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    inner = re.sub(r"<[^>]+>", "", match.group(1))
    return _normalize_space(inner)


def _extract_published_at(html: str) -> str | None:
    """从 HTML 中提取发布时间线索（JSON-LD 日期、meta 标签或 ISO8601 模式）。"""
    patterns = [
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'"dateModified"\s*:\s*"([^"]+)"',
        r'<meta[^>]+property="article:published_time"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="date"[^>]+content="([^"]+)"',
        r"(\d{4}-\d{2}-\d{2}(?:[T ][0-9:.]+(?:Z|[+-]\d{2}:?\d{2})?)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None
