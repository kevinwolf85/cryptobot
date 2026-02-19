from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from cryptobot.config import from_env
from cryptobot.models import VolumeSnapshot
from cryptobot.strategy import evaluate_signal


@dataclass
class BacktestTrade:
    side: str
    ts: int
    iso_time: str
    price: float
    qty: float
    usd_notional: float


@dataclass
class BacktestResult:
    symbol: str
    interval: str
    start: str
    end: str
    candles: int
    starting_cash: float
    ending_cash: float
    ending_asset_qty: float
    ending_price: float
    ending_equity: float
    net_pnl: float
    net_return_pct: float
    buys: int
    sells: int
    completed_round_trips: int
    winning_round_trips: int
    losing_round_trips: int
    trades: List[BacktestTrade]


def _interval_to_ms(interval: str) -> int:
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "m":
        return value * 60_000
    if unit == "h":
        return value * 60 * 60_000
    if unit == "d":
        return value * 24 * 60 * 60_000
    raise ValueError("Unsupported interval. Use values like 1m, 15m, 1h, 4h, 1d.")


def _get_json(base_url: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_klines_range(
    base_url: str,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
) -> List[list]:
    step_ms = _interval_to_ms(interval)
    cursor = start_ms
    rows: List[list] = []

    while cursor < end_ms:
        batch = _get_json(
            base_url,
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": limit,
            },
        )
        if not batch:
            break
        rows.extend(batch)
        last_open_time = int(batch[-1][0])
        cursor = last_open_time + step_ms
        # polite pacing for public endpoint
        time.sleep(0.05)

        if len(batch) < limit:
            break

    deduped: Dict[int, list] = {}
    for row in rows:
        deduped[int(row[0])] = row
    return [deduped[k] for k in sorted(deduped.keys())]


def run_backtest(
    base_url: str,
    symbol: str,
    interval: str,
    months: int,
    starting_cash: float,
    lookback_candles: int,
    fast_ema: int,
    slow_ema: int,
    signal_ema: int,
    volume_window: int,
    volume_ratio_threshold: float,
    trade_usd_size: float,
) -> BacktestResult:
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=30 * months)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    rows = fetch_klines_range(
        base_url=base_url,
        symbol=symbol,
        interval=interval,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    if len(rows) < max(lookback_candles, volume_window) + 2:
        raise RuntimeError("Not enough candles returned for requested backtest window.")

    cash = float(starting_cash)
    asset_qty = 0.0
    trades: List[BacktestTrade] = []

    running_cost_basis = 0.0
    completed_round_trips = 0
    winning_round_trips = 0
    losing_round_trips = 0

    start_index = max(lookback_candles, volume_window)
    for i in range(start_index, len(rows)):
        closes = [float(r[4]) for r in rows[i - lookback_candles + 1 : i + 1]]
        volume_rows = rows[i - volume_window + 1 : i + 1]

        buy_vol = 0.0
        sell_vol = 0.0
        for r in volume_rows:
            total_volume = float(r[5])
            taker_buy_volume = float(r[9]) if len(r) > 9 else 0.0
            buy_vol += taker_buy_volume
            sell_vol += max(0.0, total_volume - taker_buy_volume)

        signal = evaluate_signal(
            closes=closes,
            volume=VolumeSnapshot(buy_volume=buy_vol, sell_volume=sell_vol),
            fast_ema=fast_ema,
            slow_ema=slow_ema,
            signal_ema=signal_ema,
            volume_ratio_threshold=volume_ratio_threshold,
        )
        price = float(rows[i][4])
        ts = int(rows[i][0])
        iso_time = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()

        if signal.action == "buy" and cash >= trade_usd_size and trade_usd_size > 0 and price > 0:
            qty = trade_usd_size / price
            cash -= trade_usd_size
            asset_qty += qty
            running_cost_basis += trade_usd_size
            trades.append(
                BacktestTrade(
                    side="buy",
                    ts=ts,
                    iso_time=iso_time,
                    price=price,
                    qty=qty,
                    usd_notional=trade_usd_size,
                )
            )
        elif signal.action == "sell" and asset_qty > 0 and price > 0:
            proceeds = asset_qty * price
            qty = asset_qty
            cash += proceeds
            asset_qty = 0.0
            trades.append(
                BacktestTrade(
                    side="sell",
                    ts=ts,
                    iso_time=iso_time,
                    price=price,
                    qty=qty,
                    usd_notional=proceeds,
                )
            )
            completed_round_trips += 1
            pnl = proceeds - running_cost_basis
            if pnl > 0:
                winning_round_trips += 1
            elif pnl < 0:
                losing_round_trips += 1
            running_cost_basis = 0.0

    ending_price = float(rows[-1][4])
    ending_equity = cash + (asset_qty * ending_price)
    net_pnl = ending_equity - starting_cash
    net_return_pct = (net_pnl / starting_cash * 100.0) if starting_cash > 0 else math.nan

    buys = len([t for t in trades if t.side == "buy"])
    sells = len([t for t in trades if t.side == "sell"])

    return BacktestResult(
        symbol=symbol,
        interval=interval,
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        candles=len(rows),
        starting_cash=starting_cash,
        ending_cash=cash,
        ending_asset_qty=asset_qty,
        ending_price=ending_price,
        ending_equity=ending_equity,
        net_pnl=net_pnl,
        net_return_pct=net_return_pct,
        buys=buys,
        sells=sells,
        completed_round_trips=completed_round_trips,
        winning_round_trips=winning_round_trips,
        losing_round_trips=losing_round_trips,
        trades=trades,
    )


def main() -> None:
    cfg = from_env()
    parser = argparse.ArgumentParser(description="Run historical backtest for CryptoBot MACD/volume strategy.")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--interval", type=str, default="1h")
    parser.add_argument("--symbol", type=str, default=cfg.symbol)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    result = run_backtest(
        base_url=cfg.market_data_base_url,
        symbol=args.symbol,
        interval=args.interval,
        months=args.months,
        starting_cash=cfg.paper_starting_cash,
        lookback_candles=cfg.lookback_candles,
        fast_ema=cfg.fast_ema,
        slow_ema=cfg.slow_ema,
        signal_ema=cfg.signal_ema,
        volume_window=cfg.volume_window,
        volume_ratio_threshold=cfg.volume_ratio_threshold,
        trade_usd_size=cfg.trade_usd_size,
    )

    if args.as_json:
        payload = asdict(result)
        payload["trades"] = [asdict(t) for t in result.trades]
        print(json.dumps(payload, indent=2))
        return

    print("Backtest Complete")
    print(f"Symbol: {result.symbol}")
    print(f"Interval: {result.interval}")
    print(f"Window: {result.start} -> {result.end}")
    print(f"Candles: {result.candles}")
    print(f"Starting cash: ${result.starting_cash:,.2f}")
    print(f"Ending equity: ${result.ending_equity:,.2f}")
    print(f"Net PnL: ${result.net_pnl:,.2f} ({result.net_return_pct:.2f}%)")
    print(f"Trades: buys={result.buys}, sells={result.sells}")
    print(
        "Round trips: "
        f"{result.completed_round_trips} "
        f"(wins={result.winning_round_trips}, losses={result.losing_round_trips})"
    )


if __name__ == "__main__":
    main()
