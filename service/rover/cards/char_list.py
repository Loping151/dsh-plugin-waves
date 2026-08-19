"""练度统计卡片: 原 PIL 版角色列表改为 HTML 输出, 1000x110 的角色条逐坐标搬运。"""

import asyncio
import importlib
from typing import Any, Callable, Dict, List, Tuple

from rover.cards import _shared
from rover.logger import logger

TEMPLATE = "char_list.html"

# 角色条几何, 与 PIL 版逐项对齐
BAR_W, BAR_H = 1000, 110
COL_PITCH = 920  # 双列时左列的横向步长
# 技能格与武器块在 PIL 里先按大尺寸画好再缩小, 这里保留原坐标, 靠 CSS 缩放还原
SKILL_SCALE_X, SKILL_SCALE_Y = 70 / 120, 82 / 140
WEAPON_SCALE = 260 / 600
# 技能等级配色取 CHAIN_COLOR_LIST 末尾五档, 对应 10/9/8/7/6 级
SKILL_LEVEL_COLORS = {10: -1, 9: -2, 8: -3, 7: -4, 6: -5}


def _skill_color(module, level: int) -> str:
    index = SKILL_LEVEL_COLORS.get(level)
    if index is None:
        return "#ffffff"
    return _shared.css_color(module.CHAIN_COLOR_LIST[index])


def _rgba(color: Any, alpha: float) -> str:
    parts = list(color)[:3]
    return "rgba({}, {}, {}, {})".format(*parts, alpha)


def _reson_color(module, level: int) -> str:
    """N 阶底块压在武器图上, 亮底(5 阶)调暗才压得住白字。"""
    rgb = module.WEAPON_RESONLEVEL_COLOR[level]
    if 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2] > 135:
        rgb = tuple(int(c * 0.6) for c in rgb)
    return _rgba(rgb, 0.85)


