import asyncio
import time

import pytest

from exmachina.lib.time_semaphore import TimeSemaphore


@pytest.mark.asyncio
async def test_TimeSemaphore():
    async def func(sem):
        starts = []
        start = time.time()

        async def limited_sleep(num, wait, task_time):
            await asyncio.sleep(wait)
            async with sem:
                starts.append(round(time.time() - start, 2))
                await asyncio.sleep(task_time)

        tasks = [
            asyncio.create_task(limited_sleep(1, 0.00, 0.2)),
            asyncio.create_task(limited_sleep(2, 0.02, 0.1)),
            asyncio.create_task(limited_sleep(3, 0.04, 0.2)),
            asyncio.create_task(limited_sleep(4, 0.06, 0.2)),
            asyncio.create_task(limited_sleep(5, 0.08, 0.2)),
        ]
        await asyncio.wait(tasks)
        return starts

    sem = TimeSemaphore(entire_calls_limit=4, time_calls_limit=3, time_limit=0.1)
    starts = await func(sem)
    assert starts[3] >= 0.1  # 1秒以内で4個目のタスクなのでtask[1]の制限時間切れを待つ必要がある
    assert starts[4] >= 0.12  # 時間制限かつ5個目のタスクなので、task[1]の時間切れとtask[2]の終了を待つ必要がある

    sem = TimeSemaphore(entire_calls_limit=4)
    starts = await func(sem)
    assert starts[3] >= 0.06  # 4つ目まですんなり実行される
    assert starts[4] >= 0.12  # 5つ目は全体の制約でtask[2]の終了を待つ

    sem = TimeSemaphore(time_calls_limit=3, time_limit=0.1)
    starts = await func(sem)
    assert starts[3] >= 0.1  # 1秒以内で4個目のタスクなのでtask[1]の制限時間切れを待つ必要がある
    assert starts[4] >= 0.12  # 1秒以内で同じく4個目(2, 3, 4の次)のタスクなので、task[2]の制限時間切れを待つ必要がある

    # キャンセル
    sem = TimeSemaphore(time_calls_limit=1, time_limit=2)

    async def cancel():
        with pytest.raises(asyncio.CancelledError):
            async with sem:
                await asyncio.sleep(100)

    task1 = asyncio.create_task(cancel())  # sem._value -> 0
    await asyncio.sleep(0)
    assert sem._value == 0
    task2 = asyncio.create_task(cancel())  # sem._valueに変化なし
    await asyncio.sleep(0)
    assert sem._value == 0
    sem._wake_up_next()  # sem._value -> 1
    assert sem._value == 1
    task2.cancel()
    assert sem._value == 1
    task1.cancel()


@pytest.mark.asyncio
async def test_TimeSemaphore_decorator():
    # デコレータとしてTimeSemaphoreを使っても問題ないことを確認

    sem = TimeSemaphore(entire_calls_limit=3, time_calls_limit=2, time_limit=0.1)

    starts = []
    start = time.time()

    @sem
    async def func(task_time: float):
        starts.append(round(time.time() - start, 2))
        await asyncio.sleep(task_time)

    # 最初とその次のタスクを即時実行する、ただし三つ目は時間制約により0.1秒後に実行される、
    # 四つ目は全体制約により最初のタスクが終了する0.2秒後以降に実行される
    tasks = [
        asyncio.create_task(func(0.2)),
        asyncio.create_task(func(0.2)),
        asyncio.create_task(func(0.1)),
        asyncio.create_task(func(0)),
    ]

    await asyncio.wait(tasks)

    assert starts[2] == 0.1  # 三つ目のタスクが実行されるのは0.1秒後
    assert starts[3] == 0.2  # 1つめ乃至二つ目のタスクの終了を待つので0.2秒後
