"""角色总排行 / 声骸总排行 的 HTML 卡片。

取数沿用原绘图函数, 版式按 PIL 版逐坐标搬运; 构图出错时回退原图。
"""

import asyncio
import base64
import importlib
import time
from io import BytesIO
from typing import Any, Dict, List, Optional

from rover.cards import _shared
from rover.logger import logger

# char_mask.png 的竖向渐变(实测采样): 410px 起淡出, 500px 全透
_MASK_GRADIENT = (
    "linear-gradient(to bottom, rgba(0,0,0,1) 0px, rgba(0,0,0,1) 410px,"
    " rgba(0,0,0,.84) 435px, rgba(0,0,0,.6) 450px, rgba(0,0,0,.32) 465px,"
    " rgba(0,0,0,.11) 480px, rgba(0,0,0,0) 500px)"
)
_HEADER_H = 500
# 标题图与人物立绘在原版里整体左移 300px 后再上遮罩
_TITLE_DX = -300


def _plugin(module, path: str):
    """按插件根包取兄弟模块, 不写死插件的导入路径。"""
    return importlib.import_module(f"{module.__name__.rsplit('.', 2)[0]}.{path}")


def _sibling(module, name: str):
    return importlib.import_module(f"{module.__name__.rsplit('.', 1)[0]}.{name}")


def _prefix(module) -> str:
    try:
        return _plugin(module, "wutheringwaves_config").PREFIX
    except Exception:
        return "ww"


def _font_css_url(module) -> str:
    try:
        return _shared.font_css_url(_plugin(module, "utils.render_utils"))
    except Exception:
        return ""


def _css(color: Any, alpha: Optional[float] = None) -> str:
    """插件里的颜色有 (r,g,b) 元组和 '#RRGGBB' 两种写法, 统一成 CSS。"""
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
    """重复出现的图(武器/评级/合鸣/徽章底)只内联一次, 行内按 class 引用。"""

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


def _bot_badge(module, assets: _Assets, background: str, name: str) -> Optional[dict]:
    """bot 主人徽章: 底图按 388x72 → 208x39 等比缩放后居中, 名字压在中间。"""
    if not name:
        return None
    try:
        image = _plugin(module, "utils.image").get_bot_bg(background or "")
    except Exception as e:
        logger.debug(f"[鸣潮·排行卡] 徽章底图取用失败: {e}")
        image = None
    badge: Dict[str, Any] = {"name": name, "cls": "", "w": 0, "h": 0}
    if image is not None:
        badge["cls"] = assets.add(("botbg", background or "", id(image)), image)
        badge["w"] = round(image.width * 208 / 388)
        badge["h"] = round(image.height * 39 / 72)
    return badge


def _rank_box(rank_id: int) -> dict:
    """非前三名的名次底板: 位数越多底板越宽(照原版三档)。"""
    if rank_id > 1000:
        return {"left": 10, "w": 100, "text": "999+"}
    if rank_id > 999:
        return {"left": 10, "w": 100, "text": str(rank_id)}
    if rank_id > 99:
        return {"left": 25, "w": 75, "text": str(rank_id)}
    return {"left": 40, "w": 50, "text": str(rank_id)}


async def _header_context(module, char_id: str, title_name: str, pile_x: int) -> dict:
    """人物立绘头部: 标题底图 + 立绘 + 遮罩, 坐标照原版整体左移 300。"""
    version = module.get_version()
    header: Dict[str, Any] = {
        "title_bg": _data_uri(module.TITLE_II, 85),
        "logo": _data_uri(module.logo_img),
        "title_dx": _TITLE_DX,
        "title_name": title_name,
        "version": f"v{version}",
        "version_x": 240 + 31 * len(title_name),
        "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "mask": _MASK_GRADIENT,
        "pile": None,
    }
    try:
        pile, _ = await module.get_role_pile_default(char_id, custom=True)
        header["pile"] = {
            "uri": _data_uri(pile, 82),
            "x": pile_x,
            "y": -120,
            "w": pile.width,
            "h": pile.height,
        }
    except Exception as e:
        logger.debug(f"[鸣潮·排行卡] 立绘取用失败 char_id={char_id}: {e}")
    return header


def _background(module, quality: int = 72) -> str:
    bg = module.get_custom_waves_bg(bg="bg3", crop=False)
    return _data_uri(bg.convert("RGB"), quality)


