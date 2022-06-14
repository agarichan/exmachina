from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from collections import defaultdict
from dataclasses import InitVar, dataclass, field
from functools import partial
from time import perf_counter
from typing import Any, Awaitable, Callable, Coroutine, NoReturn, TypeVar

from exmachina.lib.helper import TimeSemaphore, execute_functions, interval_to_second

from . import exception as E
from .depends_contoroller import DependsContoroller
from .helper import set_verbose
from .retry import Retry

try:
    from typing import Literal  # type: ignore
except ImportError:
    from typing_extensions import Literal

DecoratedCallable = TypeVar("DecoratedCallable", bound=Callable[..., Awaitable[None]])
DecoratedResultCallable = TypeVar("DecoratedResultCallable", bound=Callable[..., Awaitable[Any]])


@dataclass
class Emit:
    name: str
    func: Callable[..., Awaitable[None]]
    interval: str  # 次回の実行までの待機時間
    mode: Literal["after", "entire"]
    alive: bool  # 動作中か非動作中か
    count: int | None = None  # ループの回数、未指定の場合無限回 (immutable)


@dataclass
class Execute:
    name: str
    func: Callable[..., Awaitable[Any]]
    concurrent_groups: list[ConcurrentGroup] = field(default_factory=list)
    retry: Retry | None = None


@dataclass
class ConcurrentGroup:
    name: str
    semaphore: TimeSemaphore


@dataclass
class Event:
    epoch: int  # 1,2,...
    previous_execution_time: float  # seconds

    bot: InitVar[Machina]

    def __post_init__(self, bot: Machina):
        self._bot = bot

    def stop(self, emit_name: str, force: bool = False):
        if force:
            task = self._bot._emit_tasks[emit_name]
            task.cancel()
        else:
            self._bot._emits[emit_name].alive = False

    def start(self, emit_name: str) -> asyncio.Task:
        self._bot._add_emit_task(emit_name)
        return self._bot._emit_tasks[emit_name]

    def get(self, emit_name: str) -> asyncio.Task | None:
        return self._bot._emit_tasks.get(emit_name)

    def execute(self, execute_name: str, *args, **kwargs) -> asyncio.Task:
        task = self._bot._add_execute_task(execute_name, *args, **kwargs)
        return task


class TaskManager:
    emit_tasks: list[asyncio.Task[None]]
    execute_tasks: list[asyncio.Task]


