"""Walk-forward 时间窗口切分框架。

P1-W9-01 仅实现滚动窗口生成与防泄漏校验：
- 不做自动选参；
- 不接策略；
- 不修改任何策略参数。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class WalkForwardWindow:
    """一组 walk-forward 训练 / 测试闭区间。"""

    train_start: date
    train_end: date
    test_start: date
    test_end: date
    index: int


def generate_walk_forward_windows(
    *,
    start_date: date,
    end_date: date,
    train_months: int,
    test_months: int,
    step_months: int,
) -> list[WalkForwardWindow]:
    """生成完整 walk-forward 窗口。

    生成规则：
    - 训练区间：`[train_start, train_end]`；
    - 测试区间：`[test_start, test_end]`；
    - `test_start = train_end + 1 day`，禁止训练 / 测试重叠；
    - 每轮 `train_start` 按 `step_months` 向前滚动；
    - 最后一段如果不能形成完整测试窗口，则丢弃，不做截断。
    """
    _validate_inputs(
        start_date=start_date,
        end_date=end_date,
        train_months=train_months,
        test_months=test_months,
        step_months=step_months,
    )

    windows: list[WalkForwardWindow] = []
    cursor = start_date
    index = 0
    while True:
        train_end = _add_months(cursor, train_months) - timedelta(days=1)
        test_start = train_end + timedelta(days=1)
        test_end = _add_months(test_start, test_months) - timedelta(days=1)
        if test_end > end_date:
            break
        windows.append(
            WalkForwardWindow(
                train_start=cursor,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                index=index,
            )
        )
        cursor = _add_months(cursor, step_months)
        index += 1

    validate_train_before_test(windows)
    return windows


def validate_no_overlap(windows: list[WalkForwardWindow]) -> None:
    """校验窗口之间的测试区间不重叠，且单个窗口内 train/test 不重叠。"""
    validate_train_before_test(windows)
    ordered = sorted(windows, key=lambda w: (w.test_start, w.test_end, w.index))
    for prev, curr in zip(ordered, ordered[1:]):
        if curr.test_start <= prev.test_end:
            raise ValueError("walk-forward test windows must not overlap")


def validate_train_before_test(windows: list[WalkForwardWindow]) -> None:
    """校验每个窗口的训练区间严格早于测试区间。"""
    for window in windows:
        if window.train_start > window.train_end:
            raise ValueError("train_start must be <= train_end")
        if window.test_start > window.test_end:
            raise ValueError("test_start must be <= test_end")
        if window.train_end >= window.test_start:
            raise ValueError("train window must end before test window starts")


def _validate_inputs(
    *,
    start_date: date,
    end_date: date,
    train_months: int,
    test_months: int,
    step_months: int,
) -> None:
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")
    if train_months <= 0:
        raise ValueError("train_months must be positive")
    if test_months <= 0:
        raise ValueError("test_months must be positive")
    if step_months <= 0:
        raise ValueError("step_months must be positive")


def _add_months(value: date, months: int) -> date:
    """按日历月滚动，月底日期自动夹到目标月最后一天。"""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    first_next_month = date(year, month + 1, 1)
    return (first_next_month - timedelta(days=1)).day