# ---------------------------------------------------------------- 角色总排行


async def _build_all_rank(module, bot, ev, char, rank_type, pages, modal, group_uids):
    self_uid = ""
    is_self_ck = False
    try:
        self_uid = await module.WavesBind.get_uid_by_game(ev.user_id, ev.bot_id)
        is_self_ck, _ = await module.waves_api.get_ck_result(self_uid, ev.user_id, ev.bot_id)
    except Exception:
        pass

    char_id = module.char_name_to_char_id(char)
    if not char_id:
        return "未找到指定角色, 请检查输入是否正确！"
    char_name = module.alias_to_char_name(char)
    char_model = module.get_char_model(char_id)
    if not char_model:
        return f"[鸣潮] 角色名【{char_name}】暂未适配！\n"
    attribute_name = module.ATTRIBUTE_ID_MAP[char_model.attributeId]

    rank_type_num = 3 if rank_type == "综合评分" else (2 if rank_type == "伤害" else 1)
    page_num = module.RANK_PAGE_SIZE
    if not modal:
        options = module.get_modal_options(int(char_id))
        if options:
            role = await module.find_role_detail(self_uid, char_id) if self_uid else None
            modal = module.get_role_modal(role) if role else module.get_default_modal(int(char_id))

    is_group = group_uids is not None
    if is_group:
        resp = await module.get_cards_rank(
            module.CardsRankRequest(
                char_id=int(char_id),
                rank_type=rank_type_num,
                modal=modal,
                waves_ids=[str(u) for u in group_uids if u],
            )
        )
        if not resp:
            return "获取群排行失败"
        if not resp.data or not resp.data.details:
            return "暂无排行数据"
        details = [d for d in resp.data.details if d.overall_score > 0]
        if not details:
            return "[鸣潮] 群内暂无该角色综合评分数据\n需【登录】并【刷新单角色面板】上传后才会上榜"
        details.sort(key=lambda d: d.overall_score, reverse=True)
        for i, d in enumerate(details):
            d.rank = i + 1
        self_entry = next((d for d in details if self_uid and d.waves_id == self_uid), None)
        details, _, page_count, page_item_count = module.paginate_group_rank(
            details, pages, self_entry.rank if self_entry else None, self_entry
        )
        if page_item_count == 0:
            return module.group_rank_empty_page_message(pages, page_count)
    else:
        item = module.RankItem(
            char_id=int(char_id),
            page=pages,
            page_num=page_num,
            rank_type=rank_type_num,
            waves_id=self_uid,
            version=module.get_version(
                dynamic=True, waves_id=self_uid, char_id=char_id, rank_type=rank_type, pages=pages
            ),
            modal=modal,
        )
        rank_info = await module.get_rank(item)
        if not rank_info:
            return "获取排行失败"
        if rank_info.message and not rank_info.data:
            return rank_info.message
        if not rank_info.data or not rank_info.data.details:
            return "暂无排行数据"
        details = rank_info.data.details

    assets = _Assets()
    avatars = await asyncio.gather(
        *[
            module.get_avatar(rank.user_id, getattr(rank, "sender_avatar", ""), char_id=rank.char_id)
            for rank in details
        ]
    )
    mask_uid = None
    if is_group:
        mask_uid = await module.build_uid_masker(
            [(d.waves_id, d.user_id) for d in details], ev.bot_id
        )

    attribute_icon = assets.add(
        ("attr", attribute_name),
        (await module.get_attribute(attribute_name, is_simple=True)).resize((40, 40)).convert("RGBA"),
    )

    prefix = _prefix(module)
    rows: List[dict] = []
    total_score = 0.0
    total_damage = 0.0
    avg_num = 0
    damage_name = ""
    valid_pairs = [(r, a) for r, a in zip(details, avatars) if r.rank > 0]

    for index, (rank, avatar) in enumerate(valid_pairs):
        damage_name = rank.expected_name
        weapon_model = module.get_weapon_model(rank.weapon_id)
        if not weapon_model:
            logger.warning("[鸣潮·排行卡] 武器无法找到, 可能暂未适配")
            continue

        weapon_icon = module.crop_center_img(await module.get_square_weapon(rank.weapon_id), 110, 110)
        weapon_bg = module.get_weapon_icon_bg(weapon_model.starLevel, module.TEXT_PATH)
        weapon_bg.paste(weapon_icon, (10, 20), weapon_icon)

        score_value = rank.overall_score if rank_type == "综合评分" else rank.phantom_score
        score: Optional[dict] = None
        if score_value > 0.0:
            grade = (
                module.get_panel_score_grade(score_value)
                if rank_type == "综合评分"
                else rank.phantom_score_bg
            )
            emblem = module.Image.open(module.TEXT_PATH / f"score_{grade}.png")
            score = {
                "cls": assets.add(("score", grade), emblem),
                "value": f"{int(score_value * 100) / 100:.2f}",
                "label": "综合评分" if rank_type == "综合评分" else "声骸分数",
            }

        if rank.sonata_name:
            sonata_label = module.get_sonata_label(rank.sonata_name)
            sonata_cls = assets.add(
                ("sonata", rank.sonata_name), await module.get_sonata_effect_image(rank.sonata_name, 50)
            )
        else:
            sonata_label, sonata_cls = "合鸣效果", ""

        if is_group:
            uid_text = mask_uid(rank.waves_id, rank.user_id)
        else:
            uid_text = module.hide_uid(rank.waves_id, user_pref="on" if rank.hide_uid else "")

        rows.append(
            {
                "rank": rank.rank,
                "medal": assets.add(
                    ("medal", rank.rank), _sibling(module, "rank_badge")._load_badge(rank.rank)
                ),
                "box": _rank_box(rank.rank),
                "avatar": _data_uri(avatar, 80),
                "chain": module.get_chain_name(rank.chain),
                "chain_color": _css(module.CHAIN_COLOR[rank.chain], 0.9),
                "level": f"Lv.{rank.level}",
                "attribute": attribute_icon,
                "uid": f"特征码: {uid_text}",
                "uid_color": _css(module.RED) if is_self_ck and self_uid == rank.waves_id else "white",
                # 点行按对方 uid 查这个角色的面板(对方未公开则由命令自己回提示)
                "cmd": f"{_shared.prefix()}{rank.waves_id}{char_name}面板" if rank.waves_id else "",
                "name": str(rank.kuro_name),
                "badge": _bot_badge(module, assets, getattr(rank, "background", ""), rank.alias_name),
                "score": score,
                "sonata": sonata_cls,
                "sonata_label": sonata_label,
                "sonata_size": 14 if len(sonata_label) > 4 else 16,
                "weapon": {
                    "cls": assets.add(("weapon", rank.weapon_id, weapon_model.starLevel), weapon_bg),
                    "name": weapon_model.name,
                    "level": f"Lv.{rank.weapon_level}/90",
                    "reson": f"{rank.weapon_reson_level}阶",
                    "reson_color": _css(module.WEAPON_RESONLEVEL_COLOR[rank.weapon_reson_level], 0.8),
                },
                "damage": f"{rank.expected_damage:,.0f}",
                "damage_name": rank.expected_name,
            }
        )

        if index + 1 + (pages - 1) * page_num == rank.rank:
            total_score += rank.overall_score if rank_type == "综合评分" else rank.phantom_score
            total_damage += rank.expected_damage
            avg_num += 1

    title_char = module.SPECIAL_CHAR_NAME.get(char_id, char_name)
    title_name = f"{title_char}{rank_type}{'群排行' if is_group else '总排行'}"

    modal_options = module.get_modal_options(int(char_id))
    if rank_type == "伤害":
        notes = "排行标准：以期望伤害（计算暴击率的伤害，不代表实际伤害) 为排序的排名"
    elif rank_type == "综合评分":
        notes = "综合评分为个性化标准，按各自配置估算得出，仅供参考，非公平对比。"
    else:
        notes = "排行标准：以声骸分数（声骸评分高，不代表实际伤害高) 为排序的排名"
    cond = {
        "height": 170 if modal_options else 130,
        "line1": "1. 声骸套装为常规套装",
        "line2": "2. 登录用户&刷新单角色面板" if rank_type == "综合评分" else "2. 登录用户&刷新面板",
        "modal": "",
        "modal_current": "",
        "notes": notes,
    }
    if modal_options:
        names = "/".join(o["name"] for o in modal_options)
        cond["modal"] = f"支持模态: {prefix}{char}总排行 {names}"
        current = module.get_modal_name(int(char_id), modal)
        if current:
            cond["modal_current"] = f"当前模态: {current}"

    header = await _header_context(module, char_id, title_name, 600)
    header["stats"] = [
        {
            "x": 300,
            "value": f"{total_score / avg_num:.1f}" if avg_num else "0",
            "label": "平均综合评分" if rank_type == "综合评分" else "平均声骸分数",
        },
        {
            "x": 490,
            "value": f"{total_damage / avg_num:,.0f}" if avg_num else "0",
            "label": "平均治疗量" if "治疗" in damage_name else "平均伤害",
        },
    ]

    return {
        "card_w": 1300,
        "header_h": _HEADER_H,
        "row_h": 110,
        "bg": _background(module),
        "bar": _data_uri(module.Image.open(module.TEXT_PATH / "bar1.png")),
        "font_css_url": _font_css_url(module),
        "gold": _css(module.SPECIAL_GOLD),
        "grey": _css(module.GREY),
        "header": header,
        "cond": cond,
        "rows": rows,
        "assets": assets.items,
        "cmd_score": f"{prefix}{char_name}评分总排行",
        "cmd_damage": f"{prefix}{char_name}总排行",
        "cmd_phantom": f"{prefix}{char_name}声骸总排行",
    }


