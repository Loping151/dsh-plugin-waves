"""线程池。to_thread 是装饰器：被装饰函数为协程函数时在线程内新建事件循环执行。"""

import asyncio
import functools
import inspect
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable, Coroutine, ParamSpec, TypeVar, cast, overload

T = TypeVar("T")
P = ParamSpec("P")

_executor = ThreadPoolExecutor(max_workers=10)


@overload
def to_thread(func: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, Awaitable[T]]: ...


@overload
def to_thread(func: Callable[P, T]) -> Callable[P, Awaitable[T]]: ...


def to_thread(func: Callable[..., Any]) -> Callable[..., Awaitable[Any]]:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()

        def sync_worker():
            if inspect.iscoroutinefunction(func):
                new_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(new_loop)
                    return new_loop.run_until_complete(func(*args, **kwargs))
                finally:
                    new_loop.close()
            return func(*args, **kwargs)

        return await loop.run_in_executor(_executor, sync_worker)

    return cast(Callable[..., Awaitable[Any]], wrapper)


run_in_thread_pool = to_thread
