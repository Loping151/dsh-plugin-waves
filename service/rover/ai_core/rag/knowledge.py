"""知识库同步与检索。当前未接入向量库，同步为空操作、检索恒为空结果。"""

from typing import Any, List, Optional

from rover.logger import logger


async def sync_knowledge() -> None:
    """把已注册知识点推送到向量库。"""
    logger.debug("[AI 知识库] 未接入向量库，跳过同步")


async def query_knowledge(
    query: str,
    limit: int = 5,
    plugin_filter: Optional[List[str]] = None,
    category_filter: Optional[str] = None,
    exclude_plugins: Optional[List[str]] = None,
    exclude_sources: Optional[List[str]] = None,
) -> List[Any]:
    """检索知识库，返回带 payload / score 的结果列表。"""
    logger.debug(f"[AI 知识库] 未接入向量库，检索返回空: {query!r}")
    return []
