"""卡片公共件: 模板环境、字体、配色、以及面板/声骸/排行都要用的片段。

面板与声骸列表共用声骸格与词条行, 各排行之间共用榜行骨架与名次配色,
统一放这里, 避免各模板各写一套导致样式漂移。
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

# 名次配色, 与 PIL 版前三名一致
RANK_COLORS = {1: "#e5c07b", 2: "#c8ccd4", 3: "#c98a5e"}

# 词条评分档位配色
SCORE_COLORS = (
    (1.0, "#ff6b6b"),
    (0.85, "#f0a020"),
    (0.7, "#c678dd"),
    (0.5, "#61afef"),
    (0.0, "#98a2b3"),
)

_env = None


def template(name: str):
    global _env
    if _env is None:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        _env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        _env.globals.update(rank_color=rank_color, score_color=score_color)
    return _env.get_template(name)


def font_css_url(render_utils) -> str:
    """字体由本服务自己挂载, 不依赖外部部署。"""
    css = render_utils._FONTS_DIR / render_utils._FONT_CSS_NAME
    if css.exists():
        return f"{render_utils._get_local_base_url()}/waves/fonts/{render_utils._FONT_CSS_NAME}"
    return render_utils._get_font_css_url()


def prefix() -> str:
    """命令前缀, 取配置里的第一个。"""
    from rover.sv import all_prefixes

    items = all_prefixes()
    return items[0] if items else ""


def css_color(value: Any) -> str:
    """插件里的颜色可能是名字, 也可能是 RGB 元组。"""
    if isinstance(value, (tuple, list)):
        parts = list(value)[:3]
        return "rgb({}, {}, {})".format(*parts)
    return str(value)


def rank_color(rank: int) -> str:
    return RANK_COLORS.get(int(rank or 0), "#8b93a7")


def score_color(ratio: float) -> str:
    for edge, color in SCORE_COLORS:
        if float(ratio or 0) >= edge:
            return color
    return SCORE_COLORS[-1][1]


def avatar_override(context: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    """配置了自定义头像时覆盖模板里的头像字段。"""
    try:
        from rover.avatar import get_avatar_url
    except ImportError:
        return context
    url = get_avatar_url()
    if not url:
        return context
    for key in keys or ("avatar_url", "avatar"):
        if key in context:
            context[key] = url
    return context


def head_context(
    account_info: Any,
    uid: str = "",
    user_pref: str = "",
    hide_uid: Optional[Callable[..., str]] = None,
) -> Dict[str, Any]:
    """标准头部: 昵称/UID(按偏好打码)/等级/世界等级。hide_uid 由调用方从插件传入。"""
    value = uid or getattr(account_info, "id", "")
    return {
        "user_name": getattr(account_info, "name", ""),
        "user_id": hide_uid(value, user_pref=user_pref) if hide_uid else value,
        "level": getattr(account_info, "level", ""),
        "world_level": getattr(account_info, "worldLevel", ""),
        "show_stats": getattr(account_info, "is_full", True),
    }


def render(name: str, context: Dict[str, Any], template_name: Optional[str] = None):
    """渲模板并挂上点击/自适应桥。"""
    from rover.html_actions import annotate_html
    from rover.media import HtmlBytes

    html = template(name).render(**context)
    marked = template_name or name
    return HtmlBytes(annotate_html(html, marked, context), marked)


def phantom_rows(phantoms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """声骸词条行归一, 面板与声骸列表共用。"""
    rows = []
    for item in phantoms or []:
        rows.append(
            {
                "name": item.get("name", ""),
                "value": item.get("value", ""),
                "color": css_color(item.get("color", "#98a2b3")),
                "ratio": item.get("ratio", 0),
            }
        )
    return rows