class Machina:
    def __init__(
        self,
        *,
        on_startup: list[Callable[[], Coroutine[Any, Any, None]] | Callable[[], None]] = [],
        on_shutdown: list[Callable[[], Coroutine[Any, Any, None]] | Callable[[], None]] = [],
        logger: logging.Logger | None = None,
        verbose: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
    ) -> None:
        self._emits: dict[str, Emit] = {}
        self._executes: dict[str, Execute] = {}
        self._concurrent_groups: dict[str, ConcurrentGroup] = {}
        self._emit_tasks: dict[str, asyncio.Task] = {}
        self._execute_tasks: dict[str, list[asyncio.Task]] = defaultdict(list)
        self._execute_task_executings: dict[str, int] = defaultdict(int)
        self.on_startup = on_startup
        self.on_shutdown = on_shutdown
        self.logger = logger or logging.getLogger(__name__)
        # 全てのタスクが終わったことを確認するようの変数
        self._unfinished_tasks = 0
        self.__finished = None

        if verbose is not None:
            set_verbose(logger, verbose)

    @property
    def _finished(self):
        """loop作成前にEventは作成できないので実行時に取得する"""
        if self.__finished is None:
            self.__finished = asyncio.Event()
        return self.__finished

    async def run(self):
        """botを起動する関数
        全てのemitが停止するまで永遠に待機する
        """
        await self._startup()

        try:
            for emit in self._emits.values():
                if emit.alive:
                    self._add_emit_task(emit.name)

            if self._unfinished_tasks > 0:
                self._finished.clear()
                await self._finished.wait()
                for task in self._emit_tasks.values():
                    await task
        finally:
            await self._shutdown()

    async def _startup(self):
        self.__finished = None
        await execute_functions(self.on_startup)

    async def _shutdown(self):
        await execute_functions(self.on_shutdown)

    def create_concurrent_group(
        self, name: str, entire_calls_limit: int | None = None, time_limit: float = 0, time_calls_limit: int = 1
    ) -> ConcurrentGroup:
        """並列実行の制限グループを作成する

        例えば、1秒あたりに5回まで実行を許可し、実行中タスクの最大数を6個にする場合は
        time_limit = 1, time_calls_limit = 5, entire_calls_limit = 6
        とする

        Args:
            name (str): 名前
            entire_calls_limit (int, optional): グループ全体での最大並列実行数. Defaults to None.
            time_limit (float, optional): 制限時間[sec]. Defaults to 0.
            time_calls_limit (int, optional): 制限時間あたりの最大並列実行数. Defaults to 1.

        Raises:
            E.MachinaException: 同じ名前を登録しようとした時の例外

        Returns:
            ConcurrentGroup: 並列実行の制限グループ
        """
        if name in self._concurrent_groups:
            raise E.MachinaException(f"このconcurrent_groupはすでに登録されています別の名前にしてください: [{name}]")

        cg = ConcurrentGroup(
            name=name,
            semaphore=TimeSemaphore(
                entire_calls_limit=entire_calls_limit, time_limit=time_limit, time_calls_limit=time_calls_limit
            ),
        )
        self._concurrent_groups[name] = cg
        return cg

    def emit(
        self,
        *,
        name: str | None = None,
        count: int | None = None,
        interval: str = "0s",
        mode: Literal["after", "entire"] = "after",
        alive: bool = True,
    ) -> Callable[[Callable[..., Awaitable[None]]], Callable[[], NoReturn]]:
        """Emitを登録します

        Emitは基本的にループで一定間隔で登録された関数を繰り返します
        登録する関数はevent: Eventを引数に取れます

        Args:
            name (str, optional): 名前(ユニーク),省略するとデコレートした関数名を使用する
            count (int, optional): 指定すると指定回数だけループが回ったあと終了する. Defaults to None.
            interval (str, optional): 次の実行までの待機時間. Defaults to "0s".
            mode (Literal['after', 'entire'], optional): 待機時間に処理時間を含むかどうか. Defaults to "after".
                after: 処理の後interval秒待機する
                entire: intervalから処理時間を引いた時間待機する
            alive (bool, optional): ループを稼働するかどうか. Defaults to True.
        """
        if count is not None and count < 0:
            raise E.MachinaException("countは0以上を指定してください")

        def decorator(func: Callable[..., Awaitable[None]]):
            _name = func.__name__ if name is None else name
            emit = Emit(name=_name, func=func, interval=interval, alive=alive, mode=mode, count=count)
            if _name in self._emits:
                raise E.MachinaException(f"このemitはすでには登録されています、別の名前にしてください: [{_name}]")
            self._emits[_name] = emit

            def no_return():
                raise E.MachinaException("emitは直接呼び出せません")

            return no_return

        return decorator

    def execute(self, *, name: str | None = None, concurrent_groups: list[str] = [], retry: Retry | None = None):
        def decorator(func: DecoratedResultCallable) -> DecoratedResultCallable:
            _name = func.__name__ if name is None else name
            _concurrent_groups = [self._concurrent_groups[cg_name] for cg_name in concurrent_groups]
            execute = Execute(name=_name, func=func, concurrent_groups=_concurrent_groups, retry=retry)
            if _name in self._executes:
                raise E.MachinaException(f"このexecuteはすでには登録されています、別の名前にしてください: [{_name}]")
            self._executes[_name] = execute

            @functools.wraps(func)
            def wrap(*args, **kwargs):
                task = self._add_execute_task(_name, *args, **kwargs)
                return task

            return wrap  # type: ignore

        return decorator

    def _add_emit_task(self, name: str) -> str:
        emit = self._emits.get(name)
        if emit is None:
            raise E.MachinaException(f"emitsに存在しないnameを指定しています: [{name}]")

        task = self._emit_tasks.get(name)
        if task is not None:
            if not task.done():
                self.logger.warning(f"emit taskを起動しようとしましたが、すでに作動中です: [{name}]")
                return name

        emit.alive = True

        @cancelled_wrapper(name, "emit", self.logger)
        async def func():
            return await set_interval(emit, self)

        task = asyncio.create_task(func())
        task.add_done_callback(partial(self._emit_task_done, emit))
        self._emit_tasks[emit.name] = task
        self._unfinished_tasks += 1

        return name

    def _emit_task_done(self, emit: Emit, _: asyncio.Task):
        """emitのtaskが終了した時(cancelも含む)に呼ばれるcallback関数
        タスクが全て終わったことを確認するための変数を更新する
        """
        self._unfinished_tasks -= 1
        emit.alive = False
        self.logger.debug(f'Done emit task: "{emit.name}", remain tasks: {self._unfinished_tasks}')
        if self._unfinished_tasks == 0:
            self._finished.set()

    def _add_execute_task(self, name: str, *args, **kwargs) -> asyncio.Task:
        execute = self._executes.get(name)
        if execute is None:
            raise E.MachinaException(f"executesに存在しないnameを指定しています: [{name}]")

        tasks = self._execute_tasks[name]

        @cancelled_wrapper(name, "execute", self.logger)
        async def func():
            return await execute_wrapper(execute, self, *args, **kwargs)

        task = asyncio.create_task(func())
        task.add_done_callback(partial(self._execute_task_done, execute))
        tasks.append(task)

        self._unfinished_tasks += 1

        return task

    def _execute_task_done(self, execute: Execute, task: asyncio.Task):
        self._unfinished_tasks -= 1
        tasks = self._execute_tasks[execute.name]
        # 終了したこのタスク自身をリストから消去
        tasks.pop(tasks.index(task))

        if self._unfinished_tasks == 0:
            self._finished.set()


