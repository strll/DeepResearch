

REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_MAX_CHARS = 12000
USER_AGENT = "DeepResearchBot/0.1 (+https://example.local/research)"


async def read_web_page(url: str, max_chars: int = DEFAULT_MAX_CHARS) -> dict[str, Any]:
    """读取网页正文和基础元数据。

    输入为 URL；输出为标题、发布时间线索、正文摘要和读取状态。该工具只做轻量解析，
    不对网页内容做事实判断。
    """
