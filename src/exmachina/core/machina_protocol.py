from __future__ import annotations

from typing import Protocol


class MachinaProtocol(Protocol):
    async def run(self):
        """botを起動する関数
        全てのemitが停止するまで永遠に待機する
        """
        raise NotImplementedError

    async def emit(
        self,
        name: str | None = None,
        count: int | None = None,
        interval: str = "0s",
        alive: bool = True,
    ):
        """Emitterを登録するデコレーター

        Emitterは基本的にループであり、一定間隔で登録された関数を繰り返し実行します
        登録する関数は
        * event: EmitEvent を引数に取れます(省略もできます)
        * db: DataBase = Depends(get_db) のようなDpendsも取れます。
        eventは別のEmitterを起動/終了したり、Executeorの起動が行えます

        ```python
        from exmachina import Depends, EmitEvent, Machina
        from .your.module.database import DataBase, get_db

        bot = Machina()

        @bot.emitter("sample_emit", interval="1s")
        async def sample_emit(event: EmitEvent, db: DataBase = Depends(get_db)):
            data = event.
        ```

        Args:
            name (str): 名前(Emitterでユニーク)
            count (int, optional): 指定すると指定回数だけループが回ったあと終了する. Defaults to None.
            interval (str, optional): 次の実行までの待機時間. Defaults to "0s".
            alive (bool, optional): ループを稼働するかどうか.Falseにすると明示的に起動する必要がある Defaults to True.
        """
        raise NotImplementedError

    async def execute(self, name: str | None = None, concurrent_groups: list[str] = []):
        """Executeorを登録するデコレーター

        Args:
            name (str): 名前(Executeorでユニーク省略すると)
            concurrent_groups (list[str], optional): 非同期IOの同時実行数の制限. Defaults to [].
        """
        raise NotImplementedError
