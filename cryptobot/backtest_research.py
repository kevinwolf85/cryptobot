from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import product
from typing import Iterable, List, Optional

from cryptobot.backtest import _interval_to_ms, fetch_klines_range
from cryptobot.config import from_env
from cryptobot.indicators import crossover_direction, ema, macd_series, rsi_series


@dataclass(frozen=True)
class ResearchParams:
    interval: str
    macd_fast: int
    macd_slow: int
    macd_signal: int
    volume_ratio_threshold: float
    stop_loss_pct: float
    take_profit_pct: float
    trend_filter: bool
    short_enabled: bool
    rsi_filter: bool
    max_annual_vol: Optional[float]


@dataclass
class ResearchResult:
    params: ResearchParams
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    sharpe_like: float
    trades: int
    wins: int
    losses: int
    ending_equity: float


def _annualization_factor(interval: str) -> float:
    ms = _interval_to_ms(interval)
    periods_per_year = (365.0 * 24 * 60 * 60 * 1000) / ms
    return periods_per_year


def _annualized_return(total_return: float, years: float) -> float:
    if years <= 0:
        return 0.0
    if total_return <= -0.999999:
        return -1.0
    return (1.0 + total_return) ** (1.0 / years) - 1.0


def _max_drawdown_pct(equity_curve: Iterable[float]) -> float:
    peak = -math.inf
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd * 100.0


def _rolling_annual_vol(closes: List[float], idx: int, lookback: int, interval: str) -> float:
    if idx - lookback < 1:
        return 0.0
    rets: List[float] = []
    for i in range(idx - lookback + 1, idx + 1):
        prev = closes[i - 1]
        curr = closes[i]
        if prev <= 0:
            continue
        rets.append(math.log(curr / prev))
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / (len(rets) - 1)
    std = math.sqrt(max(var, 0.0))
    return std * math.sqrt(_annualization_factor(interval))


def _volume_ratio(rows: List[list], end_idx: int, window: int) -> float:
    start = max(0, end_idx - window + 1)
    buy = 0.0
    sell = 0.0
    for r in rows[start : end_idx + 1]:
        total = float(r[5])
        taker_buy = float(r[9]) if len(r) > 9 else 0.0
        buy += taker_buy
        sell += max(0.0, total - taker_buy)
    if sell <= 0:
        return float("inf")
    return buy / sell


def _apply_exec_price(price: float, side: str, slippage_bps: float) -> float:
    slip = slippage_bps / 10_000.0
    if side in {"buy", "cover"}:
        return price * (1.0 + slip)
    return price * (1.0 - slip)


