"""练度总排行 / 无尽总排行 / 矩阵总排行(含单队) 的 HTML 卡片。

取数沿用原绘图函数, 版式按 PIL 版逐坐标搬运; 构图出错时回退原图。
"""

import asyncio
import base64
import importlib
import time
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from rover.cards import _shared
from rover.logger import logger

_HEADER_H = 510
_TITLE_H = 500
_ROW_H = 110

_scratch: Dict[str, Any] = {}


def _plugin(module, path: str):
    """按插件根包取模块, 不写死插件的导入路径。"""
    return importlib.import_module(f"{module.__name__.rsplit('.', 2)[0]}.{path}")


def _sibling(module, name: str):
    return importlib.import_module(f"{module.__name__.rsplit('.', 1)[0]}.{name}")


def _font_css_url(module) -> str:
    try:
        return _shared.font_css_url(_plugin(module, "utils.render_utils"))
    except Exception:
        return ""


def _css(color: Any, alpha: Optional[float] = None) -> str:
    """插件里的颜色有 (r,g,b) 元组和 '#RRGGBB'/名字两种写法, 统一成 CSS。"""
    if color is None:
        return "inherit"
    if isinstance(color, str):
        return color
    r, g, b = color[0], color[1], color[2]
    if alpha is None and len(color) > 3:
        alpha = color[3] / 255
    if alpha is None:
        return f"rgb({r},{g},{b})"
    return f"rgba({r},{g},{b},{alpha:.3f})"


def _data_uri(image, quality: int = 0) -> str:
    buffer = BytesIO()
    if quality:
        image.save(buffer, format="WEBP", quality=quality)
        mime = "webp"
    else:
        image.save(buffer, format="PNG")
        mime = "png"
    return f"data:image/{mime};base64," + base64.b64encode(buffer.getvalue()).decode()


class _Assets:
    """重复出现的图(角色头像/合鸣/徽章底)只内联一次, 行内按 class 引用。"""

    def __init__(self) -> None:
        self.items: List[Dict[str, str]] = []
        self._index: Dict[Any, str] = {}

    def add(self, key: Any, image, quality: int = 0) -> str:
        if image is None:
            return ""
        name = self._index.get(key)
        if name is None:
            name = f"g{len(self.items)}"
            self.items.append({"cls": name, "uri": _data_uri(image, quality)})
            self._index[key] = name
        return name


def _draw_ctx(module):
    """fit_text 要一个画布量文字宽度, 全局借一张 1x1。"""
    ctx = _scratch.get("draw")
    if ctx is None:
        ctx = module.ImageDraw.Draw(module.Image.new("RGBA", (1, 1)))
        _scratch["draw"] = ctx
    return ctx


def _fit_name(module, text: str, max_width: int) -> Tuple[int, str]:
    fonts = tuple(getattr(module, f"waves_font_{s}") for s in (20, 18, 16, 14, 12))
    font, fitted = module.fit_text(_draw_ctx(module), str(text), max_width, fonts)
    return int(font.size), fitted


