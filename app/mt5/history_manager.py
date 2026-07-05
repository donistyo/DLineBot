from datetime import datetime
import MetaTrader5 as mt5

from app.mt5.session import MT5Session


class HistoryManager:

    def __init__(self):

        MT5Session.ensure_connection()

    # =====================================
    # Get Today Deals
    # =====================================

    def today(self):

        MT5Session.ensure_connection()

        now = datetime.now()

        start = datetime(
            now.year,
            now.month,
            now.day
        )

        deals = mt5.history_deals_get(
            start,
            now
        )

        if deals is None:
            return []

        return list(deals)

    # =====================================
    # Summary
    # =====================================

    def summary(self):

        deals = self.today()

        trade = len(deals)

        win = 0
        loss = 0
        profit = 0

        gross_profit = 0
        gross_loss = 0

        largest_win = 0
        largest_loss = 0

        for deal in deals:

            p = deal.profit

            profit += p

            if p > 0:

                win += 1

                gross_profit += p

                if p > largest_win:
                    largest_win = p

            elif p < 0:

                loss += 1

                gross_loss += abs(p)

                if p < largest_loss:
                    largest_loss = p

        win_rate = 0

        if trade > 0:

            win_rate = round(
                win / trade * 100,
                2
            )

        profit_factor = 0

        if gross_loss > 0:

            profit_factor = round(
                gross_profit / gross_loss,
                2
            )

        return {

            "trade": trade,

            "win": win,

            "loss": loss,

            "profit": profit,

            "gross_profit": gross_profit,

            "gross_loss": gross_loss,

            "profit_factor": profit_factor,

            "largest_win": largest_win,

            "largest_loss": largest_loss,

            "win_rate": win_rate

        }

    # =====================================
    # Last Deal
    # =====================================

    def last_trade(self):

        deals = self.today()

        if not deals:
            return None

        return deals[-1]