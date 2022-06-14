# Ex-Machina

<p align="center">
  <em>python で bot 書くためのフレームワーク</em>
</p>
<p align="center">
<a href="https://github.com/agarichan/exmachina/actions/workflows/test.yaml" target="_blank">
  <img src="https://github.com/agarichan/exmachina/actions/workflows/test.yaml/badge.svg?branch=main" alt="Test">
</a>
<a href="https://codecov.io/gh/agarichan/exmachina" target="_blank">
  <img src="https://img.shields.io/codecov/c/github/agarichan/exmachina?color=%2334D058" alt="Coverage">
</a>
<a href="https://pypi.org/project/exmachina" target="_blank">
  <img src="https://img.shields.io/pypi/v/exmachina?color=%2334D058&label=pypi%20package" alt="Package version">
</a>
<a href="https://pypi.org/project/exmachina" target="_blank">
  <img src="https://img.shields.io/pypi/pyversions/exmachina.svg?color=%2334D058" alt="Supported Python versions">
</a>
</p>

---

## インストール

using pip

```
pip install -U exmachina
```

using poetry

```
poetry add exmachina@latest
```

## 使い方


```python
import asyncio

from exmachina import Event, Machina, Retry, RetryFixed

bot = Machina()

bot.create_concurrent_group(
    name='limit',
    entire_calls_limit=4,
    time_calls_limit=3,
    time_limit=1,
)

@bot.emit(interval='1s')
async def emit(event: Event):
    res = await event.execute('execute')
    assert res == 42
    # or
    res = await execute()
    assert res == 42

# 特定の例外でリトライしたい場合
retry = Retry([
  RetryFixed(HTTPError, wait_time=1, retries=5),
])

@bot.execute(concurrent_groups=['limit'], retry=retry)
async def execute():
    return 42

if __name__ == "__main__":
    try:
        wasyncio.run(bot.run())
    except KeyboardInterrupt:
        print("終了")
```

### Emit

定期的に実行したい関数を登録するためのデコレータ

- `name`
  - Emitでユニークな名前をつける
  - 省略した場合はデコレートした関数名になる
- `count`
  - 実行回数. これで指定した回数実行した後、`alive`が`False`になる
  - `None`を指定した場合は無限回実行する
  - デフォルトは`None`
- `interval`
  - ループのインターバル `1s`や`1d4h`などと指定できる
  - デフォルトは`0s`. つまり待機しない
- `alive`
  - `True`の場合、botの実行時に自動で実行される
  - 手動で起動する場合は`False`を指定する
  - デフォルトは`True`

### Concurrent Group

時間あたりや同時実行数を制限するグループ  
作成したグループは後述のExecuteに対して設定できる

- `name`
  - 必須プロパティ. Concurrent Groupでユニークな名前をつける
- `entire_calls_limit`
  - 全体の実行数制限
  - このグループに所属するExecuteの並列実行数
  - `None`を指定した場合、無制限
  - デフォルトは`None`
- `time_calls_limit`
  - このグループに所属する`time_limit`秒あたりに実行"開始"できるExecuteの数
  - デフォルトは`1`
- `time_limit`
  - `time_calls_limit`の制限時間(秒)
  - デフォルト`0`. つまり、制限なし

### Execute

Emitから呼び出される、一回きりのタスク  
Emitは主にbotの制御を行い、Executeは計算処理や外部との通信を行う処理を書く想定

- `name`
  - Executeでユニークな名前をつける
  - 省略した場合はデコレートした関数名になる
- `concurrent_groups`
  - executeの所属するconcurrent_groupを配列で指定する
  - デフォルトは`[]`
- `retry`
  - Execute実行中に発生した例外をトリガーにリトライを行う設定を指定する
  - `from exmachina import Retry`
  - デフォルトは`None`

## Event

Emitする関数に渡されるオブジェクト

- 停止中の別のEmit起動や停止
- Executeの実行
- ループの状態を確認できる属性を持つ

### Emitの起動と停止

```python
event.start('emit_name')
event.stop('emit_name')
```

### Executeの実行

```python
event.execute('execute_name', *args, **kwargs)
```

または、直接呼び出し

```python
await execute_name(*args, **kwargs)
````

event.executeはexecuteのTaskを返す

### 属性

```python
event.epoch # emitのループ回数
event.previous_execution_time # 直前のループの処理時間
event.count # emitの残りの実行回数(未指定の場合はNone)
```

## Retry

Executeのリトライの設定を書くためのもの  
特定の秒数を待機した後、そのまま再実行を行う

- `rules`
  - 指定するルールの配列
- `logger`
  - 自前のloggerを渡したい場合に使う

### RetryRule

- `RetryFixed`: 常に`wait_time`の間隔でリトライ
- `RetryFibonacci`: 1,1,2,3,5,...とフィボナッチ数列秒の間隔でリトライ
- `RetryRange`: `min`と`max`を指定し、その間の乱数秒の間隔でリトライ
- `RetryExponentialAndJitter`: 指数関数倍的に最大の待機時間を伸ばしつつリトライ
のいずれかを使用する

共通引数
- `exception`
  - 指定する例外のクラス
- `retries`
  - リトライ回数. 省略すると`RecursionError`が出るまで再実行する
  - デフォルトは`None`
- `filter`
  - 例外インスタンスを引数に`bool`を返す関数を指定
  - Trueを返した場合にこのリトライ条件にマッチする
  - HTTPのステータスコードなどで引っ掛けたいリトライ設定が異なる場合などを想定
  - デフォルトは`None`. つまり、常に`True`を返す
## 開発

### init

```bash
poetry install
poetry shell
```

### fmt

```
poe fmt
```

### lint

```
poe lint
```

### test

```
poe test
```
