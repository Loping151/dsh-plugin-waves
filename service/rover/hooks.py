"""对插件行为的运行时改造。

插件目录保持上游原样以便随时更新, 本地需要的差异全部在这里施加:
渲染改为直接产出 HTML、卡片内角色可点击、裁掉本地用不到的命令。
"""

import importlib
from typing import Dict, List, Set, Tuple

from rover.logger import logger

# (SV 名, 触发词) —— 群聊/多用户场景才有意义的命令, 本地不注册
DROP_TRIGGERS: List[Tuple[str, str]] = [
    ("鸣潮删除群成员", "^删除群成员"),
    ("鸣潮删除群成员", "^(删除|清除|清理)不活跃"),
    ("waves面板图权限提示和审核", "*"),
    ("ww角色排行", "*"),
    ("ww声骸排行", "*"),
    ("ww练度排行", "*"),
    ("waves无尽排行", "*"),
    ("waves矩阵排行", "*"),
    ("waves抽卡排行", "*"),
    ("订阅鸣潮公告", "*"),
    ("RoverSign-全部签到", "^(订阅|取消订阅)签到结果$"),
    # 本机就是主人自己, 这条只是往订阅表里写一行
    ("联系主人", "*"),
]

# 帮助里的扩展模块条目按实际装了哪些插件给, 否则会列出根本没装的功能
HELP_EXTRA_MODULES = {
    "roversign": ("RoverSign",),
    "scoreecho": ("ScoreEcho",),
    "roverreminder": ("RoverReminder",),
    "todayecho": ("WavesTodayEcho", "TodayEcho"),
}

# 各卡片模板里的用户头像字段
AVATAR_CONTEXT_KEY = "avatar_url"

# 帮助条目里含这些词的均属已裁功能, 渲染时一并剔除
DROP_HELP_MARKERS = (
    "群成员", "不活跃", "群排行", "群排名", "抽卡排行", "练度排行", "群持有率",
    "订阅公告", "退订公告", "订阅签到结果", "联系主人",
)

# 命令里的这些关键词只在群里有意义, 从触发词元组中摘掉
DROP_KEYWORDS: Set[str] = {
    "群角色持有率",
    "群角色持有率列表",
    "群持有率",
    "群练度排行",
    "练度群排行",
    "练度群排行榜",
    "群练度排名",
    "练度群排名",
}


def _iter_triggers():
    from rover.sv import SL

    for sv in SL.lst.values():
        for ttype, table in list(sv.TL.items()):
            for key, trigger in list(table.items()):
                yield sv, ttype, key, trigger


def _drop_buttons() -> int:
    """快捷按钮里指向已裁命令的条目一并去掉, 免得点了没反应。"""
    from rover.segment import MessageSegment

    original = MessageSegment.buttons

    @staticmethod
    def buttons(items=None):
        if items:
            kept = []
            for row in items:
                if isinstance(row, list):
                    row = [b for b in row if getattr(b, "data", "") not in DROP_KEYWORDS]
                    if row:
                        kept.append(row)
                elif getattr(row, "data", "") not in DROP_KEYWORDS:
                    kept.append(row)
            items = kept
        return original(items)

    MessageSegment.buttons = buttons
    return 0


def align_help_modules(installed=None) -> None:
    """帮助里的扩展模块条目跟着已装插件走, 没装的模块不列。

    帮助表是在插件 import 时一次性建好的, 所以这一步必须赶在载入插件之前。
    """
    from rover.utils.plugins_config.gs_config import all_config_list

    if installed is None:
        from rover.sv import SL

        installed = set(SL.plugins)
    config = all_config_list.get("XutheringWavesUID")
    if config is None:
        return
    item = config.get_config("HelpExtraModules")
    if item is None:
        return
    want = sorted(
        key for key, names in HELP_EXTRA_MODULES.items()
        if any(name in installed for name in names)
    )
    if list(getattr(item, "data", []) or []) != want:
        config.set_config("HelpExtraModules", want)
        logger.info(f"[改造] 帮助扩展模块按已装插件对齐: {want}")


