"""启动/关闭钩子注册与执行。

三类钩子：
- on_core_start_before: 阻塞式，服务开始接受连接前必须跑完（数据库迁移等）
- on_core_start: 启动后执行
- on_core_shutdown: 关闭前执行

同一 priority 的钩子并发执行，全部完成后再进入下一 priority；单个钩子失败只记日志。
"""

import asyncio
from dataclasses import dataclass, field
from itertools import groupby
from typing import Any, Callable, List, Optional, Set, TypeVar, overload

from rover.logger import logger

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class _DefHook:
    priority: int
    func: Callable = field(compare=False)

    def __hash__(self) -> int:
        return hash(self.func)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _DefHook):
            return self.func is other.func
        return NotImplemented

    def __lt__(self, other: "_DefHook") -> bool:
        return self.priority < other.priority


core_start_def: Set[_DefHook] = set()
core_start_before_def: Set[_DefHook] = set()
core_shutdown_def: Set[_DefHook] = set()


@overload
def on_core_start(func: F, /) -> F: ...


@overload
def on_core_start(func: None = None, /, priority: int = 0) -> Callable[[F], F]: ...


def on_core_start(func: Optional[Callable] = None, /, priority: int = 0):
    def decorator(f: Callable) -> Callable:
        core_start_def.add(_DefHook(priority=priority, func=f))
        return f

    if func is not None:
        return decorator(func)
    return decorator


@overload
def on_core_start_before(func: F, /) -> F: ...


@overload
def on_core_start_before(func: None = None, /, priority: int = 0) -> Callable[[F], F]: ...


def on_core_start_before(func: Optional[Callable] = None, /, priority: int = 0):
    def decorator(f: Callable) -> Callable:
        core_start_before_def.add(_DefHook(priority=priority, func=f))
        return f

    if func is not None:
        return decorator(func)
    return decorator


@overload
def on_core_shutdown(func: F, /) -> F: ...


@overload
def on_core_shutdown(func: None = None, /, priority: int = 0) -> Callable[[F], F]: ...


def on_core_shutdown(func: Optional[Callable] = None, /, priority: int = 0):
    def decorator(f: Callable) -> Callable:
        core_shutdown_def.add(_DefHook(priority=priority, func=f))
        return f

    if func is not None:
        return decorator(func)
    return decorator


async def _execute(hooks: Set[_DefHook], tag: str) -> None:
    try:
        sorted_defs: List[_DefHook] = sorted(hooks)
    except Exception as e:
        logger.exception(f"[{tag}] 钩子排序失败: {e}")
        return

    logger.info(f"[{tag}] 执行钩子: {[hook.func.__name__ for hook in sorted_defs]}")
    for _, group in groupby(sorted_defs, key=lambda h: h.priority):
        group_hooks = list(group)
        results = await asyncio.gather(
            *[
                (hook.func() if asyncio.iscoroutinefunction(hook.func) else asyncio.to_thread(hook.func))
                for hook in group_hooks
            ],
            return_exceptions=True,
        )
        for hook, result in zip(group_hooks, results):
            if isinstance(result, BaseException):
                logger.error(
                    f"[{tag}] 钩子 {hook.func.__name__} 执行失败: {result}",
                    exc_info=result,
                )


async def core_start_before_execute() -> None:
    await _execute(core_start_before_def, "启动前钩子")


async def core_start_execute() -> None:
    await _execute(core_start_def, "启动钩子")


async def core_shutdown_execute() -> None:
    await _execute(core_shutdown_def, "关闭钩子")
