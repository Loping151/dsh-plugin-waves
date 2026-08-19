"""功能注册。插件用 Plugins/SV 声明命令, 触发器按前缀展开后进 SL 供分发器遍历。"""

from __future__ import annotations

import traceback
from copy import deepcopy
from functools import wraps
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional, Set, Tuple, Union

from rover.logger import logger
from rover.models import Event
from rover.trigger import Trigger, TriggerType

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_PLUGINS_DIR = _SERVICE_ROOT / "plugins"

# file/meta/message 匹配不读 prefix, 展开只会产生等价副本导致重复执行
_PREFIXLESS_TYPES = frozenset({"file", "meta", "message"})


class SVList:
    def __init__(self):
        self.lst: Dict[str, SV] = {}
        self.plugins: Dict[str, Plugins] = {}
        self.detail_lst: Dict[Plugins, List[SV]] = {}

    @property
    def get_lst(self):
        return self.lst


SL = SVList()


def _configured_prefix() -> Optional[List[str]]:
    """命令前缀由本地配置统一决定; 逗号分隔多个, 空表示不需要前缀。"""
    import re

    from rover.config import core_config

    value = core_config.get_config("command_prefix")
    if not isinstance(value, str):
        return None
    return [p for p in (x.strip() for x in re.split(r"[,，]", value)) if p]


def _sv_overrides(sv_name: str) -> Dict:
    from rover.config import core_config

    table = core_config.get_config("sv")
    if isinstance(table, dict):
        one = table.get(sv_name)
        if isinstance(one, dict):
            return one
    return {}


def _caller_plugin_name() -> str:
    """插件名取 plugins 下一级目录名, 与上游的注册名一致。"""
    for frame in reversed(traceback.extract_stack()[:-1]):
        try:
            rel = Path(frame.filename).resolve().relative_to(_PLUGINS_DIR)
        except (ValueError, OSError):
            continue
        if rel.parts:
            return rel.parts[0]
    return "XutheringWavesUID"


def modify_func(func):
    @wraps(func)
    async def wrapper(bot, event: Event):
        try:
            return await func(bot, event)
        except Exception as e:
            logger.error(f"执行命令 {event.command} 时出现错误")
            logger.exception(e)

    return wrapper


class Plugins:
    def __new__(cls, *args, **kwargs):
        name = args[0] if len(args) >= 1 else kwargs.get("name")
        if name is None:
            raise ValueError("Plugins.name is None!")
        if name in SL.plugins and not kwargs.get("force"):
            return SL.plugins[name]
        _plugin = super().__new__(cls)
        _plugin.__init__(*args, **kwargs)
        SL.plugins[name] = _plugin
        return _plugin

    def __hash__(self) -> int:
        return hash(f"{self.name}{self.priority}{self.pm}{self.area}")

    def __eq__(self, other):
        if isinstance(other, Plugins):
            return (self.name, self.pm, self.priority) == (other.name, other.pm, other.priority)
        return False

    def __init__(
        self,
        name: str = "",
        pm: int = 6,
        priority: int = 5,
        enabled: bool = True,
        area: Literal["GROUP", "DIRECT", "ALL", "SV"] = "SV",
        black_list: List = [],
        white_list: List = [],
        sv: Dict = {},
        prefix: Union[List[str], str] = [],
        force_prefix: List[str] = [],
        disable_force_prefix: bool = False,
        allow_empty_prefix: Optional[bool] = None,
        force: bool = False,
        alias: List[str] = [],
    ):
        if isinstance(prefix, str):
            prefix = [prefix]
        configured = _configured_prefix()
        if configured is not None:
            force_prefix = configured
            prefix = []
            disable_force_prefix = False
            allow_empty_prefix = not configured
        if allow_empty_prefix is None:
            _pf = [p for p in prefix + force_prefix if p != ""]
            allow_empty_prefix = not _pf

        self.name = name
        self.priority = priority
        self.enabled = enabled
        self.pm = pm
        self.black_list = black_list
        self.area = area
        self.white_list = white_list
        self.sv: Dict[str, SV] = {}
        self.prefix = prefix
        self.allow_empty_prefix = allow_empty_prefix
        self.force_prefix = force_prefix
        self.disable_force_prefix = disable_force_prefix
        self.alias = alias

    def set(self, is_lazy: bool = True, **kwargs):
        for var, value in kwargs.items():
            setattr(self, var, value)

    def enable(self):
        self.set(enabled=True)

    def disable(self):
        self.set(enabled=False)


