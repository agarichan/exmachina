import asyncio
import time

import pytest

from exmachina.lib.helper import interval_to_second, to_thread


@pytest.mark.parametrize(
    "input, expected",
    [
        ("1d", 86400.0),
        ("1h", 3600.0),
        ("1m", 60.0),
        ("1s", 1.0),
        ("1000ms", 1.0),
        ("0d 0m 10s", 10.0),
        ("1d12h35m59s500ms", 131759.5),
    ],
)
def test_interval_to_second(input, expected):
    assert interval_to_second(input) == expected


def test_interval_to_second_error():
    with pytest.raises(ValueError):
        interval_to_second("")


@pytest.mark.asyncio
async def test_to_thread():
    results = []

    def sleep(x):
        time.sleep(0.001)
        results.append(x)
        return x

    async def async_sleep(x):
        await asyncio.sleep(0.002)
        results.append(x)
        return x

    task2 = asyncio.create_task(to_thread(sleep, 1))
    task1 = asyncio.create_task(async_sleep(2))
    res = await asyncio.gather(task1, task2)
    assert res == [2, 1]
    assert results == [1, 2]
