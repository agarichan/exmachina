import pytest

from exmachina.core.depends_contoroller import DependsContoroller
from exmachina.core.exception import MachinaException

# from exmachina import Depends
from exmachina.core.params import Depends
from exmachina.core.params_function import Depends as fDepends


def depends_function():
    return 42


def depends_generator():
    yield 42


async def depends_async_function():
    return 42


async def depends_async_generator():
    yield 42


@pytest.mark.parametrize(
    "depends",
    [
        Depends(depends_function),
        Depends(depends_generator),
        Depends(depends_async_function),
        Depends(depends_async_generator),
    ],
)
@pytest.mark.asyncio
async def test_depends(depends: Depends):
    res = await DependsContoroller.recurrent_execute_depends(depends)
    assert res == 42
    # test cache
    res = await DependsContoroller.recurrent_execute_depends(depends)
    assert res == 42


@pytest.mark.asyncio
async def test_depends_error():
    class CallableClass:
        def __call__(self):
            return 42

    depends = Depends(CallableClass())
    with pytest.raises(MachinaException):
        await DependsContoroller.recurrent_execute_depends(depends)

    def func(a: int):
        return a

    depends = Depends(func)
    with pytest.raises(MachinaException):
        await DependsContoroller.recurrent_execute_depends(depends)


@pytest.mark.asyncio
async def test_depends_tree():
    def a(x=1):
        return x

    async def b(x: int = fDepends(a)):
        return x

    def c(y=2, x: int = fDepends(b)):
        yield x + y

    async def d(z: int = fDepends(c), x: int = fDepends(b)):
        yield x + z

    async def unwrap_func(q=1, xz: int = fDepends(d)):
        ...

    res = await DependsContoroller.get_depends_result(unwrap_func)

    assert res == dict(xz=4)


def test_repr():
    def a(x=1):
        return x

    assert str(Depends(a, use_cache=False)) == "Depends(a, use_cache=False)"
