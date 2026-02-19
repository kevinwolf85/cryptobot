from cryptobot.indicators import crossover_direction, macd_series
from cryptobot.models import SignalResult, VolumeSnapshot


def evaluate_signal(
    closes: list[float],
    volume: VolumeSnapshot,
    fast_ema: int,
    slow_ema: int,
    signal_ema: int,
    volume_ratio_threshold: float,
) -> SignalResult:
    macd, signal, hist = macd_series(
        closes,
        fast_period=fast_ema,
        slow_period=slow_ema,
        signal_period=signal_ema,
    )
    cross = crossover_direction(macd, signal)
    ratio = volume.ratio

    if cross == "bullish" and ratio >= volume_ratio_threshold:
        return SignalResult(
            action="buy",
            reason="bullish MACD crossover with strong buy volume",
            macd=macd[-1],
            signal=signal[-1],
            histogram=hist[-1],
            volume_ratio=ratio,
        )

    bearish_trigger = 1 / max(volume_ratio_threshold, 0.0001)
    if cross == "bearish" and ratio <= bearish_trigger:
        return SignalResult(
            action="sell",
            reason="bearish MACD crossover with strong sell volume",
            macd=macd[-1],
            signal=signal[-1],
            histogram=hist[-1],
            volume_ratio=ratio,
        )

    return SignalResult(
        action="hold",
        reason="conditions not met",
        macd=macd[-1],
        signal=signal[-1],
        histogram=hist[-1],
        volume_ratio=ratio,
    )
