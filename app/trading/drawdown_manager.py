from app.mt5.session import MT5Session
import MetaTrader5 as mt5


class DrawdownManager:

    def __init__(self, max_drawdown=10.0):
        self.peak_balance = 0
        self.max_drawdown = max_drawdown

    def allow(self):

        MT5Session.ensure_connection()

        account = mt5.account_info()

        if account is None:
            print("MT5 Error :", mt5.last_error())
            return {
                "allowed": False,
                "reason": "MT5 Account tidak tersedia."
            }

        balance = account.balance

        if balance > self.peak_balance:
            self.peak_balance = balance

        if self.peak_balance == 0:
            return {
                "allowed": True,
                "reason": "Peak balance belum terbentuk.",
                "peak_balance": balance,
                "current_balance": balance,
                "drawdown": 0,
                "max_dd": self.max_drawdown
            }

        drawdown = round(
            (self.peak_balance - balance) / self.peak_balance * 100, 2
        )

        if drawdown >= self.max_drawdown:

            return {
                "allowed": False,
                "reason": "Max Drawdown tercapai. Trading diblokir.",
                "peak_balance": self.peak_balance,
                "current_balance": balance,
                "drawdown": drawdown,
                "max_dd": self.max_drawdown
            }

        return {
            "allowed": True,
            "reason": "Drawdown dalam batas aman.",
            "peak_balance": self.peak_balance,
            "current_balance": balance,
            "drawdown": drawdown,
            "max_dd": self.max_drawdown
        }