def _build_context(
    module,
    image,
    render_utils,
    account_info,
    avatar,
    char_assets,
    stats,
    user_pref,
    two_col,
) -> Dict[str, Any]:
    texture = module.TEXT_PATH
    # 头像/技能图/武器图在几十条里反复出现, 统一收进 CSS 类, 元素只带类名
    assets: List[str] = []
    classes: Dict[Tuple, str] = {}

    def asset_class(key: Tuple, make: Callable[[], str]) -> str:
        if key not in classes:
            assets.append(make())
            classes[key] = f"a{len(assets) - 1}"
        return classes[key]

    count = len(char_assets)
    per_col = (count + 1) // 2 if two_col else count

    rows: List[Dict[str, Any]] = []
    for index, asset in enumerate(char_assets):
        rank = asset["rank"]
        detail = asset["role_detail"]
        role_id = detail.role.roleId
        chain = detail.get_chain_num()
        star = min(max(rank.starLevel, 3), 5)

        skills = []
        for i, item in enumerate(detail.get_skill_list()):
            if item.skill.type in ("延奏技能", "谐度破坏"):
                continue
            icon = asset["skill_imgs"][i]
            skills.append(
                {
                    "left": 100 + i * 65,
                    "icon_class": asset_class(
                        ("skill", role_id, item.skill.name),
                        lambda im=icon: image.pil_to_b64(im.resize((70, 70)), quality=80),
                    )
                    if icon is not None
                    else "",
                    "level": item.level,
                    "color": _skill_color(module, item.level),
                }
            )

        weapon_data = detail.weaponData
        weapon = weapon_data.weapon
        weapon_star = min(max(weapon.weaponStarLevel, 3), 5)
        breach = module.get_breach(weapon_data.breach, weapon_data.level) or 0

        score = None
        if rank.score > 0.0:
            emblem = f"score_{rank.score_bg}.png"
            if not (texture / emblem).exists():
                emblem = "score_c.png"
            score = {
                "emblem_class": asset_class(
                    ("score", emblem), lambda n=emblem: image.img_to_b64(texture / n)
                ),
                "value": f"{int(rank.score * 100) / 100:.2f}",
            }

        char_name = module.SPECIAL_CHAR_NAME.get(str(role_id), rank.roleName)
        rows.append(
            {
                "left": COL_PITCH * (1 if two_col and index >= per_col else 0),
                "top": BAR_H * (index - per_col if two_col and index >= per_col else index),
                "bar_class": asset_class(
                    ("bar", star), lambda s=star: image.img_to_b64(texture / f"bar_{s}star.png")
                ),
                "avatar_class": asset_class(
                    ("avatar", role_id),
                    lambda im=asset["role_avatar"]: image.pil_to_b64(im, quality=80),
                ),
                "attr_class": asset_class(
                    ("attr", detail.role.attributeName),
                    lambda im=asset["role_attribute"]: image.pil_to_b64(
                        im.resize((40, 40)).convert("RGBA"), quality=80
                    ),
                ),
                "level": rank.level,
                "chain_name": detail.get_chain_name(),
                "chain_color": _rgba(module.CHAIN_COLOR[chain], 0.9),
                "score": score,
                "skills": skills,
                "weapon": {
                    "bg_class": asset_class(
                        ("weapon_bg", weapon_star),
                        lambda s=weapon_star: image.img_to_b64(texture / f"weapon_icon_bg_{s}.png"),
                    ),
                    "icon_class": asset_class(
                        ("weapon", weapon.weaponId),
                        lambda im=asset["weapon_icon"]: image.pil_to_b64(
                            module.crop_center_img(im, 110, 110), quality=80
                        ),
                    ),
                    "name": weapon.weaponName,
                    "level": weapon_data.level,
                    "pips": list(range(breach)),
                    "reson": weapon_data.resonLevel,
                    "reson_color": _reson_color(module, weapon_data.resonLevel),
                },
                "cmd": f"{module.PREFIX}{char_name}面板" if char_name else "",
            }
        )

    head = _shared.head_context(account_info, user_pref=user_pref, hide_uid=module.hide_uid)
    head["user_name"] = str(head["user_name"])[:10]

    # 头部走统一样式; 四项统计仍用画布版的底图与坐标
    grid_w = COL_PITCH + BAR_W if two_col else BAR_W
    stat_cells = [
        (240, f"{stats['up_num']}/{stats['all_up_num']}", "up角色"),
        (410, f"{stats['level_num']}/{stats['all_num']}", "高练角色"),
        (580, f"{stats['chain_num']}/{stats['all_num'] - stats['all_num_5']}", "高链4星"),
        (750, f"{stats['chain_num_5']}/{stats['all_num_5']}", "高链5星"),
    ]
    context = {
        "font_css_url": _shared.font_css_url(render_utils),
        "bg_url": image.pil_to_b64(
            image.get_custom_waves_bg(bg="bg3", crop=False).convert("RGB"), quality=75
        ),
        "footer_url": render_utils.get_footer_b64(footer_type="white") or "",
        "avatar_url": image.pil_to_b64(avatar.crop((20, 20, 180, 180)), quality=85),
        "info_bg_url": image.img_to_b64(texture / "info_bg.png"),
        "skill_bg_url": image.img_to_b64(texture / "skill_bg.png"),
        "promote_url": image.img_to_b64(texture / "promote_icon.png"),
        "assets": assets,
        "grey": _shared.css_color(module.GREY),
        "gold": _shared.css_color(module.SPECIAL_GOLD),
        "page_w": grid_w + 80,
        "grid_w": grid_w,
        "grid_h": BAR_H * per_col,
        "two_col": two_col,
        "stat_cells": [{"x": x, "value": v, "label": t} for x, v, t in stat_cells],
        "bar_w": BAR_W,
        "bar_h": BAR_H,
        "skill_scale_x": round(SKILL_SCALE_X, 6),
        "skill_scale_y": round(SKILL_SCALE_Y, 6),
        "weapon_scale": round(WEAPON_SCALE, 6),
        "hint": f"可指定  {module.PREFIX}练度统计 五星/四星/全部" if two_col else "",
        "rows": rows,
    }
    context.update(head)
    return _shared.avatar_override(context, "avatar_url")


def _patch(module) -> None:
    from rover.media import HtmlBytes

    original = module._compose_char_list
    package = module.__name__.rsplit(".", 2)[0]
    image = importlib.import_module(f"{package}.utils.image")
    render_utils = importlib.import_module(f"{package}.utils.render_utils")

    async def compose(account_info, avatar, char_assets, stats, user_pref, two_col):
        try:
            context = await asyncio.to_thread(
                _build_context,
                module,
                image,
                render_utils,
                account_info,
                avatar,
                char_assets,
                stats,
                user_pref,
                two_col,
            )
            card = _shared.render(TEMPLATE, context)
            logger.info(f"[练度统计] {len(card) / 1024 / 1024:.2f}MB")
            return card
        except Exception as e:
            logger.exception(f"[练度统计] HTML 渲染失败, 回退原图: {e}")
            return await original(account_info, avatar, char_assets, stats, user_pref, two_col)

    module._compose_char_list = compose

    original_convert = module.convert_img

    async def convert_img(img, *args, **kwargs):
        if isinstance(img, HtmlBytes):
            return img
        return await original_convert(img, *args, **kwargs)

    module.convert_img = convert_img


PATCHES = {
    "XutheringWavesUID": {
        "wutheringwaves_charlist.draw_char_list": _patch,
    },
}
