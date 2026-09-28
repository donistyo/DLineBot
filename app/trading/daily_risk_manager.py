from datetime import datetime, timedelta

from app.mt5.history_manager import HistoryManager

class DailyRiskManager:

    def __init__(
        self,
        max_trade=5,
        max_daily_loss=-150,
        max_daily_profit=300,
        sl_break_count=0,
        sl_break_minutes=0
    ):
        self.history = HistoryManager()

        self.max_trade = max_trade
        self.max_daily_loss = max_daily_loss
        self.max_daily_profit = max_daily_profit
        self.sl_break_count = int(sl_break_count or 0)
        self.sl_break_minutes = int(sl_break_minutes or 0)

    def allow(self, symbol=None):

        summary = self.history.summary(symbol=symbol, bot_only=True)

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

        # =====================================
        # SL BREAK: N event SL dalam N menit -> istirahat
        # (dual pair dihitung 1 event; window, otomatis
        # jalan lagi setelah window lewat)
        # =====================================
        if self.sl_break_count > 0 and self.sl_break_minutes > 0:

            sl_events = self.history.sl_events(symbol=symbol, bot_only=True)

            if sl_events:

                window_start = datetime.now() - timedelta(minutes=self.sl_break_minutes)

                recent = [
                    t for t in sl_events
                    if datetime.fromtimestamp(t) >= window_start
                ]

                if len(recent) >= self.sl_break_count:

                    last_sl = max(recent)
                    resume_at = datetime.fromtimestamp(last_sl) + timedelta(minutes=self.sl_break_minutes)
                    now = datetime.now()

                    if now < resume_at:

                        remaining = max(1, int((resume_at - now).total_seconds() // 60) + 1)

                        return {
                            "allowed": False,
                            "reason": (
                                f"ISTIRAHAT: {len(recent)} SL dalam {self.sl_break_minutes} menit. "
                                f"Jalan lagi dalam {remaining} menit."
                            )
                        }

        return {
            "allowed": True,
            "reason": "Trading diizinkan.",
            "trade_today": trade_today,
            "profit_today": profit_today
        }