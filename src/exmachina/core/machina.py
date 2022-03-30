from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import InitVar, dataclass, field
from functools import partial
from collections import defaultdict
from time import time
from typing import Awaitable, Callable, TypeVar

from exmachina.lib.helper import interval_to_second, TimeSemaphore

from . import exception as E
from .depends_contoroller import DependsContoroller
from .helper import set_verbose


try:
    from typing import Literal  # type: ignore
except ImportError:
    from typing_extensions import Literal

DecoratedCallable = TypeVar("DecoratedCallable", bound=Callable[..., Awaitable[None]])

logger = logging.getLogger(__name__)


@dataclass
class Emit:
    name: str
    func: Callable[..., Awaitable[None]]
    interval: str  # 次回の実行までの待機時間
    alive: bool  # 動作中か非動作中か
    count: int | None = None  # ループの回数、未指定の場合無限回 (immutable)


@dataclass
class Execute:
    name: str
    func: Callable[..., Awaitable[None]]
    concurrent_groups: list[ConcurrentGroup] = field(default_factory=list)


@dataclass
class ConcurrentGroup:
    name: str
    semaphore: TimeSemaphore
    # max_concurrent_calls: int  # 最大並列同時実行数、上限に達したら枠が空くまで待機
    # max_concurrent_time_limit_calls: int  # 最大並列同時実行数、上限に達したら枠が空くまで待機
    # time_limit: str | None = None  # max_concurrent_callsが有効な時間


@dataclass
class Event:
    epoch: int  # 1,2,...
    previous_execution_time: float  # seconds
    previous_interval_delay_time: float  # seconds

    bot: InitVar[Machina]

    def __post_init__(self, bot: Machina):
        self._bot = bot

    def stop(self, emit_name: str, force: bool = False):
        if force:
            self._bot._emit_tasks[emit_name].cancel()
        else:
            self._bot._emits[emit_name].alive = False

    def start(self, emit_name: str):
        self._bot._add_emit_task(emit_name)

    def execute(self, execute_name: str, *args, **kwargs) -> asyncio.Task:
        task = self._bot._add_execute_task(execute_name)
        return task


class TaskManager:
    emit_tasks: list[asyncio.Task[None]]
    execute_tasks: list[asyncio.Task]