# ---------------------------------------------------------------- 声骸总排行


def _phantom_geometry(module) -> dict:
    """行内坐标全部取原模块实测常量, 保证与 PIL 版逐像素一致。"""
    return {
        "width": module.WIDTH,
        "item_h": module.ITEM_H,
        "rank_x": module._RANK_X,
        "medal_y": module._RANK_MEDAL_Y,
        "medal_size": module._RANK_MEDAL_SIZE[0],
        "box_y": module._RANK_BOX_Y,
        "box_h": module._RANK_BOX_SIZE[1],
        "box_cx": module._RANK_X + module._RANK_BOX_SIZE[0] // 2,
        "user_x": module.USER_INFO_X,
        "name_y": module._USER_NAME_Y,
        "name_max": module._USER_NAME_MAX_WIDTH,
        "uid_y": module._USER_UID_Y,
        "badge_x": module._BOT_BADGE_POS[0],
        "badge_y": module._BOT_BADGE_POS[1],
        "thumb_x": module.PHANTOM_THUMB_X - module._THUMB_SHIFT,
        "icon_y": module._PHANTOM_ICON_Y,
        "icon_size": module._PHANTOM_ICON_SIZE[0],
        "fetter_dx": 58,
        "fetter_y": module._FETTER_ICON_POS[1],
        "fetter_size": module._FETTER_ICON_SIZE[0],
        "pip_size": module._PROMOTE_SIZE[0],
        "pip_y": module._PROMOTE_Y,
        "name_col_max": module._NAME_MAX,
        "emblem_x": module._EMBLEM_X,
        "emblem_y": module._EMBLEM_Y,
        "emblem_size": module._EMBLEM_SIZE[0],
        "score_x": module._SCORE_NUM_X,
        "score_y": module._SCORE_NUM_Y,
        "score_label_x": module._SCORE_LABEL_X,
        "score_label_y": module._SCORE_LABEL_Y,
    }


