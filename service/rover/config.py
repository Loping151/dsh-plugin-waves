"""核心配置: 数据根下的 config.json。"""

import json
import time
from typing import Any, Dict, List, Union, Literal, overload

from boltons.fileutils import atomic_save

from rover.data_store import get_res_path

CONFIG_PATH = get_res_path() / "config.json"

CONFIG_DEFAULT: Dict[str, Any] = {
    # 把插件作为工具暴露给模型(占少量上下文); 关闭后只能用 /ww 命令
    "expose_to_model": True,
    # 卡片头部头像: 本地图片路径 / http(s) 链接 / QQ 号; 置空用插件自带的
    "avatar": "",
    # 服务监听地址; 登录页与字体链接也按它拼
    "HOST": "127.0.0.1",
    "PORT": "9777",
    # 命令前缀, 多个用逗号分隔, 置空则不需要前缀
    "command_prefix": "ww",
    # 本机使用者标识, 数据都归属它, 一般不用改
    "masters": ["local"],
    # 定时任务允许的迟到秒数
    "misfire_grace_time": 90,
    # 单条命令最长执行秒数
    "command_timeout": 300,
    # 竖图(高>宽)在会话区里的最大宽度百分比
    "image_portrait_max_percent": 50,
    # 横图(宽>=高)的最大宽度百分比
    "image_landscape_max_percent": 75,
    # 渲染产物目录容量上限(MB), 超出时按最旧优先淘汰; 0 表示不限
    "media_max_mb": 512,
    # 日志级别; 输出固定为 stdout + data/logs 下的滚动文件(有上限, 不会涨爆)
    "log_level": "INFO",
    # 已写过初值的插件, 写过就不再覆盖用户的选择
    "seeded": [],
    # 单个功能项的覆盖: {"功能名": {"enabled": false, "pm": 0}}
    "sv": {},
}

STR_CONFIG = Literal["HOST", "PORT", "command_prefix", "avatar", "log_level"]
INT_CONFIG = Literal[
    "misfire_grace_time",
    "command_timeout",
    "media_max_mb",
    "image_portrait_max_percent",
    "image_landscape_max_percent",
]
LIST_CONFIG = Literal["masters", "seeded"]
DICT_CONFIG = Literal["sv"]
BOOL_CONFIG = Literal["expose_to_model"]


class CoreConfig:
    def __init__(self) -> None:
        if not CONFIG_PATH.exists():
            with open(CONFIG_PATH, "w", encoding="UTF-8") as file:
                json.dump(CONFIG_DEFAULT, file, indent=4, ensure_ascii=False)

        self.update_config()

    def write_config(self):
        max_retries = 3
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                with atomic_save(
                    str(CONFIG_PATH),
                    text_mode=False,
                    overwrite=True,
                    overwrite_part=True,
                    file_perms=0o644,
                ) as file:
                    if file:
                        json_str = json.dumps(
                            self.config,
                            indent=4,
                            ensure_ascii=False,
                        )
                        file.write(json_str.encode("utf-8"))
                    else:
                        raise RuntimeError("写入配置文件失败!")
                return
            except OSError as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise RuntimeError(f"写入配置文件失败，已重试 {max_retries} 次: {str(e)}")

    def update_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="UTF-8") as f:
                self.config: Dict[str, Any] = json.load(f)
        except UnicodeDecodeError:
            with open(CONFIG_PATH, "r") as f:
                self.config = json.load(f)

        # 旧版把日志写成 {level,output,module} 一整块, 只保留级别
        legacy = self.config.pop("log", None)
        if isinstance(legacy, dict) and "log_level" not in self.config:
            self.config["log_level"] = legacy.get("level") or "INFO"

        # 对没有的值，添加默认值
        for key in CONFIG_DEFAULT:
            if key not in self.config:
                self.config[key] = CONFIG_DEFAULT[key]
            if isinstance(CONFIG_DEFAULT[key], Dict):
                for sub_key in CONFIG_DEFAULT[key]:
                    if sub_key not in self.config[key]:
                        self.config[key][sub_key] = CONFIG_DEFAULT[key][sub_key]

    @overload
    def get_config(self, key: STR_CONFIG) -> str: ...

    @overload
    def get_config(self, key: LIST_CONFIG) -> List: ...

    @overload
    def get_config(self, key: INT_CONFIG) -> int: ...

    def get_config(self, key: str) -> Union[str, Dict, List, int, bool]:
        if key in self.config:
            return self.config[key]
        elif key in CONFIG_DEFAULT:
            self.update_config()
            return self.config[key]
        else:
            return {}

    @overload
    def set_config(self, key: STR_CONFIG, value: str) -> bool: ...

    @overload
    def set_config(self, key: LIST_CONFIG, value: List) -> bool: ...

    @overload
    def set_config(self, key: INT_CONFIG, value: int) -> bool: ...

    def set_config(self, key: str, value: Union[str, List, Dict, int, bool]) -> bool:
        if key in CONFIG_DEFAULT:
            self.config[key] = value
            self.write_config()
            return True
        else:
            return False

    def lazy_write_config(self):
        self.write_config()

    def lazy_set_config(self, key: str, value: Union[str, List, Dict, int, bool]):
        """只改内存, 由 lazy_write_config 统一落盘。"""
        if key in CONFIG_DEFAULT:
            self.config[key] = value


core_config: CoreConfig = CoreConfig()
