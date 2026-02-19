from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cryptobot.models import ExecutedTrade


@dataclass
class PaperAccount:
    cash: float
    base_asset_qty: float = 0.0
    trades: list[ExecutedTrade] = field(default_factory=list)

    def can_buy(self, usd_notional: float) -> bool:
        return self.cash >= usd_notional

    def can_sell(self, qty: float) -> bool:
        return self.base_asset_qty >= qty


class PaperBroker:
    def __init__(self, state_file: str, starting_cash: float) -> None:
        self._state_file = Path(state_file)
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self.account = self._load_or_create(starting_cash)

    def _load_or_create(self, starting_cash: float) -> PaperAccount:
        if not self._state_file.exists():
            account = PaperAccount(cash=starting_cash)
            self._save(account)
            return account

        payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        trades = [ExecutedTrade(**t) for t in payload.get("trades", [])]
        return PaperAccount(
            cash=float(payload.get("cash", starting_cash)),
            base_asset_qty=float(payload.get("base_asset_qty", 0.0)),
            trades=trades,
        )

    def _save(self, account: PaperAccount | None = None) -> None:
        account = account or self.account
        payload = {
            "cash": account.cash,
            "base_asset_qty": account.base_asset_qty,
            "trades": [asdict(t) for t in account.trades],
        }
        self._state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def buy(self, symbol: str, price: float, usd_notional: float) -> ExecutedTrade | None:
        if price <= 0 or usd_notional <= 0 or not self.account.can_buy(usd_notional):
            return None

        qty = usd_notional / price
        trade = ExecutedTrade.now("buy", symbol, qty, price)
        self.account.cash -= usd_notional
        self.account.base_asset_qty += qty
        self.account.trades.append(trade)
        self._save()
        return trade

    def sell_all(self, symbol: str, price: float) -> ExecutedTrade | None:
        qty = self.account.base_asset_qty
        if price <= 0 or qty <= 0:
            return None

        usd_value = qty * price
        trade = ExecutedTrade.now("sell", symbol, qty, price)
        self.account.cash += usd_value
        self.account.base_asset_qty = 0.0
        self.account.trades.append(trade)
        self._save()
        return trade

    def snapshot(self, mark_price: float) -> dict:
        equity = self.account.cash + (self.account.base_asset_qty * mark_price)
        return {
            "cash": round(self.account.cash, 2),
            "base_asset_qty": round(self.account.base_asset_qty, 8),
            "mark_price": round(mark_price, 2),
            "equity": round(equity, 2),
            "trade_count": len(self.account.trades),
        }
