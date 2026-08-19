import sys
import json
import datetime
from copy import deepcopy
from typing import Any, Dict, List, Union
from pathlib import Path

from msgspec import ValidationError, json as msgjson, to_builtins
from boltons.fileutils import atomic_save

from rover.logger import logger
from rover.data_store import CONFIGS_PATH, core_path

from .models import (
    Divider,
    IntConfig,
    StrConfig,
    BoolConfig,
    DateConfig,
    DictConfig,
    ColorConfig,
    ConfigItem,
    FloatConfig,
    TimeRConfig,
    ListStrConfig,
    TimeRangeConfig,
    RepeatGroupConfig,
)


def reconcile_config(
    stored: Dict[str, ConfigItem],
    default: Dict[str, ConfigItem],
    *,
    config_name: str = "",
) -> Dict[str, ConfigItem]:
    """把已存配置向默认模板对齐(递归)。非破坏: 缺项补默认、类型不符仅该项重置、
    孤儿键保留; RepeatGroupConfig 的每个 data 项再对 template 递归调和。"""
    result: Dict[str, ConfigItem] = {}
    for key, dft in default.items():
        if key not in stored:
            result[key] = deepcopy(dft)
            continue
        cur = stored[key]
        if type(cur) is not type(dft):
            logger.warning(
                f"[{config_name}] 配置项 {key} 类型不符({type(cur).__name__} != {type(dft).__name__}), 已重置为默认值"
            )
            result[key] = deepcopy(dft)
            continue
        # 同类型: 刷新代码侧元数据, 保留用户 data
        if isinstance(cur, (StrConfig, ListStrConfig)) and isinstance(dft, (StrConfig, ListStrConfig)):
            cur.options = dft.options
        cur.title = dft.title
        cur.desc = dft.desc
        # secret 字段并非所有类型都有 (Divider / ColorConfig 无), 条件访问防 AttributeError
        if not isinstance(cur, (Divider, ColorConfig)) and not isinstance(dft, (Divider, ColorConfig)):
            cur.secret = dft.secret
        # 递归分支: 组模板由代码所有(覆盖), data 每项对 template 再调和
        if isinstance(cur, RepeatGroupConfig) and isinstance(dft, RepeatGroupConfig):
            cur.template = deepcopy(dft.template)
            cur.data = [reconcile_config(item, dft.template, config_name=config_name) for item in cur.data]
        result[key] = cur
    # 孤儿键(默认里没有)保留, 不静默丢用户数据
    for key, val in stored.items():
        if key not in default:
            result[key] = val
    return result


def _rebuild_group_item(raw: Dict[str, Any], template: Dict[str, ConfigItem]) -> Dict[str, ConfigItem]:
    """用前端回传的值 raw(字段名->值) + template 重建一组 Dict[str, ConfigItem]。
    嵌套 RepeatGroupConfig 递归重建; 其余叶子把值写进 .data。"""
    out: Dict[str, ConfigItem] = {}
    for key, field in template.items():
        proto = deepcopy(field)
        if isinstance(proto, RepeatGroupConfig) and isinstance(field, RepeatGroupConfig):
            sub_raw = raw[key] if key in raw and isinstance(raw[key], list) else []
            proto.data = [_rebuild_group_item(r, field.template) for r in sub_raw if isinstance(r, dict)]
        elif not isinstance(proto, Divider) and key in raw:
            proto.data = raw[key]
        out[key] = proto
    return out


