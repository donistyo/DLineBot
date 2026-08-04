from app.mt5.history_manager import HistoryManager

class DailyRiskManager:

    def __init__(
        self,
        max_trade=5,
        max_daily_loss=-150,
        max_daily_profit=300
    ):
        self.history = HistoryManager()

        self.max_trade = max_trade
        self.max_daily_loss = max_daily_loss
        self.max_daily_profit = max_daily_profit

    def allow(self, symbol=None):

        summary = self.history.summary(symbol=symbol)

        trade_today = summary["trade"]

        profit_today = summary["profit"]

        if trade_today >= self.max_trade:

            return {
                "allowed": False,
                "reason": "Batas trade harian tercapai."
            }

        if profit_today <= self.max_daily_loss:

            return {
                "allowed": False,
                "reason": "Max Daily Loss tercapai."
            }

        if profit_today >= self.max_daily_profit:

            return {
                "allowed": False,
                "reason": "Target profit harian tercapai."
            }

        return {
            "allowed": True,
            "reason": "Trading diizinkan.",
            "trade_today": trade_today,
            "profit_today": profit_today
        }