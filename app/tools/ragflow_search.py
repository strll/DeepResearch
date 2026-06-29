from typing import Any


async def ragflow_search(
    query: str,
    dataset_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    page: int = 1,
    page_size: int = 10,
    similarity_threshold: float = 0.2,
    vector_similarity_weight: float = 0.3,
    top_k: int = 1024,
    keyword: bool = False,
) -> dict[str, Any]:
    """检索 RAGFlow 内部知识库。

    输入为问题、数据集或文档范围；输出为归一化 chunk 列表。dataset_ids 和
    document_ids 至少需要提供一项，否则返回跳过结果。
    """