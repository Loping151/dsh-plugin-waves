"""角色面板 HTML 卡片: 面板/查询/伤害/权重/优化 五个入口接管 PIL 出图。

上游取数流程在此复刻一遍, 只把最后的画布排版换成模板渲染;
任何一步出错都回落原函数, 命令不会因此失败。
"""

import base64
import copy
import importlib
import sys
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rover.logger import logger

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
TEMPLATE_NAME = "char_panel.html"

# 图片编码结果按 key 复用, 素材是静态的
_URI_CACHE: Dict[str, str] = {}
_env = None


# ── 基础工具 ────────────────────────────────────────────────────────────


def _template():
    global _env
    if _env is None:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        _env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    return _env.get_template(TEMPLATE_NAME)


def _color(value: Any, default: str = "#ffffff") -> str:
    """PIL 的颜色写法统一成 CSS。"""
    if value is None:
        return default
    if isinstance(value, (tuple, list)):
        parts = list(value)[:4]
        if len(parts) == 4:
            r, g, b, a = parts
            return f"rgba({int(r)},{int(g)},{int(b)},{round(int(a) / 255, 3)})"
        if len(parts) == 3:
            return "rgb({},{},{})".format(*[int(i) for i in parts])
        return default
    return str(value)


def _encode(img, key: str = "", quality: int = 88) -> str:
    """PIL 图 → data URI(webp), 有 key 时跨请求复用。"""
    if key and key in _URI_CACHE:
        return _URI_CACHE[key]
    buffer = BytesIO()
    img.save(buffer, format="WEBP", quality=quality, method=4)
    uri = "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode()
    if key:
        if len(_URI_CACHE) > 400:
            _URI_CACHE.clear()
        _URI_CACHE[key] = uri
    return uri


def _fit(img, width: int = 0, height: int = 0):
    if width and height and img.size != (width, height):
        from PIL import Image

        return img.resize((width, height), Image.LANCZOS)
    return img


class Icons:
    """同一张图在页面里只出一份 base64, 元素按 class 引用。"""

    def __init__(self):
        self.entries: List[Tuple[str, str]] = []
        self.index: Dict[str, str] = {}

    def put(self, key: str, uri: str) -> str:
        if not uri:
            return ""
        name = self.index.get(key)
        if name is None:
            name = f"i{len(self.entries)}"
            self.index[key] = name
            self.entries.append((name, uri))
        return name

    def has(self, key: str) -> Optional[str]:
        return self.index.get(key)

    def image(self, key: str, img, width: int = 0, height: int = 0, quality: int = 88, cache: bool = True) -> str:
        name = self.index.get(key)
        if name is not None:
            return name
        return self.put(key, _encode(_fit(img, width, height), key if cache else "", quality))


# ── 插件侧模块与素材 ────────────────────────────────────────────────────


def _root(m) -> str:
    return m.__name__.rsplit(".", 2)[0]


def _mod(m, suffix: str):
    return importlib.import_module(f"{_root(m)}.{suffix}")


def _sibling(m, name: str):
    return importlib.import_module(f"{m.__name__.rsplit('.', 1)[0]}.{name}")


def _texture_uri(m, name: str, quality: int = 90) -> str:
    """charinfo 的 texture2d 素材, 返回 data URI。"""
    from PIL import Image

    key = f"tex:{name}"
    if key in _URI_CACHE:
        return _URI_CACHE[key]
    path = m.TEXT_PATH / name
    if not path.exists():
        return ""
    return _encode(Image.open(path).convert("RGBA"), key, quality)


def _texture(m, name: str, icons: Icons, quality: int = 90) -> str:
    cached = icons.has(f"tex:{name}")
    if cached:
        return cached
    return icons.put(f"tex:{name}", _texture_uri(m, name, quality))


def _font_css_url() -> str:
    from rover.config import core_config

    host = core_config.get_config("HOST") or "127.0.0.1"
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    return f"http://{host}:{core_config.get_config('PORT')}/waves/fonts/fonts.css"


async def _background(m) -> str:
    """卡片底图: 沿用 bg3 与自定义背景开关, 模糊参数也跟着配置走。"""
    from PIL import Image

    path = None
    if m.ShowConfig.get_config("CardBg").data:
        custom = Path(m.ShowConfig.get_config("CardBgPath").data)
        if custom.is_file():
            path = custom
    key = f"bg:{path or 'bg3'}"
    if key in _URI_CACHE:
        return _URI_CACHE[key]
    img = Image.open(path).convert("RGBA") if path else m.get_waves_bg(bg="bg3", crop=False)
    scale = 1200 / img.width
    img = img.resize((1200, max(1, int(img.height * scale))), Image.LANCZOS)
    img = await m.get_custom_gaussian_blur(img)
    return _encode(img.convert("RGB"), key, quality=72)


def _footer(m, icons: Icons) -> str:
    image_mod = _mod(m, "utils.image")
    return icons.image("footer", image_mod.get_footer("white"), quality=90)


# ── 头部 / 立绘 / 右侧 ──────────────────────────────────────────────────


def _header_ctx(m, icons: Icons, account_info, avatar, uid, user_pref, locale) -> dict:
    """头部照画布版摆: base_info_bg(35,-30) / 头像(45,20)+光环(55,30) / title_bar(200,15)。"""
    name = account_info.name[:10] if account_info else (uid or "")
    ident = account_info.id if account_info else (uid or "")
    image_mod = _mod(m, "utils.image")
    logo = image_mod.get_small_logo(2)
    return {
        "avatar": icons.image(f"avatar:{ident}", avatar, quality=90, cache=False),
        "avatar_ring": _texture(m, "avatar_ring.png", icons),
        "base_info": _texture(m, "base_info_bg.png", icons),
        "title_bar": _texture(m, "title_bar.png", icons),
        "logo": icons.image("small_logo", logo, quality=90),
        "logo_w": logo.width,
        "logo_h": logo.height,
        "name": name,
        "uid": m.hide_uid(ident, user_pref=user_pref),
        "uid_label": m.t("特征码", locale),
        "level": account_info.level if account_info else "",
        "world_level": account_info.worldLevel if account_info else "",
        "level_label": m.t("联觉等级", locale),
        "world_label": m.t("索拉等阶", locale),
        "show_stats": bool(account_info and account_info.is_full),
    }