def drop_commands() -> int:
    """按黑名单摘掉触发器。上游改名导致某条失配时告警, 不静默。"""
    from rover.sv import SL

    dropped = 0
    matched_rules: Set[Tuple[str, str]] = set()

    for sv_name, keyword in DROP_TRIGGERS:
        sv = SL.lst.get(sv_name)
        if sv is None:
            continue
        for ttype, table in list(sv.TL.items()):
            for key, trigger in list(table.items()):
                if keyword == "*" or trigger.keyword.startswith(keyword):
                    del table[key]
                    dropped += 1
                    matched_rules.add((sv_name, keyword))
            if not table:
                sv.TL.pop(ttype, None)

    for sv, ttype, key, trigger in _iter_triggers():
        if trigger.keyword in DROP_KEYWORDS:
            sv.TL[ttype].pop(key, None)
            dropped += 1

    stale = [f"{n}:{k}" for n, k in DROP_TRIGGERS if (n, k) not in matched_rules]
    if stale:
        logger.warning(f"[改造] 命令黑名单有 {len(stale)} 条未命中(上游可能已改名): {stale}")
    _drop_buttons()
    logger.info(f"[改造] 已裁掉 {dropped} 个触发器")
    return dropped


def _patch_render(module) -> None:
    """把截图渲染换成直接产出 HTML, 并给卡片里的角色挂上点击命令。"""
    from rover.html_actions import annotate_html
    from rover.media import HtmlBytes

    def apply_avatar(context: dict) -> None:
        """深塔/海墟/矩阵/全息/资源/体力等模板的头像字段统一叫 avatar_url。"""
        from rover.avatar import get_avatar_url

        if AVATAR_CONTEXT_KEY not in context:
            return
        url = get_avatar_url()
        if url:
            context[AVATAR_CONTEXT_KEY] = url

    def font_css_url() -> str:
        """字体由本服务自己挂载, 不依赖外部部署。"""
        from rover.config import core_config

        if getattr(module, "_FONTS_DIR", None) is not None and module._FONTS_DIR.exists():
            host = core_config.get_config("HOST") or "127.0.0.1"
            if host in ("0.0.0.0", ""):
                host = "127.0.0.1"
            return f"http://{host}:{core_config.get_config('PORT')}/waves/fonts/fonts.css"
        return module._get_font_css_url()

    async def render_html(waves_templates, template_name: str, context: dict):
        try:
            template = waves_templates.get_template(template_name)
            context["font_css_url"] = font_css_url()
            try:
                apply_avatar(context)
            except Exception as e:
                logger.warning(f"[渲染] 头像覆盖失败: {e}")
            html = template.render(**context)
        except Exception as e:
            logger.error(f"[渲染] 模板失败 {template_name}: {e}")
            return None
        html = annotate_html(html, template_name, context)
        logger.info(f"[渲染] {template_name} {len(html) / 1024 / 1024:.2f}MB")
        return HtmlBytes(html, template_name)

    module.render_html = render_html
    module.PLAYWRIGHT_AVAILABLE = True


def _patch_stamina(module) -> None:
    """体力卡多账号时拼接 HTML, 不再走 PIL 画布。"""
    from rover.html_actions import merge_html_cards
    from rover.media import HtmlBytes

    original = module._assemble_stamina_canvas

    def assemble(stamina_imgs: list, canvas_w: int, row_h: int):
        html_parts = [i for i in stamina_imgs if isinstance(i, HtmlBytes)]
        if html_parts and len(html_parts) == len(stamina_imgs):
            return merge_html_cards(html_parts)
        return original(stamina_imgs, canvas_w, row_h)

    module._assemble_stamina_canvas = assemble

    original_convert = module.convert_img

    async def convert_img(img, *args, **kwargs):
        if isinstance(img, HtmlBytes):
            return img
        return await original_convert(img, *args, **kwargs)

    module.convert_img = convert_img

    # 上游把渲染结果交给 Image.open 包装, HTML 要在这一步放行
    image_module = module.Image

    class _ImageProxy:
        def __getattr__(self, name):
            return getattr(image_module, name)

        @staticmethod
        def open(fp, *args, **kwargs):
            # BytesIO 会拷贝字节丢掉类型, 只能按内容判断
            raw = fp.getvalue() if hasattr(fp, "getvalue") else b""
            if raw[:400].lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
                return HtmlBytes(raw.decode("utf-8", "replace"), "stamina_card.html")
            return image_module.open(fp, *args, **kwargs)

    module.Image = _ImageProxy()


# 签到侧与查询侧同名的配置, 统一读查询侧的值
RS_SHARED_KEYS = {"LocalProxyUrl", "KuroUrlProxyUrl", "NeedProxyFunc", "HideUid"}


def _patch_rs_shared(module) -> None:
    config = module.RoverSignConfig
    original = config.get_config

    def get_config(key: str, *args, **kwargs):
        item = original(key, *args, **kwargs)
        if key not in RS_SHARED_KEYS:
            return item
        from rover.utils.plugins_config.gs_config import all_config_list

        waves = all_config_list.get("XutheringWavesUID")
        if waves is None:
            return item
        shared = waves.get_config(key)
        if shared is not None:
            item.data = shared.data
        return item

    config.get_config = get_config


