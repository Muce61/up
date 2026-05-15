"""回归测试：固定 seed 的 1000 笔随机订单流滑点结果。"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Literal

import pytest

from execution import slippage

EXPECTED_ORDER_FLOW_DIGEST = (
    "36ccc8e008601932b8c2885dccfe88517855b224f62f282a079d2db8cb84f222"
)

AdvCase = Literal["none", "zero", "positive"]
AtrCase = Literal["none", "zero", "positive"]


def _adv_amount(
    *, rng: random.Random, idx: int, order_amount: float
) -> tuple[float | None, AdvCase]:
    case = idx % 3
    if case == 0:
        return None, "none"
    if case == 1:
        return 0.0, "zero"
    return round(max(order_amount / rng.uniform(0.001, 0.20), 1_000.0), 2), "positive"


def _atr_pct(*, rng: random.Random, idx: int) -> tuple[float | None, AtrCase]:
    case = idx % 4
    if case == 0:
        return None, "none"
    if case == 1:
        return 0.0, "zero"
    return round(rng.uniform(0.001, 0.12), 6), "positive"


def _generate_order_flow(seed: int = 20260515) -> list[dict[str, object]]:
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    for idx in range(1_000):
        side: slippage.TradeSide = "buy" if idx % 2 == 0 else "sell"
        base_price = round(rng.uniform(0.5, 500.0), 4)
        order_amount = 0.0 if idx % 97 == 0 else round(10 ** rng.uniform(3.0, 8.0), 2)
        adv_amount, adv_case = _adv_amount(rng=rng, idx=idx, order_amount=order_amount)
        atr_pct, atr_case = _atr_pct(rng=rng, idx=idx)
        max_bps = 20.0 if idx % 10 == 0 else 100.0
        config = slippage.SlippageConfig(max_bps=max_bps)

        bps = slippage.estimate_slippage_bps(
            order_amount=order_amount,
            adv_amount=adv_amount,
            atr_pct=atr_pct,
            config=config,
        )
        fill_price = slippage.execution_price(
            side=side,
            base_price=base_price,
            order_amount=order_amount,
            adv_amount=adv_amount,
            atr_pct=atr_pct,
            config=config,
        )

        if side == "buy":
            assert fill_price >= base_price
        else:
            assert fill_price <= base_price

        rows.append(
            {
                "idx": idx,
                "side": side,
                "order_amount": order_amount,
                "adv_case": adv_case,
                "atr_case": atr_case,
                "max_bps": max_bps,
                "slippage_bps": round(bps, 10),
                "fill_price": round(fill_price, 10),
            }
        )
    return rows


def _digest(rows: list[dict[str, object]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.regression
def test_slippage_random_order_flow_is_reproducible() -> None:
    first = _generate_order_flow()
    second = _generate_order_flow()

    assert first == second
    assert len(first) == 1_000
    assert sum(row["side"] == "buy" for row in first) == 500
    assert sum(row["side"] == "sell" for row in first) == 500
    assert {row["adv_case"] for row in first} == {"none", "zero", "positive"}
    assert {row["atr_case"] for row in first} == {"none", "zero", "positive"}
    assert sum(row["slippage_bps"] == row["max_bps"] for row in first) == 156
    assert _digest(first) == EXPECTED_ORDER_FLOW_DIGEST
