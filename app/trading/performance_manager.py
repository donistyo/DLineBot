from app.mt5.history_manager import HistoryManager


class PerformanceManager:

    def __init__(self):
        self.history = HistoryManager()

    def summary(self):

        h = self.history.summary()

        total = h["trade"]
        win = h["win"]
        loss = h["loss"]
        gross_profit = h["gross_profit"]
        gross_loss = h["gross_loss"]

        pf = 0
        if gross_loss > 0:
            pf = round(gross_profit / gross_loss, 2)

        return {
            "total_trade": total,
            "win": win,
            "loss": loss,
            "win_rate": h["win_rate"],
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_profit": h["profit"],
            "profit_factor": pf,
            "avg_win": round(gross_profit / win, 2) if win else 0,
            "avg_loss": round(gross_loss / loss, 2) if loss else 0,
            "largest_win": h["largest_win"],
            "largest_loss": h["largest_loss"]
        }