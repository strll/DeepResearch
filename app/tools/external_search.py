

async def external_search(    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    time_range: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,)->dict:
    """执行公开互联网搜索。

    输入为搜索问题和可选过滤条件；输出为归一化搜索结果。当前实现优先调用 Tavily
    Search API；未配置 API Key 时返回可解释的跳过结果，避免智能体编造来源。
    """

    pass