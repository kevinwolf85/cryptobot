import unittest

from cryptobot.indicators import crossover_direction, ema, macd_series, rsi_series


class IndicatorTests(unittest.TestCase):
    def test_ema_basic(self):
        values = [1, 2, 3]
        series = ema(values, period=2)
        self.assertEqual(len(series), 3)
        self.assertAlmostEqual(series[0], 1)
        self.assertTrue(series[-1] > series[0])

    def test_macd_series_lengths(self):
        closes = [float(i) for i in range(1, 120)]
        macd, signal, hist = macd_series(closes)
        self.assertEqual(len(macd), len(closes))
        self.assertEqual(len(signal), len(closes))
        self.assertEqual(len(hist), len(closes))

    def test_crossover(self):
        macd = [0.1, -0.1, 0.2]
        signal = [0.2, 0.0, 0.1]
        self.assertEqual(crossover_direction(macd, signal), "bullish")

    def test_rsi_bounds(self):
        closes = [100, 101, 99, 102, 98, 103, 97, 104, 96, 105, 95, 106, 94, 107, 93, 108]
        values = rsi_series(closes, period=14)
        self.assertEqual(len(values), len(closes))
        self.assertTrue(all(0.0 <= x <= 100.0 for x in values))


if __name__ == "__main__":
    unittest.main()