async def _pile_ctx(m, icons: Icons, role_detail, locale, uid, char_name) -> dict:
    """立绘区: 立绘按 char_mask 裁形, char_fg 压在上面, 属性/武器型标在原坐标。"""
    pin_token = None
    if uid and char_name and m._force_pile_path.get() is None:
        try:
            pin_key = m.panel_card_pref.pair_pin_key(role_detail.role.roleId, char_name)
            pinned_hash = m.panel_card_pref.get_pin(str(uid), pin_key)
            if pinned_hash:
                pinned_path = m._hash_lookup_in_pair("card", str(role_detail.role.roleId), pinned_hash)
                if pinned_path is not None and pinned_path.is_file():
                    pin_token = m._force_pile_path.set(pinned_path)
        except Exception as e:
            logger.debug(f"[面板] 面板图绑定不可用, 用默认图: {e}")
    try:
        is_custom, role_pile, role_pile_path = await m.get_role_pile_with_path(role_detail.role.roleId, True)
    finally:
        if pin_token is not None:
            m._force_pile_path.reset(pin_token)

    from PIL import Image

    canvas = Image.new("RGBA", (560, 1000))
    pile = m.resize_and_center_image(role_pile, is_custom=is_custom)
    canvas.paste(pile, ((560 - pile.size[0]) // 2, (1000 - pile.size[1]) // 2), pile)

    attribute = await m.get_attribute(role_detail.role.attributeName)
    weapon_type = await m.get_weapon_type(role_detail.role.weaponTypeName)
    role_name = role_detail.role.roleName
    if "漂泊者" in role_name:
        role_name = "漂泊者"

    hash_id = ""
    if is_custom and role_pile_path is not None:
        hash_id = m.compute_hash(role_pile_path.name)

    return {
        "image": icons.image(
            f"pile:{role_pile_path}", canvas, quality=82, cache=role_pile_path is not None
        ),
        "fg": _texture(m, "char_fg.png", icons),
        "attribute": icons.image(f"attr:{role_detail.role.attributeName}", attribute, 50, 50),
        "weapon_type": icons.image(f"wtype:{role_detail.role.weaponTypeName}", weapon_type, 40, 40),
        "name": f"{m.t(role_name, locale)} Lv.{role_detail.role.level}",
        "hash_id": hash_id,
    }


async def _prop_icon(m, icons: Icons, name: str) -> str:
    key = f"prop:{name}"
    cached = icons.has(key)
    if cached:
        return cached
    return icons.image(key, await m.get_attribute_prop(name), 40, 40)


async def _panel_props(m, icons: Icons, calc, role_detail, locale) -> List[dict]:
    """右侧十项面板属性, 末位取治疗与四类技能加成里的最高项。"""
    shuxing = f"{role_detail.role.attributeName}伤害加成"

    def percent(value):
        try:
            return float(str(value).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    candidates = ("治疗效果加成", "普攻伤害加成", "重击伤害加成", "共鸣技能伤害加成", "共鸣解放伤害加成")
    last_slot = max(candidates, key=lambda k: percent(calc.role_card.get(k, "0")))
    items = list(m.card_sort_name[:-1]) + [(last_slot, "0.0%")]

    rows = []
    for index, (name, default) in enumerate(items):
        if name == "属性伤害加成":
            value = calc.role_card.get(shuxing, default)
            icon = await _prop_icon(m, icons, shuxing)
            color, _ = m.get_valid_color(shuxing, value, calc.calc_temp)
            label = m.t(shuxing, locale)
        else:
            value = calc.role_card.get(name, default)
            icon = await _prop_icon(m, icons, name)
            color, _ = m.get_valid_color(name, value, calc.calc_temp)
            label = m.t(name.replace("破坏", "") if index < 4 else name, locale)
        rows.append({"icon": icon, "name": label, "value": str(value), "color": _color(color)})
    return rows


async def _weapon_ctx(m, icons: Icons, role_detail, locale) -> dict:
    weapon_data = role_detail.weaponData
    weapon = weapon_data.weapon
    branch = role_detail.get_skill_branch()

    icon = await m.get_square_weapon(weapon.weaponId)
    icon = m.crop_center_img(icon, 110, 110)
    icon_bg = m.get_weapon_icon_bg(weapon.weaponStarLevel, m.TEXT_PATH)
    icon_bg.paste(icon, (10, 20), icon)

    detail = m.get_weapon_detail(weapon.weaponId, weapon_data.level, weapon_data.breach, weapon_data.resonLevel)
    stats = []
    for item in detail.stats[:2]:
        stats.append(
            {
                "icon": await _prop_icon(m, icons, item["name"]),
                "name": m.t(item["name"], locale, partial=True),
                "value": str(item["value"]),
            }
        )

    branch_icon = ""
    if branch:
        skill_img = await m.get_attribute_skill(branch.branchName, locale)
        branch_icon = icons.image(f"branch:{branch.branchName}", skill_img, 100, 100)

    return {
        "bg": _texture(m, "weapon_branch_bg.png" if branch else "weapon_bg.png", icons),
        "icon": icons.image(f"weapon:{weapon.weaponId}", icon_bg, quality=90),
        "name": m.t(weapon.weaponName, locale),
        "level": f"Lv.{weapon_data.level}/90",
        "reson": m._weapon_reson_text(weapon_data.resonLevel, locale),
        "reson_color": _color(m.WEAPON_RESONLEVEL_COLOR[weapon_data.resonLevel] + (204,)),
        "breach": m.get_breach(weapon_data.breach, weapon_data.level) or 0,
        "promote": _texture(m, "promote_icon.png", icons),
        "stats": stats,
        "branch_icon": branch_icon,
        "has_branch": bool(branch),
        "cmd": f"{m.PREFIX}{m.t(weapon.weaponName, locale)}图鉴",
    }


async def _skills_ctx(m, icons: Icons, role_detail, locale) -> dict:
    items = []
    for skill in role_detail.get_skill_list():
        if skill.skill.type in ["延奏技能", "谐度破坏"]:
            continue
        image = await m.get_skill_img(role_detail.role.roleId, skill.skill.name, skill.skill.iconUrl)
        items.append(
            {
                "icon": icons.image(f"skill:{role_detail.role.roleId}:{skill.skill.name}", image, 70, 70),
                "type": m.t(skill.skill.type, locale),
                "level": f"Lv.{skill.level}",
            }
        )
    char_name = m.t(role_detail.role.roleName, locale)
    return {
        "bar": _texture(m, "skill_bar.png", icons),
        "bg": _texture(m, "skill_bg.png", icons),
        "entries": items,
        "cmd": f"{m.PREFIX}{char_name}技能",
    }


async def _chains_ctx(m, icons: Icons, role_detail, locale) -> dict:
    """共鸣链: 底框与链图按属性色染色/压暗后整体成图, 名字仍是文字。"""
    from PIL import Image, ImageEnhance

    shuxing_color = m.WAVES_SHUXING_MAP[role_detail.role.attributeName]
    items = []
    for chain in role_detail.chainList:
        frame = Image.open(m.TEXT_PATH / "mz_bg.png")
        image = await m.get_chain_img(role_detail.role.roleId, chain.order, chain.iconUrl)
        image = image.resize((100, 100))
        frame.paste(image, (95, 75), image)
        temp = Image.new("RGBA", frame.size)
        temp.alpha_composite(frame, dest=(0, 0))
        if chain.unlocked:
            temp = await m.change_color(temp, shuxing_color)
        else:
            temp = ImageEnhance.Brightness(temp).enhance(0.3)
        name = m.re.sub(r'[",，]+', "", chain.name) if chain.name else ""
        name = m.t(name, locale, partial=True)
        items.append(
            {
                "image": icons.image(
                    f"chain:{role_detail.role.roleId}:{chain.order}:{int(chain.unlocked)}", temp, quality=88
                ),
                "name": name,
                "small": len(name) >= 8,
            }
        )
    char_name = m.t(role_detail.role.roleName, locale)
    return {"items": items, "cmd": f"{m.PREFIX}{char_name}共鸣链"}


# ── 声骸区 ──────────────────────────────────────────────────────────────


async def _stat_grid(m, icons: Icons, calc, card, role_detail, locale) -> List[List[dict]]:
    """声骸词条统计: 三列四行。"""
    shuxing = f"{role_detail.role.attributeName}伤害加成"
    groups = []
    for group in m.ph_sort_name:
        rows = []
        for index, (name, default) in enumerate(group):
            key = shuxing if name == "属性伤害加成" else name
            value = card.get(key, default)
            color, _ = m.get_valid_color(key, value, calc.calc_temp)
            rows.append(
                {
                    "icon": await _prop_icon(m, icons, key),
                    "name": m.t(key, locale),
                    "value": str(value),
                    "color": _color(color),
                    "odd": index % 2 == 1,
                }
            )
        groups.append(rows)
    return groups


def _grade_ctx(m, icons: Icons, grade: str, top: str, value: str, bottom: str) -> dict:
    return {
        "bg": _texture(m, f"sh_score_bg_{grade}.png", icons, quality=84),
        "fg": _texture(m, f"sh_score_{grade}.png", icons, quality=88),
        "top": top,
        "value": value,
        "bottom": bottom,
    }


def _grade_empty(m, icons: Icons, locale) -> dict:
    return {
        "empty": True,
        "bg": _texture(m, "abs.png", icons, quality=84),
        "top": m.t("暂无", locale),
        "value": f"- {m.t('分', locale)}",
    }


async def _echo_card(m, icons: Icons, phantom, calc, role_detail, locale, with_entry: bool) -> Tuple[dict, float]:
    """单件声骸卡: with_entry 时每条词条右侧再挂单条得分(权重图)。"""
    props = phantom.get_props()
    score, grade = m.calc_phantom_score(role_detail.role.roleId, props, phantom.cost, calc.calc_temp)
    if score > 49.95:
        score = 50.0

    icon = await m.get_phantom_img(phantom.phantomProp.phantomId, phantom.phantomProp.iconUrl)
    fetter = await m.get_attribute_effect(phantom.fetterDetail.name)
    icon.alpha_composite(fetter.resize((50, 50)), dest=(205, 0))

    name = m.t(phantom.phantomProp.name, locale).replace("·", " ").replace("（", " ").replace("）", "")
    short_name = name if locale == "en" else m.get_short_name(phantom.phantomProp.phantomId, name)

    rows = []
    for index, prop in enumerate(props):
        name_color = value_color = "white"
        if index > 1:
            name_color, value_color = m.get_valid_color(prop.attributeName, prop.attributeValue, calc.calc_temp)
        row = {
            "icon": await _prop_icon(m, icons, prop.attributeName),
            "name": m.t(prop.attributeName, locale, partial=True)[: 12 if locale == "en" else 6],
            "value": str(prop.attributeValue),
            "name_color": _color(name_color),
            "value_color": _color(value_color),
        }
        if with_entry:
            _, final_score = m.calc_phantom_entry(
                index, prop, phantom.cost, calc.calc_temp, role_detail.role.attributeName or ""
            )
            row["entry"] = f"{final_score}{m.t('分', locale)}"
            row["entry_color"] = _color(m.WAVES_FREEZING if final_score > 0 else m.WAVES_MOONLIT)
        rows.append(row)

    card = {
        "bg": _texture(m, "sh_bg.png", icons),
        "title": _texture(m, f"sh_title_{grade}.png", icons, quality=86),
        "icon": icons.image(f"phantom:{phantom.phantomProp.phantomId}:{phantom.fetterDetail.name}", icon, 100, 100),
        "name": short_name,
        "level": f"Lv.{phantom.level}",
        "score": f"{score}{m.t('分', locale)}",
        "cost": phantom.cost,
        "promote": _texture(m, "promote_icon.png", icons),
        "props": rows,
        "wide_score": locale == "en",
        # 单件声骸跳它自己的图鉴, 比跳仓库更有意义
        "cmd": f"{m.PREFIX}{m.t(phantom.phantomProp.name, locale)}图鉴"
        if getattr(phantom.phantomProp, "name", "")
        else "",
    }
    if with_entry:
        max_score, _ = m.get_max_score(phantom.cost, calc.calc_temp)
        card["max_line"] = f"C{phantom.cost}MAX:{max_score}{m.t('分', locale)}"
    return card, score


async def _optimal_card(m, icons: Icons, slot, phantom, calc, locale) -> dict:
    """培养目标声骸卡: 图标沿用实际声骸, 词条换成最优解。"""
    icon_cls = ""
    name = m.t("推荐声骸", locale)
    if phantom and phantom.phantomProp:
        image = await m.get_phantom_img(phantom.phantomProp.phantomId, phantom.phantomProp.iconUrl)
        fetter = await m.get_attribute_effect(phantom.fetterDetail.name)
        image.alpha_composite(fetter.resize((50, 50)), dest=(205, 0))
        icon_cls = icons.image(
            f"phantom:{phantom.phantomProp.phantomId}:{phantom.fetterDetail.name}", image, 100, 100
        )
        raw = m.t(phantom.phantomProp.name, locale).replace("·", " ").replace("（", " ").replace("）", "")
        name = raw if locale == "en" else m.get_short_name(phantom.phantomProp.phantomId, raw)

    display = [
        (slot.main1_name, f"{slot.main1_value_pct:.1f}%"),
        (slot.main2_name, m._fmt_opt_val(slot.main2_name, slot.main2_value_flat)),
    ]
    for sub_name, sub_value in list(slot.subs)[:5]:
        display.append((sub_name, m._fmt_opt_val(sub_name, float(str(sub_value).replace("%", "")))))

    rows = []
    for index_prop, (prop_name, prop_value) in enumerate(display[:7]):
        color = "white"
        if index_prop > 1:
            color, _ = m.get_valid_color(prop_name.rstrip("%"), prop_value, calc.calc_temp)
        rows.append(
            {
                "icon": await _prop_icon(m, icons, prop_name),
                "name": m.t(prop_name.rstrip("%"), locale, partial=True)[: 12 if locale == "en" else 6],
                "value": prop_value,
                "name_color": _color(color),
                "value_color": _color(color),
            }
        )

    return {
        "bg": _texture(m, "sh_bg.png", icons),
        "title": _texture(m, "sh_title_s.png", icons, quality=86),
        "icon": icon_cls,
        "name": name,
        "badge": f"Lv.25 {m.t('模板声骸', locale)}",
        "cost": slot.cost,
        "promote": _texture(m, "promote_icon.png", icons),
        "props": rows,
    }


# ── 计算 ────────────────────────────────────────────────────────────────


def _prepare_calc(m, role_detail, enemy_detail=None, is_limit=False):
    """与 ph_card_draw 同一套预处理, 只取数不出图。"""
    calc_module = _mod(m, "utils.calc")
    modal = _mod(m, "utils.damage.modal")
    _sibling(m, "role_info_change").ensure_default_modal(role_detail)

    calc = calc_module.WuWaCalc(role_detail, enemy_detail, is_limit=is_limit)
    if role_detail.phantomData and role_detail.phantomData.equipPhantomList:
        calc.phantom_pre = calc.prepare_phantom()
        calc.phantom_card = calc.enhance_summation_phantom_value(calc.phantom_pre)
        calc.calc_temp = m.get_calc_map(
            calc.phantom_card,
            role_detail.role.roleName,
            role_detail.role.roleId,
            modal.get_role_modal(role_detail),
        )
    return calc


def _damage_rows(m, calc, role_detail, damage_list, locale) -> List[dict]:
    rows = []
    for damage in damage_list:
        title = damage["title"]
        attribute = copy.deepcopy(calc.damageAttribute)
        setattr(attribute, "_log_title", title)
        crit, expected = damage["func"](attribute, role_detail)
        # 数值为 0 的条目(如命座未解锁的技能)不出行, 与画布版一致
        if (not crit or str(crit) == "0") and str(expected) == "0":
            continue
        rows.append(
            {
                "name": m.t(title, locale, partial=True),
                "crit": str(crit) if crit and expected else "",
                "expected": str(expected),
                "single": not (crit and expected),
            }
        )
    return rows


def _rank_rows(m, one_rank, locale) -> List[dict]:
    rows = []
    labels = [("评分排名", "估计评分排名"), ("伤害排名", "估计伤害排名")]
    for index, item in enumerate(one_rank.data[:2]):
        exact, estimated = labels[index]
        rows.append(
            {
                "name": m.t(exact if item.rank > 0 else estimated, locale),
                "value": f"{item.rank}" if item.rank > 0 else str(item.inter_rank),
                "single": True,
                "gold": True,
            }
        )
    return rows


# ── 面板 / 查询 / 伤害 ──────────────────────────────────────────────────


async def _render_detail(
    m, ev, uid, char, user_id, waves_id, is_force_avatar, change_list_regex, is_limit_query, show_score
):
    locale = await m.WavesLangSettings.get_lang(ev.user_id)
    user_pref = await m.get_hide_uid_pref(waves_id or uid, user_id, ev.bot_id)
    char, damage_id = m.parse_text_and_number(char)

    char_name = m.alias_to_char_name(char)
    char_id = m.char_name_to_char_id(char)
    if char_name == "漂泊者" and not waves_id:
        rover_canon = await m._rawdata_rover_canon(uid)
        if rover_canon:
            char_id = rover_canon
    if not char_id or len(char_id) != 4 or not char_id.isdigit():
        return "未找到指定角色, 请检查输入是否正确！"

    damage_detail = m.DamageDetailRegister.find_class(char_id)
    if damage_detail and not m.WutheringWavesConfig.get_config("WavesToken").data:
        damage_detail = None

    is_draw = False if damage_id and damage_detail else True
    # 单条查询的编号跟随列表显示顺序(0 值条目不占编号), 得等面板数据齐了才能算, 推迟到下面选
    if is_draw and damage_id and not damage_detail:
        return f"[鸣潮] 角色【{char_name}】暂不支持伤害计算！\n"

    ck = ""
    if waves_id:
        uid = waves_id

    if not is_limit_query:
        info, ck, _ = await m.base_info_cache.load_account_context(
            uid, user_id, ev.bot_id, force_ck=bool(waves_id)
        )
        if isinstance(info, str):
            if not ck:
                return info
            account_info = None
        else:
            account_info = info
        force_resource_id = None
    else:
        account_info = m.AccountBaseInfo.model_validate(
            {"name": "库洛交个朋友", "id": uid, "level": 100, "worldLevel": 10, "creatTime": 1739375719}
        )
        force_resource_id = char_id

    avatar, role_detail = await m.get_role_need(
        ev, char_id, ck, uid, char_name, waves_id, is_force_avatar, force_resource_id, is_limit_query,
        change_list_regex,
    )
    if isinstance(role_detail, str):
        return role_detail

    change_command = ""
    enemy_detail = m.EnemyDetailData()
    if change_list_regex:
        backup = copy.deepcopy(role_detail)
        try:
            role_detail, change_command = await m.change_role_detail(
                uid, ck, role_detail, enemy_detail, change_list_regex, user_id=str(user_id), bot_id=ev.bot_id
            )
            if change_command and change_command.startswith("[鸣潮]"):
                return change_command
        except Exception as e:
            logger.warning(f"[面板] 角色数据转换失败: {e}")
            role_detail = backup

    phantom_dirty = _sibling(m, "role_info_change").is_phantom_dirty(change_command)
    calc = _prepare_calc(m, role_detail, enemy_detail, is_limit_query or phantom_dirty)
    calc.role_card = calc.enhance_summation_card_value(calc.phantom_card)

    has_phantom = bool(role_detail.phantomData and role_detail.phantomData.equipPhantomList)
    icons = Icons()

    # 单条伤害视图: 只出该类型的暴击/期望与 buff 列表
    single_damage = None
    if not is_draw and damage_detail and has_phantom:
        calc.damageAttribute = calc.card_sort_map_to_attribute(calc.role_card)
        shown = 0
        damage_calc = None
        attribute = None
        for item in damage_detail:
            probe = copy.deepcopy(calc.damageAttribute)
            setattr(probe, "_log_title", item["title"])
            crit, expected = item["func"](probe, role_detail)
            if (not crit or str(crit) == "0") and str(expected) == "0":
                continue
            shown += 1
            if shown == int(damage_id):
                damage_calc, attribute = item, probe
                break
        if damage_calc is None or attribute is None:
            return f"[鸣潮] 角色【{char_name}】未找到该伤害类型[{damage_id}], 请先检查输入是否正确！\n"
        single_damage = {
            "row": {
                "name": m.t(damage_calc["title"], locale, partial=True),
                "crit": str(crit) if crit and expected else "",
                "expected": str(expected),
                "single": not (crit and expected),
            },
            "buffs": [
                {"name": m.t(effect.element_msg, locale, partial=True), "value": str(effect.element_value)}
                for effect in attribute.effect
            ],
        }

    score_report = None
    score_detail = m.ScoreDetailRegister.find_class(char_id)
    if score_detail and show_score and not is_limit_query and has_phantom:
        try:
            score_calc = score_detail[0] if isinstance(score_detail, list) else score_detail
            setattr(calc, "_score_title", score_calc.get("title", f"综合评分-{char_name}"))
            score_report = score_calc["func"](calc, role_detail)
        except Exception as e:
            logger.warning(f"[面板] {char_name} 综合评分失败: {e}")

    # 声骸卡与总分
    cards = []
    phantom_score = 0.0
    if has_phantom:
        for phantom in role_detail.phantomData.equipPhantomList:
            if not (phantom and phantom.phantomProp):
                continue
            card, score = await _echo_card(m, icons, phantom, calc, role_detail, locale, with_entry=False)
            cards.append(card)
            phantom_score += score
        phantom_score = round(phantom_score, 2)
        if phantom_score > 249.9:
            phantom_score = 250.0

    # 伤害排行与评分排行
    rank_rows: List[dict] = []
    if not is_limit_query:
        rank_expected = None
        rank_detail = m.DamageRankRegister.find_class(char_id)
        if rank_detail and has_phantom:
            try:
                calc.damageAttribute = calc.card_sort_map_to_attribute(calc.role_card)
                _, expected_str = rank_detail["func"](calc.damageAttribute, role_detail)
                rank_expected = m.comma_separated_number(expected_str)
            except Exception as e:
                logger.warning(f"[面板] 排行伤害计算失败: {e}")
        one_rank = await m.get_one_rank(
            m.OneRankRequest(
                char_id=int(char_id),
                waves_id=uid,
                phantom_score=phantom_score if phantom_score > 0 else None,
                expected_damage=rank_expected,
            )
        )
        if one_rank and len(one_rank.data) > 0:
            rank_rows = _rank_rows(m, one_rank, locale)

    if has_phantom and phantom_score > 0:
        grade = m.get_total_score_bg(role_detail.role.roleName, phantom_score, calc.calc_temp)
        grade_ctx = _grade_ctx(
            m, icons, grade, m.t("声骸评级", locale),
            f"{phantom_score:.2f}{m.t('分', locale)}", m.t("声骸评分", locale),
        )
    elif has_phantom:
        grade_ctx = _grade_empty(m, icons, locale)
    else:
        grade_ctx = None

    damage_rows = []
    if is_draw and damage_detail and has_phantom:
        calc.damageAttribute = calc.card_sort_map_to_attribute(calc.role_card)
        damage_rows = _damage_rows(m, calc, role_detail, damage_detail, locale)

    if not has_phantom:
        echo_height = 120
    elif is_draw:
        echo_height = 1540
    else:
        echo_height = 370

    ctx = await _base_ctx(m, icons, account_info, avatar, role_detail, calc, locale, uid, user_pref, char_name)
    ctx["score_band"] = _score_band(m, icons, score_report, locale, f"{m.PREFIX}{char_name}优化")
    ctx["echo"] = {
        "banner": _texture(m, "banner3.png", icons),
        "bar_even": _texture(m, "ph_0.png", icons),
        "bar_odd": _texture(m, "ph_1.png", icons),
        "stat_groups": await _stat_grid(m, icons, calc, calc.phantom_card, role_detail, locale) if has_phantom else [],
        "template_label": m.t("评分模板", locale),
        "template_name": m.t(calc.calc_temp["name"], locale, partial=True) if has_phantom else "",
        "change_command": change_command,
        "grade": grade_ctx if is_draw else None,
        "cards": cards if is_draw else [],
        "card_top": 370,
        "card_gap": 600,
        "card_height": 550,
        "height": echo_height,
        "card_cmd": f"{m.PREFIX}声骸",
    }
    # 排名行随伤害总表一起出; 单伤害视图与无伤害数据时都不带总表
    if damage_rows:
        for index, row in enumerate(damage_rows):
            row["cmd"] = f"{m.PREFIX}{char_name}伤害{index + 1}"
        ctx["damage"] = {
            "bar_even": _texture(m, "damage_bar2.png", icons),
            "bar_odd": _texture(m, "damage_bar1.png", icons),
            "head": {
                "name": m.t("伤害类型", locale),
                "crit": m.t("暴击伤害", locale),
                "expected": m.t("期望伤害", locale),
            },
            "rows": damage_rows + rank_rows,
        }
    if single_damage:
        ctx["single_damage"] = {
            "bar_even": _texture(m, "damage_bar2.png", icons),
            "bar_odd": _texture(m, "damage_bar1.png", icons),
            "head": {
                "name": m.t("伤害类型", locale),
                "crit": m.t("暴击伤害", locale),
                "expected": m.t("期望伤害", locale),
            },
            "buff_title": m.t("buff列表", locale),
            "row": single_damage["row"],
            "buffs": single_damage["buffs"],
        }

    html = await _render(ctx, char_name)

    # 仅本人查询才写状态与建议, 与上游一致
    is_self = not waves_id and user_id == ev.user_id
    if not is_limit_query and not change_list_regex and is_self:
        try:
            char_state = await m.record_view(uid, char_id)
            if char_state is not None and score_report is not None and score_report.partial_max:
                grade = m.get_panel_score_grade(score_report.score)
                if grade in ("b", "c") and score_report.score > 40 and char_state.get("advice_dirty", True):
                    advice = f"[鸣潮] {char_name} 建议提升词条方向: {score_report.partial_max[0]}"
                    if await m.record_advice_sent(uid, char_id, advice):
                        m.queue_pending_advice(ev, advice)
        except Exception as e:
            logger.warning(f"[面板] 角色状态记录失败: {e}")
    return html


# ── 权重 ────────────────────────────────────────────────────────────────


async def _render_weight(m, ev, uid, char, user_id, waves_id, is_limit_query):
    locale = await m.WavesLangSettings.get_lang(ev.user_id)
    user_pref = await m.get_hide_uid_pref(waves_id or uid, user_id, ev.bot_id)
    char, _damage_id = m.parse_text_and_number(char)

    char_id = m.char_name_to_char_id(char)
    if not char_id or len(char_id) != 4 or not char_id.isdigit():
        return "未找到指定角色, 请检查输入是否正确！"
    char_name = m.alias_to_char_name(char)

    ck = ""
    if waves_id:
        uid = waves_id

    if not is_limit_query:
        info, ck, _ = await m.base_info_cache.load_account_context(
            uid, user_id, ev.bot_id, force_ck=bool(waves_id)
        )
        if isinstance(info, str):
            if not ck:
                return info
            account_info = None
        else:
            account_info = info
        force_resource_id = None
    else:
        account_info = m.AccountBaseInfo.model_validate(
            {"name": "库洛交个朋友", "id": uid, "level": 100, "worldLevel": 10, "creatTime": 1739375719}
        )
        force_resource_id = char_id

    avatar, role_detail = await m.get_role_need(
        ev, char_id, ck, uid, char_name, waves_id,
        is_force_avatar=False, force_resource_id=force_resource_id, is_limit_query=is_limit_query,
    )
    if isinstance(role_detail, str):
        return role_detail

    modal = _mod(m, "utils.damage.modal")
    weight_modals = modal.get_modal_options(int(role_detail.role.roleId))

    calc = _prepare_calc(m, role_detail, None, is_limit_query)
    icons = Icons()
    has_phantom = bool(role_detail.phantomData and role_detail.phantomData.equipPhantomList)
    if is_limit_query and has_phantom:
        calc.role_card = calc.enhance_summation_card_value(calc.phantom_card)

    cards = []
    phantom_score = 0.0
    tables = []
    stat_groups = []
    if has_phantom:
        for phantom in role_detail.phantomData.equipPhantomList:
            if not (phantom and phantom.phantomProp):
                continue
            card, score = await _echo_card(m, icons, phantom, calc, role_detail, locale, with_entry=True)
            cards.append(card)
            phantom_score += score
        phantom_score = round(phantom_score, 2)
        if phantom_score > 249.9:
            phantom_score = 250.0

        panel_card = calc.role_card if is_limit_query and getattr(calc, "role_card", None) else calc.phantom_card
        stat_groups = await _stat_grid(m, icons, calc, panel_card, role_detail, locale)

        shuxing = f"{role_detail.role.attributeName}伤害加成"
        if weight_modals:
            weight_temps = [
                (
                    m.get_calc_map(
                        calc.phantom_card, role_detail.role.roleName, role_detail.role.roleId, option["key"]
                    ),
                    option["name"],
                )
                for option in weight_modals
            ]
        else:
            weight_temps = [(calc.calc_temp, "")]
        for calc_temp, modal_name in weight_temps:
            tables.append(_weight_table(m, calc_temp, shuxing, role_detail.role.roleName, modal_name))

    if has_phantom and phantom_score > 0:
        grade = m.get_total_score_bg(role_detail.role.roleName, phantom_score, calc.calc_temp)
        grade_ctx = _grade_ctx(
            m, icons, grade, m.t("声骸评级", locale),
            f"{phantom_score:.2f}{m.t('分', locale)}", m.t("声骸评分", locale),
        )
    elif has_phantom:
        grade_ctx = _grade_empty(m, icons, locale)
    else:
        grade_ctx = None

    ctx = await _base_ctx(
        m, icons, account_info, avatar, role_detail, calc, locale, uid, user_pref, char_name, light=True
    )
    ctx["stat_column"] = {
        "bar_even": _texture(m, "ph_0.png", icons),
        "bar_odd": _texture(m, "ph_1.png", icons),
        "groups": stat_groups,
    }
    ctx["echo"] = {
        "banner": _texture(m, "banner3.png", icons),
        "bar_even": _texture(m, "ph_0.png", icons),
        "bar_odd": _texture(m, "ph_1.png", icons),
        "stat_groups": [],
        "template_label": m.t("评分模板", locale),
        "template_name": m.t(calc.calc_temp["name"], locale, partial=True) if has_phantom else "",
        "change_command": "",
        "grade": grade_ctx,
        "cards": cards,
        "card_top": 120,
        "card_gap": 630,
        "card_height": 620,
        "height": 1390 if cards else 120,
        "card_cmd": f"{m.PREFIX}声骸",
    }
    ctx["weight_tables"] = tables
    return await _render(ctx, char_name)


def _weight_table(m, calc_temp, shuxing, role_name, modal_name) -> dict:
    rows = m._build_weight_rows(calc_temp, shuxing)
    table = []
    for index, row in enumerate(rows):
        cells = []
        for column, cell in enumerate(row.split(",")):
            color = "#ffffff"
            if index > 0 and column == 0:
                name_color, _ = m.get_valid_color(cell, "", calc_temp)
                color = _color(name_color)
            cells.append({"text": cell, "color": color})
        table.append({"cells": cells, "head": index == 0, "odd": index % 2 == 1})

    grade = calc_temp["total_grade"]
    title = f"#{role_name}词条权重表"
    if modal_name:
        title = f"#{role_name}（{modal_name}）词条权重表"
    return {
        "title": title,
        "rows": table,
        "notes": [
            "词条得分：词条数值 * 当前词条权重 / 声骸未对齐最高分 * 对齐分数(50)",
            f"声骸评分标准：SSS≥{grade[-1] * 250:.2f}分/ SS≥{grade[-2] * 250:.2f}分／S≥{grade[-3] * 250:.2f}分 "
            f"/ A≥{grade[-4] * 250:.2f}分 / B≥{grade[-5] * 250:.2f}分 / C",
            "当前角色评分标准仅供参考与娱乐，不代表任何官方或权威的评价。",
        ],
    }


# ── 优化 ────────────────────────────────────────────────────────────────


async def _render_optimize(m, ev, uid, char, user_id, waves_id, change_list_regex, is_limit_query):
    locale = await m.WavesLangSettings.get_lang(ev.user_id)
    user_pref = await m.get_hide_uid_pref(waves_id or uid, user_id, ev.bot_id)

    char_id = m.char_name_to_char_id(char)
    if not char_id or len(char_id) != 4 or not char_id.isdigit():
        return "未找到指定角色, 请检查输入是否正确！"
    char_name = m.alias_to_char_name(char)

    score_detail = m.ScoreDetailRegister.find_class(char_id)
    if not score_detail:
        return f"[鸣潮] {char_name} 暂无综合评分"

    if waves_id:
        uid = waves_id

    ck = ""
    force_resource_id = None
    if not is_limit_query:
        info, ck, _ = await m.base_info_cache.load_account_context(
            uid, user_id, ev.bot_id, force_ck=bool(waves_id)
        )
        if isinstance(info, str):
            if not ck:
                return info
            account_info = None
        else:
            account_info = info
    else:
        account_info = m.AccountBaseInfo.model_validate(
            {"name": "库洛交个朋友", "id": uid, "level": 100, "worldLevel": 10, "creatTime": 1739375719}
        )
        force_resource_id = char_id

    avatar, role_detail = await m.get_role_need(
        ev, char_id, ck, uid, char_name, waves_id,
        force_resource_id=force_resource_id, is_limit_query=is_limit_query,
        change_list_regex=change_list_regex,
    )
    if isinstance(role_detail, str):
        return role_detail

    enemy_detail = m.EnemyDetailData()
    change_command = ""
    if change_list_regex:
        backup = copy.deepcopy(role_detail)
        try:
            role_detail, change_command = await m.change_role_detail(
                uid, ck, role_detail, enemy_detail, change_list_regex, user_id=str(user_id), bot_id=ev.bot_id
            )
            if change_command and change_command.startswith("[鸣潮]"):
                return change_command
        except Exception as e:
            logger.warning(f"[面板] 角色数据转换失败: {e}")
            role_detail = backup

    phantom_data = role_detail.phantomData
    equip_list = phantom_data.equipPhantomList if phantom_data else None
    if not equip_list or sum(1 for p in equip_list if p and getattr(p, "phantomProp", None)) < 5:
        return f"[鸣潮] {char_name} 声骸件数不足, 暂无优化建议"

    phantom_dirty = _sibling(m, "role_info_change").is_phantom_dirty(change_command)
    calc = _prepare_calc(m, role_detail, enemy_detail, phantom_dirty)
    calc.role_card = calc.enhance_summation_card_value(calc.phantom_card)

    score_report = None
    try:
        score_calc = score_detail[0] if isinstance(score_detail, list) else score_detail
        setattr(calc, "_score_title", score_calc.get("title", f"综合评分-{char_name}"))
        score_report = score_calc["func"](calc, role_detail)
    except Exception as e:
        logger.warning(f"[面板] {char_name} 优化计算失败: {e}")
    if score_report is None:
        return f"[鸣潮] {char_name} 优化计算失败，请检查服务器连接状态"

    icons = Icons()
    partials = sorted(
        [(name, float(value)) for name, value in (getattr(score_report, "partials", None) or {}).items()
         if abs(float(value)) > 1e-9],
        key=lambda item: item[1],
        reverse=True,
    )

    def localized(name: str) -> str:
        base = m.t(name.rstrip("%"), locale, partial=True)
        return f"{base}%" if name.endswith("%") else base

    is_self = not waves_id and user_id == ev.user_id
    score_rows = []
    partial_max = getattr(score_report, "partial_max", None)
    if partial_max and is_self:
        score_rows.append((m.t("建议提升词条方向", locale), localized(partial_max[0])))
    if partials:
        for index in range(0, len(partials), 3):
            group = partials[index:index + 3]
            label = m.t("词条提升收益情况", locale) if index == 0 else ""
            text = "    ".join(f"{localized(name)} {value:+.1f}" for name, value in group)
            score_rows.append((label, text))
    else:
        score_rows.append((m.t("词条提升收益情况", locale), m.t("暂无", locale)))
    score_rows.extend(
        (m.t("备注", locale), m.t(str(note), locale, partial=True))
        for note in (getattr(score_report, "notes", None) or [])
    )

    rule_lines = []
    for line in m._SCORE_RULE_LINES:
        rule_lines.extend(m._wrap_plain(m.t(line, locale), 46))

    cards = []
    for index, slot in enumerate((getattr(score_report, "best_loadout", None) or [])[:5]):
        phantom = equip_list[index] if index < len(equip_list) else None
        cards.append(await _optimal_card(m, icons, slot, phantom, calc, locale))

    ctx = await _base_ctx(
        m, icons, account_info, avatar, role_detail, calc, locale, uid, user_pref, char_name,
        diff_props=await _diff_props(m, icons, calc, score_report, role_detail, locale),
    )
    ctx["score_band"] = _score_band(m, icons, score_report, locale, f"{m.PREFIX}{char_name}面板")
    ctx["echo"] = {
        "banner": _texture(m, "banner3.png", icons),
        "bar_even": _texture(m, "ph_0.png", icons),
        "bar_odd": _texture(m, "ph_1.png", icons),
        "stat_groups": [],
        "title_bar": _texture(m, "damage_bar1.png", icons),
        "title": m.t("声骸培养目标参考", locale),
        "template_label": "",
        "template_name": "",
        "change_command": change_command,
        "grade": _grade_ctx(
            m, icons, "sss", m.t("综合评级", locale), f"150.00{m.t('分', locale)}", m.t("综合评分", locale)
        ),
        "cards": cards,
        "card_top": 180,
        "card_gap": 600,
        "card_height": 550,
        "height": 1350,
        "card_cmd": f"{m.PREFIX}声骸",
    }
    ctx["optimize"] = {
        "bar_even": _texture(m, "damage_bar2.png", icons),
        "bar_odd": _texture(m, "damage_bar1.png", icons),
        "title": f"{m.t(char_name, locale)} {m.t('综合评分', locale)} {score_report.score:.1f} / 150",
        "rows": [{"label": left, "text": right} for left, right in score_rows],
        "rule_title": m.t(m._SCORE_RULE_TITLE, locale, partial=True),
        "rule_hint": f"{m.t('评分细则请发送', locale)} {m.PREFIX}综合评分说明",
        "rule_lines": rule_lines,
    }
    return await _render(ctx, char_name)


async def _diff_props(m, icons: Icons, calc, score_report, role_detail, locale) -> List[dict]:
    """优化图右侧: 当前值 → 最优值, 按提升幅度排序取前八。"""
    shuxing = f"{role_detail.role.attributeName}伤害加成"
    best_card = getattr(score_report, "best_card", None) or {}

    def percent(value):
        try:
            return float(str(value).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    candidates = ("治疗效果加成", "普攻伤害加成", "重击伤害加成", "共鸣技能伤害加成", "共鸣解放伤害加成")
    last_slot = max(candidates, key=lambda k: percent(calc.role_card.get(k, "0")))
    skip = {"谐度破坏增幅", "偏谐值累积效率"}
    items = [(name, default) for name, default in m.card_sort_name[:-1] if name not in skip]
    items.append((last_slot, "0.0%"))

    rows = []
    for name, default in items:
        key = shuxing if name == "属性伤害加成" else name
        label = m.t(key, locale)
        value = calc.role_card.get(key, default)
        best = best_card.get(key, value)
        try:
            delta = float(str(best).replace("%", "")) - float(str(value).replace("%", ""))
        except (TypeError, ValueError):
            delta = 0.0
        is_percent = "%" in str(value) or "%" in str(best)
        if abs(delta) < 1e-6:
            delta_text = ""
        elif is_percent:
            delta_text = f"{delta:+.1f}%"
        else:
            delta_text = f"{int(round(delta)):+d}"
        rows.append(
            {
                "icon": await _prop_icon(m, icons, key),
                "name": label,
                "value": f"{value} → {best}",
                "delta": delta_text,
                "delta_color": _color(m.SPECIAL_GOLD if delta > 0 else m.GREY),
                "order": delta,
            }
        )
    rows.sort(key=lambda row: row["order"], reverse=True)
    return rows[:8]


# ── 公共上下文与渲染 ────────────────────────────────────────────────────


def _score_band(m, icons: Icons, score_report, locale, cmd: str = "") -> Optional[dict]:
    if score_report is None:
        return None
    grade = m.get_panel_score_grade(score_report.score)
    return {
        "icon": _texture(m, f"panel_score_{grade}.png", icons),
        "value": f"{score_report.score:.2f}",
        "label": m.t("综合评分", locale),
        "cmd": cmd,
    }


async def _base_ctx(
    m, icons: Icons, account_info, avatar, role_detail, calc, locale, uid, user_pref, char_name,
    light: bool = False, diff_props: Optional[List[dict]] = None,
) -> dict:
    """头部/立绘/右侧/技能/共鸣链。light=True 时只出头部与立绘(权重图)。"""
    ctx = {
        "font_css_url": _font_css_url(),
        "bg": await _background(m),
        "mask_uri": _texture_uri(m, "char_mask.png"),
        "footer": _footer(m, icons),
        "header": _header_ctx(m, icons, account_info, avatar, uid, user_pref, locale),
        "pile": await _pile_ctx(m, icons, role_detail, locale, uid, char_name),
        "icons": icons,
        "score_band": None,
        "right": None,
        "skills": None,
        "chains": None,
        "echo": None,
        "damage": None,
        "single_damage": None,
        "stat_column": None,
        "weight_tables": None,
        "optimize": None,
    }
    if light:
        ctx["side_strip"] = _texture(m, "char.png", icons)
        return ctx

    ctx["right"] = {
        "banner_top": _texture(m, "banner4.png", icons),
        "banner_weapon": _texture(m, "banner2.png", icons),
        "prop_bg": _texture(m, "prop_bg_single.png" if diff_props else "prop_bg.png", icons),
        "props": diff_props if diff_props is not None else await _panel_props(m, icons, calc, role_detail, locale),
        "diff": diff_props is not None,
        "weapon": await _weapon_ctx(m, icons, role_detail, locale),
    }
    ctx["skills"] = await _skills_ctx(m, icons, role_detail, locale)
    ctx["chains"] = await _chains_ctx(m, icons, role_detail, locale)
    return ctx


async def _render(ctx: dict, char_name: str):
    from rover.html_actions import annotate_html
    from rover.media import HtmlBytes

    icons: Icons = ctx.pop("icons")
    ctx["icon_css"] = icons.entries
    html = _template().render(**ctx)
    html = annotate_html(html, TEMPLATE_NAME, {})
    logger.info(f"[面板] {char_name} HTML {len(html) / 1024 / 1024:.2f}MB")
    return HtmlBytes(html, TEMPLATE_NAME)


# ── 接管 ────────────────────────────────────────────────────────────────


def _install(m, name: str, func) -> None:
    """模块内与已按值绑定的上层包一起替换。"""
    setattr(m, name, func)
    parent = sys.modules.get(m.__name__.rsplit(".", 1)[0])
    if parent is not None and hasattr(parent, name):
        setattr(parent, name, func)


def _patch(m) -> None:
    original_detail = m.draw_char_detail_img
    original_score = m.draw_char_score_img
    original_optimize = m.draw_char_optimize_img

    async def draw_char_detail_img(
        ev, uid, char, user_id, waves_id=None, need_convert_img=True, is_force_avatar=False,
        change_list_regex=None, is_limit_query=False, show_score=True, fallback_to_generic=False,
        role_detail_override=None,
    ):
        args = (ev, uid, char, user_id, waves_id, need_convert_img, is_force_avatar, change_list_regex,
                is_limit_query, show_score, fallback_to_generic, role_detail_override)
        # 拼图/预览等路径要的是 PIL 画布, 交回原实现
        if not need_convert_img or fallback_to_generic or role_detail_override is not None:
            return await original_detail(*args)
        try:
            return await _render_detail(
                m, ev, uid, char, user_id, waves_id, is_force_avatar, change_list_regex,
                is_limit_query, show_score,
            )
        except Exception as e:
            logger.exception(f"[面板] HTML 渲染失败, 回落原图: {e}")
        return await original_detail(*args)

    async def draw_char_score_img(ev, uid, char, user_id, waves_id=None, is_limit_query=False):
        try:
            return await _render_weight(m, ev, uid, char, user_id, waves_id, is_limit_query)
        except Exception as e:
            logger.exception(f"[面板] 权重 HTML 渲染失败, 回落原图: {e}")
        return await original_score(ev, uid, char, user_id, waves_id, is_limit_query)

    async def draw_char_optimize_img(
        ev, uid, char, user_id, waves_id=None, change_list_regex=None, is_limit_query=False
    ):
        try:
            return await _render_optimize(m, ev, uid, char, user_id, waves_id, change_list_regex, is_limit_query)
        except Exception as e:
            logger.exception(f"[面板] 优化 HTML 渲染失败, 回落原图: {e}")
        return await original_optimize(ev, uid, char, user_id, waves_id, change_list_regex, is_limit_query)

    _install(m, "draw_char_detail_img", draw_char_detail_img)
    _install(m, "draw_char_score_img", draw_char_score_img)
    _install(m, "draw_char_optimize_img", draw_char_optimize_img)


PATCHES = {"XutheringWavesUID": {"wutheringwaves_charinfo.draw_char_card": _patch}}
