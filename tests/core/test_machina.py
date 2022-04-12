import asyncio
from unittest.mock import MagicMock, patch

import pytest

from exmachina.core.exception import MachinaException
from exmachina.core.machina import Event, Machina


@pytest.fixture(scope="class")
def bot():
    return Machina()


class TestMachina:
    def test_concurrent_group(self, bot: Machina):
        bot.create_concurrent_group(name="test", entire_calls_limit=4, time_limit=1, time_calls_limit=2)
        cg = bot._concurrent_groups["test"]

        assert cg.semaphore.entire_calls_limit == 4
        assert cg.semaphore._time_limit == 1
        assert cg.semaphore._value == 2

        # 同名のconcurrent_groupの作成は禁止
        with pytest.raises(MachinaException):
            bot.create_concurrent_group(name="test")

    @pytest.mark.asyncio
    async def test_emit(self, bot: Machina):
        # countに負の値は入れられない
        with pytest.raises(MachinaException):

            @bot.emit(count=-1)
            async def test_emit2():
                ...

        count = 0

        @bot.emit(count=3, interval="5ms")
        async def test_emit1(event: Event):
            try:
                nonlocal count
                count += 1
            except BaseException as e:
                print(type(e))

        # emitの直接呼び出しは禁止
        with pytest.raises(MachinaException):
            test_emit1()

        assert "test_emit1" in bot._emits

        # count3のチェック
        await bot.run()
        assert count == 3
        # 一度完了したemitはフラグが折れる
        assert bot._emits["test_emit1"].alive is False
        # 再実行してもカウントは増えない
        await bot.run()
        assert count == 3

        # 同名のemitを登録するとエラー
        with pytest.raises(MachinaException):

            @bot.emit(name="test_emit1")
            async def _():
                ...

        # emitの再スタートと強制終了
        @bot.emit(count=1)
        async def test_emit3(event: Event):
            # test_emit1の再実行
            event.start(emit_name="test_emit1")
            # 二重起動(warningが出るだけ)
            event.start(emit_name="test_emit1")

            await asyncio.sleep(0)
            event.stop(emit_name="test_emit1", force=True)

            with pytest.raises(MachinaException):
                event.start(emit_name="test_not_exists")

        await bot.run()
        assert count == 4

        # emitの再スタートと待機終了(次の1ループの終了までは保障する)
        @bot.emit(count=1)
        async def test_emit4(event: Event):
            # test_emit1の再実行
            event.start(emit_name="test_emit1")
            event.stop(emit_name="test_emit1")

        await bot.run()
        assert count == 5

        # entireモード
        @bot.emit(count=2, mode="entire", interval="50ms")
        async def test_emit5():
            await asyncio.sleep(0.1)

        await bot.run()

    @pytest.mark.asyncio
    async def test_execute(self, bot: Machina):
        @bot.execute(concurrent_groups=["test"])
        async def test_execute1(x: int):
            await asyncio.sleep(0)
            return x

        # 同一名のexecuteの再定義
        with pytest.raises(MachinaException):

            @bot.execute(name="test_execute1")
            async def dummy():
                ...

        @bot.emit(count=1)
        async def test_emit6(event: Event):
            # eventを介したexecuteの呼び出し
            x = await event.execute("test_execute1", 42)
            assert x == 42
            # 直接のexecuteを呼びだし
            x = await test_execute1(42)
            assert x == 42

            # 存在しないexecuteの呼び出し
            with pytest.raises(MachinaException):
                event.execute("test_not_exist")

        await bot.run()

    @pytest.mark.asyncio
    async def test_start_shutdown(self):
        expect = {"async_start": False, "start": False, "async_shutdown": False, "shutdown": False}

        async def async_start():
            expect["async_start"] = True

        def start():
            expect["start"] = True

        async def async_shutdown():
            expect["async_shutdown"] = True

        def shutdown():
            expect["shutdown"] = True

        bot = Machina(on_startup=[async_start, start], on_shutdown=[async_shutdown, shutdown])

        await bot.run()

        assert all(expect.values())

    @pytest.mark.asyncio
    async def test_error(self, bot: Machina):
        @bot.emit(count=1)
        async def emit_error():
            raise ZeroDivisionError

        with pytest.raises(ZeroDivisionError):
            await bot.run()

    @patch("exmachina.core.machina.set_verbose")
    def test_set_verbose(self, mock: MagicMock):
        # set_verboseの呼び出し確認
        Machina(verbose="DEBUG")
        assert mock.call_count == 1
