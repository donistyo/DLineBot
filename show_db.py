from app.database.db_logger import DatabaseLogger
from app.database.session import SessionLocal
from app.database.models import TradeLog, EquitySnapshot

db = SessionLocal()

print("\n=== TRADE LOG ===")
trades = db.query(TradeLog).order_by(TradeLog.id.desc()).limit(20).all()
for t in trades:
    print(f"{t.time} | {t.signal:4} | conf={t.confidence:.0%} | {t.action:8} | {t.status:8} | {t.reason or ''}")

print(f"\nTotal hari ini: {db.query(TradeLog).count()}")

print("\n=== EQUITY SNAPSHOT ===")
snapshots = db.query(EquitySnapshot).order_by(EquitySnapshot.id.desc()).limit(10).all()
for s in snapshots:
    print(f"{s.time} | balance={s.balance} | equity={s.equity} | dd={s.drawdown}%")

db.close()
