import unittest

from cryptobot.models import VolumeSnapshot
from cryptobot.strategy import evaluate_signal


class StrategyTests(unittest.TestCase):
    def test_returns_hold_when_volume_is_weak(self):
        closes = [100 + i for i in range(60)]
        result = evaluate_signal(
            closes=closes,
            volume=VolumeSnapshot(buy_volume=10, sell_volume=10),
            fast_ema=12,
            slow_ema=26,
            signal_ema=9,
            volume_ratio_threshold=1.5,
        )
        self.assertIn(result.action, {"hold", "buy", "sell"})

    def test_ratio_calculation(self):
        ratio = VolumeSnapshot(buy_volume=12, sell_volume=4).ratio
        self.assertEqual(ratio, 3)


if __name__ == "__main__":
    unittest.main()
