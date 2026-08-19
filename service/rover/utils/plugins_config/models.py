import datetime
from typing import Dict, List, Tuple, Union, Optional
from typing_extensions import deprecated

import msgspec


class Config(msgspec.Struct, tag=True):
    """基类, 禁止直接使用"""

    title: str
    desc: str


class StrConfig(Config, tag=True):
    """字符串配置"""

    data: str
    options: List[str] = []
    regex: Optional[str] = None
    """仅用于前端正则校验的正则表达式"""
    details: Optional[dict] = None
    secret: bool = False


class BoolConfig(Config, tag=True):
    """布尔开关配置"""

    data: bool
    secret: bool = False


class DictConfig(Config, tag=True):
    """字典配置"""

    data: Dict[str, List]
    secret: bool = False


class ListStrConfig(Config, tag=True):
    """字符串列表配置"""

    data: List[str]
    options: List[str] = []
    secret: bool = False


class ListConfig(Config, tag=True):
    """整数列表配置"""

    data: List[int]
    secret: bool = False


class IntConfig(Config, tag=True):
    """整数配置"""

    data: int
    max_value: Optional[int] = None
    options: List[int] = []
    secret: bool = False


class FloatConfig(Config, tag=True):
    """浮点数配置"""

    data: float
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    secret: bool = False


class ImageConfig(Config, tag=True):
    """图片配置

    upload_to: 通过 get_res_path() 获取的绝对目录路径，不可写相对路径或跨插件路径
    """

    data: str
    upload_to: str
    filename: str
    suffix: str = "jpg"
    secret: bool = False


class TimeRConfig(Config, tag=True):
    """时间点配置, data为时、分"""

    data: Tuple[int, int]
    secret: bool = False


class Divider(Config, tag=True):
    """无实际作用, 在前端中用于分割配置, 便于用户UX"""

    data: Optional[str] = None
    """分割线标题, 为None时前端仅渲染分割线, 非None时渲染带标题的分割线"""


class FileUploadConfig(Config, tag=True):
    """文件上传配置

    upload_to: 通过 get_res_path() 获取的绝对目录路径，不可写相对路径或跨插件路径
    """

    data: str
    upload_to: str
    filename: str
    suffix: str = "html"
    secret: bool = False


class FilesUploadConfig(Config, tag=True):
    """批量文件上传配置

    data: 通过 get_res_path() 获取的绝对目录路径，同时也是上传目标目录，
          不可写相对路径或跨插件路径
    """

    data: str
    suffix: str = "html"
    secret: bool = False


class DateConfig(Config, tag=True):
    """日期配置 (如 YYYY-MM-DD)"""

    data: datetime.date
    secret: bool = False


class TimeRangeConfig(Config, tag=True):
    """时间范围配置 (如 允许访问的时间段: 08:00 - 20:00)"""

    data: Tuple[Tuple[int, int], Tuple[int, int]]
    secret: bool = False


class ColorConfig(Config, tag=True):
    """颜色配置 (HEX格式如 #FFFFFF 或 RGBA)"""

    data: str


class RepeatGroupConfig(Config, tag=True):
    """可重复配置组：data 每项是一组子配置(Dict[str, ConfigItem], 与整份插件配置同构),
    template 是新增一项的原型/默认。可再嵌套本类型。前端复用逐项渲染器递归渲染。
    """

    # "ConfigItem" 为字符串前向引用: 定义在本类之后, msgspec 加载时惰性解析。
    data: List[Dict[str, "ConfigItem"]]
    template: Dict[str, "ConfigItem"]
    secret: bool = False


@deprecated("TimeConfig 已废弃，请使用 TimeRConfig 代替")
class TimeConfig(Config, tag=True):
    """deprecated/已废弃"""

    data: str
    secret: bool = False


ConfigItem = Union[
    DictConfig,
    BoolConfig,
    ListConfig,
    ListStrConfig,
    StrConfig,
    IntConfig,
    FloatConfig,
    ImageConfig,
    TimeRConfig,
    Divider,
    FileUploadConfig,
    FilesUploadConfig,
    DateConfig,
    TimeRangeConfig,
    ColorConfig,
    RepeatGroupConfig,
    TimeConfig,
]