# 插件名 → {模块后缀: 补丁}
def _patch_skip_ai(module) -> None:
    """本地由 dsh 自己的模型对话, 插件侧的知识库注册跳过。"""
    import sys
    from types import ModuleType

    name = f"{module.__name__.rsplit('.', 3)[0]}.wutheringwaves_ai_rag"
    if name in sys.modules:
        return
    stub = ModuleType(name)

    async def reload_ai_rag(*args, **kwargs):
        return None

    stub.reload_ai_rag = reload_ai_rag
    sys.modules[name] = stub


def _patch_score_token(module) -> None:
    """评分与排行是同一套 token, 让评分侧直接读排行的配置项。"""
    config = module.seconfig
    original = config.get_config

    def get_config(key: str, *args, **kwargs):
        item = original(key, *args, **kwargs)
        if key != "xwtoken":
            return item
        from rover.utils.plugins_config.gs_config import all_config_list

        waves = all_config_list.get("XutheringWavesUID")
        if waves is None:
            return item
        shared = waves.get_config("WavesToken")
        if shared is not None and shared.data:
            item.data = shared.data
        return item

    config.get_config = get_config


_PATCHES = {
    "XutheringWavesUID": {
        "utils.render_utils": _patch_render,
        "utils.resource.download_all_resource": _patch_skip_ai,
        "wutheringwaves_stamina.draw_waves_stamina": _patch_stamina,
    },
    "RoverSign": {
        "roversign_config.roversign_config": _patch_rs_shared,
    },
    "ScoreEcho": {
        "scoreecho_config.config": _patch_score_token,
    },
}


_cards_patches = None


def _all_patches(plugin_name: str) -> Dict[str, object]:
    """内置补丁 + rover/cards 下自动发现的模板补丁。"""
    global _cards_patches
    if _cards_patches is None:
        from rover import cards

        _cards_patches = cards.discover()
    table = dict(_PATCHES.get(plugin_name, {}))
    table.update(_cards_patches.get(plugin_name, {}))
    return table


def patch_modules(plugin_name: str, package: str) -> None:
    """在插件功能模块被 import 之前打补丁, 让它们按值绑定到新实现。"""
    for suffix, patch in _all_patches(plugin_name).items():
        name = f"{package}.{suffix}"
        try:
            module = importlib.import_module(name)
        except Exception as e:
            logger.warning(f"[改造] 跳过 {name}: {e}")
            continue
        try:
            patch(module)
            logger.debug(f"[改造] 已改造 {name}")
        except Exception as e:
            logger.error(f"[改造] {name} 失败: {e}")


def align_local_urls() -> None:
    """配置里指向别处部署的地址改成本服务自己的。"""
    from rover.config import core_config
    from rover.utils.plugins_config.gs_config import all_config_list

    waves = all_config_list.get("XutheringWavesUID")
    if waves is None:
        return
    host = core_config.get_config("HOST") or "127.0.0.1"
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    local = f"http://{host}:{core_config.get_config('PORT')}/waves/fonts/fonts.css"
    item = waves.get_config("FontCssUrl")
    if item is not None and item.data != local:
        waves.set_config("FontCssUrl", local)
        logger.info(f"[改造] 字体地址改为本服务 {local}")


def seed_defaults(configs: Dict[str, Dict[str, object]]) -> None:
    """初值只写一次。写过就记在案, 之后用户在设置页改成什么就是什么。"""
    from rover.config import core_config
    from rover.utils.plugins_config.gs_config import all_config_list

    seeded = list(core_config.get_config("seeded") or [])
    for config_name, values in configs.items():
        if config_name in seeded:
            continue
        config = all_config_list.get(config_name)
        if config is None:
            continue
        for key, value in values.items():
            item = config.get_config(key)
            if item is not None and item.data != value:
                config.set_config(key, value)
        seeded.append(config_name)
        logger.info(f"[改造] {config_name} 首次装载, 已写入初值")
    if seeded != (core_config.get_config("seeded") or []):
        core_config.set_config("seeded", seeded)


def apply_defaults(configs: Dict[str, Dict[str, object]]) -> None:
    """运行时前提项, 每次启动都校正; 这些键不进设置页, 不会和用户的选择打架。"""
    from rover.utils.plugins_config.gs_config import all_config_list

    for config_name, values in configs.items():
        config = all_config_list.get(config_name)
        if config is None:
            logger.warning(f"[改造] 未找到配置 {config_name}")
            continue
        for key, value in values.items():
            item = config.get_config(key)
            if item is not None and item.data != value:
                config.set_config(key, value)
