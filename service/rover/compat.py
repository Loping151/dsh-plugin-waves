"""让上游插件源码零改动运行。

插件按它们原本的框架命名空间 import; 这里把那些名字全部指向本运行时的实现,
因此插件目录可以直接 git pull 上游, 不需要改一行源码。
"""

import importlib
import sys
from types import ModuleType
from typing import Dict, List

from rover.logger import logger

# 上游框架的顶层包名与插件命名空间
UPSTREAM = "gsuid_core"
UPSTREAM_PLUGINS = f"{UPSTREAM}.plugins"

# 上游模块路径 → 本运行时模块路径
MODULE_MAP: Dict[str, str] = {
    "": "rover",
    "bot": "rover.bot",
    "models": "rover.models",
    "segment": "rover.segment",
    "sv": "rover.sv",
    "trigger": "rover.trigger",
    "handler": "rover.handler",
    "logger": "rover.logger",
    "config": "rover.config",
    "data_store": "rover.data_store",
    "aps": "rover.aps",
    "pool": "rover.pool",
    "gss": "rover.gss",
    "server": "rover.server",
    "subscribe": "rover.subscribe",
    "i18n": "rover.i18n",
    "message_models": "rover.message_models",
    "web_app": "rover.web_app",
    "app_life": "rover.app_life",
    "utils": "rover.utils",
    "utils.database": "rover.utils.database",
    "utils.database.base_models": "rover.utils.database.base_models",
    "utils.database.models": "rover.utils.database.models",
    "utils.database.startup": "rover.utils.database.startup",
    "utils.plugins_config": "rover.utils.plugins_config",
    "utils.plugins_config.models": "rover.utils.plugins_config.models",
    "utils.plugins_config.gs_config": "rover.utils.plugins_config.gs_config",
    "utils.image": "rover.utils.image",
    "utils.image.convert": "rover.utils.image.convert",
    "utils.image.image_tools": "rover.utils.image.image_tools",
    "utils.image.utils": "rover.utils.image.utils",
    "utils.fonts": "rover.utils.fonts",
    "utils.fonts.fonts": "rover.utils.fonts.fonts",
    "utils.download_resource": "rover.utils.download_resource",
    "utils.download_resource.download_file": "rover.utils.download_resource.download_file",
    "utils.download_resource.download_core": "rover.utils.download_resource.download_core",
    "utils.cookie_manager": "rover.utils.cookie_manager",
    "utils.cookie_manager.qrlogin": "rover.utils.cookie_manager.qrlogin",
    "utils.boardcast": "rover.utils.boardcast",
    "utils.boardcast.models": "rover.utils.boardcast.models",
    "help": "rover.help",
    "help.model": "rover.help.model",
    "help.utils": "rover.help.utils",
    "help.draw_new_plugin_help": "rover.help.draw_new_plugin_help",
    "status": "rover.status",
    "status.plugin_status": "rover.status.plugin_status",
    "webconsole": "rover.webconsole",
    "webconsole.mount_app": "rover.webconsole.mount_app",
    "ai_core": "rover.ai_core",
    "ai_core.models": "rover.ai_core.models",
    "ai_core.register": "rover.ai_core.register",
    "ai_core.resource": "rover.ai_core.resource",
    "ai_core.rag": "rover.ai_core.rag",
    "ai_core.rag.knowledge": "rover.ai_core.rag.knowledge",
    "ai_core.skills": "rover.ai_core.skills",
    "ai_core.skills.operations": "rover.ai_core.skills.operations",
}

# 上游的重启入口在 buildin 插件里, 这里造一个同路径模块转发过去
RESTART_PATH = f"{UPSTREAM}.buildin_plugins.core_command.core_restart.restart"

