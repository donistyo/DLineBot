from datetime import datetime
from app.database.session import SessionLocal
from app.database.models import TradeLog, EquitySnapshot, LearningRecord


def _parse_time(val):
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
    return datetime.now()


class DatabaseLogger:

    def __init__(self):
        self.db = SessionLocal()

    def close(self):
        self.db.close()

    def log_trade(self, trade_data):

        entry = TradeLog(
            time=_parse_time(trade_data.get("time")),
            symbol=trade_data.get("symbol", "XAUUSD"),
            signal=trade_data.get("signal"),
            confidence=trade_data.get("confidence"),
            action=trade_data.get("action"),
            status=trade_data.get("status"),
            reason=trade_data.get("reason"),
            entry_price=trade_data.get("entry_price"),
            stop_loss=trade_data.get("stop_loss"),
            take_profit=trade_data.get("take_profit"),
            lot_size=trade_data.get("lot_size"),
            profit=trade_data.get("profit"),
            ticket=trade_data.get("ticket"),
            created_at=datetime.now()
        )
        self.db.add(entry)
        self.db.commit()

    def log_equity(self, equity_data):

        entry = EquitySnapshot(
            time=datetime.now(),
            balance=equity_data.get("balance"),
            equity=equity_data.get("equity"),
            floating_pl=equity_data.get("floating_pl"),
            drawdown=equity_data.get("drawdown"),
            peak_balance=equity_data.get("peak_balance"),
            created_at=datetime.now()
        )
        self.db.add(entry)
        self.db.commit()

    def log_learning_record(self, record_data):
        entry = LearningRecord(
            symbol=record_data.get("symbol", "XAUUSD"),
            signal=record_data.get("signal"),
            confidence=record_data.get("confidence"),
            entry_price=record_data.get("entry_price"),
            status="PENDING",
            entry_time=datetime.now()
        )
        self.db.add(entry)
        self.db.commit()
        return entry.id

    def update_learning_record(self, record_id, profit, exit_price):
        rec = self.db.query(LearningRecord).filter_by(id=record_id).first()
        if rec:
            rec.profit = profit
            rec.exit_price = exit_price
            rec.status = "CLOSED"
            rec.close_time = datetime.now()
            self.db.commit()

    def get_recent_trades(self, limit=20):

        return (
            self.db.query(TradeLog)
            .order_by(TradeLog.id.desc())
            .limit(limit)
            .all()
        )

    def get_trade_count_today(self):

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            self.db.query(TradeLog)
            .filter(TradeLog.created_at >= today)
            .count()
        )

    def get_learning_records(self, limit=50):
        return (
            self.db.query(LearningRecord)
            .order_by(LearningRecord.id.desc())
            .limit(limit)
            .all()
        )
