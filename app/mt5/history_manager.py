from datetime import datetime
import MetaTrader5 as mt5

from app.mt5.session import MT5Session

DEAL_ENTRY_IN = 0


class HistoryManager:

    def __init__(self):

        MT5Session.ensure_connection()

    # =====================================
    # Get Today Closed Trades
    # =====================================

    def _today_exits(self, symbol=None, bot_only=False):

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

        exits = [
            d for d in deals
            if d.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL)
            and d.entry == mt5.DEAL_ENTRY_OUT
            and (symbol is None or d.symbol == symbol)
            and (not bot_only or (d.comment and d.comment.startswith("DLineBot")))
        ]

        return list(exits)

    def today(self, symbol=None, bot_only=False):

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

        trades = [
            d for d in deals
            if d.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL)
            and d.entry == DEAL_ENTRY_IN
            and (symbol is None or d.symbol == symbol)
            and (not bot_only or (d.comment and d.comment.startswith("DLineBot")))
        ]

        return list(trades)

    def today_exits(self, symbol=None, bot_only=False):

        return self._today_exits(symbol, bot_only)

    def summary(self, symbol=None, bot_only=False):

        entries = self.today(symbol, bot_only)
        exits = self._today_exits(symbol, bot_only=False)

        entry_pos_ids = {d.position_id for d in entries}
        matched_exits = [e for e in exits if e.position_id in entry_pos_ids]

        trade = len(entries)

        win = 0
        loss = 0
        profit = 0

        gross_profit = 0
        gross_loss = 0

        largest_win = 0
        largest_loss = 0

        for deal in matched_exits:

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