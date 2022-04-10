from __future__ import annotations

import inspect
from typing import Any, AsyncGenerator, Callable, Generator

from . import exception as E
from .params import Depends


class DependsContoroller:
    generators: list[AsyncGenerator | Generator] = []
    caches: dict[Callable, Any] = {}

    @classmethod
    async def get_depends_result(cls, func: Callable):
        signature = inspect.signature(func)

        kwargs = {}
        for key, arg in signature.parameters.items():
            if not isinstance(arg.default, Depends):
                continue
            kwargs[key] = await cls.recurrent_execute_depends(arg.default)
        return kwargs

    @classmethod
    async def recurrent_execute_depends(cls, depends: Depends):
        func = depends.dependency
        signature = inspect.signature(func)

        if depends.use_cache and func in cls.caches:
            return cls.caches[func]

        kwargs = {}
        for key, arg in signature.parameters.items():
            if arg.default is inspect.Parameter.empty:
                raise E.MachinaException("Dependsにdefault値のない引数を宣言しないでください。")
            if not isinstance(arg.default, Depends):
                kwargs[key] = arg.default
                continue
            kwargs[key] = await cls.recurrent_execute_depends(arg.default)

        if inspect.iscoroutinefunction(func):
            res = await func(**kwargs)
        elif inspect.isasyncgenfunction(func):
            gen = func(**kwargs)
            cls.generators.append(gen)
            res = await gen.__anext__()
        elif inspect.isgeneratorfunction(func):
            gen = func(**kwargs)
            cls.generators.append(gen)
            res = gen.__next__()
        elif inspect.isfunction(func) or inspect.ismethod(func):
            res = func(**kwargs)
        else:
            raise E.MachinaException("funcが想定外のパターンです: {func}")
        if depends.use_cache:
            cls.caches[func] = res
        return res


async def get_depends(func: Callable[..., Any]) -> Any:
    return await DependsContoroller.recurrent_execute_depends(Depends(func))
