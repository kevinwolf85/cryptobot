from __future__ import annotations

import threading
import time
from dataclasses import asdict

from cryptobot.broker import PaperBroker
from cryptobot.config import AppConfig
from cryptobot.market import BinanceMarketData
from cryptobot.strategy import evaluate_signal


class BotEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.market = BinanceMarketData(base_url=config.market_data_base_url)
        self.broker = PaperBroker(config.paper_state_file, config.paper_starting_cash)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

        self.last_signal: dict = {"action": "hold", "reason": "initializing"}
        self.last_error: str | None = None
        self.last_tick_ts: float | None = None
        self.last_price: float = 0.0

        if self.config.live_trading_enabled:
            raise RuntimeError("Live trading is not implemented. Keep LIVE_TRADING_ENABLED=false.")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="cryptobot-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            started = time.time()
            self.run_once()
            elapsed = time.time() - started
            to_sleep = max(1, self.config.poll_seconds - int(elapsed))
            self._stop_event.wait(timeout=to_sleep)

    def run_once(self) -> None:
        try:
            candles = self.market.fetch_candles(
                symbol=self.config.symbol,
                interval=self.config.interval,
                limit=self.config.lookback_candles,
            )
            volume = self.market.fetch_volume_snapshot(
                symbol=self.config.symbol,
                limit=self.config.volume_window,
            )
            last_price = candles[-1].close
            closes = [c.close for c in candles]

            signal = evaluate_signal(
                closes=closes,
                volume=volume,
                fast_ema=self.config.fast_ema,
                slow_ema=self.config.slow_ema,
                signal_ema=self.config.signal_ema,
                volume_ratio_threshold=self.config.volume_ratio_threshold,
            )

            executed_trade = None
            if signal.action == "buy":
                executed_trade = self.broker.buy(
                    symbol=self.config.symbol,
                    price=last_price,
                    usd_notional=self.config.trade_usd_size,
                )
            elif signal.action == "sell":
                executed_trade = self.broker.sell_all(
                    symbol=self.config.symbol,
                    price=last_price,
                )

            with self._lock:
                payload = asdict(signal)
                payload["trade_executed"] = asdict(executed_trade) if executed_trade else None
                self.last_signal = payload
                self.last_error = None
                self.last_tick_ts = time.time()
                self.last_price = last_price

        except Exception as exc:  # pragma: no cover
            with self._lock:
                self.last_error = str(exc)
                self.last_tick_ts = time.time()

    def status(self) -> dict:
        with self._lock:
            price = self.last_price
            account = self.broker.snapshot(mark_price=price)
            return {
                "symbol": self.config.symbol,
                "interval": self.config.interval,
                "last_signal": self.last_signal,
                "last_error": self.last_error,
                "last_tick_ts": self.last_tick_ts,
                "account": account,
                "live_trading_enabled": self.config.live_trading_enabled,
            }

    def trades(self) -> list[dict]:
        return [asdict(t) for t in self.broker.account.trades]

    def config_view(self) -> dict:
        redacted = asdict(self.config)
        redacted["live_trading_enabled"] = False
        return redacted