def cancelled_wrapper(name: str, type: Literal["emit", "execute"], logger: logging.Logger):
    def decorator(afunc: Callable[[], Awaitable[Any]]):
        @functools.wraps(afunc)
        async def _inner():
            try:
                return await afunc()
            except asyncio.CancelledError:
                logger.debug(f'Cancelled {type} task: "{name}"')
            except BaseException:
                logger.error(f'Uncatched error {type} task: "{name}"', exc_info=True)
                raise

        return _inner

    return decorator


def get_args(func) -> tuple[list[str], dict[str, Any]]:
    signature = inspect.signature(func)
    args = [k for k, v in signature.parameters.items() if v.default is inspect.Parameter.empty]
    kwargs = {k: v.default for k, v in signature.parameters.items() if v.default is not inspect.Parameter.empty}
    return args, kwargs


async def set_interval(emit: Emit, bot: Machina):
    bot.logger.debug(f'Start emit task: "{emit.name}"')
    interval = interval_to_second(emit.interval)
    previous_execution_time = 0.0
    epoch = 1
    count = emit.count
    while count is None or count > 0:
        # デバッグ用の変数
        event = Event(
            epoch=epoch,
            previous_execution_time=previous_execution_time,
            bot=bot,
        )
        # 引数の設定
        args, kwargs = get_args(emit.func)
        if "event" in args:
            kwargs.update({"event": event})
        # Dependsの実行
        kwargs.update(await DependsContoroller.get_depends_result(emit.func))
        start = perf_counter()
        # 実行
        await emit.func(**kwargs)
        # 計測
        previous_execution_time = perf_counter() - start
        epoch += 1
        if count is not None:
            count -= 1
            if count <= 0:
                break
        if not emit.alive:
            break
        # 待機
        if emit.mode == "after":
            await asyncio.sleep(interval)
        else:
            wait = interval - previous_execution_time
            if wait < 0:
                bot.logger.warning(f"指定されたインターバルより{-wait:.0f}秒以上遅延しています.")
            await asyncio.sleep(0 if wait < 0 else wait)


async def execute_wrapper(execute: Execute, bot: Machina, *args, **kwargs):

    retry = execute.retry or (lambda func: func)

    @retry
    async def nest(concurrent_groups: list[ConcurrentGroup]):
        if concurrent_groups != []:
            async with concurrent_groups[0].semaphore:
                return await nest(concurrent_groups[1:])
        else:
            bot._execute_task_executings[execute.name] += 1
            _t = len(bot._execute_tasks[execute.name])
            _e = bot._execute_task_executings[execute.name]
            bot.logger.debug(f'Start execute task: "{execute.name}" [tasks={_t}, executings={_e}]')
            try:
                # Dependsの実行
                kwargs.update(await DependsContoroller.get_depends_result(execute.func))
                res = await execute.func(*args, **kwargs)
            finally:
                bot._execute_task_executings[execute.name] -= 1
            return res

    return await nest(execute.concurrent_groups)
