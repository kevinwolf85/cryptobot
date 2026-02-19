import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    market_data_base_url: str = "https://api.binance.us"
    symbol: str = "BTCUSDT"
    interval: str = "1m"
    fast_ema: int = 12
    slow_ema: int = 26
    signal_ema: int = 9
    lookback_candles: int = 200
    poll_seconds: int = 20
    trade_usd_size: float = 50.0
    volume_window: int = 40
    volume_ratio_threshold: float = 1.2
    paper_starting_cash: float = 10_000.0
    paper_state_file: str = "state/paper_account.json"
    live_trading_enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8080


def _as_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _as_float(value: str, default: float) -> float:
    if value is None:
        return default
    return float(value)


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def from_env() -> AppConfig:
    load_dotenv()

    return AppConfig(
        market_data_base_url=os.getenv("MARKET_DATA_BASE_URL", "https://api.binance.us"),
        symbol=os.getenv("SYMBOL", "BTCUSDT"),
        interval=os.getenv("INTERVAL", "1m"),
        fast_ema=_as_int(os.getenv("FAST_EMA"), 12),
        slow_ema=_as_int(os.getenv("SLOW_EMA"), 26),
        signal_ema=_as_int(os.getenv("SIGNAL_EMA"), 9),
        lookback_candles=_as_int(os.getenv("LOOKBACK_CANDLES"), 200),
        poll_seconds=_as_int(os.getenv("POLL_SECONDS"), 20),
        trade_usd_size=_as_float(os.getenv("TRADE_USD_SIZE"), 50.0),
        volume_window=_as_int(os.getenv("VOLUME_WINDOW"), 40),
        volume_ratio_threshold=_as_float(os.getenv("VOLUME_RATIO_THRESHOLD"), 1.2),
        paper_starting_cash=_as_float(os.getenv("PAPER_STARTING_CASH"), 10_000.0),
        paper_state_file=os.getenv("PAPER_STATE_FILE", "state/paper_account.json"),
        live_trading_enabled=_as_bool(os.getenv("LIVE_TRADING_ENABLED"), False),
        host=os.getenv("HOST", "127.0.0.1"),
        port=_as_int(os.getenv("PORT"), 8080),
    )
