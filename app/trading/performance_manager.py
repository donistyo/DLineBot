import os
import pandas as pd


class PerformanceManager:

    def __init__(self):

        self.log_file = "logs/live_trade_log.csv"

    def summary(self):

        if not os.path.exists(self.log_file):

            return {

                "total_trade": 0,
                "win": 0,
                "loss": 0,

                "win_rate": 0,

                "gross_profit": 0,
                "gross_loss": 0,
                "net_profit": 0,

                "profit_factor": 0,

                "avg_win": 0,
                "avg_loss": 0,

                "largest_win": 0,
                "largest_loss": 0

            }

        df = pd.read_csv(self.log_file)

        if "profit" not in df.columns:

            return {

                "total_trade": len(df),
                "win": 0,
                "loss": 0,

                "win_rate": 0,

                "gross_profit": 0,
                "gross_loss": 0,
                "net_profit": 0,

                "profit_factor": 0,

                "avg_win": 0,
                "avg_loss": 0,

                "largest_win": 0,
                "largest_loss": 0

            }

        profit = df["profit"].fillna(0)

        win = profit[profit > 0]
        loss = profit[profit < 0]

        total = len(profit)

        gross_profit = win.sum()

        gross_loss = abs(loss.sum())

        if gross_loss == 0:

            pf = 0

        else:

            pf = gross_profit / gross_loss

        return {

            "total_trade": total,

            "win": len(win),

            "loss": len(loss),

            "win_rate":
                (len(win) / total * 100)
                if total > 0 else 0,

            "gross_profit": gross_profit,

            "gross_loss": gross_loss,

            "net_profit": gross_profit - gross_loss,

            "profit_factor": pf,

            "avg_win":
                win.mean() if len(win) else 0,

            "avg_loss":
                loss.mean() if len(loss) else 0,

            "largest_win":
                win.max() if len(win) else 0,

            "largest_loss":
                loss.min() if len(loss) else 0

        }