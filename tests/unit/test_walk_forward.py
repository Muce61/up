"""单元测试：walk-forward 时间窗口切分。"""
from __future__ import annotations

from datetime import date

import pytest

from backtest.walk_forward import (
    WalkForwardWindow,
    generate_walk_forward_windows,
    validate_no_overlap,
    validate_train_before_test,
)


@pytest.mark.unit
def test_train_window_is_before_test_window() -> None:
    windows = generate_walk_forward_windows(
        start_date=date(2020, 1, 1),
        end_date=date(2021, 12, 31),
        train_months=12,
        test_months=3,
        step_months=3,
    )

    assert windows
    for window in windows:
        assert window.train_start <= window.train_end
        assert window.train_end < window.test_start
        assert window.test_start <= window.test_end


@pytest.mark.unit
def test_test_windows_roll_by_step_without_overlap() -> None:
    windows = generate_walk_forward_windows(
        start_date=date(2020, 1, 1),
        end_date=date(2021, 12, 31),
        train_months=12,
        test_months=3,
        step_months=3,
    )

    assert [window.test_start for window in windows] == [
        date(2021, 1, 1),
        date(2021, 4, 1),
        date(2021, 7, 1),
        date(2021, 10, 1),
    ]
    assert [window.test_end for window in windows] == [
        date(2021, 3, 31),
        date(2021, 6, 30),
        date(2021, 9, 30),
        date(2021, 12, 31),
    ]
    validate_no_overlap(windows)


@pytest.mark.unit
def test_boundary_dates_are_correct() -> None:
    windows = generate_walk_forward_windows(
        start_date=date(2020, 1, 31),
        end_date=date(2020, 7, 30),
        train_months=1,
        test_months=1,
        step_months=1,
    )

    first = windows[0]
    assert first == WalkForwardWindow(
        train_start=date(2020, 1, 31),
        train_end=date(2020, 2, 28),
        test_start=date(2020, 2, 29),
        test_end=date(2020, 3, 28),
        index=0,
    )


@pytest.mark.unit
def test_validate_train_before_test_rejects_leakage() -> None:
    leaked = [
        WalkForwardWindow(
            train_start=date(2020, 1, 1),
            train_end=date(2020, 6, 30),
            test_start=date(2020, 6, 30),
            test_end=date(2020, 9, 30),
            index=0,
        )
    ]

    with pytest.raises(ValueError, match="train window must end before test window starts"):
        validate_train_before_test(leaked)


@pytest.mark.unit
def test_validate_no_overlap_rejects_overlapping_test_windows() -> None:
    windows = [
        WalkForwardWindow(
            train_start=date(2020, 1, 1),
            train_end=date(2020, 12, 31),
            test_start=date(2021, 1, 1),
            test_end=date(2021, 3, 31),
            index=0,
        ),
        WalkForwardWindow(
            train_start=date(2020, 1, 1),
            train_end=date(2021, 2, 28),
            test_start=date(2021, 3, 1),
            test_end=date(2021, 5, 31),
            index=1,
        ),
    ]

    with pytest.raises(ValueError, match="walk-forward test windows must not overlap"):
        validate_no_overlap(windows)


@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"start_date": date(2021, 1, 1), "end_date": date(2020, 1, 1)}, "start_date"),
        ({"train_months": 0}, "train_months"),
        ({"test_months": 0}, "test_months"),
        ({"step_months": 0}, "step_months"),
        ({"train_months": -1}, "train_months"),
        ({"test_months": -1}, "test_months"),
        ({"step_months": -1}, "step_months"),
    ],
)
def test_invalid_parameters_raise(kwargs: dict[str, object], message: str) -> None:
    base = {
        "start_date": date(2020, 1, 1),
        "end_date": date(2021, 12, 31),
        "train_months": 12,
        "test_months": 3,
        "step_months": 3,
    }
    base.update(kwargs)

    with pytest.raises(ValueError, match=message):
        generate_walk_forward_windows(**base)


@pytest.mark.unit
def test_incomplete_final_test_window_is_dropped() -> None:
    windows = generate_walk_forward_windows(
        start_date=date(2020, 1, 1),
        end_date=date(2021, 11, 30),
        train_months=12,
        test_months=3,
        step_months=3,
    )

    assert [window.test_start for window in windows] == [
        date(2021, 1, 1),
        date(2021, 4, 1),
        date(2021, 7, 1),
    ]
    assert windows[-1].test_end == date(2021, 9, 30)
