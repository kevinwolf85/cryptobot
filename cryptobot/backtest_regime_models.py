from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, List

from cryptobot.backtest import _interval_to_ms, fetch_klines_range
from cryptobot.config import from_env
from cryptobot.indicators import ema, macd_series, rsi_series


@dataclass(frozen=True)
class ModelResult:
    model: str
    interval: str
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    trades: int


def _annualization_factor(interval: str) -> float:
    ms = _interval_to_ms(interval)
    return (365.0 * 24 * 60 * 60 * 1000) / ms


def _annualized_return(total_return: float, years: float) -> float:
    if years <= 0:
        return 0.0
    if total_return <= -0.999999:
        return -1.0
    return (1.0 + total_return) ** (1.0 / years) - 1.0


def _max_drawdown_pct(curve: Iterable[float]) -> float:
    peak = -math.inf
    max_dd = 0.0
    for x in curve:
        if x > peak:
            peak = x
        if peak > 0:
            dd = (peak - x) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd * 100.0


def _rolling_ann_vol(closes: List[float], i: int, window: int, interval: str) -> float:
    if i - window < 1:
        return 0.0
    rets = []
    for j in range(i - window + 1, i + 1):
        p0, p1 = closes[j - 1], closes[j]
        if p0 > 0:
            rets.append(math.log(p1 / p0))
    if len(rets) < 2:
        return 0.0
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(max(var, 0.0)) * math.sqrt(_annualization_factor(interval))


def _atr(rows: List[list], period: int = 14) -> List[float]:
    tr = [0.0]
    for i in range(1, len(rows)):
        high = float(rows[i][2])
        low = float(rows[i][3])
        prev_close = float(rows[i - 1][4])
        tr_i = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr.append(tr_i)
    return ema(tr, period)


def _equity_backtest(
    rows: List[list],
    interval: str,
    decide_position: Callable[[int, List[float], List[float], List[float], List[float], List[float]], int],
    starting_equity: float = 10_000.0,
    trade_notional: float = 1_000.0,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    stop_loss_pct: float = 0.02,
    take_profit_pct: float = 0.06,
    atr_stop_mult: float = 0.0,
    atr_take_mult: float = 0.0,
) -> tuple[float, float, float, int]:
    closes = [float(r[4]) for r in rows]
    highs = [float(r[2]) for r in rows]
    lows = [float(r[3]) for r in rows]
    e50 = ema(closes, 50)
    e200 = ema(closes, 200)
    atr = _atr(rows, 14)
    fee_rate = fee_bps / 10_000.0
    slip = slippage_bps / 10_000.0

    cash = starting_equity
    qty = 0.0
    side = 0
    entry = 0.0
    trades = 0
    curve: List[float] = []
    start = 220

    for i in range(start, len(rows)):
        px = closes[i]

        if side != 0 and entry > 0:
            pnl_pct = (px - entry) / entry if side > 0 else (entry - px) / entry
            sl_hit = pnl_pct <= -stop_loss_pct
            tp_hit = pnl_pct >= take_profit_pct
            if atr_stop_mult > 0:
                sl_hit = sl_hit or (abs(px - entry) >= atr[i] * atr_stop_mult and pnl_pct < 0)
            if atr_take_mult > 0:
                tp_hit = tp_hit or (abs(px - entry) >= atr[i] * atr_take_mult and pnl_pct > 0)
            if sl_hit or tp_hit:
                if side > 0:
                    ex = px * (1.0 - slip)
                    notional = qty * ex
                    cash += notional - (notional * fee_rate)
                else:
                    ex = px * (1.0 + slip)
                    notional = abs(qty) * ex
                    cash -= notional + (notional * fee_rate)
                qty = 0.0
                side = 0
                entry = 0.0
                trades += 1

        wanted = decide_position(i, closes, highs, lows, e50, e200)

        if side == -1 and wanted >= 0:
            ex = px * (1.0 + slip)
            notional = abs(qty) * ex
            cash -= notional + (notional * fee_rate)
            qty = 0.0
            side = 0
            entry = 0.0
            trades += 1
        elif side == 1 and wanted <= 0:
            ex = px * (1.0 - slip)
            notional = qty * ex
            cash += notional - (notional * fee_rate)
            qty = 0.0
            side = 0
            entry = 0.0
            trades += 1

        if side == 0 and wanted != 0 and cash > 0:
            notional = min(trade_notional, cash)
            if wanted > 0:
                ex = px * (1.0 + slip)
                q = notional / ex
                fee = notional * fee_rate
                if notional + fee <= cash:
                    cash -= notional + fee
                    qty = q
                    side = 1
                    entry = ex
                    trades += 1
            else:
                ex = px * (1.0 - slip)
                q = notional / ex
                fee = notional * fee_rate
                cash += notional - fee
                qty = -q
                side = -1
                entry = ex
                trades += 1

        curve.append(cash + qty * px)

    if side != 0:
        px = closes[-1]
        if side > 0:
            ex = px * (1.0 - slip)
            notional = qty * ex
            cash += notional - (notional * fee_rate)
        else:
            ex = px * (1.0 + slip)
            notional = abs(qty) * ex
            cash -= notional + (notional * fee_rate)
        trades += 1

    ending = cash
    total = (ending / starting_equity) - 1.0
    years = (len(rows) * _interval_to_ms(interval)) / (365.0 * 24 * 60 * 60 * 1000)
    ann = _annualized_return(total, years)
    dd = _max_drawdown_pct(curve if curve else [starting_equity, ending])
    return total * 100.0, ann * 100.0, dd, trades