class StringConfig:
    def __new__(cls, *args, **kwargs):
        # 判断是否已经被初始化
        if len(args) >= 1:
            name = args[0]
        else:
            name = kwargs.get("config_name")

        if name is None:
            raise ValueError("Config.name is None!")

        if name in all_config_list:
            return all_config_list[name]
        else:
            _config = super().__new__(cls)
            all_config_list[name] = _config
            return _config

    def __init__(
        self,
        config_name: str,
        CONFIG_PATH: Union[Path, List[Path]],
        config_list: Dict[str, ConfigItem],
    ) -> None:
        """
        初始化配置文件管理器。

        Args:
            config_name: 配置名称，用于标识配置项。
            CONFIG_PATH: 配置文件路径，可以是单个路径或路径列表。
                         当为列表时，将按照以下逻辑处理：
                         1. 首先检查列表中除最后一个路径外的其他路径是否存在配置文件
                         2. 如果在 [0:-1] 范围内的任何路径找到配置文件，
                            会将其安全迁移到最后一个路径（index=-1）所指向的位置
                         3. 最终加载和使用的配置文件始终是 index=-1 指向的路径
                         4. 迁移过程中，原有配置文件会被读取后写入新位置，然后删除
                         5. 如果目标路径已存在配置文件，则不会进行迁移操作
            config_list: 配置项的默认字典，用于初始化或校验配置。

        Example:
            # 单路径方式
            CONFIG_PATH = Path("config.json")

            # 多路径方式 - 会从 path1 迁移到最终路径
            CONFIG_PATH = [Path("old_config.json"), Path("new_config.json")]
        """
        self.config_list = config_list
        self.config_default = config_list
        self.config_name = config_name
        self.CONFIG_PATH: Path = None  # type: ignore

        if isinstance(CONFIG_PATH, list):
            # 按照 [0:-1] 的顺序查找是否存在配置文件
            for old_path in CONFIG_PATH[:-1]:
                if old_path.exists():
                    final_path = CONFIG_PATH[-1]
                    # 安全迁移：将找到的配置文件迁移到最终路径
                    self._migrate_config(old_path, final_path)
                    break
            # 最终配置文件路径始终为列表的最后一个元素
            CONFIG_PATH = CONFIG_PATH[-1]

        if not CONFIG_PATH.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_PATH, "wb") as file:
                file.write(msgjson.encode(config_list))

        self.CONFIG_PATH = CONFIG_PATH
        self.config: Dict[str, ConfigItem] = {}  # type: ignore
        # 获取调用者的插件名
        self.plugin_name = self._get_caller_plugin_name()
        self.update_config()

    def _migrate_config(self, old_path: Path, new_path: Path) -> None:
        """
        安全地将配置文件从旧路径迁移到新路径。

        只有当新路径不存在配置文件时，才会进行迁移操作。
        迁移过程：读取旧配置 -> 写入新路径 -> 删除旧文件

        Args:
            old_path: 旧的配置文件路径。
            new_path: 新的配置文件路径。
        """
        # 如果新路径已存在配置文件，则不进行迁移
        if new_path.exists():
            logger.info(f"[{self.config_name}] 目标配置文件已存在, 跳过迁移: {old_path}")
            return

        # 确保目标目录存在
        new_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 读取旧配置文件内容
            with open(old_path, "r", encoding="UTF-8") as f:
                content = f.read()

            # 写入新路径
            with open(new_path, "w", encoding="UTF-8") as f:
                f.write(content)

            # 删除旧文件
            old_path.unlink()

            logger.info(f"[{self.config_name}] 配置文件已迁移: {old_path} -> {new_path}")
        except Exception as e:
            logger.error(f"[{self.config_name}] 配置文件迁移失败: {e}")

    def _get_caller_plugin_name(self):
        """调用者所在的插件包名(service 下第一级目录), 运行时自身返回 None。"""
        try:
            frame = sys._getframe(2)
            caller = Path(frame.f_code.co_filename).resolve()
            rel = caller.relative_to(core_path.parent.resolve())
        except (ValueError, AttributeError):
            return None

        if len(rel.parts) < 2 or rel.parts[0] == core_path.name:
            return None
        return rel.parts[0]

    def __len__(self):
        return len(self.config)

    def __iter__(self):
        return iter(self.config)

    def __getitem__(self, key) -> ConfigItem:
        return self.config[key]

    def get_raw_config(self) -> Dict:
        return to_builtins(self.config)

    def sort_config(self):
        _config = {}

        for i in self.config_list:
            if i in self.config:
                _config[i] = self.config[i]

        for i in self.config:
            if i not in _config:
                _config[i] = self.config[i]

        self.config = _config

        self.write_config()

    def write_config(self):
        payload = msgjson.format(msgjson.encode(self.config), indent=4)
        # 内容没变就不落盘: 光是 import 一下配置也会走到这里, 白写一次会碰只读环境的沙箱
        try:
            if self.CONFIG_PATH.read_bytes() == payload:
                return
        except OSError:
            pass
        with atomic_save(
            str(self.CONFIG_PATH),
            text_mode=False,
            overwrite=True,
            overwrite_part=True,
            file_perms=0o644,
        ) as file:
            if file:
                file.write(payload)
            else:
                logger.error(f"[{self.config_name}] 配置文件写入失败!")

    def repair_config(self):
        with open(self.CONFIG_PATH, "r", encoding="UTF-8") as f:
            logger.warning(f"[{self.config_name}] 配置文件格式已变动, 正在修复...")
            temp_config: Dict[str, Any] = json.load(f)

            for key in self.config_list:
                defalut_dict = to_builtins(self.config_list[key])
                if key not in temp_config:
                    continue
                stored = temp_config[key]
                # 容错：已知配置项的值若不是 dict（如被外部模块误写成字符串），
                # 直接当作"格式异常"重置为默认值，避免后续 .keys() 抛 AttributeError。
                if not isinstance(stored, dict):
                    temp_config[key] = defalut_dict
                    continue
                # key 集合一致不代表值类型合法; 不实测一次 decode 会陷入
                # repair <-> decode 死循环 (RecursionError), 故非法条目直接重置。
                try:
                    msgjson.decode(msgjson.encode(stored), type=ConfigItem)
                except ValidationError:
                    temp_config[key] = defalut_dict
                    continue
                if list(stored.keys()) == list(defalut_dict.keys()):
                    continue
                else:
                    temp_config[key] = defalut_dict

            # 旁路字段清理: 非配置结构 (非 dict, 或 dict 但 decode 失败) 一律移除,
            # 保证 repair 后必为合法 Dict[str, ConfigItem]; 合法历史条目仍保留待迁移。
            foreign_keys = [k for k in temp_config if k not in self.config_list]
            for k in foreign_keys:
                v = temp_config[k]
                if isinstance(v, dict):
                    try:
                        msgjson.decode(msgjson.encode(v), type=ConfigItem)
                        continue
                    except ValidationError:
                        pass
                logger.warning(f"[{self.config_name}] 已移除不符合配置结构的旁路字段: {k} ({type(v).__name__})")
                temp_config.pop(k)

        with open(self.CONFIG_PATH, "w", encoding="UTF-8") as f:
            json.dump(temp_config, f, indent=4, ensure_ascii=False)

    def update_config(self):
        # 最多修复一次后重试 decode; repair_config 已保证收敛, 失败兜底重置默认,
        # 杜绝 update_config <-> repair_config 无限递归 (RecursionError)。
        for attempt in range(2):
            try:
                with open(self.CONFIG_PATH, "r", encoding="UTF-8") as f:
                    d = f.read()
            except UnicodeDecodeError:
                with open(self.CONFIG_PATH, "r") as f:
                    d = f.read()

            try:
                self.config: Dict[str, ConfigItem] = msgjson.decode(
                    d,
                    type=Dict[str, ConfigItem],
                )
                break
            except ValidationError:
                if attempt == 0:
                    self.repair_config()
                else:
                    logger.error(f"[{self.config_name}] 配置文件无法解析, 已回退默认值!")
                    self.config = dict(self.config_list)

        # 逐键调和: 补默认 / 类型不符重置 / 刷新元数据; RepeatGroupConfig 递归(见函数)
        self.config = reconcile_config(self.config, self.config_list, config_name=self.config_name)

        # 重新写回
        self.sort_config()

    def get_config(self, key: str, default_value: Any = None) -> Any:
        if key in self.config:
            return self.config[key]
        elif key in self.config_list:
            logger.info(f"[{self.config_name}] 配置项 {key} 不存在, 正在更新配置文件...")
            self.update_config()
            return self.config[key]
        else:
            logger.warning(f"[{self.config_name}] 配置项 {key} 不存在!")
            if default_value is None:
                return BoolConfig("缺省值", "获取错误的配置项", False)

            if isinstance(default_value, str):
                return StrConfig("缺省值", "获取错误的配置项", default_value)
            elif isinstance(default_value, bool):
                return BoolConfig("缺省值", "获取错误的配置项", default_value)
            elif isinstance(default_value, List):
                return ListStrConfig("缺省值", "获取错误的配置项", default_value)
            elif isinstance(default_value, Dict):
                return DictConfig("缺省值", "获取错误的配置项", default_value)
            else:
                return BoolConfig("缺省值", "获取错误的配置项", False)

    def set_config(self, key: str, value: Union[str, List, bool, Dict, int]) -> bool:
        if key in self.config_list:
            item = self.config[key]
            temp = item.data
            # 组配置: 前端回传 List[{字段->值}], 用 template 重建成 List[Dict[str, ConfigItem]]。
            # 必须先于下方通用 list==list 分支, 否则会把裸值直接塞进 data 破坏结构。
            if isinstance(item, RepeatGroupConfig) and isinstance(value, list):
                item.data = [_rebuild_group_item(r, item.template) for r in value if isinstance(r, dict)]
                self.write_config()
                return True
            if type(value) == type(temp):  # noqa: E721
                # 设置值
                self.config[key].data = value  # type: ignore
                # 重新写回
                self.write_config()
                return True
            elif isinstance(item, TimeRConfig) and isinstance(value, list):
                # TimeRConfig 接受 list 类型并转换为 tuple
                self.config[key].data = tuple(value)  # type: ignore
                self.write_config()
                return True
            elif isinstance(item, TimeRangeConfig) and isinstance(value, (list, tuple)) and len(value) == 2:
                # 前端/命令传入嵌套 list, 落库需转换为嵌套 tuple
                start, end = value
                try:
                    item.data = ((int(start[0]), int(start[1])), (int(end[0]), int(end[1])))
                except (ValueError, TypeError, IndexError):
                    logger.warning(f"[{self.config_name}] 配置项 {key} 时间范围格式非法: {value}")
                    return False
                self.write_config()
                return True
            elif isinstance(item, FloatConfig) and isinstance(value, int) and not isinstance(value, bool):
                # 前端可能以整数 JSON (如 10, 而非 10.0) 传入浮点配置, 归一化为 float
                item.data = float(value)
                self.write_config()
                return True
            elif isinstance(item, DateConfig) and isinstance(value, str):
                # 前端/命令传入 ISO 日期字符串, 落库需转换为 datetime.date
                try:
                    item.data = datetime.date.fromisoformat(value)
                except ValueError:
                    logger.warning(f"[{self.config_name}] 配置项 {key} 日期格式非法: {value}")
                    return False
                self.write_config()
                return True
            else:
                logger.warning(f"[{self.config_name}] 配置项 {key} 写入类型不正确!")
                return False
        else:
            return False

    def migrate_from(self, old_configs: Union["StringConfig", List["StringConfig"]]):
        """
        自动从旧配置实例中吸取同名键的数据（仅迁移用户设定的 data 值，保留新配置的 title/desc）。
        完成后自动从旧文件中清理该键。
        """
        if not isinstance(old_configs, list):
            old_configs = [old_configs]

        changed = False

        for old_config in old_configs:
            old_changed = False

            for key in self.config_list:
                if key in old_config.config:
                    # 仅转移最核心的 data 用户数据，这样就不会覆盖新配置的文本描述
                    self.config[key].data = old_config.config[key].data  # type: ignore
                    changed = True

                    old_config.config.pop(key)
                    old_changed = True
                    logger.info(f"[配置迁移] 配置项 {key}: {old_config.config_name} -> {self.config_name}")

            if old_changed:
                old_config.sort_config()

        if changed:
            self.sort_config()


