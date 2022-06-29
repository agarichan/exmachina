from __future__ import annotations

import asyncio
import functools
from collections import deque


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

    def __call__(self, func):
        @functools.wraps(func)
        async def wrap(*args, **kwargs):
            async with self:
                return await func(*args, **kwargs)

        return wrap

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