def run_strategy(
    rows: List[list],
    params: ResearchParams,
    starting_equity: float,
    trade_notional: float,
    fee_bps: float,
    slippage_bps: float,
    lookback: int,
    volume_window: int,
) -> ResearchResult:
    closes = [float(r[4]) for r in rows]
    fast_ema = ema(closes, params.macd_fast)
    slow_ema = ema(closes, params.macd_slow)
    macd = [a - b for a, b in zip(fast_ema, slow_ema)]
    signal = ema(macd, params.macd_signal)
    rsi = rsi_series(closes, period=14)
    trend_fast = ema(closes, 50)
    trend_slow = ema(closes, 200)

    cash = float(starting_equity)
    qty = 0.0
    entry_price = 0.0
    entry_side = "flat"
    wins = 0
    losses = 0
    trades = 0
    equity_curve: List[float] = []
    bar_returns: List[float] = []
    prev_equity = starting_equity
    fee_rate = fee_bps / 10_000.0

    start_idx = max(lookback, params.macd_slow + params.macd_signal + 2, 210)
    for i in range(start_idx, len(rows)):
        price = closes[i]
        vol_ratio = _volume_ratio(rows, i, volume_window)
        cross = crossover_direction(macd[: i + 1], signal[: i + 1])
        trend_ok_long = True
        trend_ok_short = True
        if params.trend_filter:
            trend_ok_long = trend_fast[i] > trend_slow[i]
            trend_ok_short = trend_fast[i] < trend_slow[i]

        if params.max_annual_vol is not None:
            ann_vol = _rolling_annual_vol(closes, i, lookback=48, interval=params.interval)
            if ann_vol > params.max_annual_vol:
                # Risk-off: flatten and skip entries.
                if qty > 0:
                    px = _apply_exec_price(price, "sell", slippage_bps)
                    notional = qty * px
                    fee = notional * fee_rate
                    cash += notional - fee
                    trades += 1
                    pnl = (px - entry_price) / entry_price if entry_price > 0 else 0.0
                    wins += 1 if pnl > 0 else 0
                    losses += 1 if pnl <= 0 else 0
                    qty = 0.0
                    entry_price = 0.0
                    entry_side = "flat"
                elif qty < 0:
                    px = _apply_exec_price(price, "cover", slippage_bps)
                    notional = abs(qty) * px
                    fee = notional * fee_rate
                    cash -= notional + fee
                    trades += 1
                    pnl = (entry_price - px) / entry_price if entry_price > 0 else 0.0
                    wins += 1 if pnl > 0 else 0
                    losses += 1 if pnl <= 0 else 0
                    qty = 0.0
                    entry_price = 0.0
                    entry_side = "flat"
                equity = cash + qty * price
                equity_curve.append(equity)
                if prev_equity > 0:
                    bar_returns.append((equity / prev_equity) - 1.0)
                prev_equity = equity
                continue

        if qty > 0 and entry_price > 0:
            pnl_pct = (price - entry_price) / entry_price
            if pnl_pct <= -params.stop_loss_pct or pnl_pct >= params.take_profit_pct:
                px = _apply_exec_price(price, "sell", slippage_bps)
                notional = qty * px
                fee = notional * fee_rate
                cash += notional - fee
                trades += 1
                wins += 1 if pnl_pct > 0 else 0
                losses += 1 if pnl_pct <= 0 else 0
                qty = 0.0
                entry_price = 0.0
                entry_side = "flat"
        elif qty < 0 and entry_price > 0:
            pnl_pct = (entry_price - price) / entry_price
            if pnl_pct <= -params.stop_loss_pct or pnl_pct >= params.take_profit_pct:
                px = _apply_exec_price(price, "cover", slippage_bps)
                notional = abs(qty) * px
                fee = notional * fee_rate
                cash -= notional + fee
                trades += 1
                wins += 1 if pnl_pct > 0 else 0
                losses += 1 if pnl_pct <= 0 else 0
                qty = 0.0
                entry_price = 0.0
                entry_side = "flat"

        want_long = False
        want_short = False
        if cross == "bullish" and vol_ratio >= params.volume_ratio_threshold and trend_ok_long:
            if not params.rsi_filter or rsi[i] < 65:
                want_long = True
        if cross == "bearish" and vol_ratio <= (1.0 / max(params.volume_ratio_threshold, 0.0001)) and trend_ok_short:
            if (not params.rsi_filter or rsi[i] > 35) and params.short_enabled:
                want_short = True

        if qty < 0 and want_long:
            px = _apply_exec_price(price, "cover", slippage_bps)
            notional = abs(qty) * px
            fee = notional * fee_rate
            cash -= notional + fee
            trades += 1
            pnl_pct = (entry_price - px) / entry_price if entry_price > 0 else 0.0
            wins += 1 if pnl_pct > 0 else 0
            losses += 1 if pnl_pct <= 0 else 0
            qty = 0.0
            entry_price = 0.0
            entry_side = "flat"
        elif qty > 0 and want_short:
            px = _apply_exec_price(price, "sell", slippage_bps)
            notional = qty * px
            fee = notional * fee_rate
            cash += notional - fee
            trades += 1
            pnl_pct = (px - entry_price) / entry_price if entry_price > 0 else 0.0
            wins += 1 if pnl_pct > 0 else 0
            losses += 1 if pnl_pct <= 0 else 0
            qty = 0.0
            entry_price = 0.0
            entry_side = "flat"

        if qty == 0.0:
            if want_long and cash > 0:
                notional = min(trade_notional, cash)
                px = _apply_exec_price(price, "buy", slippage_bps)
                qty_open = notional / px if px > 0 else 0.0
                fee = notional * fee_rate
                total_cash_spend = notional + fee
                if total_cash_spend <= cash and qty_open > 0:
                    cash -= total_cash_spend
                    qty = qty_open
                    entry_price = px
                    entry_side = "long"
                    trades += 1
            elif want_short and params.short_enabled:
                equity_now = cash
                if equity_now > 0:
                    notional = min(trade_notional, equity_now)
                    px = _apply_exec_price(price, "short", slippage_bps)
                    qty_open = notional / px if px > 0 else 0.0
                    fee = notional * fee_rate
                    cash += notional - fee
                    qty = -qty_open
                    entry_price = px
                    entry_side = "short"
                    trades += 1

        equity = cash + (qty * price)
        equity_curve.append(equity)
        if prev_equity > 0:
            bar_returns.append((equity / prev_equity) - 1.0)
        prev_equity = equity

    final_price = closes[-1]
    if qty > 0:
        px = _apply_exec_price(final_price, "sell", slippage_bps)
        notional = qty * px
        fee = notional * fee_rate
        cash += notional - fee
        trades += 1
        pnl_pct = (px - entry_price) / entry_price if entry_price > 0 else 0.0
        wins += 1 if pnl_pct > 0 else 0
        losses += 1 if pnl_pct <= 0 else 0
        qty = 0.0
    elif qty < 0:
        px = _apply_exec_price(final_price, "cover", slippage_bps)
        notional = abs(qty) * px
        fee = notional * fee_rate
        cash -= notional + fee
        trades += 1
        pnl_pct = (entry_price - px) / entry_price if entry_price > 0 else 0.0
        wins += 1 if pnl_pct > 0 else 0
        losses += 1 if pnl_pct <= 0 else 0
        qty = 0.0

    ending_equity = cash
    total_return = (ending_equity / starting_equity) - 1.0 if starting_equity > 0 else 0.0
    years = (len(rows) * _interval_to_ms(params.interval)) / (365.0 * 24 * 60 * 60 * 1000)
    ann_return = _annualized_return(total_return, years)
    max_dd = _max_drawdown_pct(equity_curve if equity_curve else [starting_equity, ending_equity])

    ann_rf = 0.08
    periods_per_year = _annualization_factor(params.interval)
    rf_per_bar = (1.0 + ann_rf) ** (1.0 / periods_per_year) - 1.0
    sharpe_like = 0.0
    if len(bar_returns) > 2:
        ex = [r - rf_per_bar for r in bar_returns]
        mean_ex = sum(ex) / len(ex)
        var_ex = sum((x - mean_ex) ** 2 for x in ex) / (len(ex) - 1)
        std_ex = math.sqrt(max(var_ex, 0.0))
        if std_ex > 0:
            sharpe_like = (mean_ex / std_ex) * math.sqrt(periods_per_year)

    return ResearchResult(
        params=params,
        total_return_pct=total_return * 100.0,
        annualized_return_pct=ann_return * 100.0,
        max_drawdown_pct=max_dd,
        sharpe_like=sharpe_like,
        trades=trades,
        wins=wins,
        losses=losses,
        ending_equity=ending_equity,
    )


