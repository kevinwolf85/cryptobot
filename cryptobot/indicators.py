from typing import Iterable, List


def ema(values: Iterable[float], period: int) -> List[float]:
    values = list(values)
    if period <= 0:
        raise ValueError("period must be > 0")
    if not values:
        return []

    alpha = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append((v * alpha) + (result[-1] * (1 - alpha)))
    return result


def macd_series(
    closes: Iterable[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[float], list[float], list[float]]:
    closes = list(closes)
    if slow_period <= fast_period:
        raise ValueError("slow_period must be > fast_period")

    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)
    macd = [f - s for f, s in zip(fast, slow)]
    signal = ema(macd, signal_period)
    hist = [m - s for m, s in zip(macd, signal)]
    return macd, signal, hist


def crossover_direction(macd: list[float], signal: list[float]) -> str:
    if len(macd) < 2 or len(signal) < 2:
        return "none"

    prev_diff = macd[-2] - signal[-2]
    curr_diff = macd[-1] - signal[-1]

    if prev_diff <= 0 < curr_diff:
        return "bullish"
    if prev_diff >= 0 > curr_diff:
        return "bearish"
    return "none"


def rsi_series(closes: Iterable[float], period: int = 14) -> list[float]:
    values = list(closes)
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(values) < 2:
        return [50.0 for _ in values]

    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[1 : period + 1]) / period if len(values) > period else sum(gains[1:]) / max(len(values) - 1, 1)
    avg_loss = sum(losses[1 : period + 1]) / period if len(values) > period else sum(losses[1:]) / max(len(values) - 1, 1)

    out: list[float] = [50.0] * len(values)
    start = min(period + 1, len(values))
    for i in range(start, len(values)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out