class SV:
    is_initialized = False

    def __new__(cls, *args, **kwargs):
        name = args[0] if len(args) >= 1 else kwargs.get("name")
        if name is None:
            raise ValueError("SV.name is None!")
        if name in SL.lst:
            return SL.lst[name]
        _sv = super().__new__(cls)
        SL.lst[name] = _sv
        return _sv

    def __init__(
        self,
        name: str = "",
        pm: int = 6,
        priority: int = 5,
        enabled: bool = True,
        area: Literal["GROUP", "DIRECT", "ALL"] = "ALL",
        black_list: List = [],
        white_list: List = [],
    ):
        if self.is_initialized:
            return
        self.name = name
        self.TL: Dict[str, Dict[str, Trigger]] = {}
        self.is_initialized = True
        self.self_plugin_name = plugins_name = _caller_plugin_name()

        if plugins_name in SL.plugins:
            plugins = SL.plugins[plugins_name]
        else:
            plugins = Plugins(name=plugins_name)

        self.plugins = plugins
        self.priority = priority
        self.enabled = enabled
        self.pm = pm
        self.black_list = black_list
        self.area = area
        self.white_list = white_list

        for key, value in _sv_overrides(name).items():
            if hasattr(self, key):
                setattr(self, key, value)

        plugins.sv[name] = self
        SL.detail_lst.setdefault(plugins, [])
        if self not in SL.detail_lst[plugins]:
            SL.detail_lst[plugins].append(self)

    def set(self, is_lazy: bool = True, **kwargs):
        for var, value in kwargs.items():
            setattr(self, var, value)

    def enable(self):
        self.set(enabled=True)

    def disable(self):
        self.set(enabled=False)

    def _on(
        self,
        type: TriggerType,
        keyword: Union[str, Tuple[str, ...]],
        block: bool = False,
        to_me: bool = False,
        prefix: bool = True,
        to_ai: str = "",
    ):
        def deco(func: Callable) -> Callable:
            keyword_list = (keyword,) if isinstance(keyword, str) else keyword

            _pp = deepcopy(self.plugins.prefix)
            if "" in _pp:
                _pp.remove("")
            if not self.plugins.disable_force_prefix:
                _pp.extend(self.plugins.force_prefix)
            if self.plugins.allow_empty_prefix:
                _pp.append("")
            _pp = list(set(_pp))

            for _k in keyword_list:
                if _k in self.TL:
                    continue
                if type not in self.TL:
                    self.TL[type] = {}
                if prefix and _pp and type not in _PREFIXLESS_TYPES:
                    for _p in _pp:
                        self.TL[type][_p + _k] = Trigger(
                            type, _k, modify_func(func), _p, block, to_me
                        )
                else:
                    self.TL[type][_k] = Trigger(type, _k, modify_func(func), "", block, to_me)

            if to_ai.strip():
                AI_COMMANDS.append(
                    {
                        "sv": self.name,
                        "plugin": self.self_plugin_name,
                        "type": type,
                        "keyword": list(keyword_list),
                        "desc": to_ai.strip(),
                    }
                )

            @wraps(func)
            async def wrapper(bot, msg) -> Optional[Callable]:
                return await func(bot, msg)

            return wrapper

        return deco

    def on_fullmatch(
        self,
        keyword: Union[str, Tuple[str, ...]],
        block: bool = False,
        to_me: bool = False,
        prefix: bool = True,
        to_ai: str = "",
    ) -> Callable:
        return self._on("fullmatch", keyword, block, to_me, prefix, to_ai=to_ai)

    def on_prefix(
        self,
        keyword: Union[str, Tuple[str, ...]],
        block: bool = False,
        to_me: bool = False,
        prefix: bool = True,
        to_ai: str = "",
    ) -> Callable:
        return self._on("prefix", keyword, block, to_me, prefix, to_ai=to_ai)

    def on_suffix(
        self,
        keyword: Union[str, Tuple[str, ...]],
        block: bool = False,
        to_me: bool = False,
        prefix: bool = True,
        to_ai: str = "",
    ) -> Callable:
        return self._on("suffix", keyword, block, to_me, prefix, to_ai=to_ai)

    def on_keyword(
        self,
        keyword: Union[str, Tuple[str, ...]],
        block: bool = False,
        to_me: bool = False,
        prefix: bool = True,
        to_ai: str = "",
    ) -> Callable:
        return self._on("keyword", keyword, block, to_me, prefix, to_ai=to_ai)

    def on_command(
        self,
        keyword: Union[str, Tuple[str, ...]],
        block: bool = False,
        to_me: bool = False,
        prefix: bool = True,
        to_ai: str = "",
    ) -> Callable:
        return self._on("command", keyword, block, to_me, prefix, to_ai=to_ai)

    def on_file(
        self,
        file_type: Union[str, Tuple[str, ...]],
        block: bool = False,
        to_me: bool = False,
        prefix: bool = False,
        to_ai: str = "",
    ) -> Callable:
        return self._on("file", file_type, block, to_me, prefix, to_ai=to_ai)

    def on_regex(
        self,
        pattern: Union[str, Tuple[str, ...]],
        block: bool = False,
        to_me: bool = False,
        prefix: bool = True,
        to_ai: str = "",
    ) -> Callable:
        return self._on("regex", pattern, block, to_me, prefix, to_ai=to_ai)

    def on_message(
        self,
        block: bool = False,
        to_me: bool = False,
        to_ai: str = "",
    ) -> Callable:
        return self._on("message", "message", block, to_me, prefix=False, to_ai=to_ai)

    def on_meta(
        self,
        event_name: Union[str, Tuple[str, ...]],
        block: bool = False,
    ) -> Callable:
        return self._on("meta", event_name, block=block, to_me=False, prefix=False)


