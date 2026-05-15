"""测试基础设施自检：_pytest_compat shim 的 raises() 行为。

为什么需要它：项目无法访问 PyPI，测试套件依赖 tests/_pytest_compat.py 这个
最小 pytest 兼容层。shim 一旦缺失某个被测试用到的 API，整个套件会崩溃或
给出假绿。本文件把 shim 自身的关键行为也纳入回归保护。
"""
from __future__ import annotations

import pytest


@pytest.mark.unit
def test_raises_catches_expected_exception() -> None:
    with pytest.raises(ValueError):
        raise ValueError("boom")


@pytest.mark.unit
def test_raises_accepts_tuple_of_types() -> None:
    with pytest.raises((ImportError, NotImplementedError)):
        raise NotImplementedError("phase 2 locked")


@pytest.mark.unit
def test_raises_with_matching_pattern_passes() -> None:
    with pytest.raises(ValueError, match="must be non-negative"):
        raise ValueError("capacity_pct must be non-negative")


@pytest.mark.unit
def test_raises_with_partial_regex_pattern_passes() -> None:
    # match 是 re.search 语义：子串 / 正则片段即可命中
    with pytest.raises(ValueError, match=r"window.*before"):
        raise ValueError("train window must end before test window starts")


@pytest.mark.unit
def test_raises_with_nonmatching_pattern_fails() -> None:
    # 异常类型对，但 message 不匹配 → shim 必须自己抛 AssertionError
    raised_assertion = False
    try:
        with pytest.raises(ValueError, match="this will not be found"):
            raise ValueError("completely different message")
    except AssertionError:
        raised_assertion = True
    assert raised_assertion, "match 不命中时 raises() 必须抛 AssertionError"


@pytest.mark.unit
def test_raises_when_no_exception_fails() -> None:
    raised_assertion = False
    try:
        with pytest.raises(ValueError):
            pass  # 不抛异常
    except AssertionError:
        raised_assertion = True
    assert raised_assertion, "未抛出预期异常时 raises() 必须抛 AssertionError"


@pytest.mark.unit
def test_raises_exposes_caught_value() -> None:
    with pytest.raises(ValueError, match="payload") as ctx:
        raise ValueError("payload 123")
    assert ctx.value is not None
    assert "payload" in str(ctx.value)