def _name_size(name: str, max_width: int) -> int:
    """词条名照原版逐级缩字号(18/16/14), 汉字宽度按字号估算。"""
    for size in (18, 16, 14):
        if len(name) * size <= max_width:
            return size
    return 14


def _phantom_props(module, detail, calc_map, geo) -> List[dict]:
    """词条 2 列表: 名左对齐, 数值与单词条分各按固定右边界对齐。"""
    entries = module.build_entries(detail.main_props, detail.sub_props, calc_map)
    props: List[dict] = []
    for i, entry in enumerate(entries[:6]):
        name, value, pscore, is_main, name_color, num_color = entry
        row, col = divmod(i, 2)
        name_x = module._COL_NAME_X[col]
        score_right = module._COL_SCORE_RIGHT[col]
        props.append(
            {
                "name": name,
                "name_size": _name_size(name, geo["name_col_max"]),
                "value": value,
                "score": f"+{pscore:.2f}",
                "name_x": name_x,
                "value_right": geo["width"] - module._COL_VALUE_RIGHT[col],
                "score_right": geo["width"] - score_right,
                "y": module._PROP_ROW_Y[row],
                "name_color": _css(name_color),
                "value_color": _css(num_color),
                "score_color": _css(module.SCORE_POS if pscore > 0 else module.SCORE_ZERO),
                "highlight": {"left": name_x - 6, "w": score_right - name_x + 12} if is_main else None,
            }
        )
    return props


