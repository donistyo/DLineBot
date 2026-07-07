from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, JSON, Boolean
from app.database.session import Base


class TradeLog(Base):

    __tablename__ = "trade_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    time = Column(DateTime, default=datetime.now)
    symbol = Column(String(20))
    signal = Column(String(10))
    confidence = Column(Float)
    action = Column(String(20))
    status = Column(String(20))
    reason = Column(String(255), nullable=True)
    entry_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=True)
    profit = Column(Float, nullable=True)
    ticket = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class EquitySnapshot(Base):

    __tablename__ = "equity_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    time = Column(DateTime, default=datetime.now)
    balance = Column(Float)
    equity = Column(Float)
    floating_pl = Column(Float)
    drawdown = Column(Float)
    peak_balance = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class LearningRecord(Base):

    __tablename__ = "learning_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket = Column(Integer, nullable=True)
    symbol = Column(String(20))
    signal = Column(String(10))
    confidence = Column(Float)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    profit = Column(Float, nullable=True)
    status = Column(String(20), default="PENDING")
    entry_time = Column(DateTime, default=datetime.now)
    close_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