all_config_list: Dict[str, StringConfig] = {}


DATABASE_DEFAULT: Dict[str, ConfigItem] = {
    "db_type": StrConfig(
        "数据库类型",
        "设置喜欢的数据库类型",
        "SQLite",
        ["SQLite", "MySql", "PostgreSQL", "自定义"],
    ),
    "db_driver": StrConfig(
        "MySQL驱动",
        "设置喜欢的MySQL驱动",
        "aiomysql",
        ["aiomysql", "asyncmy"],
    ),
    "db_custom_url": StrConfig(
        "自定义数据库连接地址 (一般无需填写)",
        "设置自定义数据库连接",
        "",
    ),
    "db_host": StrConfig(
        "数据库地址",
        "设置数据库地址",
        "localhost",
        ["localhost"],
    ),
    "db_port": StrConfig(
        "数据库端口",
        "设置数据库端口",
        "3306",
        ["3306"],
    ),
    "db_user": StrConfig(
        "数据库用户名",
        "设置数据库用户名",
        "root",
        ["root", "admin", "postgres"],
    ),
    "db_password": StrConfig(
        "数据库密码",
        "设置数据库密码",
        "root",
        ["root", "123456"],
    ),
    "db_name": StrConfig(
        "数据库名称",
        "设置数据库名称",
        "WavesData",
        ["WavesData"],
    ),
    "db_pool_size": IntConfig(
        "数据库连接池大小",
        "设置数据库连接池大小",
        5,
        options=[5, 10, 20, 30, 40, 50],
    ),
    "db_echo": BoolConfig(
        "数据库调试模式",
        "设置数据库调试模式",
        False,
    ),
    "db_pool_recycle": IntConfig(
        "数据库连接池回收时间",
        "设置数据库连接池回收时间",
        1500,
        options=[1500, 3600, 7200, 14400, 28800],
    ),
}

database_config = StringConfig(
    "数据库配置",
    CONFIGS_PATH / "database_config.json",
    DATABASE_DEFAULT,
)
