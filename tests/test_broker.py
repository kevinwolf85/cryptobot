import tempfile
import unittest
from pathlib import Path

from cryptobot.broker import PaperBroker


class BrokerTests(unittest.TestCase):
    def test_buy_and_sell_flow(self):
        with tempfile.TemporaryDirectory() as d:
            state_file = str(Path(d) / "paper.json")
            broker = PaperBroker(state_file=state_file, starting_cash=1000)

            buy_trade = broker.buy(symbol="BTCUSDT", price=100, usd_notional=100)
            self.assertIsNotNone(buy_trade)
            self.assertAlmostEqual(broker.account.cash, 900)

            sell_trade = broker.sell_all(symbol="BTCUSDT", price=120)
            self.assertIsNotNone(sell_trade)
            self.assertAlmostEqual(broker.account.base_asset_qty, 0)
            self.assertTrue(broker.account.cash > 1000)


if __name__ == "__main__":
    unittest.main()
