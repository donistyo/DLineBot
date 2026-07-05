from app.mt5.session import MT5Session
import MetaTrader5 as mt5


class EquityManager:

    def __init__(self, drawdown_warning=5.0, drawdown_danger=10.0):
        self.peak_equity = 0
        self.max_drawdown = 0
        self.drawdown_warning = drawdown_warning
        self.drawdown_danger = drawdown_danger

    def get_info(self):

        MT5Session.ensure_connection()

        account = mt5.account_info()

        if account is None:
            print("MT5 Error :", mt5.last_error())
            return None

        balance = account.balance
        equity = account.equity
        floating_pl = equity - balance

        if equity > self.peak_equity:
            self.peak_equity = equity

        current_drawdown = 0
        if self.peak_equity > 0 and equity < self.peak_equity:
            current_drawdown = round(
                (self.peak_equity - equity) / self.peak_equity * 100, 1
            )

        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown

        if current_drawdown >= self.drawdown_danger:
            status = "DANGER"
        elif current_drawdown >= self.drawdown_warning:
            status = "WARNING"
        else:
            status = "SAFE"

        return {
            "balance": balance,
            "equity": equity,
            "floating_pl": floating_pl,
            "drawdown": current_drawdown,
            "max_drawdown": self.max_drawdown,
            "peak_equity": self.peak_equity,
            "status": status,
            "currency": account.currency
        }
