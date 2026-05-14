"""日级事件循环回测引擎（周频调仓）。

约束（CLAUDE.md §3）：
- 所有撮合判断通过 `execution.tradeability`，不直接调用 `backtest.market_rules_cn`；
- 同一 (strategy_id, params, snapshot_version) 两次运行 byte-for-byte 一致。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from data import schema
from execution import fee_model, order_model, slippage, tradeability
from portfolio import capacity

TRADING_DAYS_PER_YEAR = 252

EQUITY_COLUMNS = ["trade_date", "equity", "cash", "position_value", "drawdown"]
TRADE_COLUMNS = [
    "trade_date",
    "symbol",
    "side",
    "quantity",
    "price",
    "amount",
    "commission",
    "stamp_tax",
    "transfer_fee",
    "total_cost",
    "status",
    "reject_reason",
]
HOLDING_COLUMNS = ["trade_date", "symbol", "quantity", "market_value", "weight"]


@dataclass
class BacktestConfig:
    strategy_id: str
    start_date: date
    end_date: date
    initial_capital: float
    snapshot_version: str = "fixtures-mini"
    fee_config: fee_model.FeeConfig = field(default_factory=fee_model.FeeConfig)
    random_seed: int = 42
    lot_size: int = 100
    n_capacity_pct: float = 0.05


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    holdings: pd.DataFrame
    metrics: dict[str, Any]
    manifest: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_bar(prices: pd.DataFrame, symbol: str, trade_date: date) -> pd.Series | None:
    rows = prices[(prices["symbol"] == symbol) & (prices["trade_date"] == trade_date)]
    if rows.empty:
        return None
    return rows.iloc[0]


def _adj_factor(bar: pd.Series) -> float:
    if "adj_factor" not in bar.index or pd.isna(bar["adj_factor"]):
        return 1.0
    return float(bar["adj_factor"])


def _adjusted_price(bar: pd.Series, field: str) -> float:
    return float(bar[field]) * _adj_factor(bar)


def _weekly_rebalance_dates(calendar_df: pd.DataFrame) -> set[date]:
    """取每个 ISO 周的最后一个交易日。"""
    cal = calendar_df.copy()
    cal["_iso"] = pd.to_datetime(cal["trade_date"]).apply(
        lambda d: (d.isocalendar().year, d.isocalendar().week)
    )
    last = cal.groupby("_iso")["trade_date"].max()
    return set(last.tolist())


def _next_trade_date(calendar_dates: list[date], current: date) -> date | None:
    for d in calendar_dates:
        if d > current:
            return d
    return None


def _bar_atr_pct(bar: pd.Series) -> float | None:
    if "atr_pct" in bar.index and pd.notna(bar["atr_pct"]):
        return float(bar["atr_pct"])
    if all(col in bar.index for col in ["high", "low", "close"]) and _adjusted_price(bar, "close") > 0:
        return max(_adjusted_price(bar, "high") - _adjusted_price(bar, "low"), 0.0) / _adjusted_price(
            bar, "close"
        )
    return None


def _bar_adv_amount(bar: pd.Series) -> float | None:
    if "amount" not in bar.index or pd.isna(bar["amount"]):
        return None
    amount = float(bar["amount"])
    return amount if amount > 0 else None


def _rolling_adv_amount(
    prices: pd.DataFrame,
    symbol: str,
    exec_date: date,
    *,
    window: int = 60,
) -> float | None:
    rows = prices[
        (prices["symbol"] == symbol)
        & (prices["trade_date"] < exec_date)
        & (~prices["is_suspended"].astype(bool))
    ].sort_values("trade_date")
    if rows.empty or "amount" not in rows.columns:
        return None
    amounts = rows["amount"].astype(float)
    amounts = amounts[amounts > 0]
    if amounts.empty:
        return 0.0
    return float(amounts.tail(window).mean())


def _capacity_max_trade_amount(
    prices: pd.DataFrame,
    symbol: str,
    exec_date: date,
    capacity_pct: float,
) -> float | None:
    adv_amount = _rolling_adv_amount(prices, symbol, exec_date)
    if adv_amount is None:
        return None
    return capacity.max_trade_amount(adv_amount=adv_amount, capacity_pct=capacity_pct)


def _exec_price(
    bar: pd.Series,
    side: str,
    slippage_bps: float,
    *,
    order_amount: float | None = None,
) -> float:
    base = _adjusted_price(bar, "open")
    return slippage.execution_price(
        side=side,  # type: ignore[arg-type]
        base_price=base,
        order_amount=float(order_amount if order_amount is not None else base),
        adv_amount=_bar_adv_amount(bar),
        atr_pct=_bar_atr_pct(bar),
        config=slippage.SlippageConfig(base_bps=float(slippage_bps)),
    )


def _execution_bar(
    bar: pd.Series,
    symbol: str,
    trade_date: date,
    *,
    is_delisted: bool,
    execution_price: float | None = None,
) -> order_model.ExecutionBar:
    return order_model.ExecutionBar(
        symbol=symbol,
        trade_date=trade_date,
        open=float(bar["open"]),
        high=float(bar["high"]),
        low=float(bar["low"]),
        close=float(bar["close"]),
        limit_up=float(bar["limit_up"]),
        limit_down=float(bar["limit_down"]),
        is_suspended=bool(bar["is_suspended"]),
        is_delisted=is_delisted,
        execution_price=execution_price,
    )


def _make_trade_record(
    trade_date: date,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    amount: float,
    cost: fee_model.CostBreakdown | None,
    status: str,
    reject_reason: str | None,
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "symbol": symbol,
        "side": side,
        "quantity": int(quantity),
        "price": float(price),
        "amount": float(amount),
        "commission": float(cost.commission) if cost else 0.0,
        "stamp_tax": float(cost.stamp_tax) if cost else 0.0,
        "transfer_fee": float(cost.transfer_fee) if cost else 0.0,
        "total_cost": float(cost.total) if cost else 0.0,
        "status": status,
        "reject_reason": reject_reason,
    }


def _try_execute(
    symbol: str,
    side: str,
    qty: int,
    exec_date: date,
    prices: pd.DataFrame,
    master_row: pd.Series,
    config: BacktestConfig,
    holdings: dict[str, dict[str, Any]],
    calendar_dates: list[date],
    capacity_pct: float | None = None,
) -> tuple[dict[str, Any], float]:
    """尝试在 exec_date 开盘成交一笔订单。返回 (record, signed_cash_flow)。"""
    bar = _get_bar(prices, symbol, exec_date)
    if bar is None or qty <= 0:
        return (
            _make_trade_record(exec_date, symbol, side, qty, 0.0, 0.0, None, "rejected", "no_bar"),
            0.0,
        )

    is_delisted = (
        master_row["delist_date"] is not None and exec_date >= master_row["delist_date"]
    )
    # T+1 check for sell
    if side == "sell":
        last_buy = holdings.get(symbol, {}).get("last_buy_date")
        if tradeability.is_t1_violation(
            etf_type=master_row["etf_type"],
            last_buy_trade_date=last_buy,
            current_trade_date=exec_date,
            trading_calendar=calendar_dates,
        ):
            return (
                _make_trade_record(
                    exec_date, symbol, side, qty, 0.0, 0.0, None, "rejected", "t1_violation"
                ),
                0.0,
            )

    approx_order_amount = qty * float(bar["open"])
    exec_price = _exec_price(
        bar,
        side,
        config.fee_config.slippage_bps,
        order_amount=approx_order_amount,
    )
    order = order_model.Order(
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        quantity=int(qty),
        order_type="market",
    )
    execution = order_model.execute_order(
        order,
        _execution_bar(
            bar,
            symbol,
            exec_date,
            is_delisted=is_delisted,
            execution_price=exec_price,
        ),
        max_trade_amount=_capacity_max_trade_amount(
            prices,
            symbol,
            exec_date,
            config.n_capacity_pct if capacity_pct is None else capacity_pct,
        ),
    )
    if execution.status == "rejected":
        return (
            _make_trade_record(
                exec_date,
                symbol,
                side,
                qty,
                float(bar["open"]),
                0.0,
                None,
                "rejected",
                execution.reject_reason,
            ),
            0.0,
        )

    amount = execution.traded_amount
    cost = fee_model.calculate_cost(
        amount=amount,
        side=side,  # type: ignore[arg-type]
        stamp_tax_applicable=bool(master_row["stamp_tax_applicable"]),
        exchange=str(master_row["exchange"]),
        config=config.fee_config,
    )
    cash_flow = (-amount - cost.total) if side == "buy" else (amount - cost.total)
    record = _make_trade_record(
        exec_date,
        symbol,
        side,
        execution.filled_quantity,
        execution.fill_price,
        amount,
        cost,
        execution.status,
        execution.reject_reason,
    )
    return record, cash_flow


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SignalFn = Callable[[date, pd.DataFrame, pd.DataFrame, Any], pd.DataFrame]


def run_backtest(
    *,
    config: BacktestConfig,
    prices: pd.DataFrame,
    master: pd.DataFrame,
    calendar: pd.DataFrame,
    signal_fn: SignalFn,
    params: Any,
    output_dir: str | Path | None = None,
) -> BacktestResult:
    prices = schema.validate_prices(prices)
    master = schema.validate_master(master)
    calendar = schema.validate_calendar(calendar)

    cal_df = calendar.sort_values("trade_date").reset_index(drop=True)
    cal_df = cal_df[
        (cal_df["trade_date"] >= config.start_date) & (cal_df["trade_date"] <= config.end_date)
    ].reset_index(drop=True)
    calendar_dates: list[date] = cal_df["trade_date"].tolist()
    rebalance_dates = _weekly_rebalance_dates(cal_df)
    capacity_pct = float(getattr(params, "n_capacity_pct", config.n_capacity_pct))

    cash = float(config.initial_capital)
    holdings: dict[str, dict[str, Any]] = {}
    trades_log: list[dict[str, Any]] = []
    equity_records: list[dict[str, Any]] = []
    holdings_records: list[dict[str, Any]] = []
    running_peak = cash

    for trade_date in calendar_dates:
        # Mark-to-market
        pos_value = 0.0
        for sym, h in holdings.items():
            bar = _get_bar(prices, sym, trade_date)
            if bar is not None:
                pos_value += h["quantity"] * _adjusted_price(bar, "close")
        equity = cash + pos_value
        running_peak = max(running_peak, equity)
        drawdown = (equity - running_peak) / running_peak if running_peak > 0 else 0.0
        equity_records.append(
            {
                "trade_date": trade_date,
                "equity": equity,
                "cash": cash,
                "position_value": pos_value,
                "drawdown": drawdown,
            }
        )
        for sym, h in holdings.items():
            bar = _get_bar(prices, sym, trade_date)
            mv = h["quantity"] * (_adjusted_price(bar, "close") if bar is not None else 0.0)
            holdings_records.append(
                {
                    "trade_date": trade_date,
                    "symbol": sym,
                    "quantity": int(h["quantity"]),
                    "market_value": mv,
                    "weight": (mv / equity) if equity > 0 else 0.0,
                }
            )

        if trade_date not in rebalance_dates:
            continue

        target_df = signal_fn(trade_date, prices, master, params)
        next_date = _next_trade_date(calendar_dates, trade_date)
        if next_date is None:
            continue

        target_weights = (
            dict(zip(target_df["symbol"], target_df["target_weight"])) if not target_df.empty else {}
        )

        # 1) 卖出目标外标的
        to_sell = [s for s in list(holdings.keys()) if s not in target_weights]
        for sym in to_sell:
            qty = int(holdings[sym]["quantity"])
            mrow = master[master["symbol"] == sym].iloc[0]
            rec, cf = _try_execute(
                sym,
                "sell",
                qty,
                next_date,
                prices,
                mrow,
                config,
                holdings,
                calendar_dates,
                capacity_pct,
            )
            trades_log.append(rec)
            if rec["status"] == "filled":
                cash += cf
                del holdings[sym]
            elif rec["status"] == "partial_filled":
                cash += cf
                holdings[sym]["quantity"] = int(holdings[sym]["quantity"]) - int(rec["quantity"])
                if holdings[sym]["quantity"] <= 0:
                    del holdings[sym]

        # 2) 重估 equity（卖出后）
        post_sell_value = 0.0
        for sym, h in holdings.items():
            bar = _get_bar(prices, sym, next_date)
            if bar is not None:
                post_sell_value += h["quantity"] * _adjusted_price(bar, "close")
        pre_buy_equity = cash + post_sell_value

        # 3) 调整或新建目标仓位
        for sym, w in target_weights.items():
            mrow = master[master["symbol"] == sym].iloc[0]
            bar = _get_bar(prices, sym, next_date)
            if bar is None:
                continue
            target_value = w * pre_buy_equity
            cur_qty = int(holdings.get(sym, {}).get("quantity", 0))
            cur_value = cur_qty * _adjusted_price(bar, "close")
            diff_value = target_value - cur_value
            side = "buy" if diff_value > 0 else "sell"
            exec_price = _exec_price(
                bar,
                side,
                config.fee_config.slippage_bps,
                order_amount=abs(diff_value),
            )
            qty = int(abs(diff_value) / exec_price / config.lot_size) * config.lot_size
            if qty <= 0:
                continue
            rec, cf = _try_execute(
                sym,
                side,
                qty,
                next_date,
                prices,
                mrow,
                config,
                holdings,
                calendar_dates,
                capacity_pct,
            )
            trades_log.append(rec)
            if rec["status"] not in {"filled", "partial_filled"}:
                continue
            cash += cf
            filled_qty = int(rec["quantity"])
            if side == "buy":
                if sym in holdings:
                    holdings[sym]["quantity"] = int(holdings[sym]["quantity"]) + filled_qty
                    holdings[sym]["last_buy_date"] = next_date
                else:
                    holdings[sym] = {"quantity": filled_qty, "last_buy_date": next_date}
            else:
                holdings[sym]["quantity"] = int(holdings[sym]["quantity"]) - filled_qty
                if holdings[sym]["quantity"] <= 0:
                    del holdings[sym]

    equity_df = pd.DataFrame(equity_records, columns=EQUITY_COLUMNS)
    trades_df = (
        pd.DataFrame(trades_log, columns=TRADE_COLUMNS)
        if trades_log
        else pd.DataFrame(columns=TRADE_COLUMNS)
    )
    holdings_df = pd.DataFrame(holdings_records, columns=HOLDING_COLUMNS)
    metrics = compute_metrics(equity_df, trades_df)
    manifest = _build_manifest(config, params, metrics)

    if output_dir is not None:
        _persist(output_dir, equity_df, trades_df, holdings_df, metrics, manifest)

    return BacktestResult(
        equity_curve=equity_df,
        trades=trades_df,
        holdings=holdings_df,
        metrics=metrics,
        manifest=manifest,
    )


def compute_metrics(equity_df: pd.DataFrame, trades_df: pd.DataFrame) -> dict[str, Any]:
    if equity_df.empty:
        return {
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "calmar": 0.0,
            "turnover": 0.0,
            "trade_count": 0,
            "final_equity": 0.0,
            "n_trading_days": 0,
        }
    eq = equity_df["equity"].to_numpy(dtype=float)
    years = max(len(eq) / TRADING_DAYS_PER_YEAR, 1e-9)
    annualized_return = float((eq[-1] / eq[0]) ** (1.0 / years) - 1.0) if eq[0] > 0 else 0.0
    max_dd = float(equity_df["drawdown"].min())
    daily_ret = pd.Series(eq).pct_change().fillna(0).to_numpy(dtype=float)
    sd = float(np.std(daily_ret, ddof=1)) if len(daily_ret) > 1 else 0.0
    mu = float(np.mean(daily_ret))
    sharpe = (mu / sd) * np.sqrt(TRADING_DAYS_PER_YEAR) if sd > 0 else 0.0
    downside = daily_ret[daily_ret < 0]
    dsd = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sortino = (mu / dsd) * np.sqrt(TRADING_DAYS_PER_YEAR) if dsd > 0 else 0.0
    calmar = annualized_return / abs(max_dd) if max_dd < 0 else 0.0
    if not trades_df.empty:
        filled = trades_df[trades_df["status"].isin(["filled", "partial_filled"])]
        gross = float(filled["amount"].sum()) if "amount" in filled.columns else 0.0
        avg_eq = float(equity_df["equity"].mean())
        turnover = gross / avg_eq / years if (avg_eq > 0) else 0.0
        trade_count = int(len(filled))
    else:
        turnover = 0.0
        trade_count = 0
    return {
        "annualized_return": float(annualized_return),
        "max_drawdown": float(max_dd),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "calmar": float(calmar),
        "turnover": float(turnover),
        "trade_count": int(trade_count),
        "final_equity": float(eq[-1]),
        "n_trading_days": int(len(eq)),
    }


def _build_manifest(
    config: BacktestConfig, params: Any, metrics: dict[str, Any]
) -> dict[str, Any]:
    params_dict = (
        asdict(params) if hasattr(params, "__dataclass_fields__") else dict(params.__dict__)
    )
    params_str = json.dumps(params_dict, sort_keys=True, default=str)
    params_hash = hashlib.sha256(params_str.encode("utf-8")).hexdigest()
    return {
        "strategy_id": config.strategy_id,
        "snapshot_version": config.snapshot_version,
        "params_hash": params_hash,
        "params": params_dict,
        "metrics_summary": metrics,
        "random_seed": config.random_seed,
        "start_date": str(config.start_date),
        "end_date": str(config.end_date),
        "initial_capital": float(config.initial_capital),
    }


def _persist(
    output_dir: str | Path,
    equity_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    holdings_df: pd.DataFrame,
    metrics: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    equity_df.to_csv(out / "equity_curve.csv", index=False)
    trades_df.to_csv(out / "trades.csv", index=False)
    holdings_df.to_csv(out / "holdings.csv", index=False)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