AI_COMMANDS: List[Dict] = []


def get_plugin_prefixs(plugin_name: str) -> List[str]:
    plugin = SL.plugins.get(plugin_name)
    if plugin is None:
        raise ValueError(f"插件{plugin_name}不存在!")
    return plugin.prefix


def get_plugin_prefix(plugin_name: str) -> str:
    return get_plugin_prefixs(plugin_name)[0]


def get_plugin_force_prefixs(plugin_name: str) -> List[str]:
    plugin = SL.plugins.get(plugin_name)
    if plugin is None:
        raise ValueError(f"插件{plugin_name}不存在!")
    return plugin.force_prefix


def get_plugin_force_prefix(plugin_name: str) -> str:
    return get_plugin_force_prefixs(plugin_name)[0]


def get_plugin_available_prefix(plugin_name: str) -> str:
    plugin = SL.plugins.get(plugin_name)
    if plugin is None:
        raise ValueError(f"插件{plugin_name}不存在!")
    if not plugin.disable_force_prefix and plugin.force_prefix:
        return plugin.force_prefix[0]
    if plugin.disable_force_prefix and plugin.prefix:
        return plugin.prefix[0]
    return ""


def all_prefixes() -> List[str]:
    out: List[str] = []
    for plugin in SL.plugins.values():
        if not plugin.disable_force_prefix:
            out.extend(plugin.force_prefix)
        out.extend(p for p in plugin.prefix if p)
    # 去重但保序: 配置里写在前面的就排在前面, 卡片上生成的命令才不会每次重启换一个前缀
    seen: Set[str] = set()
    ordered = [p for p in out if not (p in seen or seen.add(p))]
    return sorted(ordered, key=len, reverse=True)
