from app.mt5.position_controller import PositionController


class EmergencyExit:

    def __init__(self, max_loss_per_trade=50, max_daily_loss=200,
                 max_drawdown_pct=15, max_spread_mult=3):
        self.controller = PositionController()
        self.max_loss_per_trade = max_loss_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_drawdown_pct = max_drawdown_pct
        self.max_spread_mult = max_spread_mult
        self._daily_loss = 0
        self._peak_balance = 0

    def process(self, position, account=None, market=None):
        ticket = position.ticket
        profit = position.profit
        reasons = []

        if profit < 0 and abs(profit) >= self.max_loss_per_trade:
            result = self.controller.close(position)
            return {"status": "CLOSED", "action": "EMERGENCY",
                    "reason": f"Max loss per trade (${abs(profit):.0f}/${self.max_loss_per_trade}).",
                    "ticket": ticket, "result": result, "emergency_type": "max_loss"}

        if account:
            if isinstance(account, dict):
                equity = account.get("equity", 0)
                balance = account.get("balance", 0)
            else:
                equity = account.equity
                balance = account.balance
            if equity > self._peak_balance:
                self._peak_balance = equity

            dd_pct = 0
            if self._peak_balance > 0:
                dd_pct = (self._peak_balance - equity) / self._peak_balance * 100

            if dd_pct >= self.max_drawdown_pct:
                result = self.controller.close(position)
                return {"status": "CLOSED", "action": "EMERGENCY",
                        "reason": f"Max drawdown ({dd_pct:.1f}%/{self.max_drawdown_pct}%).",
                        "ticket": ticket, "result": result, "emergency_type": "drawdown"}

        if market is not None:
            try:
                spread = float(market.get("spread", 0))
                atr = float(market.get("ATR", 1))
                if atr > 0 and spread > atr * self.max_spread_mult:
                    result = self.controller.close(position)
                    return {"status": "CLOSED", "action": "EMERGENCY",
                            "reason": f"Spread membengkak ({spread:.0f} > {atr:.0f}x{self.max_spread_mult}).",
                            "ticket": ticket, "result": result, "emergency_type": "spread"}
            except Exception:
                pass

        return {"status": "SAFE", "action": "NONE",
                "reason": "Tidak ada kondisi darurat.", "ticket": ticket}

    def set_daily_loss(self, value):
        self._daily_loss = value

    def set_peak_balance(self, value):
        self._peak_balance = max(self._peak_balance, value)