def _regime_switch_decider(interval: str) -> Callable[[int, List[float], List[float], List[float], List[float], List[float]], int]:
    def decide(i: int, closes: List[float], _h: List[float], _l: List[float], e50: List[float], e200: List[float]) -> int:
        trend_strength = abs(e50[i] - e200[i]) / max(closes[i], 1e-9)
        vol = _rolling_ann_vol(closes, i, 48, interval)
        macd, signal, _ = macd_series(closes[i - 220 : i + 1], fast_period=12, slow_period=26, signal_period=9)
        cross_up = macd[-2] <= signal[-2] and macd[-1] > signal[-1]
        cross_dn = macd[-2] >= signal[-2] and macd[-1] < signal[-1]

        trend_regime = trend_strength > 0.01 and vol < 1.8
        range_regime = trend_strength < 0.003
        if trend_regime:
            if cross_up:
                return 1
            if cross_dn:
                return -1
        elif range_regime:
            return 0
        return 0

    return decide


def _breakout_atr_decider(lookback: int = 20) -> Callable[[int, List[float], List[float], List[float], List[float], List[float]], int]:
    def decide(i: int, closes: List[float], highs: List[float], lows: List[float], e50: List[float], e200: List[float]) -> int:
        if i - lookback < 1:
            return 0
        upper = max(highs[i - lookback : i])
        lower = min(lows[i - lookback : i])
        px = closes[i]
        trend_up = e50[i] > e200[i]
        trend_dn = e50[i] < e200[i]
        if px > upper and trend_up:
            return 1
        if px < lower and trend_dn:
            return -1
        return 0

    return decide


def _range_reversion_decider(interval: str) -> Callable[[int, List[float], List[float], List[float], List[float], List[float]], int]:
    def decide(i: int, closes: List[float], _h: List[float], _l: List[float], e50: List[float], e200: List[float]) -> int:
        trend_strength = abs(e50[i] - e200[i]) / max(closes[i], 1e-9)
        vol = _rolling_ann_vol(closes, i, 48, interval)
        if not (trend_strength < 0.004 and vol < 1.4):
            return 0
        rsi = rsi_series(closes[i - 220 : i + 1], period=14)
        if rsi[-1] < 30:
            return 1
        if rsi[-1] > 70:
            return -1
        return 0

    return decide


def run_models(symbol: str, months: int, intervals: List[str]) -> List[ModelResult]:
    cfg = from_env()
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=30 * months)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    out: List[ModelResult] = []
    for interval in intervals:
        rows = fetch_klines_range(cfg.market_data_base_url, symbol, interval, start_ms, end_ms)
        if len(rows) < 260:
            continue
        t_ret, t_ann, t_dd, t_trades = _equity_backtest(
            rows,
            interval,
            _regime_switch_decider(interval),
            stop_loss_pct=0.02,
            take_profit_pct=0.06,
        )
        out.append(ModelResult("regime_trend_macd", interval, t_ret, t_ann, t_dd, t_trades))

        b_ret, b_ann, b_dd, b_trades = _equity_backtest(
            rows,
            interval,
            _breakout_atr_decider(20),
            stop_loss_pct=0.02,
            take_profit_pct=0.06,
            atr_stop_mult=2.0,
            atr_take_mult=4.0,
        )
        out.append(ModelResult("breakout_atr", interval, b_ret, b_ann, b_dd, b_trades))

        r_ret, r_ann, r_dd, r_trades = _equity_backtest(
            rows,
            interval,
            _range_reversion_decider(interval),
            stop_loss_pct=0.015,
            take_profit_pct=0.03,
        )
        out.append(ModelResult("range_mean_reversion", interval, r_ret, r_ann, r_dd, r_trades))
    return out


def main() -> None:
    cfg = from_env()
    parser = argparse.ArgumentParser(description="Backtest regime/breakout/range models.")
    parser.add_argument("--symbol", type=str, default=cfg.symbol)
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--intervals", type=str, default="30m,1h,2h,4h,6h,8h,12h")
    parser.add_argument("--hurdle", type=float, default=8.0)
    args = parser.parse_args()

    intervals = [x.strip() for x in args.intervals.split(",") if x.strip()]
    results = run_models(args.symbol, args.months, intervals)
    results.sort(key=lambda x: x.annualized_return_pct, reverse=True)

    print("Regime Model Battery Complete")
    print("Rank | Model                 | Interval | AnnRet% | TotRet% | MaxDD% | Trades")
    print("-----+-----------------------+----------+---------+---------+--------+-------")
    for i, r in enumerate(results, 1):
        print(
            f"{i:>4} | {r.model:<21} | {r.interval:<8} | {r.annualized_return_pct:>7.2f} | "
            f"{r.total_return_pct:>7.2f} | {r.max_drawdown_pct:>6.2f} | {r.trades:>5}"
        )

    winners = [r for r in results if r.annualized_return_pct >= args.hurdle]
    print(f"\nAbove {args.hurdle:.2f}% annualized: {len(winners)}")
    for r in winners:
        print(f"- {r.model} @ {r.interval}: ann={r.annualized_return_pct:.2f}% dd={r.max_drawdown_pct:.2f}%")


if __name__ == "__main__":
    main()
