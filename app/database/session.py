from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from app.config.settings import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    connect_args={"check_same_thread": False, "timeout": 15}
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


@contextmanager
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.database.models import TradeLog, EquitySnapshot, LearningRecord
    from sqlalchemy import inspect, text
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA busy_timeout=15000"))
        conn.commit()
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("trade_log")]
    with engine.connect() as conn:
        if "profit" not in columns:
            conn.execute(text("ALTER TABLE trade_log ADD COLUMN profit FLOAT"))
        if "ticket" not in columns:
            conn.execute(text("ALTER TABLE trade_log ADD COLUMN ticket INTEGER"))
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
