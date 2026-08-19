"""插件状态结构。"""

from typing import Awaitable, Callable, Dict, TypedDict, Union

from PIL import Image


class PluginStatus(TypedDict):
    icon: Image.Image
    status: Dict[str, Callable[..., Awaitable[Union[str, int, float]]]]
