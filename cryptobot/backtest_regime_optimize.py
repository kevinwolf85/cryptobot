from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import product
from typing import Callable, List, Tuple

from cryptobot.backtest import fetch_klines_range
from cryptobot.backtest_regime_models import (
    _breakout_atr_decider,
    _equity_backtest,
    _range_reversion_decider,
    _regime_switch_decider,
)
from cryptobot.config import from_env


@dataclass(frozen=True)
class Candidate:
    model: str
    interval: str
    params: str
    avg_ann_return_pct: float
    min_ann_return_pct: float
    avg_max_dd_pct: float
    folds_over_8: int
    fold_count: int


def _split_walk_forward(rows: List[list], folds: int = 3) -> List[List[list]]:
    if folds <= 1:
        return [rows]
    n = len(rows)
    chunk = n // folds
    windows: List[List[list]] = []
    for i in range(folds):
        s = i * chunk
        e = (i + 1) * chunk if i < folds - 1 else n
        window = rows[s:e]
        if len(window) > 260:
            windows.append(window)
    return windows


def _score_candidate(
    rows: List[list],
    interval: str,
    model_name: str,
    param_name: str,
    decider_factory: Callable[[], Callable],
    sl: float,
    tp: float,
    atr_sl: float,
    atr_tp: float,
) -> Candidate:
    windows = _split_walk_forward(rows, folds=3)
    anns: List[float] = []
    dds: List[float] = []
    over8 = 0
    for w in windows:
        _, ann, dd, _ = _equity_backtest(
            rows=w,
            interval=interval,
            decide_position=decider_factory(),
            stop_loss_pct=sl,
            take_profit_pct=tp,
            atr_stop_mult=atr_sl,
            atr_take_mult=atr_tp,
        )
        anns.append(ann)
        dds.append(dd)
        if ann >= 8.0:
            over8 += 1
    avg_ann = sum(anns) / len(anns)
    min_ann = min(anns)
    avg_dd = sum(dds) / len(dds)
    return Candidate(
        model=model_name,
        interval=interval,
        params=param_name,
        avg_ann_return_pct=avg_ann,
        min_ann_return_pct=min_ann,
        avg_max_dd_pct=avg_dd,
        folds_over_8=over8,
        fold_count=len(anns),
    )


def run_optimization(symbol: str, months: int, intervals: List[str]) -> List[Candidate]:
    cfg = from_env()
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=30 * months)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    out: List[Candidate] = []
    for interval in intervals:
        rows = fetch_klines_range(cfg.market_data_base_url, symbol, interval, start_ms, end_ms)
        if len(rows) < 800:
            continue

        for sl, tp in product([0.01, 0.02, 0.03], [0.03, 0.06, 0.10]):
            name = f"sl={sl:.3f},tp={tp:.3f}"
            out.append(
                _score_candidate(
                    rows,
                    interval,
                    "regime_trend_macd",
                    name,
                    lambda i=interval: _regime_switch_decider(i),
                    sl=sl,
                    tp=tp,
                    atr_sl=0.0,
                    atr_tp=0.0,
                )
            )

        for lookback, atr_sl, atr_tp in product([20, 40], [1.5, 2.0, 2.5], [3.0, 4.0, 5.0]):
            name = f"lb={lookback},atrSL={atr_sl:.1f},atrTP={atr_tp:.1f}"
            out.append(
                _score_candidate(
                    rows,
                    interval,
                    "breakout_atr",
                    name,
                    lambda lb=lookback: _breakout_atr_decider(lb),
                    sl=0.02,
                    tp=0.06,
                    atr_sl=atr_sl,
                    atr_tp=atr_tp,
                )
            )

        for sl, tp in product([0.01, 0.015, 0.02], [0.02, 0.03, 0.04]):
            name = f"sl={sl:.3f},tp={tp:.3f}"
            out.append(
                _score_candidate(
                    rows,
                    interval,
                    "range_mean_reversion",
                    name,
                    lambda i=interval: _range_reversion_decider(i),
                    sl=sl,
                    tp=tp,
                    atr_sl=0.0,
                    atr_tp=0.0,
                )
            )

    out.sort(
        key=lambda c: (
            c.avg_ann_return_pct,
            c.folds_over_8,
            -c.avg_max_dd_pct,
            c.min_ann_return_pct,
        ),
        reverse=True,
    )
    return out


def main() -> None:
    cfg = from_env()
    parser = argparse.ArgumentParser(description="Walk-forward optimization for regime/breakout/range models.")
    parser.add_argument("--symbol", type=str, default=cfg.symbol)
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--intervals", type=str, default="30m,1h,2h,4h,6h,8h,12h")
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args()

    intervals = [x.strip() for x in args.intervals.split(",") if x.strip()]
    results = run_optimization(args.symbol, args.months, intervals)

    print("Walk-Forward Optimization Complete")
    print(f"Symbol: {args.symbol}")
    print(f"Intervals: {','.join(intervals)}")
    print("Rank | Model                | Interval | AvgAnn% | MinAnn% | AvgDD% | >8 Folds | Params")
    print("-----+----------------------+----------+---------+---------+--------+----------+-------")
    for i, r in enumerate(results[: args.top], 1):
        print(
            f"{i:>4} | {r.model:<20} | {r.interval:<8} | {r.avg_ann_return_pct:>7.2f} | "
            f"{r.min_ann_return_pct:>7.2f} | {r.avg_max_dd_pct:>6.2f} | "
            f"{r.folds_over_8:>8}/{r.fold_count:<1} | {r.params}"
        )

    robust = [r for r in results if r.folds_over_8 >= 2 and r.avg_ann_return_pct >= 8.0]
    print("")
    print(f"Robust candidates (avg >=8% and at least 2/3 folds >=8%): {len(robust)}")
    for r in robust[: args.top]:
        print(
            f"- {r.model} @ {r.interval} avg={r.avg_ann_return_pct:.2f}% "
            f"min={r.min_ann_return_pct:.2f}% dd={r.avg_max_dd_pct:.2f}% "
            f"folds>8={r.folds_over_8}/{r.fold_count} params={r.params}"
        )


if __name__ == "__main__":
    main()
