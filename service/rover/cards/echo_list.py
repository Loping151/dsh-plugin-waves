"""声骸仓库卡片: 原 PIL 版声骸列表改为 HTML 输出, 版式照搬 350x600 卡格与 4 列网格。"""

import asyncio
import importlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

from rover.logger import logger

TEMPLATE = "echo_list.html"
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

# 卡格几何, 与 PIL 版逐项对齐
CARD_W, CARD_H = 350, 600
COL_PITCH, ROW_PITCH = 390, 570
COLUMNS = 4
PROP_TOP, PROP_PITCH = 217, 55

_env = None


def _template():
    global _env
    if _env is None:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        _env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    return _env.get_template(TEMPLATE)


def _css_color(value: Any) -> str:
    """词条配色在插件里是颜色名或 RGB 元组。"""
    if isinstance(value, (tuple, list)):
        parts = list(value)[:3]
        return "rgb({}, {}, {})".format(*parts)
    return str(value)


def _font_css_url(render_utils) -> str:
    css = render_utils._FONTS_DIR / render_utils._FONT_CSS_NAME
    if css.exists():
        return f"{render_utils._get_local_base_url()}/waves/fonts/{render_utils._FONT_CSS_NAME}"
    return render_utils._get_font_css_url()


def _build_context(module, image, render_utils, account_info, avatar, echo_assets, page, max_page, user_pref) -> Dict:
    texture = module.TEXT_PATH
    # 同一素材在 20 张卡里反复出现, 统一收进 CSS 类, 元素只带类名
    assets: List[str] = []
    classes: Dict[Tuple, str] = {}

    def asset_class(key: Tuple, make) -> str:
        if key not in classes:
            assets.append(make())
            classes[key] = f"a{len(assets) - 1}"
        return classes[key]

    echoes: List[Dict] = []
    for index, asset in enumerate(echo_assets):
        echo = asset["echo"]
        phantom = echo.phantom
        icon = asset["phantom_icon"]

        title = f"sh_title_{echo.score_bg}.png"
        if not (texture / title).exists():
            title = "sh_title_c.png"

        props = []
        for i, prop in enumerate(echo.props):
            prop_img = asset["prop_imgs"][i]
            props.append(
                {
                    "icon_class": asset_class(
                        ("prop", prop.attributeName),
                        lambda img=prop_img: image.pil_to_b64(img.resize((40, 40)), quality=80),
                    ),
                    "name": prop.attributeName[:6],
                    "value": prop.attributeValue,
                    "name_color": _css_color(echo.name_colors[i]),
                    "value_color": _css_color(echo.num_colors[i]),
                }
            )

        echoes.append(
            {
                "left": COL_PITCH * (index % COLUMNS),
                "top": ROW_PITCH * (index // COLUMNS),
                "title_class": asset_class(("title", title), lambda: image.img_to_b64(texture / title)),
                "role_class": asset_class(
                    ("role", echo.roleId),
                    lambda: image.pil_to_b64(asset["role_avatar"], quality=80),
                ),
                "icon_class": asset_class(
                    ("phantom", phantom.phantomProp.phantomId),
                    lambda: image.pil_to_b64(icon.resize((100, 100)), quality=80),
                ),
                "fetter_class": asset_class(
                    ("fetter", phantom.fetterDetail.name),
                    lambda: image.pil_to_b64(asset["fetter_icon"].resize((50, 50)), quality=80),
                ),
                # 角标原本贴在整图 (205, 0) 处, 缩到 100x100 后按比例给百分比
                "fetter_left": 205 / max(icon.width, 1) * 100,
                "fetter_size": 50 / max(icon.width, 1) * 100,
                "name": phantom.phantomProp.name.replace("·", " ").replace("（", " ").replace("）", ""),
                "level": phantom.level,
                "score": echo.score,
                "cost": phantom.cost,
                "props": props,
                "command": f"{module.PREFIX}{echo.roleName}面板" if echo.roleName else "",
            }
        )

    rows = (len(echoes) + COLUMNS - 1) // COLUMNS

    return {
        "font_css_url": _font_css_url(render_utils),
        "bg_url": image.pil_to_b64(image.get_waves_bg(bg="bg3", crop=False), quality=75),
        "footer_url": render_utils.get_footer_b64(footer_type="white") or "",
        "sh_bg_url": image.img_to_b64(texture / "sh_bg.png"),
        "promote_url": image.img_to_b64(texture / "promote_icon.png"),
        "avatar_url": image.pil_to_b64(avatar, quality=80),
        "assets": assets,
        "user_name": account_info.name[:10],
        "user_id": module.hide_uid(account_info.id, user_pref=user_pref),
        "level": account_info.level,
        "world_level": account_info.worldLevel,
        "show_stats": account_info.is_full,
        "page_text": f"第{page}/{max_page}页" if page > 1 else "",
        "card_w": CARD_W,
        "card_h": CARD_H,
        "prop_top": PROP_TOP,
        "prop_gap": PROP_PITCH - 40,
        "grid_w": COL_PITCH * (COLUMNS - 1) + CARD_W,
        "grid_h": ROW_PITCH * max(rows - 1, 0) + CARD_H,
        "echoes": echoes,
    }


def _patch_echo_list(module) -> None:
    from rover.html_actions import annotate_html
    from rover.media import HtmlBytes

    original = module._compose_echo_list
    package = module.__name__.rsplit(".", 2)[0]
    image = importlib.import_module(f"{package}.utils.image")
    render_utils = importlib.import_module(f"{package}.utils.render_utils")

    async def compose(
        account_info,
        avatar,
        avatar_ring,
        echo_assets,
        page,
        max_page,
        user_pref,
        title_bar_logo,
    ):
        try:
            context = await asyncio.to_thread(
                _build_context,
                module,
                image,
                render_utils,
                account_info,
                avatar,
                echo_assets,
                page,
                max_page,
                user_pref,
            )
            html = annotate_html(_template().render(**context), TEMPLATE, context)
            logger.info(f"[声骸仓库] {len(html) / 1024 / 1024:.2f}MB")
            return HtmlBytes(html, TEMPLATE)
        except Exception as e:
            logger.error(f"[声骸仓库] HTML 渲染失败, 回退原图: {e}")
            return await original(
                account_info,
                avatar,
                avatar_ring,
                echo_assets,
                page,
                max_page,
                user_pref,
                title_bar_logo,
            )

    module._compose_echo_list = compose

    original_convert = module.convert_img

    async def convert_img(img, *args, **kwargs):
        if isinstance(img, HtmlBytes):
            return img
        return await original_convert(img, *args, **kwargs)

    module.convert_img = convert_img


PATCHES = {
    "XutheringWavesUID": {
        "wutheringwaves_echo.draw_echo_list": _patch_echo_list,
    },
}
