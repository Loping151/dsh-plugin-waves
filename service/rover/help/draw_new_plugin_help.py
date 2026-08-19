"""帮助渲染: 产出可点击的 HTML 卡片, 版式照画布版 1:1 摆放。

签名与旧图片实现一致, 插件零改动。条目对照当前已注册的触发器过滤,
被裁掉的命令不会出现在帮助里; 鼠标停在条目上给出该命令的说明。
"""

import base64
import re
import zlib
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rover.media import HtmlBytes

# 画布版的几何常量: 列宽/行高/分类条与条目在各自底图里的锚点
COLUMN = 5
CELL_W = 490
CELL_H = 175
ITEM_X0 = 45
SOFT = 10
BANNER_W = 1545

_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #14161c; }
body { font-family: 'Source Han Sans CN', 'Noto Sans CJK JP', sans-serif; color: #fff; }
.container { position: relative; overflow: hidden; }
.bg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.layer { position: absolute; left: 0; top: 0; }
.layer img { display: block; }
.t { position: absolute; white-space: nowrap; line-height: 1; transform: translateY(-50%); }
.badge { position: absolute; display: flex; align-items: center; border-radius: 12px;
    transform: translateY(-50%); overflow: hidden; }
.badge span { padding: 0 14px; line-height: 1; }
/* 点击桥接会给 [data-ww-cmd] 加 position:relative, 这里用更高特异性压回去 */
.container .item { position: absolute; width: 490px; height: 175px; cursor: pointer; }
.item > img { position: absolute; left: 0; top: 0; width: 490px; height: 175px; }
.item .icon { left: 6px; top: 12px; width: 150px; height: 150px; }
.item .nm { position: absolute; left: 156px; top: 67px; font-size: 38px; color: #fff;
    transform: translateY(-50%); white-space: nowrap; }
.item .eg { position: absolute; left: 156px; top: 116px; font-size: 26px; color: #cecece;
    transform: translateY(-50%); white-space: nowrap; }
.item:hover .hl { outline: 3px solid rgba(255, 214, 102, .95); outline-offset: -3px; border-radius: 12px; }
.tip { position: absolute; width: 900px; padding: 18px 22px; border-radius: 14px;
    background: rgba(12, 14, 20, .96); border: 2px solid rgba(255, 255, 255, .16);
    box-shadow: 0 12px 34px rgba(0, 0, 0, .55); font-size: 30px; line-height: 1.5;
    color: #dfe3ec; white-space: normal; opacity: 0; pointer-events: none;
    transition: opacity .12s; z-index: 9; }
.tip .k { display: block; margin-bottom: 8px; font-size: 26px; color: #ffd666;
    font-family: ui-monospace, monospace; }
.item:hover .tip { opacity: 1; }
.tip.down { top: 160px; }
.tip.up { bottom: 160px; }
.tip.left { left: 20px; }
.tip.right { right: 20px; }
.hl { position: absolute; inset: 0; }
"""


def _uri(image: Any, fmt: str = "PNG") -> str:
    if image is None:
        return ""
    try:
        buffer = BytesIO()
        image.convert("RGBA" if fmt == "PNG" else "RGB").save(buffer, format=fmt)
        mime = "png" if fmt == "PNG" else "jpeg"
        return f"data:image/{mime};base64," + base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return ""


def _file_uri(path: Path, cache: Dict[str, str]) -> str:
    key = str(path)
    if key in cache:
        return cache[key]
    try:
        raw = path.read_bytes()
    except OSError:
        cache[key] = ""
        return ""
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    cache[key] = f"data:{mime};base64," + base64.b64encode(raw).decode()
    return cache[key]


def _find_icon(name: str, icon_path: Path) -> Optional[Path]:
    """与画布版同一套匹配: 全名 → 名字里含图标名 → 通用 → 兜底。

    兜底按名字取模而不是随机: 同一条命令每次出图得是同一个图标。
    """
    if not icon_path or not icon_path.is_dir():
        return None
    icons = sorted(icon_path.glob("*.png"))
    for icon in icons:
        if icon.stem == name:
            return icon
    for icon in icons:
        if icon.stem in name:
            return icon
    generic = icon_path / "通用.png"
    if generic.exists():
        return generic
    if not icons:
        return None
    return icons[zlib.crc32(name.encode("utf-8")) % len(icons)]


def _dispatches(command: str) -> bool:
    """按分发时的同一套规则判定, 而不是宽松前缀匹配: 点了没反应的条目不该留在帮助里。"""
    from rover.models import Event
    from rover.sv import SL

    event = Event(bot_id="dsh", user_id="local", raw_text=command, user_type="group")
    for sv in SL.lst.values():
        for table in sv.TL.values():
            for trigger in table.values():
                try:
                    if trigger.check_command(event):
                        return True
                except Exception:
                    continue
    return False


def _candidates(command: str, prefix: str):
    """帮助里的示例常写成「a/b」这种并列写法, 原样点是跑不通的, 拆成真命令再试。"""
    yield command
    body = command[len(prefix) :] if prefix and command.startswith(prefix) else command
    if "+" in body:
        yield prefix + body.split("+", 1)[0].strip()
    if "/" not in body:
        return
    head, _, tail = body.partition("/")
    # 「深塔/海墟信息11」这类, 斜杠只替换前半段, 后面的尾巴是共用的
    for cut in range(1, len(tail)):
        if tail[cut:]:
            yield prefix + head + tail[cut:]
    yield prefix + head
    yield prefix + tail


def _executable(command: str, prefix: str) -> Optional[str]:
    for candidate in _candidates(command, prefix):
        if candidate and _dispatches(candidate):
            return candidate
    return None


def _clip_name(text: str) -> str:
    """画布版按字宽截断到 8 个中文宽度, 这里照做, 免得名字顶出卡片。"""
    total = 0.0
    out = ""
    for char in text:
        out += char
        if "一" <= char <= "鿿":
            total += 1
        elif re.match(r"[A-Za-z0-9]", char):
            total += 0.5
        elif re.match(r"[^\w\s]", char):
            total += 0.3
        if total >= 8:
            break
    return out


def _entries(cat: str, cat_data: dict, prefix: str, pm: int) -> List[dict]:
    from rover.hooks import DROP_HELP_MARKERS

    rows = []
    for entry in cat_data.get("data", []):
        if entry.get("need_admin") and pm > 3:
            continue
        eg = str(entry.get("eg") or entry.get("name") or "").strip()
        shown = eg if cat == "插件帮助一览" else f"{prefix}{eg}"
        name = str(entry.get("name", ""))
        if any(marker in f"{name}{eg}" for marker in DROP_HELP_MARKERS):
            continue
        command = _executable(shown, "" if cat == "插件帮助一览" else prefix) if eg else shown
        if eg and not command:
            continue
        rows.append(
            {"name": name, "label": shown, "command": command, "desc": str(entry.get("desc", ""))}
        )
    return rows


def _banner(
    width: int, scale: float, icon_uri: str, banner_uri: str, name: str, sub: str, version: str
) -> Tuple[str, int]:
    height = int(550 * scale)

    def at(x: float, y: float) -> str:
        return f"left:{x * scale:.1f}px;top:{y * scale:.1f}px"

    parts = [f'<div class="layer" style="left:0;top:0"><img src="{banner_uri}" '
             f'style="width:{width}px;height:{height}px"></div>']
    if icon_uri:
        parts.append(
            f'<img src="{icon_uri}" style="position:absolute;{at(89, 550 - 212)};'
            f'width:{128 * scale:.1f}px;height:{128 * scale:.1f}px">'
        )
    parts.append(
        f'<div class="t" style="{at(262, 550 - 172)};font-size:{50 * scale:.1f}px;'
        f'font-weight:700">{escape(name)}帮助</div>'
    )
    parts.append(
        f'<div class="t" style="{at(262, 550 - 117)};font-size:{30 * scale:.1f}px;'
        f'color:#cecece">{escape(sub)}</div>'
    )
    if version:
        # 画布版把版本号画成紧跟标题的色块, 这里按标题字宽估一个横向位置
        title = f"{name}帮助"
        em = sum(1.0 if "一" <= c <= "鿿" else 0.56 for c in title)
        left = (262 + em * 50 + 16) * scale
        parts.append(
            f'<div class="badge" style="left:{left:.1f}px;top:{(550 - 172) * scale:.1f}px;'
            f'height:{44 * scale:.1f}px;background:rgb(252,69,69);font-size:{30 * scale:.1f}px">'
            f'<span>{escape(version)}</span></div>'
        )
    return "".join(parts), height


async def get_new_help(
    plugin_name: str = "",
    plugin_info: Optional[Dict[str, str]] = None,
    plugin_icon: Any = None,
    plugin_help: Optional[Dict[str, Any]] = None,
    plugin_prefix: str = "",
    pm: int = 6,
    banner_sub_text: str = "",
    banner_bg: Any = None,
    help_bg: Any = None,
    cag_bg: Any = None,
    item_bg: Any = None,
    icon_path: Any = None,
    footer: Any = None,
    **_ignored: Any,
) -> bytes:
    from rover.html_actions import annotate_html

    width = 120 + CELL_W * COLUMN
    scale = width / BANNER_W
    cag_h = int(100 * scale)
    cache: Dict[str, str] = {}
    icon_dir = Path(icon_path) if icon_path else None

    groups = []
    for cat, cat_data in (plugin_help or {}).items():
        cat_pm = cat_data.get("pm")
        if isinstance(cat_pm, int) and pm > cat_pm:
            continue
        rows = _entries(cat, cat_data, plugin_prefix, pm)
        if rows:
            groups.append((cat, str(cat_data.get("desc", "")), rows))

    # 本机自带的运维命令上游帮助里没有, 并进同一张图, 不再单独发一段文字
    from rover.builtin import ops_help_entries

    ops = _entries("本机运维", {"data": ops_help_entries()}, plugin_prefix, pm)
    if ops:
        groups.append(("本机运维", "更新、重启与状态", ops))

    footer_uri = _uri(footer)
    footer_h = getattr(footer, "height", 0) or 0
    footer_w = getattr(footer, "width", 0) or 0

    banner_html, banner_h = _banner(
        width,
        scale,
        _uri(plugin_icon),
        _uri(banner_bg, "JPEG"),
        plugin_name,
        banner_sub_text,
        next(iter(plugin_info or {}), ""),
    )

    cag_uri = _uri(cag_bg)
    item_uri = _uri(item_bg)
    body: List[str] = [banner_html]
    hs = 0
    for cat, desc, rows in groups:
        top = banner_h + hs - 14 * scale
        body.append(
            f'<div class="layer" style="top:{top:.1f}px"><img src="{cag_uri}" '
            f'style="width:{width}px;height:{cag_h}px"></div>'
            f'<div class="t" style="left:{136 * scale:.1f}px;top:{top + 50 * scale:.1f}px;'
            f'font-size:{45 * scale:.1f}px;font-weight:700">{escape(cat)}</div>'
            f'<div class="t" style="left:{(136 + len(cat) * 45 + 15) * scale:.1f}px;'
            f'top:{top + 55 * scale:.1f}px;font-size:{30 * scale:.1f}px;color:#cecece">'
            f"{escape(desc)}</div>"
        )
        last_row = (len(rows) - 1) // COLUMN
        for index, row in enumerate(rows):
            icon_file = _find_icon(row["name"], icon_dir) if icon_dir else None
            icon_uri = _file_uri(icon_file, cache) if icon_file else ""
            x = ITEM_X0 + (index % COLUMN) * CELL_W
            y = int(banner_h + 70 * scale + (index // COLUMN) * CELL_H + hs + SOFT)
            # 提示框贴着卡片弹出, 靠边的行/列翻向内侧, 免得被容器裁掉
            column = index % COLUMN
            tip_side = "up" if index // COLUMN == last_row and last_row else "down"
            tip_side += " right" if column >= COLUMN - 2 else " left"
            body.append(
                f'<div class="item" style="left:{x}px;top:{y}px" '
                f'data-ww-cmd="{escape(row["command"], quote=True)}">'
                f'<img src="{item_uri}"><div class="hl"></div>'
                + (f'<img class="icon" src="{icon_uri}">' if icon_uri else "")
                + f'<div class="nm">{escape(_clip_name(row["name"]))}</div>'
                f'<div class="eg">{escape(row["label"])}</div>'
                f'<div class="tip {tip_side}"><span class="k">{escape(row["command"])}</span>'
                f'{escape(row["desc"])}</div></div>'
            )
        hs += ((len(rows) - 1) // COLUMN + 1) * CELL_H + cag_h + SOFT

    height = banner_h + hs + footer_h + 20
    if footer_uri:
        body.append(
            f'<img src="{footer_uri}" style="position:absolute;left:{(width - footer_w) // 2}px;'
            f'top:{height - footer_h - 20}px">'
        )

    bg_uri = _uri(help_bg, "JPEG")
    html = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<style>{_CSS}</style></head><body>"
        f'<div class="container" style="width:{width}px;height:{height}px">'
        + (f'<img class="bg" src="{bg_uri}">' if bg_uri else "")
        + "".join(body)
        + "</div></body></html>"
    )
    return HtmlBytes(annotate_html(html, "help", {}), "help")
