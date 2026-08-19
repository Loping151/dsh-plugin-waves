"""插件状态注册表。"""

from typing import Awaitable, Callable, Dict, Union

from PIL import Image

from .models import PluginStatus

plugins_status: Dict[str, PluginStatus] = {}


def register_status(
    ICON: Image.Image,
    plugin_name: str,
    plugin_status: Dict[str, Callable[..., Awaitable[Union[str, int, float]]]],
):
    plugins_status[plugin_name] = {"icon": ICON, "status": plugin_status}
