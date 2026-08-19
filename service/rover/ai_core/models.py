"""AI 数据类型。知识点/图片实体是 TypedDict（消费方按 dict 取值）。"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, NotRequired, Optional, Set, TypedDict

if TYPE_CHECKING:
    from rover.bot import Bot
    from rover.models import Event


@dataclass
class ToolContext:
    """工具执行上下文，作为 pydantic_ai RunContext 的 deps 传入。"""

    bot: Optional["Bot"] = None
    ev: Optional["Event"] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    parent_session_id: Optional[str] = None
    dynamic_tool_names: Set[str] = field(default_factory=set)
    blocked_tool_names: Set[str] = field(default_factory=set)
    allow_user_outbound: bool = True


class KnowledgeBase(TypedDict):
    """知识点基类"""

    id: str
    plugin: str
    title: str
    content: str
    tags: List[str]
    source: NotRequired[str]


class KnowledgePoint(KnowledgeBase):
    """知识点"""

    _hash: NotRequired[str]


class ImageEntity(TypedDict):
    """图片实体，供图片检索使用"""

    id: str
    plugin: str
    path: str
    tags: List[str]
    content: str
    source: str
    _hash: NotRequired[str]
