from __future__ import annotations

import json
import urllib.parse
import urllib.request

from cryptobot.models import Candle, VolumeSnapshot


class BinanceMarketData:
    def __init__(self, base_url: str = "https://api.binance.us", timeout_seconds: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _get_json(self, path: str, params: dict[str, str | int] | None = None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)

    def fetch_candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        rows = self._get_json(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        candles = []
        for row in rows:
            candles.append(
                Candle(
                    timestamp=int(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        return candles

    def fetch_volume_snapshot(self, symbol: str, limit: int) -> VolumeSnapshot:
        rows = self._get_json(
            "/api/v3/aggTrades",
            params={"symbol": symbol, "limit": limit},
        )
        buy_volume = 0.0
        sell_volume = 0.0

        for row in rows:
            qty = float(row["q"])
            is_buyer_maker = bool(row["m"])
            if is_buyer_maker:
                sell_volume += qty
            else:
                buy_volume += qty

        return VolumeSnapshot(buy_volume=buy_volume, sell_volume=sell_volume)

    def fetch_last_price(self, symbol: str) -> float:
        row = self._get_json(
            "/api/v3/ticker/price",
            params={"symbol": symbol},
        )
        return float(row["price"])