async def _build_phantom_rank(module, bot, ev, char, pages):
    char_id = module.char_name_to_char_id(char)
    if not char_id:
        return "未找到指定角色, 请检查输入是否正确！"
    char = module.char_id_to_char_name(char_id) or char
    self_uid = await module.WavesBind.get_uid_by_game(ev.user_id, ev.bot_id) or ""

    rank_info = await module.get_phantom_total_rank(
        module.PhantomTotalRankRequest(
            char_id=int(char_id),
            page=pages,
            page_num=module.RANK_PAGE_SIZE,
            waves_id=self_uid,
            version=module.get_version(dynamic=True, waves_id=self_uid, pages=pages),
        )
    )
    if not rank_info:
        return "获取声骸总排行失败"
    if rank_info.message and not rank_info.data:
        return rank_info.message
    if not rank_info.data or not rank_info.data.rank_list:
        return "暂无排行数据"

    ranking = rank_info.data.rank_list
    details = list(ranking)
    self_entry = getattr(rank_info.data, "self_entry", None)
    if self_uid and self_entry is not None:
        if self_entry.rank and self_entry.rank > 0:
            self_row = self_entry
        else:
            self_row = await module._build_local_self_row(self_uid, char_id, self_entry)
        if self_row is not None:
            details.append(self_row)
    if not details:
        return f"[鸣潮] 暂无【{char}】声骸总排行数据"

    try:
        calc_map = module.get_calc_map({}, char, char_id)
    except Exception as e:
        logger.debug(f"[鸣潮·排行卡] 词条权重取用失败 char_id={char_id}: {e}")
        calc_map = None

    avatars, phantom_icons, fetter_icons = await asyncio.gather(
        asyncio.gather(
            *[module.get_avatar(d.user_id, getattr(d, "sender_avatar", ""), char_id=d.char_id) for d in details]
        ),
        asyncio.gather(*[module._safe_phantom_icon(d) for d in details]),
        asyncio.gather(*[module._safe_fetter_icon(d.set) for d in details]),
    )

    geo = _phantom_geometry(module)
    assets = _Assets()
    rows: List[dict] = []
    for detail, avatar, phantom_icon, fetter_icon in zip(details, avatars, phantom_icons, fetter_icons):
        avatar_box = None
        if avatar is not None:
            bbox = avatar.getchannel("A").getbbox()
            if bbox is not None:
                avatar_box = {
                    "uri": _data_uri(avatar, 80),
                    "x": module._AVATAR_VISIBLE_X - bbox[0],
                    "y": module.FRAME_TOP
                    + (module.FRAME_BOTTOM - module.FRAME_TOP - (bbox[3] - bbox[1])) // 2
                    - bbox[1],
                    "w": avatar.width,
                    "h": avatar.height,
                }
        emblem = None
        try:
            emblem = module.Image.open(module.TEXT_PATH / f"score_{detail.grade}.png").resize(
                module._EMBLEM_SIZE
            )
        except Exception as e:
            logger.debug(f"[鸣潮·排行卡] 评级贴图缺失 grade={detail.grade}: {e}")

        pip_gap = 3
        pip_step = geo["pip_size"] + pip_gap
        pips_w = detail.cost * geo["pip_size"] + max(detail.cost - 1, 0) * pip_gap
        pips_x = geo["thumb_x"] + (geo["icon_size"] - pips_w) // 2

        rows.append(
            {
                "rank": detail.rank,
                "medal": assets.add(("medal", detail.rank), module._load_badge(detail.rank)),
                "box": _phantom_rank_box(module, detail.rank),
                "avatar": avatar_box,
                "name": str(detail.kuro_name),
                "uid": f"特征码: {module.hide_uid(detail.waves_id, user_pref='on' if detail.hide_uid else '')}",
                "uid_color": _css(module.RED) if detail.waves_id == self_uid else "white",
                "badge": _bot_badge(
                    module, assets, getattr(detail, "background", ""), getattr(detail, "alias_name", "")
                ),
                "icon": assets.add(("phantom", detail.phantom_id), phantom_icon, 85),
                "fetter": assets.add(("fetter", detail.set), fetter_icon),
                "pips": [pips_x + pip_step * i for i in range(detail.cost)],
                "props": _phantom_props(module, detail, calc_map, geo),
                "emblem": assets.add(("grade", detail.grade), emblem),
                "score": f"{detail.score:.2f}",
            }
        )

    avg_value = sum(d.score for d in ranking) / len(ranking) if ranking else 0
    title_char = module.SPECIAL_CHAR_NAME.get(char_id, char)
    title_name = f"{title_char}声骸总排行"
    header = await _header_context(module, char_id, title_name, geo["width"] - 700)
    header["stats"] = [{"x": 300, "value": f"{avg_value:.1f}", "label": "平均单声骸分数"}]

    prefix = _prefix(module)
    return {
        "card_w": geo["width"],
        "header_h": _HEADER_H,
        "geo": geo,
        "bg": _background(module),
        "bar": _data_uri(module.draw_phantom_bar_bg(module.Image.open(module.TEXT_PATH / "bar1.png"))),
        "pip": _data_uri(module.promote_icon.resize(module._PROMOTE_SIZE)),
        "font_css_url": _font_css_url(module),
        "gold": _css(module.SPECIAL_GOLD),
        "grey": _css(module.GREY),
        "header": header,
        "cond": {
            "height": 130,
            "line1": "1. 声骸满 5 副词条 & 常规有效套装",
            "line2": "2. 登录用户 & 刷新面板",
            "notes": "排行标准：以单声骸分数排序 (评分高不代表实际伤害高)",
        },
        "rows": rows,
        "assets": assets.items,
        "cmd_damage": f"{prefix}{char}总排行",
        "cmd_score": f"{prefix}{char}评分总排行",
    }


