from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import re
from typing import Any, Callable, Coroutine

_times = dict(d=86400.0, h=3600.0, m=60.0, s=1.0, ms=0.001)
_r = (
    r"^"
    r"(?=.*[dhms(ms)]$)"
    r"((?P<d>\d+(\.\d+)?)(?:d\s*))?"
    r"((?P<h>\d+(\.\d+)?)(?:h\s*))?"
    r"((?P<m>\d+(\.\d+)?)(?:m\s*))?"
    r"((?P<s>\d+(\.\d+)?)(?:s\s*))?"
    r"((?P<ms>\d+)(?:ms\s*))?"
    r"$"
)


def interval_to_second(interval: str) -> float:
    """1s12h35m59s500msのような文字列を秒数に変換する

    Args:
        interval (str): 時間を表す文字列

    Raises:
        ValueError: 変換できなかったときの例外

    Returns:
        float: 秒数
    """
    m = re.match(_r, interval)

    if m is None:
        raise ValueError(f'intervalは[1d12h35m59s500ms]のような形である必要があります。入力: "{interval}"')

    return sum([_times[k] * float(v) for k, v in m.groupdict().items() if v is not None])


async def to_thread(func, *args, **kwargs):
    """Asynchronously run function *func* in a separate thread.

    Any *args and **kwargs supplied for this function are directly passed
    to *func*. Also, the current :class:`contextvars.Context` is propagated,
    allowing context variables from the main thread to be accessed in the
    separate thread.

    Return a coroutine that can be awaited to get the eventual result of *func*.
    """
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    func_call = functools.partial(ctx.run, func, *args, **kwargs)
    return await loop.run_in_executor(None, func_call)


async def execute_functions(funcs: list[Callable[[], Coroutine[Any, Any, None]] | Callable[[], None]]):
    for func in funcs:
        if inspect.iscoroutinefunction(func):
            await func()  # type: ignore
        elif inspect.isfunction(func) or inspect.ismethod(func):
            func()