def _mask_gradient(mask, width: int, height: int) -> str:
    """标题遮罩: 照 PIL 的等比放大 + 底部裁切采样透明度, 转成竖向渐变。"""
    resized = mask.convert("RGBA").resize((width, mask.height * width // mask.width))
    band = resized.crop((0, resized.height - height, width, resized.height)).getchannel("A")
    x = width // 2
    solid = 0
    for y in range(height):
        if band.getpixel((x, y)) < 255:
            break
        solid = y
    stops = [f"rgb(0,0,0) {solid}px"]
    for y in range(solid, height, 8):
        stops.append(f"rgba(0,0,0,{band.getpixel((x, y)) / 255:.3f}) {y}px")
    stops.append(f"rgba(0,0,0,0) {height}px")
    return "linear-gradient(to bottom, " + ", ".join(stops) + ")"


def _title_image(module, name: str, width: int):
    """标题底图: 大图直接裁, 小图(矩阵)按宽度等比放大后再裁/垫。"""
    image = module.Image.open(module.TEXT_PATH / name).convert("RGBA")
    if name.endswith(".png"):
        image = image.resize((width, int(image.height * width / image.width)))
        if image.height <= _TITLE_H:
            padded = module.Image.new("RGBA", (width, _TITLE_H), (0, 0, 0, 0))
            padded.paste(image, (0, _TITLE_H - image.height))
            return padded
    return image.crop((0, 0, width, _TITLE_H))


def _header(module, title_name: str, title_file: str, width: int, subs: List[str]) -> dict:
    icon = module.get_ICON().resize((128, 128))
    return {
        "title": title_name,
        "art": _data_uri(_title_image(module, title_file, width).convert("RGB"), 82),
        "icon": _data_uri(icon),
        "mask": _mask_gradient(
            module.Image.open(module.TEXT_PATH / "char_mask.png"), width, _TITLE_H
        ),
        "subs": [s for s in subs if s],
    }


def _rank_slot(module, assets: _Assets, rank_id: int) -> dict:
    """名次: 前三名贴牌, 其余色块底板, 位数越多底板越宽(照原版三档)。"""
    badge = _sibling(module, "rank_badge")
    slot: Dict[str, Any] = {"medal": assets.add(("medal", rank_id), badge._load_badge(rank_id))}
    if slot["medal"]:
        return slot
    if rank_id > 1000:
        slot["box"] = {"left": 10, "w": 100, "text": "999+"}
    elif rank_id > 999:
        slot["box"] = {"left": 10, "w": 100, "text": str(rank_id)}
    elif rank_id > 99:
        slot["box"] = {"left": 25, "w": 75, "text": str(rank_id)}
    else:
        slot["box"] = {"left": 40, "w": 50, "text": str(rank_id)}
    return slot


def _bot_badge(module, assets: _Assets, background: str, name: str, x: int, y: int) -> Optional[dict]:
    """bot 主人徽章: 底图按 388x72 → 208x39 等比缩放后居中, 名字压在中间。"""
    if not name:
        return None
    try:
        image = _plugin(module, "utils.image").get_bot_bg(background or "")
    except Exception as e:
        logger.debug(f"[鸣潮·榜单卡] 徽章底图取用失败: {e}")
        image = None
    badge: Dict[str, Any] = {"name": name, "cls": "", "w": 0, "h": 0, "x": x, "y": y}
    if image is not None:
        badge["cls"] = assets.add(("botbg", background or "", id(image)), image)
        badge["w"] = round(image.width * 208 / 388)
        badge["h"] = round(image.height * 39 / 72)
    return badge


def _char_command(module, char_id: Any) -> str:
    """自己那一行的角色头像点开面板。"""
    try:
        name = _plugin(module, "utils.name_convert").char_id_to_char_name(str(char_id))
    except Exception:
        return ""
    if not name:
        return ""
    try:
        prefix = _plugin(module, "wutheringwaves_config").PREFIX
    except Exception:
        prefix = "ww"
    return f"{prefix}{name}面板"


def _base_context(module, width: int, bar, bg) -> dict:
    return {
        "card_w": width,
        "bar": _data_uri(bar),
        "bg": _data_uri(bg.convert("RGB"), 72),
        "font_css_url": _font_css_url(module),
        "grey": _css(module.GREY),
        "gold": _css(getattr(module, "SPECIAL_GOLD", (234, 183, 4))),
    }


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


# ---------------------------------------------------------------- 练度总排行

_LEVEL_CHAR_SIZE = 40
_LEVEL_CHAR_SPACING = 45
_LEVEL_CHAR_X = 570
_LEVEL_CHAR_Y = 35


def _level_char_mask(module) -> str:
    """角色头像用的小遮罩: 底部一段渐隐, 按百分比写以适配任意尺寸。"""
    mask = module.Image.open(module.TEXT_PATH / "char_mask.png").convert("RGBA")
    band = mask.resize((_LEVEL_CHAR_SIZE, _LEVEL_CHAR_SIZE)).getchannel("A")
    stops = []
    for y in range(_LEVEL_CHAR_SIZE):
        stops.append(f"rgba(0,0,0,{band.getpixel((_LEVEL_CHAR_SIZE // 2, y)) / 255:.3f}) {y * 100 / _LEVEL_CHAR_SIZE:.1f}%")
    return "linear-gradient(to bottom, " + ", ".join(stops) + ")"


async def _build_level_rank(module, bot, ev, pages):
    self_uid = await module.WavesBind.get_uid_by_game(ev.user_id, ev.bot_id) or ""
    item = module.TotalRankRequest(
        page=pages,
        page_num=module.RANK_PAGE_SIZE,
        waves_id=self_uid,
        version=module.get_version(dynamic=True, waves_id=self_uid, pages=pages),
    )
    rank_info = await module.get_rank(item)
    if not rank_info:
        return "获取练度总排行失败"
    if rank_info.message and not rank_info.data:
        return rank_info.message
    if not rank_info.data or not rank_info.data.score_details:
        return "暂无排行数据"

    details = rank_info.data.score_details
    avatars = await asyncio.gather(
        *[module.get_avatar(d.user_id, getattr(d, "sender_avatar", "")) for d in details]
    )

    top_chars = {}
    for detail in details:
        chars = sorted(
            detail.char_score_details or [], key=lambda c: c.phantom_score, reverse=True
        )[:10]
        top_chars[detail.waves_id] = chars
    char_ids = {module.randomize_special_char_id(c.char_id) for cs in top_chars.values() for c in cs}
    char_avatars = dict(
        zip(char_ids, await asyncio.gather(*[module.get_square_avatar(i) for i in char_ids]))
    )

    assets = _Assets()
    width = 1300
    rows: List[dict] = []
    for detail, avatar in zip(details, avatars):
        is_self = bool(self_uid) and detail.waves_id == self_uid
        name_size, name_text = _fit_name(module, detail.kuro_name, 130)
        best = top_chars.get(detail.waves_id) or []
        chars: List[dict] = []
        for index, char in enumerate(best):
            display_id = module.randomize_special_char_id(char.char_id)
            icon = char_avatars.get(display_id)
            if icon is None:
                continue
            chars.append(
                {
                    "x": _LEVEL_CHAR_X + index * _LEVEL_CHAR_SPACING,
                    "cls": assets.add(("char", display_id), icon.resize((40, 40)), 88),
                    "score": f"{int(char.phantom_score)}",
                    "cmd": _char_command(module, display_id) if is_self else "",
                }
            )
        row = {
            "avatar": _data_uri(avatar, 80),
            "name": name_text,
            "name_size": name_size,
            "count": len(detail.char_score_details or []),
            "uid": f"特征码: {module.hide_uid(detail.waves_id, user_pref='on' if detail.hide_uid else '')}",
            "uid_x": 350,
            "uid_color": _css(module.RED) if is_self else "white",
            "badge": _bot_badge(
                module, assets, getattr(detail, "background", ""), getattr(detail, "alias_name", ""), 346, 61
            ),
            "chars": chars,
            "best": f"{int(best[0].phantom_score)}" if best else "",
            "total": f"{detail.total_score:.1f}",
        }
        row.update(_rank_slot(module, assets, detail.rank))
        rows.append(row)

    context = _base_context(
        module, width, module.Image.open(module.TEXT_PATH / "bar1.png"),
        module.get_custom_waves_bg(bg="bg9", crop=False),
    )
    context.update(
        header=_header(module, "#练度总排行", "totalrank.jpg", width, [_now()]),
        cond={
            "line1": "1. 综合所有角色的声骸分数。具备声骸套装的角色，全量刷新面板后更新排行位置。",
            "line2": "2. 显示前10个最强角色，刷新单角色影响此处显示但不计入总分。",
            "notes": "排行标准：以所有角色评分（分数>=175）总和为排序的综合排名",
        },
        char_mask=_level_char_mask(module),
        red=_css(module.RED),
        rows=rows,
        assets=assets.items,
    )
    return context


# ---------------------------------------------------------------- 无尽总排行

_SLASH_CHAR_SIZE = 45
_SLASH_HALF_X = 570
_SLASH_HALF_SPACING = 250


async def _build_slash_rank(module, bot, ev, page):
    waves_id = await module.WavesBind.get_uid_by_game(ev.user_id, ev.bot_id) or ""
    item = module.SlashRankItem(
        page=page,
        page_num=module.RANK_PAGE_SIZE,
        waves_id=waves_id,
        version=module.get_version(dynamic=True, waves_id=waves_id, pages=page),
    )
    rank_info = await module.get_rank(item)
    if not rank_info:
        return "获取排行失败"
    if rank_info.message and not rank_info.data:
        return rank_info.message
    if not rank_info.data or not rank_info.data.rank_list:
        return "暂无排行数据"

    rank_list = rank_info.data.rank_list
    avatars = await asyncio.gather(
        *[module.get_avatar(r.user_id, getattr(r, "sender_avatar", "")) for r in rank_list]
    )

    char_ids = {
        module.randomize_special_char_id(c.char_id)
        for r in rank_list
        for half in r.half_list
        for c in half.char_detail
    }
    char_avatars = dict(
        zip(char_ids, await asyncio.gather(*[module.get_square_avatar(i) for i in char_ids]))
    )
    buff_urls = {half.buff_icon for r in rank_list for half in r.half_list if half.buff_icon}
    buff_icons = dict(
        zip(
            buff_urls,
            await asyncio.gather(
                *[module.pic_download_from_url(module.SLASH_PATH, u) for u in buff_urls],
                return_exceptions=True,
            ),
        )
    )

    assets = _Assets()
    width = 1300
    rows: List[dict] = []
    for rank, avatar in zip(rank_list, avatars):
        is_self = bool(waves_id) and rank.waves_id == waves_id
        name_size, name_text = _fit_name(module, rank.kuro_name, 130)
        gold_total = sum(
            c.chain + 1
            for half in rank.half_list
            for c in half.char_detail
            if c.chain >= 0 and module.is_limited_5star(c.char_id)
        )
        halves: List[dict] = []
        for half_index, half in enumerate(rank.half_list):
            offset = 10 if half_index == 0 else 0
            base_x = _SLASH_HALF_X + half_index * _SLASH_HALF_SPACING + offset
            chars: List[dict] = []
            for role_index, char in enumerate(half.char_detail):
                display_id = module.randomize_special_char_id(char.char_id)
                if module.get_char_model(display_id) is None:
                    continue
                icon = char_avatars.get(display_id)
                if icon is None:
                    continue
                chars.append(
                    {
                        "x": base_x + role_index * 50,
                        "cls": assets.add(("char", display_id), icon.resize((45, 45)), 88),
                        "chain": char.chain,
                        "chain_color": _css(module.CHAIN_COLOR[char.chain], 0.9) if char.chain != -1 else "",
                        "cmd": _char_command(module, display_id) if is_self else "",
                    }
                )
            buff = buff_icons.get(half.buff_icon)
            halves.append(
                {
                    "chars": chars,
                    "buff": assets.add(("buff", half.buff_icon), buff if not isinstance(buff, BaseException) else None, 88),
                    "buff_x": 720 + half_index * _SLASH_HALF_SPACING + offset,
                    "buff_color": _css(module.COLOR_QUALITY[half.buff_quality]),
                    "score": f"{half.score}",
                    "score_x": 670 + half_index * _SLASH_HALF_SPACING + offset,
                    "score_color": _css(module.get_score_color(half.score)),
                }
            )
        row = {
            "avatar": _data_uri(avatar, 80),
            "name": name_text,
            "name_size": name_size,
            "gold": f"角色限定{gold_total}金",
            "uid": f"特征码: {module.hide_uid(rank.waves_id, user_pref='on' if rank.hide_uid else '')}",
            "uid_x": 350,
            "uid_color": _css(module.RED) if is_self else "white",
            "badge": _bot_badge(
                module, assets, getattr(rank, "background", ""), rank.alias_name or "", 346, 61
            ),
            "halves": halves,
            "score": f"{rank.score}",
            "score_color": _css(module.get_score_color(rank.score)),
        }
        row.update(_rank_slot(module, assets, rank.rank))
        rows.append(row)

    period = ""
    if rank_info.data.start_date:
        rank_dt = module.parse_rank_date(rank_info.data.start_date)
        if rank_dt:
            period = f"第{module.get_slash_period_number(rank_dt)}期"

    context = _base_context(
        module, width, module.Image.open(module.TEXT_PATH / "bar1.png"),
        module.get_waves_bg(bg="bg9", crop=False),
    )
    context.update(
        header=_header(module, "#无尽总排行", "slash.jpg", width, [period, _now()]),
        rows=rows,
        assets=assets.items,
    )
    return context


# ---------------------------------------------------------------- 矩阵总排行


def _crystal_gradient(module) -> str:
    colors = _sibling(module, "_colors").CRYSTAL_COLORS
    return "linear-gradient(90deg, " + ", ".join(_css(c) for c in colors) + ")"


def _matrix_score_style(module, color) -> str:
    return "" if color == module.CRYSTAL_SENTINEL else _css(color)


async def _build_matrix_rank(module, bot, ev, single_team, page, char_ids):
    waves_id = await module.WavesBind.get_uid_by_game(ev.user_id, ev.bot_id) or ""
    item = module.MatrixRankItem(
        page=page,
        page_num=module.RANK_PAGE_SIZE,
        waves_id=waves_id,
        version=module.get_version(dynamic=True, waves_id=waves_id, pages=page),
        single_team=single_team,
        char_ids=char_ids or [],
    )
    rank_info = await module.get_rank(item)
    if not rank_info:
        return "获取矩阵排行失败"
    if rank_info.message and not rank_info.data:
        return rank_info.message
    if not rank_info.data or not rank_info.data.rank_list:
        return "暂无该队伍的排行数据" if char_ids else "暂无排行数据"

    rank_list = rank_info.data.rank_list
    width = module.MATRIX_SINGLE_TOTAL_WIDTH if single_team else module.MATRIX_TOTAL_WIDTH
    board_7digit = any(r.score >= 1_000_000 for r in rank_list)
    board_6digit = any(r.score >= 100_000 for r in rank_list)
    team_limit = 1 if single_team else 2
    char_size = 55 if single_team else 45
    char_spacing = 60 if single_team else 50
    char_y = 28 if single_team else 20
    buff_size = 60 if single_team else 50
    buff_y = 25 if single_team else 15
    chain_size = 20 if single_team else 15
    team_base_x = (580 if board_6digit else 600) if single_team else 575
    team_spacing = 232 if (not single_team and board_7digit) else 250

    avatars = await asyncio.gather(
        *[module.get_avatar(r.user_id, getattr(r, "sender_avatar", "")) for r in rank_list]
    )
    shown_teams = [
        sorted(r.teams, key=lambda t: t.score, reverse=True)[:team_limit] for r in rank_list
    ]
    ids = set()
    icon_urls = set()
    for teams in shown_teams:
        for team in teams:
            ids.update(module.randomize_special_char_id(c.char_id) for c in team.char_detail)
            if team.buff_icon:
                icon_urls.add(team.buff_icon)
            if not team.char_detail:
                icon_urls.update(team.role_icons)
    char_avatars = dict(
        zip(ids, await asyncio.gather(*[module.get_square_avatar(i) for i in ids]))
    )
    downloads = dict(
        zip(
            icon_urls,
            await asyncio.gather(
                *[module.pic_download_from_url(module.MATRIX_PATH, u) for u in icon_urls],
                return_exceptions=True,
            ),
        )
    )

    assets = _Assets()
    rows: List[dict] = []
    for rank, avatar, shown in zip(rank_list, avatars, shown_teams):
        is_self = bool(waves_id) and rank.waves_id == waves_id
        name_size, name_text = _fit_name(
            module,
            rank.kuro_name,
            module.MATRIX_SINGLE_NAME_MAX_WIDTH if single_team else module.MATRIX_TOTAL_NAME_MAX_WIDTH,
        )
        uid_text = module.hide_uid(rank.waves_id, user_pref="on" if rank.hide_uid else "")
        teams: List[dict] = []
        for team_index, team in enumerate(shown):
            base_x = team_base_x + team_index * team_spacing
            chars: List[dict] = []
            for role_index, char in enumerate(team.char_detail):
                display_id = module.randomize_special_char_id(char.char_id)
                if module.get_char_model(display_id) is None:
                    continue
                icon = char_avatars.get(display_id)
                if icon is None:
                    continue
                chars.append(
                    {
                        "x": base_x + role_index * char_spacing,
                        "cls": assets.add(("char", display_id, char_size), icon.resize((char_size, char_size)), 88),
                        "chain": char.chain,
                        "chain_color": _css(module.CHAIN_COLOR[char.chain], 0.9) if char.chain != -1 else "",
                        "round": False,
                        "cmd": _char_command(module, display_id) if is_self else "",
                    }
                )
            if not team.char_detail and team.role_icons:
                for role_index, url in enumerate(team.role_icons):
                    icon = downloads.get(url)
                    if icon is None or isinstance(icon, BaseException):
                        continue
                    chars.append(
                        {
                            "x": base_x + role_index * char_spacing,
                            "cls": assets.add(("url", url, char_size), icon.resize((char_size, char_size)), 88),
                            "chain": -1,
                            "chain_color": "",
                            "round": True,
                            "cmd": "",
                        }
                    )
            filled = len(team.char_detail) or len(team.role_icons)
            buff = downloads.get(team.buff_icon)
            score_color = module.get_team_score_color(team.score)
            teams.append(
                {
                    "chars": chars,
                    "holes": [base_x + i * char_spacing for i in range(filled, 3)],
                    "buff": assets.add(
                        ("buff", team.buff_icon, buff_size),
                        buff.resize((buff_size, buff_size)) if buff is not None and not isinstance(buff, BaseException) else None,
                        88,
                    ),
                    "buff_x": base_x + char_spacing * 3 + 10,
                    "score": f"{'最高单队得分' if team_index == 0 else '次高单队得分'}: {team.score}",
                    "score_x": base_x + 105,
                    "score_color": _matrix_score_style(module, score_color),
                }
            )
        score_color = (
            module.get_team_score_color(rank.score) if single_team else module.get_score_color(rank.score)
        )
        team_count = rank.team_count if rank.team_count else len(rank.teams)
        row = {
            "avatar": _data_uri(avatar, 80),
            "name": name_text,
            "name_size": name_size,
            "uid": f"特征码: {uid_text}" if single_team else uid_text,
            "uid_x": 350 if single_team else 210,
            "uid_color": _css(module.RED) if is_self else "white",
            "gold": module._get_matrix_team_char_gold_count(rank.teams) if single_team else 0,
            "team_count": f"上场队伍数量: {team_count}" if team_count else "",
            "badge": _bot_badge(
                module,
                assets,
                getattr(rank, "background", ""),
                rank.alias_name or "",
                346 if single_team else 350,
                60,
            ),
            "teams": teams,
            "score": f"{rank.score}",
            "score_x": 950 if single_team else 1140,
            "score_color": _matrix_score_style(module, score_color),
        }
        row.update(_rank_slot(module, assets, rank.rank))
        rows.append(row)

    period = ""
    if rank_info.data.start_date:
        rank_dt = module.parse_rank_date(rank_info.data.start_date)
        if rank_dt:
            period = f"第{module.get_matrix_period_number(rank_dt)}期"
    subs = [period, _now()]
    if period:
        subs.append(module._matrix_team_label(char_ids))

    context = _base_context(
        module, width, module._get_matrix_rank_bar(width), module.get_waves_bg(bg="bg9", crop=False)
    )
    context.update(
        header=_header(
            module,
            "#矩阵单队总排行" if single_team else "#矩阵总排行",
            "matrix.png",
            width,
            subs,
        ),
        single_team=single_team,
        char_size=char_size,
        char_y=char_y,
        chain_size=chain_size,
        buff_size=buff_size,
        buff_y=buff_y,
        hole_first_y=19 if single_team else 16,
        hole_second_y=35 if single_team else 32,
        crystal=_crystal_gradient(module),
        red=_css(module.RED),
        rows=rows,
        assets=assets.items,
    )
    return context


# ---------------------------------------------------------------- 补丁挂载


def _render(template_name: str, context: dict):
    card = _shared.render(template_name, context)
    logger.info(f"[鸣潮·榜单卡] {template_name} {len(card) / 1024 / 1024:.2f}MB")
    return card


def _bind(module, name: str, func) -> None:
    """功能模块 import 时已按值绑定, 包内同名引用一并换掉。"""
    import sys

    setattr(module, name, func)
    package = sys.modules.get(module.__name__.rsplit(".", 1)[0])
    if package is not None and hasattr(package, name):
        setattr(package, name, func)


def patch_level_rank(module) -> None:
    original = module.draw_total_rank

    async def draw_total_rank(bot, ev, pages):
        try:
            context = await _build_level_rank(module, bot, ev, pages)
            if isinstance(context, str):
                return context
            return _render("rank_level_total.html", context)
        except Exception as e:
            logger.exception(f"[鸣潮·榜单卡] 练度总排行渲染失败, 回退原图: {e}")
            return await original(bot, ev, pages)

    _bind(module, "draw_total_rank", draw_total_rank)


def patch_slash_rank(module) -> None:
    original = module.draw_all_slash_rank_card

    async def draw_all_slash_rank_card(bot, ev, page: int = 1):
        try:
            context = await _build_slash_rank(module, bot, ev, page)
            if isinstance(context, str):
                return context
            return _render("rank_slash_total.html", context)
        except Exception as e:
            logger.exception(f"[鸣潮·榜单卡] 无尽总排行渲染失败, 回退原图: {e}")
            return await original(bot, ev, page)

    _bind(module, "draw_all_slash_rank_card", draw_all_slash_rank_card)


def patch_matrix_rank(module) -> None:
    original = module.draw_all_matrix_rank_card

    async def draw_all_matrix_rank_card(bot, ev, single_team=False, page=1, char_ids=None):
        try:
            context = await _build_matrix_rank(module, bot, ev, single_team, page, char_ids)
            if isinstance(context, str):
                return context
            return _render("rank_matrix_total.html", context)
        except Exception as e:
            logger.exception(f"[鸣潮·榜单卡] 矩阵总排行渲染失败, 回退原图: {e}")
            return await original(bot, ev, single_team, page, char_ids)

    _bind(module, "draw_all_matrix_rank_card", draw_all_matrix_rank_card)


PATCHES = {
    "XutheringWavesUID": {
        "wutheringwaves_rank.draw_total_rank_card": patch_level_rank,
        "wutheringwaves_rank.slash_rank": patch_slash_rank,
        "wutheringwaves_rank.matrix_rank": patch_matrix_rank,
    }
}
