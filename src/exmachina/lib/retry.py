from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import wraps
from logging import Logger, getLogger
from random import uniform
from typing import Callable, Generator, Optional, Type, TypeVar

T = TypeVar("T", bound=BaseException)


class RetryRule(ABC):
    def __init__(
        self,
        exception: Type[T],
        retries: Optional[int] = None,
        filter: Optional[Callable[[T], bool]] = None,
    ):
        self.exception = exception
        self.retries = retries
        self.filter = filter

    def __call__(self, logger: Optional[Logger] = None):
        logger = logger or getLogger(__name__)

        def logger_wrap(func):
            retry_count = self.retries
            wait_time = self.generate_wait_time()

            @wraps(func)
            async def inner(*args, **kwargs):
                nonlocal retry_count
                try:
                    return await func(*args, **kwargs)
                except self.exception as e:
                    # filter条件を満たさないエラーはraise
                    if self.filter is not None and self.filter(e) is False:
                        raise
                    # カウントが0以下ならエラーをraise
                    if retry_count is not None:
                        if retry_count <= 0:
                            raise
                        else:
                            retry_count -= 1
                    sleep = next(wait_time)
                    logger.warning(f"[Retry] {e.__class__.__name__}を検知: {sleep}秒後に再実行します (残り{retry_count}回)")
                    await asyncio.sleep(sleep)
                    return await inner(*args, **kwargs)
                except BaseException:
                    raise

            return inner

        return logger_wrap

    @abstractmethod
    def generate_wait_time(self) -> Generator[float, None, None]:
        """次の待機時間を生成するGenerator"""
        raise NotImplementedError


class RetryFixed(RetryRule):
    def __init__(
        self,
        exception: Type[T],
        *,
        wait_time: float,
        retries: Optional[int] = None,
        filter: Optional[Callable[[T], bool]] = None,
    ):
        self.wait_time = wait_time
        super().__init__(exception=exception, retries=retries, filter=filter)

    def generate_wait_time(self) -> Generator[float, None, None]:
        while True:
            yield self.wait_time


class RetryFibonacci(RetryRule):
    def generate_wait_time(self) -> Generator[float, None, None]:
        x, y = 0.0, 1.0
        while True:
            yield y
            x, y = y, x + y


class RetryRange(RetryRule):
    def __init__(
        self,
        exception: Type[T],
        *,
        min: float,
        max: float,
        retries: Optional[int] = None,
        filter: Optional[Callable[[T], bool]] = None,
    ):
        self.min = min
        self.max = max
        super().__init__(exception=exception, retries=retries, filter=filter)

    def generate_wait_time(self) -> Generator[float, None, None]:
        while True:
            yield uniform(max(0, self.min), max(0, self.max))


class RetryExponentialAndJitter(RetryRule):
    def __init__(
        self,
        exception: Type[T],
        *,
        base_wait_time: float = 1.0,
        cap: float = 60 * 60,
        retries: Optional[int] = None,
        filter: Optional[Callable[[T], bool]] = None,
    ):
        self.base_wait_time = base_wait_time
        self.cap = cap
        super().__init__(exception=exception, retries=retries, filter=filter)

    def generate_wait_time(self) -> Generator[float, None, None]:
        retry_count = 0
        yield self.base_wait_time
        while True:
            retry_count += 1
            yield uniform(0, min(self.cap, self.base_wait_time * (2**retry_count)))


@dataclass
class Retry:
    rules: list[RetryRule]
    logger: Logger = getLogger(__name__)

    def __call__(self, func: Callable):
        @wraps(func)
        async def generate_composite(*args, **kwargs):
            return await composite(func, [rule(self.logger) for rule in self.rules])(*args, **kwargs)

        return generate_composite


def composite(base, decorators: list[Callable]):
    if len(decorators) == 0:
        return base

    func = decorators[0]

    @func
    async def wrap(*args, **kwargs):
        return await base(*args, **kwargs)

    return composite(wrap, decorators[1:])
