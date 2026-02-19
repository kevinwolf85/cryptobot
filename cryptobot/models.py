from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class VolumeSnapshot:
    buy_volume: float
    sell_volume: float

    @property
    def ratio(self) -> float:
        if self.sell_volume <= 0:
            return float("inf")
        return self.buy_volume / self.sell_volume


@dataclass(frozen=True)
class SignalResult:
    action: str
    reason: str
    macd: float
    signal: float
    histogram: float
    volume_ratio: float


@dataclass(frozen=True)
class ExecutedTrade:
    side: str
    symbol: str
    quantity: float
    price: float
    timestamp_iso: str

    @staticmethod
    def now(side: str, symbol: str, quantity: float, price: float) -> "ExecutedTrade":
        return ExecutedTrade(
            side=side,
            symbol=symbol,
            quantity=quantity,
            price=price,
            timestamp_iso=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
