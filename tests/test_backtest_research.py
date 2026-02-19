import unittest

from cryptobot.backtest_research import _annualized_return, _max_drawdown_pct


class BacktestResearchTests(unittest.TestCase):
    def test_annualized_return(self):
        # 4% over half year annualizes close to 8.16%
        ann = _annualized_return(0.04, 0.5)
        self.assertAlmostEqual(ann, 0.0816, places=3)

    def test_max_drawdown(self):
        curve = [10000, 11000, 9000, 9500, 12000, 10000]
        dd = _max_drawdown_pct(curve)
        # max drawdown is 18.18% from 11000 to 9000
        self.assertAlmostEqual(dd, 18.18, places=2)


if __name__ == "__main__":
    unittest.main()
