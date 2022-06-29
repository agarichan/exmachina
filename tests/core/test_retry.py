import pytest
from pytest_mock.plugin import MockerFixture

from exmachina.core.retry import Retry, RetryExponentialAndJitter, RetryFibonacci, RetryFixed, RetryRange, RetryRule


@pytest.mark.asyncio
async def test_retry_simple(mocker: MockerFixture):
    retry = Retry([RetryFixed(Exception, wait_time=0, retries=2, filter=lambda e: False)])

    func = mocker.MagicMock(side_effect=Exception("exception"))

    @retry
    async def wrap():
        func()

    with pytest.raises(Exception):
        await wrap()

    assert func.call_count == 1


@pytest.mark.asyncio
async def test_retry(mocker: MockerFixture):
    class ParentError(Exception):
        ...

    class ChildError(ParentError):
        ...

    # 親の例外を発生させ、retryする
    # 子供例外はretryの対象外なので実行回数は0

    parent_filter_mock = mocker.MagicMock(return_value=True)
    child_filter_mock = mocker.MagicMock(return_value=True)

    parent_retry = RetryFixed(ParentError, retries=1, wait_time=0.01, filter=parent_filter_mock)
    child_retry = RetryFixed(ChildError, retries=1, wait_time=0.01, filter=child_filter_mock)

    retry = Retry(rules=[parent_retry, child_retry])

    @retry
    async def raise_parent_error1():
        raise ParentError

    with pytest.raises(ParentError):
        await raise_parent_error1()

    assert parent_filter_mock.call_count == 2  # retry分含めて2回実行を期待
    assert child_filter_mock.call_count == 0

    # ruleの順番を変えても同じ

    retry = Retry(rules=[child_retry, parent_retry])

    @retry
    async def raise_parent_error2():
        raise ParentError

    with pytest.raises(ParentError):
        await raise_parent_error2()

    assert parent_filter_mock.call_count == 4
    assert child_filter_mock.call_count == 0

    # 子供の例外を発生させる

    retry = Retry(rules=[parent_retry, child_retry])

    @retry
    async def raise_child_error1():
        raise ChildError

    with pytest.raises(ParentError):
        await raise_child_error1()

    assert parent_filter_mock.call_count == 7  # child側のリスタートでリトライ回数を超えて一回多くカウントされる
    assert child_filter_mock.call_count == 2

    retry = Retry(rules=[child_retry, parent_retry])

    @retry
    async def raise_child_error2():
        raise ChildError

    with pytest.raises(ParentError):
        await raise_child_error2()

    assert parent_filter_mock.call_count == 9
    assert child_filter_mock.call_count == 5  # 順番を変えることで先にchild側が処理されるので一回多くなるのがこっちに変わる


def test_retry_exponential_and_jitter():
    cap = 1
    base = 0.01
    rule = RetryExponentialAndJitter(Exception, base_wait_time=base, cap=cap)

    gen = rule.generate_wait_time()
    for i in range(100):
        wait = next(gen)
        assert 0 <= wait <= max(base * 2**i, cap)


def test_retry_fibonacci():
    rule = RetryFibonacci(Exception)

    gen = rule.generate_wait_time()
    assert next(gen) == 1
    assert next(gen) == 1
    assert next(gen) == 2
    assert next(gen) == 3
    assert next(gen) == 5


def test_retry_range():
    rule = RetryRange(Exception, min=0, max=1)

    gen = rule.generate_wait_time()
    for _ in range(100):
        assert 0 <= next(gen) <= 1


def test_abstract_generate_wait_time():
    class TestRetryRule(RetryRule):
        def generate_wait_time(self):
            super().generate_wait_time()

    tr = TestRetryRule(exception=Exception, retries=0)

    with pytest.raises(NotImplementedError):
        tr.generate_wait_time()
