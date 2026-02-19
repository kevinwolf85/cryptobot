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