class Machina:
    def __init__(
        self, *, verbose: Literal["NOTEST", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None
    ) -> None:
        self._emits: dict[str, Emit] = {}
        self._executes: dict[str, Execute] = {}
        self._concurrent_groups: dict[str, ConcurrentGroup] = {}
        self._emit_tasks: dict[str, asyncio.Task] = {}
        self._execute_tasks: dict[str, list[asyncio.Task]] = defaultdict(list)
        # 全てのタスクが終わったことを確認するようの変数
        self._unfinished_tasks = 0
        self._finished = asyncio.Event()

        set_verbose(verbose)

    async def run(self):
        """botを起動する関数
        全てのemitが停止するまで永遠に待機する
        """
        for emit in self._emits.values():
            if emit.alive:
                self._add_emit_task(emit.name)

        if self._unfinished_tasks > 0:
            self._finished.clear()
            await self._finished.wait()

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
        name: str,
        *,
        count: int | None = None,
        interval: str = "0s",
        alive: bool = True,
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """Emitを登録します

        Emitは基本的にループで一定間隔で登録された関数を繰り返します
        登録する関数はevent: Eventを引数に取れます

        Args:
            name (str): 名前(ユニーク)
            count (int, optional): 指定すると指定回数だけループが回ったあと終了する. Defaults to None.
            interval (str, optional): 次の実行までの待機時間. Defaults to "0s".
            alive (bool, optional): ループを稼働するかどうか. Defaults to True.
        """
        if count is not None and count < 0:
            raise E.MachinaException("countは0以上を指定してください")

        def decorator(func: DecoratedCallable) -> DecoratedCallable:
            emit = Emit(name=name, func=func, interval=interval, alive=alive, count=count)
            if name in self._emits:
                raise E.MachinaException(f"このemitはすでには登録されています、別の名前にしてください: [{name}]")
            self._emits[name] = emit
            return func

        return decorator

    def execute(self, name: str, *, concurrent_groups: list[str] = []):
        def decorator(func: DecoratedCallable) -> DecoratedCallable:
            _concurrent_groups = [self._concurrent_groups[cg_name] for cg_name in concurrent_groups]
            execute = Execute(name=name, func=func, concurrent_groups=_concurrent_groups)
            if name in self._emits:
                raise E.MachinaException(f"このexecuteはすでには登録されています、別の名前にしてください: [{name}]")
            self._executes[name] = execute
            return func

        return decorator

    def _add_emit_task(self, name: str) -> str:
        emit = self._emits.get(name)
        if emit is None:
            raise E.MachinaException(f"emitsに存在しないnameを指定しています: [{name}]")

        task = self._emit_tasks.get(name)
        if task is not None:
            if not task.done():
                logger.warning(f"emit taskを起動しようとしましたが、すでに作動中です: [{name}]")
                return name

        emit.alive = True
        task = asyncio.create_task(cancelled_wrapper(set_interval(emit, self), name, "emit"))
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
        logger.debug(f'Done emit task: "{emit.name}", remain tasks: {self._unfinished_tasks}')
        if self._unfinished_tasks == 0:
            self._finished.set()

    def _add_execute_task(self, name: str) -> asyncio.Task:
        execute = self._executes.get(name)
        if execute is None:
            raise E.MachinaException(f"executesに存在しないnameを指定しています: [{name}]")

        tasks = self._execute_tasks[name]
        task = asyncio.create_task(cancelled_wrapper(execute_wrapper(execute, self), name, "execute"))
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

    def _task_done(self, type: Literal["emit", "execute"]):
        logger.debug(f'Done {type} task: "{emit.name}", remain tasks: {self._unfinished_tasks}')
        self._unfinished_tasks -= 1
        if self._unfinished_tasks == 0:
            self._finished.set()


async def cancelled_wrapper(aw: Awaitable, name: str, type: Literal["emit", "execute"]):
    try:
        await aw
    except asyncio.CancelledError:
        logger.debug(f'Cancelled {type} task: "{name}"')
        raise


async def set_args(func):
    signature = inspect.signature(func)
    args = [k for k, v in signature.parameters.items() if v.default is inspect.Parameter.empty]
    kwargs = {k: v.default for k, v in signature.parameters.items() if v.default is not inspect.Parameter.empty}
    ...


async def set_interval(emit: Emit, bot: Machina):
    logger.debug(f'Start emit task: "{emit.name}"')
    interval = interval_to_second(emit.interval)
    before = time()
    previous_interval_delay_time = 0.0
    previous_execution_time = 0.0
    epoch = 1
    count = emit.count
    while count is None or count > 0:
        previous_interval_delay_time = time() - before - interval
        # デバッグ用の変数
        event = Event(
            epoch=epoch,
            previous_execution_time=previous_execution_time,
            previous_interval_delay_time=previous_interval_delay_time if epoch != 1 else 0.0,
            bot=bot,
        )
        # 引数の設定
        kwargs = {"event": event}
        # Dependsの実行
        kwargs.update(await DependsContoroller.get_depends_result(emit.func))
        if previous_interval_delay_time > 1:
            logger.warning(
                f"指定されたインターバルより{previous_interval_delay_time:.0f}秒以上遅延しています。ブロッキングの時間を減らすなど、emitの処理を見直すことを推奨します。"
            )
        start = time()
        # 実行
        await emit.func(**kwargs)
        # 計測
        previous_execution_time = time() - start
        before = time()
        epoch += 1
        if count is not None:
            count -= 1
            if count <= 0:
                break
        # 待機
        if not emit.alive:
            break
        await asyncio.sleep(interval)


async def execute_wrapper(execute: Execute, bot: Machina):
    logger.debug(f'Start execute task: "{execute.name}"[{len(bot._execute_tasks[execute.name])+1}]')

    ...
