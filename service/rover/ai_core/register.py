"""AI 注册表。装饰器原样返回被装饰对象，注册内容仅留在内存。"""

from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar, Union, overload

from rover.ai_core.models import ImageEntity, KnowledgeBase, KnowledgePoint
from rover.logger import logger

F = TypeVar("F", bound=Callable[..., Any])
CheckFunc = Callable[..., Any]

# 工具注册表: {分类名: {工具名: 函数}}
_TOOL_REGISTRY: Dict[str, Dict[str, Callable]] = {}
# 插件注册的知识点与图片实体
_ENTITIES: List[Union[KnowledgePoint, KnowledgeBase, ImageEntity]] = []
_IMAGE_ENTITIES: List[ImageEntity] = []
# 别名表: {scope: {别名: [正式名, ...]}}
_ALIASES: Dict[str, Dict[str, List[str]]] = {}


@overload
def ai_tools(func: F, /) -> F: ...


@overload
def ai_tools(
    func: None = None,
    /,
    *,
    category: str = "default",
    check_func: Optional[CheckFunc] = None,
    **check_kwargs: Any,
) -> Callable[[F], F]: ...


def ai_tools(
    func: Optional[Callable] = None,
    /,
    *,
    category: str = "default",
    check_func: Optional[CheckFunc] = None,
    context_tags: Optional[List[str]] = None,
    capability_domain: Optional[str] = None,
    covers: Optional[List[str]] = None,
    aliases: Optional[List[str]] = None,
    visible_when: Optional[Callable[..., Union[bool, Awaitable[bool]]]] = None,
    timeout: Optional[float] = 60.0,
    approval: Optional[str] = None,
    **check_kwargs: Any,
):
    """用法: @ai_tools 或 @ai_tools(category="common", context_tags=[...])"""

    def decorator(f: Callable) -> Callable:
        _TOOL_REGISTRY.setdefault(category, {})[f.__name__] = f
        logger.trace(f"[AI 注册] 工具 {f.__name__} -> {category}")
        return f

    if func is not None:
        return decorator(func)
    return decorator


def ai_entity(entity: Union[KnowledgePoint, KnowledgeBase]) -> None:
    """注册知识点。"""
    entity["source"] = "plugin"
    _ENTITIES.append(entity)
    logger.trace(f"[AI 注册] 知识点 {entity.get('title')}")


def ai_image(entity: ImageEntity) -> None:
    """注册图片实体。"""
    entity["source"] = "plugin"
    _ENTITIES.append(entity)
    _IMAGE_ENTITIES.append(entity)
    logger.trace(f"[AI 注册] 图片 {entity.get('id')}")


def ai_alias(name: str, alias: Union[str, List[str]], scope: str = "global") -> None:
    """为正式名注册别名，scope 用于隔离不同业务域的同名别名。"""
    if isinstance(alias, str):
        alias = [alias]

    scope_map = _ALIASES.setdefault(scope, {})
    for a in alias:
        formals = scope_map.setdefault(a, [])
        if name not in formals:
            formals.append(name)
