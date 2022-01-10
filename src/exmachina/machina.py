from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable


class Machina:
    def __init__(self) -> None:
        ...

    async def __aenter__(self) -> Machina:
        return self

    async def __aexit__(self, ex_type, ex_value, trace) -> None:
        ...

    def run(self):
        asyncio.run(self.loop())

    async def loop(self):
        while True:
            ...

    async def stop(self):
        ...

    async def error_handling(self, execute: Callable, executor_name: str) -> None:
        try:
            await execute()
        except Exception:
            print(executor_name)
            raise

    def trigger(self, execute: Callable[..., Any], *, interval: str = "1s"):
        def decorator(func: Callable[..., Any]) -> Callable[[], Any]:
            return func()

        return decorator

    def executor(
        self,
        wrapped: Callable | None = None,
        *,
        max_retries: int = 0,
        retry_interval: int = 1,
    ):
        if wrapped is None:
            return functools.partial(self.executor, max_retries=max_retries, retry_interval=retry_interval)

        def decorator(func: Callable[..., Any]) -> Callable[[], Any]:
            return func()

        return decorator


class Trigger:
    def __init__(self, execute: Callable, interval: str) -> None:
        self.execute = execute
        self.interval = interval


bot = Machina()


@bot.execute()
async def order_execute():
    await asyncio.sleep(1)
    print("ordered!!")


@bot.trigger(execute=lambda: order_execute(), interval="500ms")
async def order_trigger() -> bool:
    ...
    return True


@bot.exception_handler()
async def http_exceptiopn_handler(exc):
    ...
    raise exc


bot.run()