# 上游配置模型的类名, 与本运行时的对应关系
CONFIG_CLASS_ALIASES = {
    "GsStrConfig": "StrConfig",
    "GsBoolConfig": "BoolConfig",
    "GsDictConfig": "DictConfig",
    "GsListStrConfig": "ListStrConfig",
    "GsListConfig": "ListConfig",
    "GsIntConfig": "IntConfig",
    "GsFloatConfig": "FloatConfig",
    "GsImageConfig": "ImageConfig",
    "GsTimeRConfig": "TimeRConfig",
    "GsDivider": "Divider",
    "GsFileUploadConfig": "FileUploadConfig",
    "GsFilesUploadConfig": "FilesUploadConfig",
    "GsDateConfig": "DateConfig",
    "GsTimeRangeConfig": "TimeRangeConfig",
    "GsColorConfig": "ColorConfig",
    "GsRepeatGroupConfig": "RepeatGroupConfig",
    "GsTimeConfig": "TimeConfig",
    "GSC": "ConfigItem",
}

# 其它沿用上游名字的符号: 运行时模块 → {上游名: 本地名}
SYMBOL_ALIASES = {
    "rover.webconsole.mount_app": {"GsAdminModel": "AdminModel"},
}

_installed = False


def _alias_module(upstream_name: str, target_name: str) -> None:
    module = importlib.import_module(target_name)
    sys.modules[upstream_name] = module


def _make_namespace(name: str, path: List[str]) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = path  # type: ignore[attr-defined]
    sys.modules[name] = module
    return module


def _install_config_aliases() -> None:
    models = importlib.import_module("rover.utils.plugins_config.models")
    for upstream_name, ours in CONFIG_CLASS_ALIASES.items():
        target = getattr(models, ours, None)
        if target is None:
            logger.warning(f"[兼容层] 配置模型缺少 {ours}")
            continue
        setattr(models, upstream_name, target)


def _install_symbol_aliases() -> None:
    for module_name, mapping in SYMBOL_ALIASES.items():
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as e:
            logger.warning(f"[兼容层] 跳过 {module_name}: {e}")
            continue
        for upstream_name, ours in mapping.items():
            target = getattr(module, ours, None)
            if target is None:
                logger.warning(f"[兼容层] {module_name} 缺少 {ours}")
                continue
            setattr(module, upstream_name, target)


def _install_restart_shim() -> None:
    import rover.restart as restart

    module = ModuleType(RESTART_PATH)
    module.restart_genshinuid = restart.restart_service  # type: ignore[attr-defined]
    for attr in dir(restart):
        if not attr.startswith("_"):
            setattr(module, attr, getattr(restart, attr))
    parts = RESTART_PATH.split(".")
    for i in range(2, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules:
            _make_namespace(parent, [])
    sys.modules[RESTART_PATH] = module
    setattr(sys.modules[".".join(parts[:-1])], parts[-1], module)


def install(plugins_path: List[str]) -> None:
    """建立命名空间映射。plugins_path 是存放上游插件包的目录列表。"""
    global _installed
    if _installed:
        return
    _installed = True

    for suffix, target in MODULE_MAP.items():
        upstream_name = UPSTREAM if not suffix else f"{UPSTREAM}.{suffix}"
        try:
            _alias_module(upstream_name, target)
        except ModuleNotFoundError as e:
            logger.warning(f"[兼容层] 跳过 {upstream_name}: {e}")

    _make_namespace(UPSTREAM_PLUGINS, list(plugins_path))
    setattr(sys.modules[UPSTREAM], "plugins", sys.modules[UPSTREAM_PLUGINS])

    _install_config_aliases()
    _install_symbol_aliases()
    _install_restart_shim()
    logger.debug(f"[兼容层] 已映射 {len(MODULE_MAP)} 个模块")


def missing_imports(source_root) -> List[str]:
    """扫描插件源码里本运行时尚未提供的框架模块, 供上游更新后自检。"""
    import ast
    from pathlib import Path

    known = {UPSTREAM if not s else f"{UPSTREAM}.{s}" for s in MODULE_MAP}
    known.add(UPSTREAM_PLUGINS)
    known.add(RESTART_PATH)
    missing = set()

    for py in Path(source_root).rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                if name == UPSTREAM or name.startswith(f"{UPSTREAM}."):
                    if name.startswith(UPSTREAM_PLUGINS):
                        continue
                    if name not in known:
                        missing.add(name)
    return sorted(missing)
