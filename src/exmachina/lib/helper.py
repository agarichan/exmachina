from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import re
from collections import deque
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


class _DummySemaphore:
    async def acquire(self):
        ...

    def release(self):
        ...


class TimeSemaphore:
    def __init__(
        self,
        *,
        entire_calls_limit: int | None = None,
        time_limit: float = 0.0,
        time_calls_limit: int = 1,
    ):
        """通常のSemaphoreに加えて、時間あたりの実行回数制限をかけられるSemaphore

        Args:
            entire_calls_limit (int, optional): 全体の最大並列実行数. Defaults to None.
            time_limit (float, optional): 時間制限[sec]. Defaults to 0.0.
            time_calls_limit (int, optional): 時間制限あたりの最大並列実行数. Defaults to 1.
        """
        self._value = time_calls_limit
        self._time_limit = time_limit
        self.__loop = None
        self._waiters = deque()
        self.entire_calls_limit = entire_calls_limit
        self.__sem = None

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(self, *args) -> None:
        self.release()

    @property
    def _loop(self):
        if self.__loop is None:
            self.__loop = asyncio.events.get_event_loop()  # 3.7~
        return self.__loop

    @property
    def _sem(self):
        if self.__sem is None:
            self.__sem = (
                _DummySemaphore() if self.entire_calls_limit is None else asyncio.Semaphore(self.entire_calls_limit)
            )
        return self.__sem

    async def acquire(self) -> bool:
        await self._sem.acquire()

        if self._time_limit == 0.0:
            return True

        while self._value <= 0:
            fut = self._loop.create_future()
            self._waiters.append(fut)
            try:
                await fut
            except BaseException:
                fut.cancel()
                if self._value > 0 and not fut.cancelled():
                    self._value -= 1
                    self._wake_up_next()
                raise
        self._value -= 1
        self._loop.call_later(self._time_limit, self._wake_up_next)
        return True

    def release(self):
        self._sem.release()

    def _wake_up_next(self):
        self._value += 1
        while self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_result(None)
                return


async def execute_functions(funcs: list[Callable[[], Coroutine[Any, Any, None]] | Callable[[], None]]):
    for func in funcs:
        if inspect.iscoroutinefunction(func):
            await func()  # type: ignore
        elif inspect.isfunction(func) or inspect.ismethod(func):
            func()