def _phantom_rank_box(module, rank_id: int) -> dict:
    """声骸榜名次底板: 金框外空间有限, 4 位数字换小一号字。"""
    if rank_id > 999:
        return {"text": "999+" if rank_id > 1000 else str(rank_id), "w": 88, "size": 30}
    if rank_id > 99:
        return {"text": str(rank_id), "w": 72, "size": 34}
    return {"text": str(rank_id), "w": module._RANK_BOX_SIZE[0], "size": 34}


# ---------------------------------------------------------------- 补丁挂载


def _render(template_name: str, context: dict):
    card = _shared.render(template_name, context)
    logger.info(f"[鸣潮·排行卡] {template_name} {len(card) / 1024 / 1024:.2f}MB")
    return card


def _bind(module, name: str, func) -> None:
    """功能模块 import 时已按值绑定, 包内同名引用一并换掉。"""
    import sys

    setattr(module, name, func)
    package = sys.modules.get(module.__name__.rsplit(".", 1)[0])
    if package is not None and hasattr(package, name):
        setattr(package, name, func)


def patch_all_rank(module) -> None:
    original = module.draw_all_rank_card

    async def draw_all_rank_card(bot, ev, char, rank_type, pages, modal="", group_uids=None):
        try:
            context = await _build_all_rank(module, bot, ev, char, rank_type, pages, modal, group_uids)
            if isinstance(context, str):
                return context
            return _render("rank_all_total.html", context)
        except Exception as e:
            logger.exception(f"[鸣潮·排行卡] 角色总排行渲染失败, 回退原图: {e}")
            return await original(bot, ev, char, rank_type, pages, modal, group_uids)

    _bind(module, "draw_all_rank_card", draw_all_rank_card)


def patch_phantom_rank(module) -> None:
    original = module.draw_phantom_total_rank

    async def draw_phantom_total_rank(bot, ev, char, pages):
        try:
            context = await _build_phantom_rank(module, bot, ev, char, pages)
            if isinstance(context, str):
                return context
            return _render("rank_phantom_total.html", context)
        except Exception as e:
            logger.exception(f"[鸣潮·排行卡] 声骸总排行渲染失败, 回退原图: {e}")
            return await original(bot, ev, char, pages)

    _bind(module, "draw_phantom_total_rank", draw_phantom_total_rank)


PATCHES = {
    "XutheringWavesUID": {
        "wutheringwaves_rank.draw_all_rank_card": patch_all_rank,
        "wutheringwaves_rank.draw_phantom_total_rank_card": patch_phantom_rank,
    }
}
