"""HTML 卡片补丁包。

每个模块定义 PATCHES = {"插件名": {"模块后缀": patch_fn}}, 由 hooks 自动发现合并。
patch_fn(module) 在插件功能模块 import 前被调用, 用于把绘图函数换成 HTML 渲染。
"""

import importlib
import pkgutil
from typing import Callable, Dict

from rover.logger import logger


def discover() -> Dict[str, Dict[str, Callable]]:
    merged: Dict[str, Dict[str, Callable]] = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"{__name__}.{info.name}")
        except Exception as e:
            logger.error(f"[卡片] {info.name} 加载失败: {e}")
            continue
        for plugin, table in getattr(module, "PATCHES", {}).items():
            merged.setdefault(plugin, {}).update(table)
    return merged
