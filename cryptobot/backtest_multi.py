from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Tuple

from cryptobot.backtest import _interval_to_ms, fetch_klines_range
from cryptobot.config import from_env
from cryptobot.indicators import crossover_direction, ema, macd_series, rsi_series


@dataclass
class StrategyResult:
    name: str
    ending_equity: float
    net_pnl: float
    net_return_pct: float
    buys: int
    sells: int


def _volume_ratio(window_rows: List[list]) -> float:
    buy_vol = 0.0
    sell_vol = 0.0
    for r in window_rows:
        total_volume = float(r[5])
        taker_buy_volume = float(r[9]) if len(r) > 9 else 0.0
        buy_vol += taker_buy_volume
        sell_vol += max(0.0, total_volume - taker_buy_volume)
    if sell_vol <= 0:
        return float("inf")
    return buy_vol / sell_vol


def _run_single(
    rows: List[list],
    lookback: int,
    volume_window: int,
    trade_usd_size: float,
    starting_cash: float,
    decision: Callable[[List[float], float], str],
) -> StrategyResult:
    cash = float(starting_cash)
    asset_qty = 0.0
    buys = 0
    sells = 0
    for i in range(max(lookback, volume_window), len(rows)):
        closes = [float(r[4]) for r in rows[i - lookback + 1 : i + 1]]
        vol_ratio = _volume_ratio(rows[i - volume_window + 1 : i + 1])
        action = decision(closes, vol_ratio)
        price = float(rows[i][4])
        if action == "buy" and cash >= trade_usd_size and price > 0:
            qty = trade_usd_size / price
            cash -= trade_usd_size
            asset_qty += qty
            buys += 1
        elif action == "sell" and asset_qty > 0 and price > 0:
            cash += asset_qty * price
            asset_qty = 0.0
            sells += 1
    ending_price = float(rows[-1][4])
    ending_equity = cash + (asset_qty * ending_price)
    pnl = ending_equity - starting_cash
    ret = (pnl / starting_cash * 100.0) if starting_cash else 0.0
    return StrategyResult(
        name="",
        ending_equity=ending_equity,
        net_pnl=pnl,
        net_return_pct=ret,
        buys=buys,
        sells=sells,
    )


def strategy_macd_volume(volume_ratio_threshold: float) -> Callable[[List[float], float], str]:
    def decide(closes: List[float], vol_ratio: float) -> str:
        macd, signal, _ = macd_series(closes, fast_period=12, slow_period=26, signal_period=9)
        cross = crossover_direction(macd, signal)
        if cross == "bullish" and vol_ratio >= volume_ratio_threshold:
            return "buy"
        if cross == "bearish" and vol_ratio <= (1.0 / max(volume_ratio_threshold, 0.0001)):
            return "sell"
        return "hold"

    return decide


def strategy_macd_only() -> Callable[[List[float], float], str]:
    def decide(closes: List[float], _: float) -> str:
        macd, signal, _ = macd_series(closes, fast_period=12, slow_period=26, signal_period=9)
        cross = crossover_direction(macd, signal)
        if cross == "bullish":
            return "buy"
        if cross == "bearish":
            return "sell"
        return "hold"

    return decide


def strategy_ema_cross_volume(volume_ratio_threshold: float) -> Callable[[List[float], float], str]:
    def decide(closes: List[float], vol_ratio: float) -> str:
        fast = ema(closes, 20)
        slow = ema(closes, 50)
        cross = crossover_direction(fast, slow)
        if cross == "bullish" and vol_ratio >= volume_ratio_threshold:
            return "buy"
        if cross == "bearish":
            return "sell"
        return "hold"

    return decide


def strategy_macd_rsi() -> Callable[[List[float], float], str]:
    def decide(closes: List[float], _: float) -> str:
        macd, signal, _ = macd_series(closes, fast_period=12, slow_period=26, signal_period=9)
        rsi = rsi_series(closes, period=14)
        cross = crossover_direction(macd, signal)
        if cross == "bullish" and rsi[-1] < 65:
            return "buy"
        if cross == "bearish" and rsi[-1] > 40:
            return "sell"
        return "hold"

    return decide


def strategy_rsi_reversion() -> Callable[[List[float], float], str]:
    def decide(closes: List[float], _: float) -> str:
        rsi = rsi_series(closes, period=14)
        if rsi[-1] < 30:
            return "buy"
        if rsi[-1] > 70:
            return "sell"
        return "hold"

    return decide


def run_multi_backtest(
    months: int,
    interval: str,
    symbol: str,
    lookback_override: int | None = None,
) -> Tuple[List[StrategyResult], int, str, str]:
    cfg = from_env()
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=30 * months)
    rows = fetch_klines_range(
        base_url=cfg.market_data_base_url,
        symbol=symbol,
        interval=interval,
        start_ms=int(start_dt.timestamp() * 1000),
        end_ms=int(end_dt.timestamp() * 1000),
    )
    lookback = lookback_override if lookback_override is not None else cfg.lookback_candles
    if len(rows) < max(lookback, cfg.volume_window) + 2:
        raise RuntimeError("Not enough candles for backtest.")

    strategies: List[Tuple[str, Callable[[List[float], float], str]]] = [
        ("macd_volume", strategy_macd_volume(cfg.volume_ratio_threshold)),
        ("macd_only", strategy_macd_only()),
        ("ema20_50_volume", strategy_ema_cross_volume(cfg.volume_ratio_threshold)),
        ("macd_rsi_filter", strategy_macd_rsi()),
        ("rsi_mean_reversion", strategy_rsi_reversion()),
    ]
    results: List[StrategyResult] = []
    for name, decider in strategies:
        res = _run_single(
            rows=rows,
            lookback=lookback,
            volume_window=cfg.volume_window,
            trade_usd_size=cfg.trade_usd_size,
            starting_cash=cfg.paper_starting_cash,
            decision=decider,
        )
        res.name = name
        results.append(res)

    results.sort(key=lambda x: x.net_pnl, reverse=True)
    return results, len(rows), start_dt.isoformat(), end_dt.isoformat()


def main() -> None:
    cfg = from_env()
    parser = argparse.ArgumentParser(description="Run multiple strategy backtests side-by-side.")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--interval", type=str, default="1h")
    parser.add_argument("--symbol", type=str, default=cfg.symbol)
    parser.add_argument("--lookback", type=int, default=cfg.lookback_candles)
    args = parser.parse_args()

    # Validate interval early.
    _interval_to_ms(args.interval)

    results, candle_count, start_s, end_s = run_multi_backtest(
        months=args.months,
        interval=args.interval,
        symbol=args.symbol,
        lookback_override=args.lookback,
    )

    print("Multi-Strategy Backtest Complete")
    print(f"Symbol: {args.symbol}")
    print(f"Interval: {args.interval}")
    print(f"Window: {start_s} -> {end_s}")
    print(f"Candles: {candle_count}")
    print("")
    print("Rank | Strategy            | Net PnL    | Return   | Buys | Sells")
    print("-----+---------------------+------------+----------+------+------")
    for idx, r in enumerate(results, start=1):
        print(
            f"{idx:>4} | "
            f"{r.name:<19} | "
            f"${r.net_pnl:>9.2f} | "
            f"{r.net_return_pct:>7.2f}% | "
            f"{r.buys:>4} | "
            f"{r.sells:>5}"
        )


if __name__ == "__main__":
    main()