def run_research(
    symbol: str,
    months: int,
    intervals: List[str],
    starting_equity: float,
    trade_notional: float,
    fee_bps: float,
    slippage_bps: float,
    lookback: int,
    volume_window: int,
) -> List[ResearchResult]:
    cfg = from_env()
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=30 * months)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    macd_sets = [(8, 21, 5), (12, 26, 9), (16, 34, 9)]
    volume_thresholds = [1.0, 1.2]
    stop_losses = [0.01, 0.02]
    take_profits = [0.03, 0.06]
    trend_filter_opts = [False, True]
    short_opts = [False, True]
    rsi_filter_opts = [False, True]
    max_ann_vol_opts: List[Optional[float]] = [None, 1.5]

    results: List[ResearchResult] = []
    for interval in intervals:
        rows = fetch_klines_range(
            base_url=cfg.market_data_base_url,
            symbol=symbol,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        if len(rows) < max(lookback, volume_window) + 5:
            continue
        combos = product(
            macd_sets,
            volume_thresholds,
            stop_losses,
            take_profits,
            trend_filter_opts,
            short_opts,
            rsi_filter_opts,
            max_ann_vol_opts,
        )
        for (mf, ms, mg), vol_th, sl, tp, trend_on, short_on, rsi_on, max_av in combos:
            params = ResearchParams(
                interval=interval,
                macd_fast=mf,
                macd_slow=ms,
                macd_signal=mg,
                volume_ratio_threshold=vol_th,
                stop_loss_pct=sl,
                take_profit_pct=tp,
                trend_filter=trend_on,
                short_enabled=short_on,
                rsi_filter=rsi_on,
                max_annual_vol=max_av,
            )
            res = run_strategy(
                rows=rows,
                params=params,
                starting_equity=starting_equity,
                trade_notional=trade_notional,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                lookback=lookback,
                volume_window=volume_window,
            )
            results.append(res)

    results.sort(key=lambda r: (r.annualized_return_pct, -r.max_drawdown_pct, r.sharpe_like), reverse=True)
    return results


def _params_brief(p: ResearchParams) -> str:
    return (
        f"itv={p.interval} macd={p.macd_fast}/{p.macd_slow}/{p.macd_signal} "
        f"vol={p.volume_ratio_threshold} sl={p.stop_loss_pct:.2f} tp={p.take_profit_pct:.2f} "
        f"trend={p.trend_filter} short={p.short_enabled} rsi={p.rsi_filter} maxVol={p.max_annual_vol}"
    )


def main() -> None:
    cfg = from_env()
    parser = argparse.ArgumentParser(description="Comprehensive multi-interval strategy research harness.")
    parser.add_argument("--symbol", type=str, default=cfg.symbol)
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument(
        "--intervals",
        type=str,
        default="15m,30m,1h,2h,4h,6h,8h,12h",
        help="Comma-separated intervals",
    )
    parser.add_argument("--lookback", type=int, default=200)
    parser.add_argument("--volume-window", type=int, default=40)
    parser.add_argument("--starting-equity", type=float, default=10_000.0)
    parser.add_argument("--trade-notional", type=float, default=1_000.0)
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Per side fee in bps")
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Per side slippage in bps")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--hurdle-annual-pct", type=float, default=8.0)
    args = parser.parse_args()

    intervals = [x.strip() for x in args.intervals.split(",") if x.strip()]
    for itv in intervals:
        _interval_to_ms(itv)

    results = run_research(
        symbol=args.symbol,
        months=args.months,
        intervals=intervals,
        starting_equity=args.starting_equity,
        trade_notional=args.trade_notional,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        lookback=args.lookback,
        volume_window=args.volume_window,
    )

    print("Comprehensive Research Complete")
    print(f"Symbol: {args.symbol}")
    print(f"Months: {args.months}")
    print(f"Intervals: {','.join(intervals)}")
    print(
        f"Costs: fee={args.fee_bps:.2f} bps/side, slippage={args.slippage_bps:.2f} bps/side, "
        f"trade_notional=${args.trade_notional:.2f}"
    )
    print(f"Total configs tested: {len(results)}")
    print("")
    print("Top Results")
    print("Rank | AnnRet% | TotRet% | MaxDD% | Sharpe | Trades | Params")
    print("-----+---------+---------+--------+--------+--------+-------")
    for idx, r in enumerate(results[: args.top], start=1):
        print(
            f"{idx:>4} | "
            f"{r.annualized_return_pct:>7.2f} | "
            f"{r.total_return_pct:>7.2f} | "
            f"{r.max_drawdown_pct:>6.2f} | "
            f"{r.sharpe_like:>6.2f} | "
            f"{r.trades:>6} | "
            f"{_params_brief(r.params)}"
        )

    winners = [r for r in results if r.annualized_return_pct >= args.hurdle_annual_pct]
    print("")
    print(f"Configs with annualized return >= {args.hurdle_annual_pct:.2f}%: {len(winners)}")
    for idx, r in enumerate(winners[: args.top], start=1):
        print(
            f"{idx:>4}. ann={r.annualized_return_pct:.2f}% tot={r.total_return_pct:.2f}% "
            f"maxDD={r.max_drawdown_pct:.2f}% trades={r.trades} {_params_brief(r.params)}"
        )


if __name__ == "__main__":
    main()
