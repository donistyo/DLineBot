from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date, timedelta
from pathlib import Path
import json
import time
import functools
import threading
import pandas as pd
import MetaTrader5 as mt5
from app.database.session import db_session
from app.database.models import TradeLog, EquitySnapshot
from app.mt5.session import MT5Session
from app.mt5.parted_order import PartedOrder
from app.mt5.position_manager import PositionManager
from app.mt5.position_controller import PositionController
from app.mt5.pending_order_manager import PendingOrderManager
from app.mt5.order_builder import OrderBuilder
from app.mt5.order_sender import OrderSender
from app.notification.telegram_notifier import TelegramNotifier
from app.trading.trade_learner import TradeLearner
from app.trading.analytics import Analytics
from app.trading.model_version import ModelVersionManager
from app.trading.grid_manager import GridManager
from app.trading.learning_manager import LearningManager
from app.trading.trade_learner import TradeLearner
from app.indicators.engine import IndicatorEngine
from app.mt5.history_manager import HistoryManager
from app.config.features import FEATURE_COLUMNS

# =====================================
# Simple in-memory cache (N seconds)
# =====================================

class _Cache:
    def __init__(self, default_ttl=5):
        self._data = {}
        self._default_ttl = default_ttl

    def get(self, key):
        if key in self._data:
            val, ts, ttl = self._data[key]
            if time.time() - ts < ttl:
                return val
        return None

    def set(self, key, value, ttl=None):
        self._data[key] = (value, time.time(), ttl or self._default_ttl)

    def clear(self):
        self._data.clear()


_cache = _Cache(default_ttl=5)


def cached(ttl=5):
    def decorator(func):
        import functools

        @functools.wraps(func)
        def wrapper(*_args, **_kwargs):
            key = f"{func.__name__}:{_args}:{sorted(_kwargs.items())}"
            cached = _cache.get(key)
            if cached is not None:
                return cached
            result = func(*_args, **_kwargs)
            _cache.set(key, result, ttl)
            return result
        return wrapper
    return decorator


# =====================================
# Background MT5 cache (biar ga blocking)
# =====================================

_mt5_cache = {"positions": [], "pending": [], "account": {}, "last_update": 0}
_mt5_lock = threading.Lock()

def _refresh_mt5_cache():
    global _mt5_cache
    while True:
        try:
            MT5Session.connect()
            with _mt5_lock:
                acc = mt5.account_info()
                if acc:
                    _mt5_cache["account"] = {
                        "balance": acc.balance,
                        "equity": acc.equity,
                        "profit": acc.profit,
                        "margin": acc.margin,
                        "margin_free": acc.margin_free,
                    }
                pos = mt5.positions_get()
                _mt5_cache["positions"] = [
                     {"ticket": p.ticket, "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                      "volume": p.volume, "symbol": p.symbol, "open_price": p.price_open,
                      "current_price": p.price_current, "profit": round(p.profit, 2),
                      "sl": p.sl or 0, "tp": p.tp or 0, "comment": p.comment,
                      "open_time": datetime.fromtimestamp(p.time).strftime("%H:%M")}
                     for p in (pos or [])
                ]
                pending = mt5.orders_get()
                _mt5_cache["pending"] = [
                    {"ticket": o.ticket, "type": "BUY_STOP" if o.type == mt5.ORDER_TYPE_BUY_STOP
                     else "SELL_STOP" if o.type == mt5.ORDER_TYPE_SELL_STOP else str(o.type),
                     "volume": o.volume_initial, "price": o.price_open,
                     "sl": o.sl or 0, "tp": o.tp or 0, "symbol": o.symbol, "comment": o.comment}
                    for o in (pending or [])
                ]
                _mt5_cache["last_update"] = time.time()
        except:
            pass
        time.sleep(2)


def _start_mt5_cache():
    t = threading.Thread(target=_refresh_mt5_cache, daemon=True)
    t.start()


def get_cached_positions(symbol=None):
    with _mt5_lock:
        if symbol:
            return [p for p in _mt5_cache["positions"] if p["symbol"] == symbol]
        return list(_mt5_cache["positions"])


# =====================================
# Engine symbol switching hook
# =====================================

def _engine_restart_symbol():
    """Tandai runner agar restart engine dengan simbol aktif terbaru."""
    try:
        Path("runtime").mkdir(exist_ok=True)
        with open("runtime/engine_restart.json", "w") as f:
            json.dump({"requested": True, "ts": time.time()}, f)
    except Exception:
        pass


def get_cached_pending(symbol=None):
    with _mt5_lock:
        if symbol:
            return [p for p in _mt5_cache["pending"] if p["symbol"] == symbol]
        return list(_mt5_cache["pending"])


def get_cached_account():
    with _mt5_lock:
        return dict(_mt5_cache["account"])


# =====================================
# Manual trade learning (save features, track outcomes, retrain)
# =====================================

_learner = TradeLearner(min_trades=5)
_history_mgr = HistoryManager()
_learning_mgr = LearningManager(_learner, _history_mgr)
_indicator_engine = IndicatorEngine()


def save_trade_features(ticket, signal, confidence):
    try:
        import MetaTrader5 as mt5
        rates = mt5.copy_rates_from_pos(_active_symbol(), mt5.TIMEFRAME_M1, 0, 2000)
        if rates is None or len(rates) < 200:
            return False
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = _indicator_engine.calculate(df)
        df = df.dropna()
        if df.empty:
            return False
        last = df.iloc[-1]
        features = {col: last[col] for col in FEATURE_COLUMNS if col in last.index}
        _learning_mgr.track_open(ticket=ticket, features=features, signal=signal, confidence=confidence)
        return True
    except Exception as e:
        print(f"[LEARNING ERROR] {e}")
        return False


def _check_closed_loop():
    while True:
        try:
            MT5Session.connect()
            _learning_mgr.check_closed()
        except:
            pass
        time.sleep(30)


def _start_learning_loop():
    t = threading.Thread(target=_check_closed_loop, daemon=True)
    t.start()


app = FastAPI(title="DLine")


@app.on_event("startup")
def _startup():
    _start_mt5_cache()
    _start_learning_loop()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/dashboard-url")
def get_dashboard_url():
    try:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("DASHBOARD_URL="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    return {"url": val}
        return {"url": "http://127.0.0.1:8000"}
    except Exception:
        return {"url": "http://127.0.0.1:8000"}


@app.get("/api/trades")
@cached(ttl=5)
def get_trades(limit=50):
    with db_session() as db:
        trades = (
            db.query(TradeLog)
            .order_by(TradeLog.id.desc())
            .limit(limit)
            .all()
        )
    return [
        {
            "id": t.id,
            "time": str(t.time),
            "symbol": t.symbol,
            "signal": t.signal,
            "confidence": round(t.confidence * 100, 1) if t.confidence else 0,
            "action": t.action,
            "status": t.status,
            "reason": t.reason,
            "entry_price": t.entry_price,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "lot_size": t.lot_size,
        }
        for t in trades
    ]


@app.get("/api/equity")
@cached(ttl=5)
def get_equity(limit=100):
    with db_session() as db:
        snapshots = (
            db.query(EquitySnapshot)
            .order_by(EquitySnapshot.id.desc())
            .limit(limit)
            .all()
        )
    return [
        {
            "time": str(s.time),
            "balance": s.balance,
            "equity": s.equity,
            "floating_pl": s.floating_pl,
            "drawdown": s.drawdown,
        }
        for s in reversed(snapshots)
    ]


@app.get("/api/overview")
@cached(ttl=3)
def get_overview():
    path = Path("runtime/overview.json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass

    return {
        "balance": 0, "equity": 0, "floating_pl": 0, "drawdown": 0,
        "margin": 0, "margin_free": 0, "margin_level": 0,
        "server_time": str(datetime.now()),
        "signal": "-", "confidence": 0, "trade": "NO", "score": "-",
        "reason": "", "auto_trader_reason": "",
        "open_positions": [], "open_count": 0,
        "trades_today": 0, "profit_today": 0,
        "trades": [], "equity_snapshots": [],
        "learning": {"total": 0, "win": 0, "loss": 0, "win_rate": 0},
        "scalping": None,
    }


@app.get("/api/learning")
@cached(ttl=5)
def get_learning():
    learner = TradeLearner()
    return learner.get_learning_stats()


@app.get("/api/scalping/engine")
@cached(ttl=3)
def get_scalping_engine():
    path = Path("runtime/scalping.json")
    if not path.exists():
        return {"scalp_score": {"score": 0, "grade": "-", "direction": "WAIT", "action": "WAIT"}}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"scalp_score": {"score": 0, "grade": "-", "direction": "WAIT", "action": "WAIT"}}


# =====================================
# Analytics API
# =====================================

analytics = Analytics()


@app.get("/api/analytics/win_rate")
@cached(ttl=10)
def api_win_rate():
    return analytics.win_rate()


@app.get("/api/analytics/monthly_profit")
@cached(ttl=10)
def api_monthly_profit(months=6):
    return analytics.monthly_profit(months)


@app.get("/api/analytics/drawdown_curve")
@cached(ttl=10)
def api_drawdown_curve(limit=100):
    return analytics.drawdown_curve(limit)


@app.get("/api/analytics/trade_distribution")
@cached(ttl=10)
def api_trade_distribution():
    return analytics.trade_distribution()


@app.get("/api/analytics/signal_distribution")
@cached(ttl=10)
def api_signal_distribution():
    return analytics.signal_distribution()


@app.get("/api/analytics/confidence_histogram")
@cached(ttl=10)
def api_confidence_histogram():
    return analytics.confidence_histogram()


@app.get("/api/analytics/hour_performance")
@cached(ttl=10)
def api_hour_performance():
    return analytics.hour_performance()


@app.get("/api/analytics/session_performance")
@cached(ttl=10)
def api_session_performance():
    return analytics.session_performance()


@app.get("/api/analytics/heatmap")
@cached(ttl=10)
def api_heatmap():
    return analytics.heatmap()


@app.get("/api/analytics/ai_accuracy")
@cached(ttl=10)
def api_ai_accuracy():
    return analytics.ai_accuracy()


@app.get("/api/analytics/feature_importance")
@cached(ttl=30)
def api_feature_importance():
    learner = TradeLearner()
    return learner.get_feature_importance()


@app.get("/api/analytics/learning_progress")
@cached(ttl=10)
def api_learning_progress():
    return analytics.learning_progress()


@app.get("/api/model_version")
@cached(ttl=30)
def api_model_version():
    mvm = ModelVersionManager()
    return mvm.get_info()


# =====================================
# Live Market API
# =====================================

@app.get("/api/live-market")
def api_live_market():
    from app.mt5.account_store import get_active_account, get_account_symbols
    login = get_active_account().get("login")
    symbols = get_account_symbols(login)
    out = []
    for sym in symbols:
        try:
            import MetaTrader5 as mt5
            connected = MT5Session.ensure_connection()
            info = mt5.symbol_info(sym)
            tick = mt5.symbol_info_tick(sym) if info else None
            if tick and info:
                spread = round((tick.ask - tick.bid) / info.point, 0)
                out.append({
                    "symbol": sym, "bid": tick.bid, "ask": tick.ask,
                    "spread": int(spread)
                })
            else:
                with open("runtime/live_market_error.log", "a") as fe:
                    fe.write(f"{datetime.now()} {sym} info={info is not None} tick={tick is not None}\n")
        except Exception as e:
            import traceback
            with open("runtime/live_market_error.log", "a") as fe:
                fe.write(f"{datetime.now()} {sym} {e}\n{traceback.format_exc()}\n")
    return {"symbols": out}

# =====================================
# Manual Order API
# =====================================

def _active_symbol():
    try:
        from app.mt5.account_store import get_active_symbol
        return get_active_symbol()
    except Exception:
        return "XAUUSDc"


@app.post("/api/order/manual")
def api_manual_order(data: dict):
    symbol = data.get("symbol") or _active_symbol()
    signal = data.get("signal", "BUY").upper()
    volume = float(data.get("volume", 0.01))
    entry = float(data["entry"]) if data.get("entry") else None
    sl = float(data["sl"]) if data.get("sl") else None
    tp1 = float(data["tp1"]) if data.get("tp1") else None
    tp2 = float(data["tp2"]) if data.get("tp2") else None

    MT5Session.connect()
    try:
        order = PartedOrder(dry_run=False)
        result = order.execute(symbol, signal, volume, entry, sl, tp1, tp2)
        order.notify_telegram(result)
        ticket = result.get("result_1", {}).get("order", 0) if isinstance(result, dict) else 0
        save_trade_features(ticket, signal, 0.5)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/order/dry-run")
def api_dry_run(data: dict):
    symbol = data.get("symbol") or _active_symbol()
    signal = data.get("signal", "BUY").upper()
    volume = float(data.get("volume", 0.01))
    entry = float(data["entry"]) if data.get("entry") else None
    sl = float(data["sl"]) if data.get("sl") else None
    tp1 = float(data["tp1"]) if data.get("tp1") else None
    tp2 = float(data["tp2"]) if data.get("tp2") else None

    order = PartedOrder(dry_run=True)
    result = order.execute(symbol, signal, volume, entry, sl, tp1, tp2)
    ticket = result.get("result_1", {}).get("order", 0) if isinstance(result, dict) else 0
    save_trade_features(ticket, signal, 0.5)
    return {"success": True, "result": result}


@app.get("/api/order/parted")
def api_get_parted_orders(limit: int = 20):
    with db_session() as db:
        tp_trades = (
            db.query(TradeLog)
            .filter(TradeLog.action.like("%TP%"))
            .order_by(TradeLog.id.desc())
            .limit(limit)
            .all()
        )
        if len(tp_trades) < limit:
            recent = (
                db.query(TradeLog)
                .filter(~TradeLog.action.like("%TP%"))
                .order_by(TradeLog.id.desc())
                .limit(limit - len(tp_trades))
                .all()
            )
            trades = tp_trades + recent
        else:
            trades = tp_trades
    return [
        {
            "id": t.id,
            "time": str(t.time),
            "symbol": t.symbol or "XAUUSDc",
            "signal": t.signal or "BUY",
            "action": t.action,
            "entry_price": t.entry_price or "",
            "stop_loss": t.stop_loss or "",
            "take_profit": t.take_profit or "",
            "lot_size": t.lot_size or 0.01,
            "status": t.status or "",
            "ticket": t.ticket or "",
        }
        for t in trades
    ]


# =====================================
# Grid & Pending Order API
# =====================================

@app.post("/api/grid/place")
def api_grid_place(data: dict):
    symbol = data.get("symbol") or _active_symbol()
    layers = int(data.get("layers", 3))
    spacing = float(data.get("spacing", 2.0))
    lot = float(data.get("lot", 0.01))
    sl_dist = float(data.get("sl_dist", 6.0))
    tp_dist = float(data.get("tp_dist", 8.0))
    dry_run = data.get("dry_run", True)

    if not dry_run:
        if not MT5Session.connect():
            return {"success": False, "error": "Gagal konek MT5"}

    try:
        import MetaTrader5 as mt5
        if not mt5.symbol_info_tick(symbol):
            MT5Session.connect()
        tick = mt5.symbol_info_tick(symbol)
        current_price = tick.bid if tick else 4000.0
    except:
        return {"success": False, "error": "Gagal ambil harga"}

    gm = GridManager(
        symbol=symbol,
        dry_run=dry_run,
        grid_layers=layers,
        lot_size=lot,
        magic=10002,
    )
    gm.grid_atr_multiplier = spacing / 10.0
    gm.sl_atr_multiplier = sl_dist / 10.0
    gm.rr_ratio = tp_dist / sl_dist if sl_dist > 0 else 2.0

    try:
        results = gm.place_grid(current_price, atr=10.0)
        return {"success": True, "count": len(results), "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/grid/cancel")
def api_grid_cancel(data: dict):
    symbol = data.get("symbol") or _active_symbol()
    dry_run = data.get("dry_run", False)

    mgr = PendingOrderManager(dry_run=dry_run)
    count = mgr.cancel_all(symbol)
    return {"success": True, "cancelled": count}


@app.get("/api/grid/status")
def api_grid_status():
    symbol = _active_symbol()
    pending = get_cached_pending(symbol)
    positions = get_cached_positions(symbol)
    return {
        "pending_orders": pending,
        "pending_count": len(pending),
        "open_positions": positions,
    }


# =====================================
# Chart API
# =====================================

@app.get("/api/chart/candles")
def api_chart_candles():
    candles = []
    try:
        MT5Session.connect()
        from_ts = int((datetime.now() - timedelta(hours=12)).timestamp())
        to_ts = int(datetime.now().timestamp())
        rates = mt5.copy_rates_range(_active_symbol(), mt5.TIMEFRAME_M1, from_ts, to_ts)
        if rates is not None:
            n = len(rates)
            for i in range(max(0, n - 200), n):
                r = rates[i]
                candles.append({
                    "time": datetime.fromtimestamp(int(r[0])).strftime("%H:%M"),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                })
    except Exception as e:
        import traceback
        with open("runtime/chart_error.log","a") as fe:
            fe.write(f"{datetime.now()} {e}\n{traceback.format_exc()}\n")
    return {"candles": candles, "count": len(candles), "symbol": _active_symbol()}

# =====================================
# Intraday API
# =====================================

@app.get("/api/intraday")
def api_intraday():
    today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    to_date = int(datetime.now().timestamp())
    try:
        MT5Session.connect()
        deals = mt5.history_deals_get(today_start, to_date)
    except:
        deals = None

    data = {
        "today": {"trades": 0, "profit": 0.0, "wins": 0, "losses": 0, "be": 0},
        "hourly": {},
        "recent": [],
    }

    if deals:
        total_profit = 0.0
        wins = 0
        losses = 0
        be = 0
        hourly = {}
        recent = []

        for d in sorted(deals, key=lambda x: x.time, reverse=True):
            total_profit += d.profit
            if d.profit > 0:
                wins += 1
            elif d.profit < 0:
                losses += 1
            else:
                be += 1

            dt = datetime.fromtimestamp(d.time)
            hour_key = dt.strftime("%H:00")
            hourly[hour_key] = hourly.get(hour_key, 0) + d.profit

            if len(recent) < 20:
                recent.append({
                    "ticket": d.ticket,
                    "symbol": d.symbol,
                    "profit": round(d.profit, 2),
                    "time": dt.strftime("%H:%M:%S"),
                    "magic": d.magic,
                    "comment": d.comment or "",
                })

        n = len(deals)
        data["today"] = {
            "trades": n,
            "profit": round(total_profit, 2),
            "wins": wins,
            "losses": losses,
            "be": be,
            "wr": round(wins / n * 100, 1) if n else 0,
        }
        data["hourly"] = hourly
        data["recent"] = recent

    account = get_cached_account()
    data["account"] = {
        "balance": account.get("balance", 0),
        "equity": account.get("equity", 0),
    }

    return data

# =====================================
# Scalping API
# =====================================

@app.get("/api/scalping")
def api_scalping():
    data = {
        "performance": {"trades": 0, "profit": 0.0, "wins": 0, "losses": 0, "be": 0, "wr": 0, "avg_win": 0, "avg_loss": 0, "best": 0, "worst": 0},
        "history": [],
        "scalp_score": {"score": 0, "grade": "-", "direction": "NEUTRAL", "action": "WAIT"},
    }

    try:
        with open("runtime/scalping.json") as f:
            s = json.load(f)
            if "scalp_score" in s:
                data["scalp_score"] = s["scalp_score"]
    except:
        pass

    try:
        with open("runtime/overview.json") as f:
            ov = json.load(f)
            trades_today = ov.get("trades_today", 0)
            profit_today = ov.get("profit_today", 0.0)
            data["performance"]["trades"] = trades_today
            data["performance"]["profit"] = round(profit_today, 2)

            today_deals = ov.get("today_deals", [])
            if today_deals:
                profits = [d["profit"] for d in today_deals]
                n = len(profits)
                wins_list = [p for p in profits if p > 0]
                losses_list = [p for p in profits if p < 0]
                be_list = sum(1 for p in profits if p == 0)
                data["performance"].update({
                    "wins": len(wins_list),
                    "losses": len(losses_list),
                    "be": be_list,
                    "wr": round(len(wins_list) / n * 100, 1) if n else 0,
                    "avg_win": round(sum(wins_list) / len(wins_list), 2) if wins_list else 0,
                    "avg_loss": round(sum(losses_list) / len(losses_list), 2) if losses_list else 0,
                    "best": round(max(wins_list), 2) if wins_list else 0,
                    "worst": round(min(losses_list), 2) if losses_list else 0,
                })
                for d in reversed(today_deals):
                    data["history"].append({
                        "ticket": d.get("ticket", ""),
                        "symbol": d.get("symbol", "XAUUSDc"),
                        "profit": d.get("profit"),
                        "time": d.get("time", ""),
                        "magic": 0,
                        "comment": d.get("comment", ""),
                    })
            else:
                trades_list = ov.get("trades", [])
                for t in trades_list[:50]:
                    p = t.get("profit")
                    data["history"].append({
                        "ticket": t.get("id", ""),
                        "symbol": t.get("symbol", "XAUUSDc"),
                        "profit": round(p, 2) if p is not None else None,
                        "time": t.get("time", "")[-5:] if t.get("time") else "",
                        "magic": t.get("magic", 0),
                        "comment": t.get("reason") or t.get("status", ""),
                    })
    except:
        pass

    return data

# =====================================
# Auto-Trade Monitor API
# =====================================

@app.get("/api/auto-trade/monitor")
def api_auto_trade_monitor():
    account = get_cached_account()
    symbol = _active_symbol()
    positions = get_cached_positions(symbol)
    pending = get_cached_pending(symbol)
    scalp_raw = {"score": 0, "grade": "-", "direction": "NEUTRAL", "action": "WAIT"}
    try:
        with open("runtime/scalping.json") as f:
            s = json.load(f)
            if "scalp_score" in s:
                scalp_raw = s["scalp_score"]
    except:
        pass

    pos_out = []
    for p in positions:
        be = p.get("sl", 0) and abs(p["sl"] - p["open_price"]) < 0.02
        ts = p.get("sl", 0) and (
            (p["type"] == "BUY" and p["sl"] > p["open_price"] + 0.01) or
            (p["type"] == "SELL" and p["sl"] < p["open_price"] - 0.01)
        )
        pos_out.append({
            "ticket": p["ticket"], "type": p["type"], "volume": p["volume"],
            "open_price": p["open_price"], "current": p["current_price"],
            "profit": p["profit"], "sl": p["sl"], "tp": p["tp"],
            "open_time": p.get("open_time", ""),
            "be": be, "ts": ts
        })

    try:
        with open("runtime/trade_config.json") as _f:
            _lot = json.load(_f).get("lot_size", 0.01)
    except:
        _lot = 0.01
    _lot_opts = [0.01, 0.02, 0.03, 0.05, 0.10, 0.20, 0.50, 1.0]

    _enabled = _AUTO_TRADE_ENABLED
    try:
        with open("runtime/auto_trade_enabled.json") as _f:
            _enabled = json.load(_f).get("enabled", True)
    except:
        pass

    return {
        "account": {"balance": account.get("balance", 0), "equity": account.get("equity", 0)},
        "scalp": scalp_raw,
        "positions": pos_out,
        "pending_orders": pending,
        "last_update": time.strftime("%H:%M:%S"),
        "auto_trade_enabled": _enabled,
        "lot_size": _lot,
        "lot_options": _lot_opts,
    }


# =====================================
# Auto-Trade Toggle API
# =====================================

_AUTO_TRADE_ENABLED = True

@app.get("/api/auto-trade/enabled")
def api_auto_trade_get_enabled():
    global _AUTO_TRADE_ENABLED
    try:
        with open("runtime/auto_trade_enabled.json") as f:
            _AUTO_TRADE_ENABLED = json.load(f).get("enabled", True)
    except:
        pass
    return {"enabled": _AUTO_TRADE_ENABLED}

@app.get("/api/auto-trade/do-enable")
def api_auto_trade_enable():
    global _AUTO_TRADE_ENABLED
    from app.trading.daily_risk_manager import DailyRiskManager
    from app.config.settings import load_trade_config, get_trade_config
    load_trade_config()
    max_trade = get_trade_config("max_trade") or 20
    drm = DailyRiskManager(max_trade=int(max_trade), max_daily_loss=-500, max_daily_profit=9999)
    dr = drm.allow(symbol=_active_symbol())
    warning = None
    if not dr["allowed"]:
        warning = dr["reason"]
    _AUTO_TRADE_ENABLED = True
    Path("runtime").mkdir(exist_ok=True)
    with open("runtime/auto_trade_enabled.json", "w") as f:
        json.dump({"enabled": True}, f)
    return {"status": "ok", "enabled": True, "warning": warning}

@app.get("/api/auto-trade/do-disable")
def api_auto_trade_disable():
    global _AUTO_TRADE_ENABLED
    _AUTO_TRADE_ENABLED = False
    Path("runtime").mkdir(exist_ok=True)
    with open("runtime/auto_trade_enabled.json", "w") as f:
        json.dump({"enabled": False}, f)
    return {"status": "ok", "enabled": False}

@app.get("/api/auto-trade/lot-size")
def api_get_lot_size():
    try:
        with open("runtime/trade_config.json") as f:
            cfg = json.load(f)
            return {"lot_size": cfg.get("lot_size", 0.01)}
    except:
        return {"lot_size": 0.01}

@app.post("/api/auto-trade/set-lot")
def api_set_lot_size(data: dict):
    lot = float(data.get("lot_size", 0.01))
    lot = max(0.01, min(lot, 10.0))
    lot = round(lot, 2)
    Path("runtime").mkdir(exist_ok=True)
    try:
        with open("runtime/trade_config.json") as f:
            cfg = json.load(f)
    except:
        cfg = {}
    cfg["lot_size"] = lot
    with open("runtime/trade_config.json", "w") as f:
        json.dump(cfg, f)
    return {"status": "ok", "lot_size": lot}

# =====================================
# Account Management API (MT5 Login)
# =====================================

@app.get("/api/account/status")
def api_account_status():
    from app.mt5.account_store import get_active_account, get_active_symbol, get_account_symbols
    if not MT5Session.is_connected():
        MT5Session.connect()
    info = {}
    try:
        acc = mt5.account_info()
        if acc:
            info = {
                "login": acc.login,
                "server": acc.server,
                "name": acc.name,
                "balance": acc.balance,
                "equity": acc.equity,
                "currency": acc.currency,
                "leverage": acc.leverage,
            }
    except Exception:
        pass
    cfg = get_active_account()
    login = cfg.get("login") or (info.get("login") if info else None)
    return {
        "connected": MT5Session.is_connected(),
        "account": info,
        "active_config": cfg,
        "symbol": get_active_symbol(),
        "symbols": get_account_symbols(login),
    }

@app.post("/api/account/login")
def api_account_login(data: dict):
    from app.mt5.account_store import set_active_account, get_active_account, get_account_symbols
    login = str(data.get("login", "")).strip()
    password = str(data.get("password", "")).strip()
    server = str(data.get("server", "")).strip()

    if not login or not password or not server:
        return {"success": False, "error": "Login, password, dan server wajib diisi"}

    old_cfg = get_active_account()

    Path("runtime").mkdir(exist_ok=True)
    with open("runtime/auto_trade_enabled.json", "w") as f:
        json.dump({"enabled": False}, f)

    set_active_account(login, password, server)

    ok = MT5Session.restart()

    if not ok:
        if old_cfg:
            set_active_account(old_cfg.get("login"), old_cfg.get("password"), old_cfg.get("server"))
        else:
            from app.mt5.account_store import clear_active_account
            clear_active_account()
        MT5Session.restart()
        err = mt5.last_error()
        return {"success": False, "error": f"Login gagal: {err}", "retry_old": True}

    acc = mt5.account_info()
    info = {}
    if acc:
        info = {
            "login": acc.login,
            "server": acc.server,
            "name": acc.name,
            "balance": acc.balance,
            "equity": acc.equity,
            "currency": acc.currency,
            "leverage": acc.leverage,
        }
    _engine_restart_symbol()
    return {
        "success": True,
        "account": info,
        "symbol": get_active_account().get("symbol", "XAUUSDc"),
        "symbols": get_account_symbols(login),
    }

@app.post("/api/account/set-enabled")
def api_account_set_enabled(data: dict):
    enabled = bool(data.get("enabled", True))
    Path("runtime").mkdir(exist_ok=True)
    with open("runtime/auto_trade_enabled.json", "w") as f:
        json.dump({"enabled": enabled}, f)
    return {"status": "ok", "enabled": enabled}

@app.get("/api/account/saved")
def api_account_saved_list():
    from app.mt5.account_store import get_saved_accounts
    accounts = get_saved_accounts()
    for a in accounts:
        a = dict(a)
        if "password" in a:
            a["password"] = "***"
    return {"accounts": accounts}

@app.post("/api/account/saved")
def api_account_saved_add(data: dict):
    from app.mt5.account_store import add_saved_account
    name = str(data.get("name", "")).strip()
    login = str(data.get("login", "")).strip()
    password = str(data.get("password", "")).strip()
    server = str(data.get("server", "")).strip()
    if not name or not login or not password or not server:
        return {"success": False, "error": "Semua field wajib diisi"}
    accounts = add_saved_account(name, login, password, server)
    for a in accounts:
        if "password" in a:
            a["password"] = "***"
    return {"success": True, "accounts": accounts}

@app.delete("/api/account/saved/{name}")
def api_account_saved_delete(name: str):
    from app.mt5.account_store import remove_saved_account
    accounts = remove_saved_account(name)
    for a in accounts:
        if "password" in a:
            a["password"] = "***"
    return {"success": True, "accounts": accounts}

@app.post("/api/account/saved/{name}/switch")
def api_account_saved_switch(name: str):
    from app.mt5.account_store import find_saved_account, set_active_account, get_active_account, get_account_symbols
    saved = find_saved_account(name)
    if not saved:
        return {"success": False, "error": f"Akun '{name}' tidak ditemukan"}

    old_cfg = get_active_account()

    Path("runtime").mkdir(exist_ok=True)
    with open("runtime/auto_trade_enabled.json", "w") as f:
        json.dump({"enabled": False}, f)

    set_active_account(saved["login"], saved["password"], saved["server"])

    ok = MT5Session.restart()

    if not ok:
        if old_cfg:
            set_active_account(old_cfg.get("login"), old_cfg.get("password"), old_cfg.get("server"))
        MT5Session.restart()
        err = mt5.last_error()
        return {"success": False, "error": f"Switch gagal: {err}", "retry_old": True}

    acc = mt5.account_info()
    info = {}
    if acc:
        info = {
            "login": acc.login,
            "server": acc.server,
            "name": acc.name,
            "balance": acc.balance,
            "equity": acc.equity,
            "currency": acc.currency,
            "leverage": acc.leverage,
        }
    _engine_restart_symbol()
    return {
        "success": True,
        "account": info,
        "symbol": get_active_account().get("symbol", "XAUUSDc"),
        "symbols": get_account_symbols(saved["login"]),
    }


@app.post("/api/account/symbol")
def api_account_symbol(data: dict):
    from app.mt5.account_store import set_active_symbol, get_active_account, get_account_symbols
    symbol = str(data.get("symbol", "")).strip()
    if not symbol:
        return {"success": False, "error": "Symbol wajib diisi"}

    login = get_active_account().get("login")
    allowed = get_account_symbols(login)
    if allowed and symbol not in allowed:
        return {"success": False, "error": f"Symbol '{symbol}' tidak tersedia untuk akun ini"}

    set_active_symbol(symbol)

    _engine_restart_symbol()

    return {"success": True, "symbol": symbol, "symbols": allowed}

# =====================================
# Position Management API
# =====================================

@app.post("/api/position/modify")
def api_position_modify(data: dict):
    ticket = int(data.get("ticket", 0))
    sl = float(data["sl"]) if data.get("sl") else None
    tp = float(data["tp"]) if data.get("tp") else None
    dry_run = data.get("dry_run", True)

    if ticket <= 0:
        return {"success": False, "error": "Ticket tidak valid"}

    if not MT5Session.connect():
        return {"success": False, "error": "Gagal konek MT5"}

    try:
        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            return {"success": False, "error": "Posisi tidak ditemukan"}
        position = positions[0]
    except:
        return {"success": False, "error": "Gagal ambil posisi"}

    controller = PositionController()
    if sl and tp:
        result = controller.modify_sl_tp(position, sl, tp)
    elif sl:
        result = controller.modify_sl(position, sl)
    elif tp:
        result = controller.modify_tp(position, tp)
    else:
        return {"success": False, "error": "SL atau TP harus diisi"}

    return {"success": True, "result": result}


@app.post("/api/position/close")
def api_position_close(data: dict):
    ticket = int(data.get("ticket", 0))
    dry_run = data.get("dry_run", True)

    if ticket <= 0:
        return {"success": False, "error": "Ticket tidak valid"}

    if not MT5Session.connect():
        return {"success": False, "error": "Gagal konek MT5"}

    try:
        positions = mt5.positions_get(ticket=ticket)
        if not positions or len(positions) == 0:
            return {"success": False, "error": "Posisi tidak ditemukan"}
        position = positions[0]
    except:
        return {"success": False, "error": "Gagal ambil posisi"}

    controller = PositionController()
    from app.mt5.position_controller import _log_close
    _log_close("DASHBOARD_MANUAL", position.ticket, position.symbol, position.profit)
    result = controller.close(position, caller="DASHBOARD_MANUAL")
    return {"success": True, "result": result}


@app.get("/api/positions/manage")
def api_positions_manage():
    return {"positions": get_cached_positions(), "count": len(get_cached_positions())}


# =====================================
# Analytics API
# =====================================

@app.get("/api/analytics/summary")
def api_analytics_summary():
    wr = analytics.win_rate()
    acc = analytics.ai_accuracy()
    td = analytics.trade_distribution()
    return {
        "win_rate": wr,
        "ai_accuracy": acc,
        "trade_distribution": td
    }


@app.get("/logo")
def serve_logo():
    logo_path = Path("DIMAS (1).png")
    if logo_path.exists():
        return FileResponse(str(logo_path), media_type="image/png")
    return HTMLResponse(status_code=404)

@app.get("/favicon")
def serve_favicon():
    icon_path = Path("logo-tab.png")
    if icon_path.exists():
        return FileResponse(str(icon_path), media_type="image/png")
    return HTMLResponse(status_code=404)

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(HTML_PAGE)


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>DLine</title>
<link rel="icon" href="/favicon" type="image/png">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Inter','Segoe UI',sans-serif; background:linear-gradient(135deg,#0c1222 0%,#1a1a2e 50%,#16213e 100%); color:#e2e8f0; min-height:100vh; }
.app { display:flex; min-height:100vh; }
.sidebar { width:200px; background:rgba(15,23,42,0.85); backdrop-filter:blur(12px); border-right:1px solid rgba(59,130,246,0.15); padding:16px 10px; flex-shrink:0; position:sticky; top:0; height:100vh; overflow-y:auto; }
.sidebar-logo { display:flex; align-items:center; gap:8px; padding:0 6px 16px; border-bottom:1px solid rgba(59,130,246,0.1); margin-bottom:12px; }
.sidebar-logo img { height:36px; border-radius:4px; }
.sidebar-logo span { font-size:15px; font-weight:700; background:linear-gradient(135deg,#60a5fa,#a78bfa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.sidebar-item { display:flex; align-items:center; gap:8px; padding:8px 10px; border-radius:8px; color:#94a3b8; cursor:pointer; font-size:13px; transition:all 0.2s; margin-bottom:2px; }
.sidebar-item:hover { background:rgba(59,130,246,0.1); color:#e2e8f0; }
.sidebar-item.active { background:rgba(59,130,246,0.2); color:#60a5fa; font-weight:600; box-shadow:inset 2px 0 0 #3b82f6; }
.sidebar-icon { font-size:16px; width:20px; text-align:center; }
.main-content { flex:1; padding:20px 24px; overflow-y:auto; max-height:100vh; }
h2 { font-size:13px; margin:20px 0 8px; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px; font-weight:600; display:flex; align-items:center; gap:8px; }
h2:before { content:''; display:inline-block; width:3px; height:14px; background:linear-gradient(180deg,#3b82f6,#8b5cf6); border-radius:2px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px,1fr)); gap:8px; margin-bottom:12px; }
.card { background:rgba(30,41,59,0.6); backdrop-filter:blur(4px); padding:12px 14px; border-radius:10px; border:1px solid rgba(59,130,246,0.08); transition:all 0.2s; }
.card:hover { border-color:rgba(59,130,246,0.25); transform:translateY(-1px); }
.card .lbl { font-size:9px; color:#64748b; text-transform:uppercase; letter-spacing:0.3px; margin-bottom:4px; }
.card .val { font-size:17px; font-weight:700; }
.chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
@media(max-width:900px) { .chart-grid { grid-template-columns:1fr; } }
.chart-container { background:rgba(30,41,59,0.5); backdrop-filter:blur(4px); border-radius:10px; padding:12px; border:1px solid rgba(59,130,246,0.08); }
.green { color:#6ee7b7; }
.red { color:#fca5a5; }
.blue { color:#60a5fa; }
.yellow { color:#fbbf24; }
.purple { color:#a78bfa; }
table { width:100%; border-collapse:separate; border-spacing:0; background:rgba(30,41,59,0.5); backdrop-filter:blur(4px); border-radius:10px; overflow:hidden; font-size:11px; border:1px solid rgba(59,130,246,0.08); }
.table-wrap { overflow-x:auto; border-radius:10px; }
th { background:rgba(51,65,85,0.5); text-align:left; padding:6px 8px; color:#94a3b8; text-transform:uppercase; font-size:9px; letter-spacing:0.3px; }
td { padding:5px 8px; border-top:1px solid rgba(51,65,85,0.3); }
tr:hover td { background:rgba(59,130,246,0.05); }
.badge { display:inline-block; padding:2px 6px; border-radius:4px; font-size:9px; font-weight:600; }
.buy { background:rgba(6,95,70,0.3); color:#6ee7b7; }
.sell { background:rgba(127,29,29,0.3); color:#fca5a5; }
.hold { background:rgba(69,26,3,0.3); color:#fdba74; }
.status-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:4px; }
.status-running { background:#6ee7b7; box-shadow:0 0 6px rgba(110,231,183,0.4); }
.status-stopped { background:#fca5a5; }
.hamburger-btn { display:none; align-items:center; justify-content:center; width:32px; height:32px; background:rgba(59,130,246,0.1); border:none; border-radius:6px; color:#94a3b8; font-size:18px; cursor:pointer; transition:all 0.2s; }
.hamburger-btn:hover { background:rgba(59,130,246,0.2); color:#e2e8f0; }
.mobile-logo { display:none; height:28px; border-radius:4px; }
.header-left { display:flex; align-items:center; gap:6px; }
.mobile-menu { display:none; }
.heatmap-grid { display:grid; grid-template-columns:repeat(24,1fr); gap:1px; font-size:8px; }
.heatmap-cell { padding:2px 0; text-align:center; border-radius:1px; }
.heatmap-label { font-size:8px; color:#64748b; }
.auto-refresh { font-size:10px; color:#64748b; margin-bottom:6px; }
.header-bar { display:flex; align-items:center; justify-content:space-between; margin-bottom:20px; flex-wrap:wrap; gap:8px; }
.header-bar h1 { font-size:18px; font-weight:700; background:linear-gradient(135deg,#e2e8f0,#94a3b8); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.header-bar .header-right { display:flex; align-items:center; gap:12px; font-size:11px; color:#64748b; }
.header-badge { display:flex; align-items:center; gap:4px; background:rgba(59,130,246,0.1); padding:4px 10px; border-radius:6px; color:#60a5fa; font-weight:500; }
@media(max-width:768px) {
  .sidebar { width:54px; padding:12px 6px; }
  .sidebar-logo span { display:none; }
  .sidebar-logo img { height:28px; }
  .sidebar-item span { display:none; }
  .sidebar-item { justify-content:center; padding:8px; }
  .sidebar-icon { font-size:18px; width:auto; }
  .main-content { padding:12px; }
  .grid { grid-template-columns:repeat(2,1fr); }
  .chart-grid { grid-template-columns:1fr; }
  .card .val { font-size:15px; }
  .heatmap-grid { grid-template-columns:repeat(12,1fr); }
  .hamburger-btn { display:none; }
}
@media(max-width:600px) {
  .sidebar { display:none; }
  .sidebar-backdrop { display:none !important; }
  .main-content { padding:8px; }
  .grid { grid-template-columns:1fr; }
  .card .val { font-size:14px; }
  .header-bar h1 { font-size:15px; }
  .header-badge { padding:3px 6px; font-size:10px; }
  .hamburger-btn { display:flex; background:none; font-size:22px; color:#e2e8f0; width:auto; height:auto; }
  .mobile-logo { display:inline-block; }
  .header-bar .header-left { display:flex; align-items:center; gap:4px; }
  .sidebar-logo img { display:none; }
  h2 { font-size:11px; }
  table { font-size:10px; }
  th, td { padding:4px 5px; }
  .heatmap-grid { grid-template-columns:repeat(8,1fr); }
  .mobile-menu { display:none; flex-direction:column; background:rgba(15,23,42,0.95); backdrop-filter:blur(12px); border-bottom:1px solid rgba(59,130,246,0.15); padding:4px 8px; margin-bottom:8px; border-radius:0 0 10px 10px; }
  .mobile-menu.open { display:flex; }
  .mobile-menu .sidebar-item { padding:10px 12px; font-size:14px; }
  .mobile-menu .sidebar-item span { display:inline; }
  .mobile-menu .sidebar-item .sidebar-icon { font-size:18px; width:24px; }
}
@media(max-width:400px) {
  .main-content { padding:6px; }
  .grid { gap:5px; }
  .card { padding:8px 10px; }
  .card .val { font-size:13px; }
  .chart-container { padding:8px; }
}
</style>
</head>
<body>

<div class="app">
<div class="sidebar">
  <div class="sidebar-logo">
    <img src="/logo" alt="logo">
  </div>
  <div class="sidebar-item active" onclick="switchTab('main',this)">
    <span class="sidebar-icon">&#9632;</span><span>Overview</span>
  </div>
  <div class="sidebar-item" onclick="switchTab('analytics',this)">
    <span class="sidebar-icon">&#9881;</span><span>Analytics</span>
  </div>
  <div class="sidebar-item" onclick="switchTab('learning',this)">
    <span class="sidebar-icon">&#9855;</span><span>AI Learning</span>
  </div>
  <div class="sidebar-item" onclick="switchTab('manual',this)">
    <span class="sidebar-icon">&#9998;</span><span>Manual Order</span>
  </div>
  <div class="sidebar-item" onclick="switchTab('grid',this)">
    <span class="sidebar-icon">&#9776;</span><span>Grid &amp; Pending</span>
  </div>
  <div class="sidebar-item" onclick="switchTab('scalping',this)">
    <span class="sidebar-icon">&#9889;</span><span>Scalping</span>
  </div>
  <div class="sidebar-item" onclick="switchTab('intraday',this)">
    <span class="sidebar-icon">&#128202;</span><span>Intraday</span>
  </div>
  <div class="sidebar-item" onclick="switchTab('settings',this)">
    <span class="sidebar-icon">&#9881;</span><span>Settings</span>
  </div>
</div>
<div class="sidebar-backdrop" onclick="closeSidebar()"></div>
<div class="main-content">

<div class="header-bar">
  <div class="header-left">
    <button class="hamburger-btn" onclick="toggleSidebar()">&#9776;</button>
    <img src="/logo" alt="logo" class="mobile-logo">
  </div>
  <h1>Dashboard</h1>
  <div class="header-right">
    <span class="header-badge" id="publicUrlBadge" style="cursor:pointer" onclick="copyUrl()" title="Click to copy">&#128279; <span id="publicUrl">tunnel...</span></span>
    <span class="header-badge"><span class="status-dot status-running" id="headerStatusDot"></span><span id="headerStatus">Running</span></span>
    <span id="serverTime"></span>
  </div>
</div>

<div class="mobile-menu" id="mobileMenu">
  <div class="sidebar-item active" onclick="switchTab('main',this)"><span class="sidebar-icon">&#9632;</span><span>Overview</span></div>
  <div class="sidebar-item" onclick="switchTab('analytics',this)"><span class="sidebar-icon">&#9881;</span><span>Analytics</span></div>
  <div class="sidebar-item" onclick="switchTab('learning',this)"><span class="sidebar-icon">&#9855;</span><span>AI Learning</span></div>
  <div class="sidebar-item" onclick="switchTab('manual',this)"><span class="sidebar-icon">&#9998;</span><span>Manual Order</span></div>
  <div class="sidebar-item" onclick="switchTab('grid',this)"><span class="sidebar-icon">&#9776;</span><span>Grid & Pending</span></div>
  <div class="sidebar-item" onclick="switchTab('scalping',this)"><span class="sidebar-icon">&#9889;</span><span>Scalping</span></div>
  <div class="sidebar-item" onclick="switchTab('intraday',this)"><span class="sidebar-icon">&#128202;</span><span>Intraday</span></div>
  <div class="sidebar-item" onclick="switchTab('settings',this)"><span class="sidebar-icon">&#9881;</span><span>Settings</span></div>
</div>

<div id="tab-main">

<div class="grid" id="stats"></div>

<h2>AI Signal</h2>
<div class="grid" id="signalBox"></div>

<h2>Open Position</h2>
<div id="positionInfo" style="margin-bottom:6px;font-size:12px;"></div>
<div class="table-wrap"><table><thead><tr>
  <th>Ticket</th><th>Type</th><th>Vol</th><th>Entry</th><th>Current</th><th>Profit</th><th>SL</th><th>TP</th>
</tr></thead><tbody id="positions"></tbody></table></div>

<h2>Equity Curve</h2>
<div class="chart-container">
  <canvas id="equityChart" height="180"></canvas>
</div>

<h2>Trade History</h2>
<div class="table-wrap"><table><thead><tr>
  <th>Time</th><th>Sig</th><th>Conf</th><th>Action</th><th>Status</th><th>Entry</th><th>Profit</th><th>Lot</th>
</tr></thead><tbody id="trades"></tbody></table></div>

</div>

<div id="tab-analytics" style="display:none">

<h2>Win Rate</h2>
<div class="grid" id="winRateBox"></div>

<div class="chart-grid">
  <div class="chart-container"><canvas id="monthlyProfitChart" height="150"></canvas></div>
  <div class="chart-container"><canvas id="drawdownCurveChart" height="150"></canvas></div>
</div>

<div class="chart-grid">
  <div class="chart-container"><canvas id="tradeDistChart" height="150"></canvas></div>
  <div class="chart-container"><canvas id="signalDistChart" height="150"></canvas></div>
</div>

<div class="chart-grid">
  <div class="chart-container"><canvas id="confidenceHistChart" height="150"></canvas></div>
  <div class="chart-container"><canvas id="hourPerfChart" height="150"></canvas></div>
</div>

<h2>Session Performance</h2>
<div class="grid" id="sessionBox"></div>

<h2>AI Accuracy</h2>
<div class="grid" id="accuracyBox"></div>

<h2>Heatmap (Day x Hour Profit)</h2>
<div style="overflow-x:auto">
<div id="heatmapContainer" style="min-width:600px"></div>
</div>

</div>

<div id="tab-manual" style="display:none">

<div style="display:flex;gap:16px;flex-wrap:wrap">

<div style="flex:1;min-width:320px;max-width:420px">
<h2>Manual Order - SL, TP1, TP2</h2>
<div style="background:#1e293b;border-radius:6px;padding:16px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div><label style="font-size:11px;color:#94a3b8">Symbol</label><br><select id="mo_symbol" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"><option value="XAUUSDc">XAUUSDc</option></select></div>
    <div><label style="font-size:11px;color:#94a3b8">Signal</label><br>
      <select id="mo_signal" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px">
        <option value="BUY">BUY</option>
        <option value="SELL">SELL</option>
      </select>
    </div>
    <div><label style="font-size:11px;color:#94a3b8">Lot</label><br><input id="mo_volume" value="0.01" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Entry (kosongkan = auto)</label><br><input id="mo_entry" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Stop Loss</label><br><input id="mo_sl" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Take Profit 1</label><br><input id="mo_tp1" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div style="grid-column:span 2"><label style="font-size:11px;color:#94a3b8">Take Profit 2</label><br><input id="mo_tp2" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
  </div>
  <div style="margin-top:12px;display:flex;gap:8px">
    <button onclick="sendManualOrder(false)" style="flex:1;padding:8px;background:#3b82f6;color:#fff;border:none;border-radius:4px;font-weight:600;cursor:pointer">KIRIM ORDER</button>
    <button onclick="sendManualOrder(true)" style="padding:8px;background:#334155;color:#94a3b8;border:none;border-radius:4px;cursor:pointer">Dry Run</button>
  </div>
  <div id="mo_result" style="margin-top:12px;font-size:12px;color:#6ee7b7;word-break:break-all"></div>
</div>
</div>

<div style="flex:1;min-width:320px">
<h2>Chart Harga</h2>
<div class="chart-container" style="height:220px">
  <canvas id="manualChart"></canvas>
</div>
</div>

</div>

<h2 style="margin-top:16px">Live Market</h2>
<div class="table-wrap"><table><thead><tr>
  <th>Symbol</th><th>Bid</th><th>Ask</th><th>Spread</th>
  <th>SL (pt)</th><th>TP (pt)</th><th>Action</th>
</tr></thead><tbody id="liveMarketPrices"></tbody></table></div>

<h2 style="margin-top:16px">Trade Monitor</h2>
<div id="atmPanel2" style="background:#1e293b;border-radius:6px;padding:16px;font-size:12px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div><span style="color:#94a3b8">Balance</span><br><span id="atm_balance2" style="font-size:20px;font-weight:700;color:#e2e8f0">-</span></div>
    <div><span style="color:#94a3b8">Equity</span><br><span id="atm_equity2" style="font-size:20px;font-weight:700;color:#e2e8f0">-</span></div>
    <div><span style="color:#94a3b8">Scalp Score</span><br><span id="atm_score2" style="font-size:16px;font-weight:600">-</span></div>
    <div><span style="color:#94a3b8">Grade</span><br><span id="atm_grade2" style="font-size:16px;font-weight:600">-</span></div>
    <div><span style="color:#94a3b8">Direction</span><br><span id="atm_dir2" style="font-size:16px;font-weight:600">-</span></div>
    <div><span style="color:#94a3b8">Action</span><br><span id="atm_action2" style="font-size:16px;font-weight:600">-</span></div>
  </div>
  <hr style="border-color:#334155;margin:12px 0">
  <div style="color:#94a3b8;margin-bottom:6px">Positions <span id="atm_pos_count2" style="color:#e2e8f0">0</span></div>
  <div id="atm_positions2" style="max-height:200px;overflow-y:auto"></div>
  <hr style="border-color:#334155;margin:12px 0">
  <div style="color:#94a3b8;margin-bottom:6px">Pending Orders <span id="atm_pend_count2" style="color:#e2e8f0">0</span></div>
  <div id="atm_pending2" style="max-height:120px;overflow-y:auto;font-size:11px;color:#64748b"></div>
  <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
    <span style="color:#475569;font-size:10px">Updated: <span id="atm_updated2">-</span></span>
  </div>
</div>

</div>

<div id="tab-grid" style="display:none">

<div style="display:flex;gap:16px;flex-wrap:wrap">

<div style="flex:1;min-width:320px">
<h2>Grid Order (Buy Stop / Sell Stop)</h2>
<div style="background:#1e293b;border-radius:6px;padding:16px;max-width:500px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div><label style="font-size:11px;color:#94a3b8">Symbol</label><br><select id="gr_symbol" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"><option value="XAUUSDc">XAUUSDc</option></select></div>
    <div><label style="font-size:11px;color:#94a3b8">Layers</label><br><input id="gr_layers" value="3" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Spacing (pt)</label><br><input id="gr_spacing" value="3.0" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Lot per level</label><br><input id="gr_lot" value="0.01" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">SL Distance (pt)</label><br><input id="gr_sl" value="6.0" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">TP Distance (pt)</label><br><input id="gr_tp" value="8.0" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
  </div>
  <div style="margin-top:12px;display:flex;gap:8px">
    <button onclick="placeGrid(false)" style="flex:1;padding:8px;background:#3b82f6;color:#fff;border:none;border-radius:4px;font-weight:600;cursor:pointer">PLACE GRID</button>
    <button onclick="placeGrid(true)" style="padding:8px;background:#334155;color:#94a3b8;border:none;border-radius:4px;cursor:pointer">Dry Run</button>
    <button onclick="cancelGrid()" style="padding:8px;background:#dc2626;color:#fff;border:none;border-radius:4px;cursor:pointer">Cancel All</button>
  </div>
  <div id="gr_result" style="margin-top:12px;font-size:12px;color:#6ee7b7"></div>
</div>
<h2>Live <span id="gridSymbolTitle">XAUUSDc</span></h2>
<div class="chart-container" style="height:140px;max-width:500px">
  <canvas id="priceChartGrid"></canvas>
</div>
</div>

<div style="flex:1;min-width:320px">
<h2>Auto-Trade Monitor</h2>
<div id="atmPanel" style="background:#1e293b;border-radius:6px;padding:16px;font-size:12px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div><span style="color:#94a3b8">Balance</span><br><span id="atm_balance" style="font-size:20px;font-weight:700;color:#e2e8f0">-</span></div>
    <div><span style="color:#94a3b8">Equity</span><br><span id="atm_equity" style="font-size:20px;font-weight:700;color:#e2e8f0">-</span></div>
    <div><span style="color:#94a3b8">Scalp Score</span><br><span id="atm_score" style="font-size:16px;font-weight:600">-</span></div>
    <div><span style="color:#94a3b8">Grade</span><br><span id="atm_grade" style="font-size:16px;font-weight:600">-</span></div>
    <div><span style="color:#94a3b8">Direction</span><br><span id="atm_dir" style="font-size:16px;font-weight:600">-</span></div>
    <div><span style="color:#94a3b8">Action</span><br><span id="atm_action" style="font-size:16px;font-weight:600">-</span></div>
  </div>
  <hr style="border-color:#334155;margin:12px 0">
  <div style="color:#94a3b8;margin-bottom:4px;font-size:11px">AutoTrade Status</div>
  <div id="autoTraderInfo" style="font-size:12px;color:#e2e8f0;margin-bottom:8px">-</div>
  <hr style="border-color:#334155;margin:12px 0">
  <div style="color:#94a3b8;margin-bottom:6px">Positions <span id="atm_pos_count" style="color:#e2e8f0">0</span></div>
  <div id="atm_positions" style="max-height:200px;overflow-y:auto"></div>
  <hr style="border-color:#334155;margin:12px 0">
  <div style="color:#94a3b8;margin-bottom:6px">Pending Orders <span id="atm_pend_count" style="color:#e2e8f0">0</span></div>
  <div id="atm_pending" style="max-height:120px;overflow-y:auto;font-size:11px;color:#64748b"></div>
    <hr style="border-color:#334155;margin:12px 0">
    <div style="color:#94a3b8;margin-bottom:4px;font-size:11px">Lot Size</div>
    <div id="atm_lot_selector" style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px"></div>
    <div style="margin-top:8px;display:flex;gap:8px;align-items:center">
      <button id="atm_toggle_btn" onclick="toggleAutoTrade()" style="flex:1;padding:6px;border:none;border-radius:4px;font-weight:600;cursor:pointer;font-size:11px">...</button>
      <span style="color:#475569;font-size:10px">Updated: <span id="atm_updated">-</span></span>
    </div>
</div>
</div>

</div>

<h2>Pending Orders</h2>
<div class="table-wrap"><table><thead><tr>
  <th>Ticket</th><th>Type</th><th>Vol</th><th>Price</th><th>SL</th><th>TP</th><th>Comment</th>
</tr></thead><tbody id="pendingOrders"></tbody></table></div>

<h2>Open Positions</h2>
<div class="table-wrap"><table><thead><tr>
  <th>Ticket</th><th>Type</th><th>Vol</th><th>Entry</th><th>Current</th><th>Profit</th><th>SL</th><th>TP</th><th>Action</th>
</tr></thead><tbody id="managePositions"></tbody></table></div>

</div>

<div id="tab-scalping" style="display:none">

<h2>Smart Scalping Engine</h2>
<div class="grid" id="scalpingScoreBox"></div>
<div class="grid" id="scalpingEngineBox"></div>

<h2>Today's Performance</h2>
<div class="grid" id="scalpingPerfBox"></div>

<h2>Scalp Score</h2>
<div class="grid" id="scalpingScoreDetail" style="grid-template-columns:repeat(auto-fit,minmax(100px,1fr))"></div>

<h2>Trade History</h2>
<div class="table-wrap"><table><thead><tr>
  <th>Time</th><th>Ticket</th><th>Symbol</th><th>Profit</th><th>Comment</th>
</tr></thead><tbody id="scalpingHistory"></tbody></table></div>

</div>

<div id="tab-intraday" style="display:none">

<h2>Intraday Performance</h2>
<div class="grid" id="intradaySummary"></div>

<h2>Hourly P&L</h2>
<div class="chart-container">
  <canvas id="hourlyChart" height="120"></canvas>
</div>

<h2>Today's Trades</h2>
<div class="table-wrap"><table><thead><tr>
  <th>Time</th><th>Ticket</th><th>Symbol</th><th>Profit</th><th>Comment</th>
</tr></thead><tbody id="intradayTrades"></tbody></table></div>

</div>

<div id="tab-learning" style="display:none">

<h2>AI Learning Status</h2>
<div class="grid" id="learningBox"></div>

<h2>Learning Progress (Win Rate over Time)</h2>
<div class="chart-container">
  <canvas id="learningProgressChart" height="120"></canvas>
</div>

<h2>Feature Importance (Adaptive Weights)</h2>
<div class="grid" id="featureWeightsBox"></div>

<h2>Learning Records</h2>
<div class="table-wrap"><table><thead><tr>
  <th>ID</th><th>Signal</th><th>Conf</th><th>Entry</th><th>Exit</th><th>Profit</th><th>Status</th><th>Time</th>
</tr></thead><tbody id="learningRecords"></tbody></table></div>

</div>

<div id="tab-settings" style="display:none">

<h2>Account MT5</h2>
<div id="accStatusBox" style="background:#1e293b;border-radius:6px;padding:16px;font-size:13px">
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px" id="accInfoGrid">
    <div><span style="color:#94a3b8">Status</span><br><span id="acc_conn" style="font-weight:700;color:#e2e8f0">-</span></div>
    <div><span style="color:#94a3b8">Login</span><br><span id="acc_login" style="font-weight:700;color:#e2e8f0">-</span></div>
    <div><span style="color:#94a3b8">Server</span><br><span id="acc_server" style="font-weight:700;color:#e2e8f0">-</span></div>
    <div><span style="color:#94a3b8">Name</span><br><span id="acc_name" style="font-weight:700;color:#e2e8f0">-</span></div>
    <div><span style="color:#94a3b8">Balance</span><br><span id="acc_balance" style="font-weight:700;color:#6ee7b7">-</span></div>
    <div><span style="color:#94a3b8">Equity</span><br><span id="acc_equity" style="font-weight:700;color:#6ee7b7">-</span></div>
    <div><span style="color:#94a3b8">Leverage</span><br><span id="acc_lev" style="font-weight:700;color:#e2e8f0">-</span></div>
  </div>
</div>

<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
  <button onclick="reloadAccountStatus()" style="padding:8px 14px;background:#334155;color:#e2e8f0;border:none;border-radius:4px;cursor:pointer">&#128260; Refresh</button>
  <button onclick="setAutoTradeAfterSwitch(true)" id="btnAutoReenable" style="padding:8px 14px;background:#22c55e;color:#fff;border:none;border-radius:4px;cursor:pointer">Aktifkan Auto-Trade</button>
  <button onclick="setAutoTradeAfterSwitch(false)" style="padding:8px 14px;background:#ef4444;color:#fff;border:none;border-radius:4px;cursor:pointer">Matikan Auto-Trade</button>
</div>

<h2 style="margin-top:18px">Symbol Trading</h2>
<div style="background:#1e293b;border-radius:6px;padding:16px;max-width:520px">
  <div><label style="font-size:11px;color:#94a3b8">Pilih simbol untuk akun ini</label><br>
    <select id="acc_symbol_sel" onchange="changeActiveSymbol()" style="width:100%;padding:8px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px;margin-top:4px"></select>
  </div>
  <div id="acc_symbol_result" style="margin-top:10px;font-size:12px;color:#94a3b8"></div>
</div>

<h2 style="margin-top:18px">Login ke Akun Lain</h2>
<div style="background:#1e293b;border-radius:6px;padding:16px;max-width:520px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div><label style="font-size:11px;color:#94a3b8">Login ID</label><br><input id="acc_login_in" placeholder="mis. 160040915" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Server</label><br><input id="acc_server_in" placeholder="mis. Exness-MT5Real20" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div style="grid-column:span 2"><label style="font-size:11px;color:#94a3b8">Password MT5</label><br><input id="acc_pass_in" type="password" placeholder="password" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
  </div>
  <div style="margin-top:12px;display:flex;gap:8px">
    <button onclick="connectAccount()" style="flex:1;padding:9px;background:#3b82f6;color:#fff;border:none;border-radius:4px;font-weight:600;cursor:pointer">CONNECT</button>
    <button onclick="saveAccountOnly()" style="padding:9px;background:#334155;color:#94a3b8;border:none;border-radius:4px;cursor:pointer">Simpan saja</button>
  </div>
  <div id="acc_login_result" style="margin-top:12px;font-size:12px;color:#6ee7b7;word-break:break-all"></div>
</div>

<h2 style="margin-top:18px">Akun Tersimpan</h2>
<div class="table-wrap" style="max-width:640px"><table><thead><tr>
  <th>Nama</th><th>Login</th><th>Server</th><th>Action</th>
</tr></thead><tbody id="savedAccountsBody"></tbody></table></div>

<div style="background:#1e293b;border-radius:6px;padding:16px;max-width:520px;margin-top:12px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div><label style="font-size:11px;color:#94a3b8">Nama Akun</label><br><input id="sv_name" placeholder="mis. Real20" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Login ID</label><br><input id="sv_login" placeholder="mis. 160040915" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Server</label><br><input id="sv_server" placeholder="mis. Exness-MT5Real20" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Password</label><br><input id="sv_pass" type="password" placeholder="password" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
  </div>
  <div style="margin-top:12px">
    <button onclick="addSavedAccount()" style="padding:9px 16px;background:#22c55e;color:#fff;border:none;border-radius:4px;cursor:pointer">+ Tambah Akun</button>
  </div>
  <div id="sv_result" style="margin-top:10px;font-size:12px;color:#6ee7b7"></div>
</div>

</div>

<script>
let charts = {};
let analyticsLoaded = false;
let learningLoaded = false;

function toggleSidebar() {
  const m = document.getElementById('mobileMenu');
  if (m) { m.classList.toggle('open'); }
}
function closeSidebar() {
  const m = document.getElementById('mobileMenu');
  if (m) { m.classList.remove('open'); }
}
function switchTab(name, el) {
  document.querySelectorAll('.sidebar-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('[id^="tab-"]').forEach(t => t.style.display = 'none');
  document.getElementById('tab-' + name).style.display = 'block';
  (el || event.target).classList.add('active');
  if (window.innerWidth <= 600) { closeSidebar(); }
  if (name === 'analytics' && !analyticsLoaded) {
    analyticsLoaded = true;
    fetchAnalytics();
  }
  if (name === 'manual') {
    fetchLiveMarket();
    fetchAutoTradeMonitor();
    fetchManualChart();
  }
  if (name === 'grid') {
    fetchGridStatus();
    fetchManagePositions();
    fetchAutoTradeMonitor();
    loadAutoTradeEnabled();
    fetchPriceChart('priceChartGrid');
  }
  if (name === 'learning' && !learningLoaded) {
    learningLoaded = true;
    fetchLearningRecords();
  }
  if (name === 'scalping') {
    fetchScalping();
  }
  if (name === 'intraday') {
    fetchIntraday();
  }
  if (name === 'settings') {
    loadAccountStatus();
    loadSavedAccounts();
  }
}

function destroyChart(name) {
  if (charts[name]) { charts[name].destroy(); delete charts[name]; }
}

let priceChartInst = null;

async function fetchPriceChart(canvasId) {
  try {
    const pc = await fetchJson('/api/chart/candles', {candles:[], symbol:'XAUUSDc'});
    if (!pc.candles || !pc.candles.length) return;
    const chartSymbol = pc.symbol || 'XAUUSDc';
    const labels = pc.candles.map(c => c.time);
    const prices = pc.candles.map(c => c.close);
    if (priceChartInst) priceChartInst.destroy();
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx) return;
    priceChartInst = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: chartSymbol,
          data: prices,
          borderColor: prices[0] <= prices[prices.length-1] ? '#6ee7b7' : '#fca5a5',
          borderWidth: 2,
          fill: { target: 'origin', above: prices[0] <= prices[prices.length-1] ? 'rgba(110,231,183,0.08)' : 'rgba(252,165,165,0.08)' },
          pointRadius: 0, tension: 0.2,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color:'#64748b', font:{size:9}, maxTicksLimit:12 }, grid: { color:'#1e293b' } },
          y: { ticks: { color:'#94a3b8', font:{size:10} }, grid: { color:'#334155' } }
        }
      }
    });
  } catch(e) { console.error('Price chart error:', e); }
}

let manualChartInst = null;

async function fetchManualChart(entryLine, slLine, tp1Line, tp2Line) {
  try {
    if (typeof ChartAnnotation !== 'undefined') {
      Chart.register(ChartAnnotation);
    }
    const pc = await fetchJson('/api/chart/candles', {candles:[], symbol:'XAUUSDc'});
    if (!pc.candles || !pc.candles.length) return;
    const chartSymbol = pc.symbol || 'XAUUSDc';
    const labels = pc.candles.map(c => c.time);
    const prices = pc.candles.map(c => c.close);
    if (manualChartInst) manualChartInst.destroy();
    const ctx = document.getElementById('manualChart')?.getContext('2d');
    if (!ctx) return;

    const annotations = {};
    if (entryLine) {
      annotations.entry = {
        type: 'line', yMin: entryLine, yMax: entryLine,
        borderColor: '#3b82f6', borderWidth: 2, borderDash: [6,3],
        label: { display: true, content: 'Entry ' + entryLine, position: 'start', backgroundColor: 'rgba(59,130,246,0.8)', font: {size:10}, color:'#fff', padding:4 }
      };
    }
    if (slLine) {
      annotations.sl = {
        type: 'line', yMin: slLine, yMax: slLine,
        borderColor: '#ef4444', borderWidth: 2, borderDash: [6,3],
        label: { display: true, content: 'SL ' + slLine, position: 'start', backgroundColor: 'rgba(239,68,68,0.8)', font: {size:10}, color:'#fff', padding:4 }
      };
    }
    if (tp1Line) {
      annotations.tp1 = {
        type: 'line', yMin: tp1Line, yMax: tp1Line,
        borderColor: '#22c55e', borderWidth: 2, borderDash: [6,3],
        label: { display: true, content: 'TP1 ' + tp1Line, position: 'end', backgroundColor: 'rgba(34,197,94,0.8)', font: {size:10}, color:'#fff', padding:4 }
      };
    }
    if (tp2Line) {
      annotations.tp2 = {
        type: 'line', yMin: tp2Line, yMax: tp2Line,
        borderColor: '#16a34a', borderWidth: 2, borderDash: [3,3],
        label: { display: true, content: 'TP2 ' + tp2Line, position: 'end', backgroundColor: 'rgba(22,163,74,0.8)', font: {size:10}, color:'#fff', padding:4 }
      };
    }

    manualChartInst = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: chartSymbol,
          data: prices,
          borderColor: prices[0] <= prices[prices.length-1] ? '#6ee7b7' : '#fca5a5',
          borderWidth: 2,
          fill: { target: 'origin', above: prices[0] <= prices[prices.length-1] ? 'rgba(110,231,183,0.08)' : 'rgba(252,165,165,0.08)' },
          pointRadius: 0, tension: 0.2,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          annotation: { annotations }
        },
        scales: {
          x: { ticks: { color:'#64748b', font:{size:9}, maxTicksLimit:12 }, grid: { color:'#1e293b' } },
          y: { ticks: { color:'#94a3b8', font:{size:10} }, grid: { color:'#334155' } }
        }
      }
    });
  } catch(e) { console.error('Manual chart error:', e); }
}

function makeChart(id, type, labels, datasets, opts) {
  destroyChart(id);
  const ctx = document.getElementById(id).getContext('2d');
  charts[id] = new Chart(ctx, {
    type,
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color:'#94a3b8', boxWidth:10, padding:6, font:{size:10} } }
      },
      scales: {
        x: { ticks: { color:'#64748b', maxTicksLimit:8, font:{size:9} }, grid: { color:'#1e293b' } },
        y: { ticks: { color:'#64748b', font:{size:9} }, grid: { color:'#1e293b' } }
      },
      ...opts
    }
  });
}

async function fetchJson(url, fallback, timeoutMs=8000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    clearTimeout(timer);
    return await res.json();
  } catch(e) {
    clearTimeout(timer);
    return fallback;
  }
}

async function fetchPublicUrl() {
  try {
    const d = await fetchJson('/api/dashboard-url', {url:'http://127.0.0.1:8000'});
    document.getElementById('publicUrl').textContent = d.url.replace(/^https?:\/\//,'');
  } catch(e) {}
}
function copyUrl() {
  const txt = document.getElementById('publicUrl').textContent;
  if (txt && txt !== 'tunnel...') {
    navigator.clipboard.writeText('https://'+txt);
    showNotif('URL copied!','#3b82f6');
  }
}
async function fetchData() {
  try {
    const overview = await fetchJson('/api/overview', {balance:0,equity:0,floating_pl:0,drawdown:0,trades_today:0,open_count:0,open_positions:[],trades:[],equity_snapshots:[],learning:{total:0,win:0,loss:0,win_rate:0},scalping:null,server_time:'loading...'});
    const trades = overview.trades || [];
    const equity = overview.equity_snapshots || [];
    const learning = overview.learning || {};
    const scalping = overview.scalping || {};

    document.getElementById('serverTime').textContent = overview.server_time || '';

    document.getElementById('stats').innerHTML = `
      <div class="card"><div class="lbl">Balance</div><div class="val green">$${(overview.balance||0).toFixed(2)}</div></div>
      <div class="card"><div class="lbl">Equity</div><div class="val blue">$${(overview.equity||0).toFixed(2)}</div></div>
      <div class="card"><div class="lbl">Floating</div><div class="val ${(overview.floating_pl||0) >= 0 ? 'green' : 'red'}">${(overview.floating_pl||0) >= 0 ? '+' : ''}$${(overview.floating_pl||0).toFixed(2)}</div></div>
      <div class="card"><div class="lbl">Drawdown</div><div class="val yellow">${(overview.drawdown||0).toFixed(1)}%</div></div>
      <div class="card"><div class="lbl">Trades Today</div><div class="val">${overview.trades_today||0}</div></div>
      <div class="card"><div class="lbl">Open Positions</div><div class="val">${overview.open_count||0}</div></div>
    `;

    document.getElementById('positionInfo').innerHTML = (overview.open_count||0) > 0
      ? '<span class="status-dot status-running"></span> ' + overview.open_count + ' posisi aktif'
      : '<span class="status-dot" style="background:#64748b"></span> Tidak ada posisi';

    const atStatus = overview.auto_trader || 'READY';
    const atReason = overview.auto_trader_reason || '';
    document.getElementById('autoTraderInfo').innerHTML =
      '<span class="status-dot ' + (atStatus === 'BLOCKED' ? 'status-stopped' : 'status-running') + '"></span> ' +
      atStatus +
      (atStatus === 'BLOCKED' && atReason ? ' — ' + atReason : '');

    document.getElementById('positions').innerHTML = (overview.open_positions||[]).map(p => '<tr><td>'+p.ticket+'</td><td><span class="badge '+(p.type||'').toLowerCase()+'">'+(p.type||'')+'</span></td><td>'+p.volume+'</td><td>'+p.price_open+'</td><td>'+p.price_current+'</td><td class="'+(p.profit>=0?'green':'red')+'">'+(p.profit>=0?'+':'')+'$'+p.profit.toFixed(2)+'</td><td>'+(p.sl||'-')+'</td><td>'+(p.tp||'-')+'</td></tr>').join('') || '<tr><td colspan="8" style="text-align:center;color:#64748b">Tidak ada posisi</td></tr>';

    const lastTrade = trades[0] || {};
    document.getElementById('signalBox').innerHTML = `
      <div class="card"><div class="lbl">Signal</div><div class="val" style="text-transform:uppercase">${lastTrade.signal||'-'}</div></div>
      <div class="card"><div class="lbl">Confidence</div><div class="val">${lastTrade.confidence||0}%</div></div>
      <div class="card"><div class="lbl">Last Action</div><div class="val">${lastTrade.action||'-'}</div></div>
      <div class="card"><div class="lbl">Status</div><div class="val">${lastTrade.status||'-'}</div></div>
    `;

    const ss = scalping.scalp_score || {};
    const ssColor = (ss.score||0) >= 75 ? 'green' : (ss.score||0) >= 65 ? 'yellow' : 'red';
    document.getElementById('scalpingScoreBox').innerHTML = `
      <div class="card"><div class="lbl">Scalp Score</div><div class="val ${ssColor}">${ss.score||0}/100</div></div>
      <div class="card"><div class="lbl">Grade</div><div class="val blue">${ss.grade||'-'}</div></div>
      <div class="card"><div class="lbl">Direction</div><div class="val" style="text-transform:uppercase">${ss.direction||'WAIT'}</div></div>
      <div class="card"><div class="lbl">Action</div><div class="val ${ss.action==='TRADE'?'green':'yellow'}">${ss.action||'WAIT'}</div></div>
    `;

    const engines = [
      ['Momentum', scalping.momentum, 'direction'],
      ['Speed', scalping.speed, 'level'],
      ['Liquidity', scalping.liquidity, 'signal'],
      ['Fake Breakout', scalping.fake_breakout, 'signal'],
      ['Session', scalping.session, 'session'],
      ['Impulse', scalping.impulse, 'signal']
    ];
    document.getElementById('scalpingEngineBox').innerHTML = engines.map(([name, data, key]) => {
      data = data || {};
      const score = data.score || 0;
      const color = score >= 75 ? 'green' : score >= 60 ? 'yellow' : 'red';
      return `<div class="card"><div class="lbl">${name}</div><div class="val ${color}">${score}</div><div class="lbl">${data[key]||'-'}</div></div>`;
    }).join('');

    document.getElementById('trades').innerHTML = trades.map(t => '<tr><td style="font-size:10px">'+(t.time?.split(' ')[1]||t.time)+'</td><td><span class="badge '+(t.signal||'').toLowerCase()+'">'+t.signal+'</span></td><td>'+t.confidence+'%</td><td>'+t.action+'</td><td>'+t.status+'</td><td>'+(t.entry_price||'-')+'</td><td class="'+(t.profit>0?'green':t.profit<0?'red':'')+'">'+((t.profit!=null)?'$'+t.profit.toFixed(2):'-')+'</td><td>'+(t.lot_size||'-')+'</td></tr>').join('');

    document.getElementById('learningBox').innerHTML = `
      <div class="card"><div class="lbl">Total Samples</div><div class="val">${learning.total??0}</div></div>
      <div class="card"><div class="lbl">Win</div><div class="val green">${learning.win??0}</div></div>
      <div class="card"><div class="lbl">Loss</div><div class="val red">${learning.loss??0}</div></div>
      <div class="card"><div class="lbl">Win Rate</div><div class="val yellow">${learning.win_rate??0}%</div></div>
    `;

    if (equity.length > 0) {
      makeChart('equityChart', 'line', equity.map(e=>(e.time?.split(' ')[1]||'').slice(0,5)), [
        { label:'Balance', data:equity.map(e=>e.balance), borderColor:'#6ee7b7', borderWidth:2, fill:false, pointRadius:0, tension:0.3 },
        { label:'Equity', data:equity.map(e=>e.equity), borderColor:'#3b82f6', borderWidth:2, fill:false, pointRadius:0, tension:0.3 }
      ], { scales:{ y:{ ticks:{ font:{size:9} } } } });
    } else {
      destroyChart('equityChart');
    }

  } catch(e) { console.error('Overview error:', e); }
}

async function fetchAnalytics() {
  try {
    const [wr, monthly, dd, td, sd, ch, hp, sp, acc, lp, mv, hm] = await Promise.all([
      fetchJson('/api/analytics/win_rate', {}),
      fetchJson('/api/analytics/monthly_profit?months=6', []),
      fetchJson('/api/analytics/drawdown_curve?limit=100', []),
      fetchJson('/api/analytics/trade_distribution', {buy:0,sell:0,hold:0}),
      fetchJson('/api/analytics/signal_distribution', {buy:0,sell:0}),
      fetchJson('/api/analytics/confidence_histogram', {}),
      fetchJson('/api/analytics/hour_performance', []),
      fetchJson('/api/analytics/session_performance', {}),
      fetchJson('/api/analytics/ai_accuracy', {accuracy:0,total:0}),
      fetchJson('/api/analytics/learning_progress', []),
      fetchJson('/api/model_version', {current_version:'-',training_date:'-'}),
      fetchJson('/api/analytics/heatmap', [])
    ]);

    document.getElementById('winRateBox').innerHTML = `
      <div class="card"><div class="lbl">Total Trades</div><div class="val">${wr.total??0}</div></div>
      <div class="card"><div class="lbl">Win</div><div class="val green">${wr.win??0}</div></div>
      <div class="card"><div class="lbl">Loss</div><div class="val red">${wr.loss??0}</div></div>
      <div class="card"><div class="lbl">Win Rate</div><div class="val yellow">${wr.win_rate??0}%</div></div>
    `;

    if (monthly.length > 0) {
      makeChart('monthlyProfitChart', 'bar', monthly.map(m=>m.month), [
        { label:'Profit', data:monthly.map(m=>m.profit), backgroundColor:monthly.map(m=>m.profit>=0?'rgba(110,231,183,0.7)':'rgba(252,165,165,0.7)'), borderColor:monthly.map(m=>m.profit>=0?'#6ee7b7':'#fca5a5'), borderWidth:1 }
      ], { plugins:{legend:{display:false}} });
    }

    if (dd.length > 0) {
      makeChart('drawdownCurveChart', 'line', dd.map(d=>(d.time||'').split(' ')[1]||''), [
        { label:'Drawdown %', data:dd.map(d=>d.drawdown), borderColor:'#fbbf24', borderWidth:2, fill:true, backgroundColor:'rgba(251,191,36,0.1)', pointRadius:0, tension:0.3 }
      ], { plugins:{legend:{display:false}} });
    }

    makeChart('tradeDistChart', 'doughnut', ['Buy','Sell','Hold'], [
      { data:[td.buy, td.sell, td.hold], backgroundColor:['rgba(110,231,183,0.7)','rgba(252,165,165,0.7)','rgba(253,186,116,0.7)'], borderColor:['#6ee7b7','#fca5a5','#fdba74'], borderWidth:1 }
    ], { plugins:{legend:{position:'bottom'}} });

    makeChart('signalDistChart', 'doughnut', ['Buy Signal','Sell Signal'], [
      { data:[sd.buy, sd.sell], backgroundColor:['rgba(59,130,246,0.7)','rgba(167,139,250,0.7)'], borderColor:['#3b82f6','#a78bfa'], borderWidth:1 }
    ], { plugins:{legend:{position:'bottom'}} });

    const histLabels = Object.keys(ch);
    makeChart('confidenceHistChart', 'bar', histLabels, [
      { label:'Count', data:histLabels.map(k=>ch[k]), backgroundColor:'rgba(59,130,246,0.7)', borderColor:'#3b82f6', borderWidth:1 }
    ], { plugins:{legend:{display:false}} });

    const hours = hp.map(h=>h.hour);
    const hourColors = hp.map(h=>h.profit>=0?'rgba(110,231,183,0.7)':'rgba(252,165,165,0.7)');
    makeChart('hourPerfChart', 'bar', hours, [
      { label:'Profit', data:hp.map(h=>h.profit), backgroundColor:hourColors, borderWidth:0 }
    ], { plugins:{legend:{display:false}, tooltip:{callbacks:{label:ctx=>'$'+ctx.parsed.y.toFixed(2)+' ('+hp[ctx.dataIndex].count+' trades)'}}} });

    document.getElementById('sessionBox').innerHTML = ['Asia','London','New York'].map(s => {
      const d = sp[s]||{count:0,profit:0};
      return '<div class="card"><div class="lbl">'+s+'</div><div class="val">'+d.count+' trades</div><div class="lbl" style="margin-top:4px">'+ (d.profit>=0?'+':'')+'$'+d.profit.toFixed(2)+'</div></div>';
    }).join('');

    const cm = acc.confusion_matrix || {};
    document.getElementById('accuracyBox').innerHTML = `
      <div class="card"><div class="lbl">AI Accuracy</div><div class="val ${(acc.accuracy||0)>=50?'green':'red'}">${acc.accuracy??0}%</div></div>
      <div class="card"><div class="lbl">TP / FP</div><div class="val green">${cm.tp||0}</div><div class="lbl red">${cm.fp||0}</div></div>
      <div class="card"><div class="lbl">FN / TN</div><div class="val red">${cm.fn||0}</div><div class="lbl green">${cm.tn||0}</div></div>
      <div class="card"><div class="lbl">Total Predictions</div><div class="val">${acc.total}</div></div>
      <div class="card"><div class="lbl">Model</div><div class="val blue">${mv.current_version||'-'}</div><div class="lbl">${mv.training_date||'-'}</div></div>
      <div class="card"><div class="lbl">Dataset</div><div class="val">${mv.dataset_size}</div><div class="lbl">rows</div></div>
    `;

    if (hm.length > 0) {
      const days = ['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu'];
      const hours = Array.from({length:24},(_,i)=>String(i).padStart(2,'0'));
      let html = '<div style="display:flex;gap:2px;margin-bottom:4px"><div style="width:40px"></div>';
      hours.forEach(h => { html += '<div style="flex:1;text-align:center;font-size:8px;color:#64748b">'+h+'</div>'; });
      html += '</div>';
      days.forEach(d => {
        html += '<div style="display:flex;gap:2px;align-items:center;margin-bottom:1px"><div style="width:40px;font-size:8px;color:#64748b">'+d.slice(0,3)+'</div>';
        hours.forEach(h => {
          const cell = hm.find(x => x.day===d && x.hour===h)||{profit:0};
          const p = cell.profit;
          let color = '#1e293b';
          if (p > 0) { const i = Math.min(1, p/50); color = `rgba(110,231,183,${0.2+i*0.6})`; }
          else if (p < 0) { const i = Math.min(1, Math.abs(p)/50); color = `rgba(252,165,165,${0.2+i*0.6})`; }
          html += '<div style="flex:1;height:16px;background:'+color+';border-radius:1px;position:relative" title="'+d+' '+h+': $'+p.toFixed(2)+'"></div>';
        });
        html += '</div>';
      });
      document.getElementById('heatmapContainer').innerHTML = html;
    }

  } catch(e) { console.error('Analytics error:', e); }
}

// =====================================
// Live Market
// =====================================

async function fetchLiveMarket() {
  try {
    const d = await fetchJson('/api/live-market', {symbols:[]});
    const syms = d.symbols || [];
    const html = syms.map(s => {
      const bid = s.bid || 0;
      const ask = s.ask || 0;
      return '<tr style="cursor:pointer" data-sym="'+s.symbol+'" data-bid="'+bid+'" data-ask="'+ask+'">' +
        '<td>'+s.symbol+'</td>' +
        '<td style="font-weight:600;color:#6ee7b7">'+bid.toFixed(2)+'</td>' +
        '<td style="font-weight:600;color:#f87171">'+ask.toFixed(2)+'</td>' +
        '<td>'+s.spread+'</td>' +
        '<td><input type="number" class="lm-sl" value="6" min="1" max="100" style="width:60px;padding:4px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px;font-size:11px"></td>' +
        '<td><input type="number" class="lm-tp" value="4" min="1" max="200" style="width:60px;padding:4px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px;font-size:11px"></td>' +
        '<td style="display:flex;gap:4px">' +
          '<button class="lm-btn-buy" style="padding:4px 10px;background:#22c55e;color:#fff;border:none;border-radius:4px;font-size:11px;cursor:pointer">BUY</button>' +
          '<button class="lm-btn-sell" style="padding:4px 10px;background:#ef4444;color:#fff;border:none;border-radius:4px;font-size:11px;cursor:pointer">SELL</button>' +
        '</td></tr>';
    }).join('');
    document.getElementById('liveMarketPrices').innerHTML = html;

    document.querySelectorAll('.lm-btn-buy').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const tr = this.closest('tr');
        fillOrder(tr, 'BUY');
      };
    });
    document.querySelectorAll('.lm-btn-sell').forEach(btn => {
      btn.onclick = function(e) {
        e.stopPropagation();
        const tr = this.closest('tr');
        fillOrder(tr, 'SELL');
      };
    });
  } catch(e) { console.error('Live market error:', e); }
}

function fillOrder(tr, side) {
  const sym = tr.dataset.sym || 'XAUUSDc';
  const bid = parseFloat(tr.dataset.bid) || 0;
  const ask = parseFloat(tr.dataset.ask) || 0;
  const entry = side === 'BUY' ? ask : bid;
  const slPt = parseFloat(tr.querySelector('.lm-sl').value) || 6;
  const tpPt = parseFloat(tr.querySelector('.lm-tp').value) || 4;
  const sl = side === 'BUY' ? (entry - slPt) : (entry + slPt);
  const tp1 = side === 'BUY' ? (entry + tpPt) : (entry - tpPt);

  document.getElementById('mo_symbol').value = sym;
  document.getElementById('mo_signal').value = side;
  document.getElementById('mo_volume').value = '0.01';
  document.getElementById('mo_entry').value = entry.toFixed(2);
  document.getElementById('mo_sl').value = sl.toFixed(2);
  document.getElementById('mo_tp1').value = tp1.toFixed(2);
  document.getElementById('mo_tp2').value = '';
  document.getElementById('mo_result').textContent = 'SL ' + slPt + 'pt / TP ' + tpPt + 'pt (dari Live Market)';
  window.scrollTo(0, document.getElementById('tab-manual').offsetTop - 10);
}

// =====================================
// =====================================
// Auto-Trade Monitor
// =====================================

function showNotif(msg, color) {
  const el = document.createElement('div');
  el.textContent = msg;
  el.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);padding:10px 24px;border-radius:6px;color:#fff;font-weight:600;font-size:13px;z-index:9999;background:'+color+';box-shadow:0 4px 12px rgba(0,0,0,0.4);transition:opacity 0.3s';
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 2000);
}

async function toggleAutoTrade() {
  const btn = document.getElementById('atm_toggle_btn');
  const wasEnabled = btn.dataset.enabled === 'true';
  const url = wasEnabled ? '/api/auto-trade/do-disable' : '/api/auto-trade/do-enable';
  try {
    const r = await fetchJson(url, {enabled:!wasEnabled});
    if (r.status === 'ok') {
      btn.dataset.enabled = r.enabled ? 'true' : 'false';
      btn.textContent = r.enabled ? 'STOP AUTO-TRADE' : 'START AUTO-TRADE';
      btn.style.background = r.enabled ? '#dc2626' : '#22c55e';
      btn.style.color = '#fff';
      if (r.warning) {
        showNotif('PERINGATAN: ' + r.warning, '#f59e0b');
      } else {
        showNotif(r.enabled ? 'AUTO-TRADE DIMULAI' : 'AUTO-TRADE DIHENTIKAN', r.enabled ? '#22c55e' : '#dc2626');
      }
    }
  } catch(e) { console.error('Toggle error:', e); }
}

async function loadAutoTradeEnabled() {
  try {
    const r = await fetchJson('/api/auto-trade/enabled', {enabled:true});
    const btn = document.getElementById('atm_toggle_btn');
    btn.dataset.enabled = r.enabled ? 'true' : 'false';
    btn.textContent = r.enabled ? 'STOP AUTO-TRADE' : 'START AUTO-TRADE';
    btn.style.background = r.enabled ? '#dc2626' : '#22c55e';
    btn.style.color = '#fff';
  } catch(e) { console.error('Load enabled error:', e); }
}

async function setLotSize(lot) {
  try {
    await fetch('/api/auto-trade/set-lot', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({lot_size:lot}) });
    fetchAutoTradeMonitor();
  } catch(e) { console.error('Set lot error:', e); }
}

async function fetchAutoTradeMonitor() {
  try {
    const d = await fetchJson('/api/auto-trade/monitor', {account:{},scalp:{},positions:[],pending_orders:[]});
    document.getElementById('atm_balance').textContent = d.account?.balance != null ? d.account.balance.toFixed(2) : '-';
    document.getElementById('atm_equity').textContent = d.account?.equity != null ? d.account.equity.toFixed(2) : '-';
    const ss = d.scalp || {};
    const sc = ss.score || 0;
    document.getElementById('atm_score').textContent = sc;
    document.getElementById('atm_score').style.color = sc >= 65 ? '#6ee7b7' : sc >= 50 ? '#facc15' : '#f87171';
    document.getElementById('atm_grade').textContent = ss.grade || '-';
    document.getElementById('atm_dir').textContent = ss.direction || '-';
    const act = ss.action || 'WAIT';
    const actEl = document.getElementById('atm_action');
    actEl.textContent = act;
    actEl.style.color = act === 'TRADE' ? '#6ee7b7' : '#f87171';

    const pos = d.positions || [];
    document.getElementById('atm_pos_count').textContent = pos.length;
    document.getElementById('atm_positions').innerHTML = pos.length ? pos.map(p =>
      '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #0f172a">' +
        '<span class="'+(p.type==='BUY'?'green':'red')+'">'+p.type+'</span>' +
        '<span>'+p.volume+'</span>' +
        '<span>'+p.profit+'</span>' +
        '<span style="font-size:10px;color:#94a3b8">'+(p.open_time||'')+'</span>' +
        '<span style="font-size:10px;color:#94a3b8">'+(p.be?'BE ':'')+(p.ts?'TS ':'')+'</span>' +
      '</div>'
    ).join('') : '<div style="color:#64748b;padding:4px 0">Tidak ada posisi</div>';

    const pen = d.pending_orders || [];
    document.getElementById('atm_pend_count').textContent = pen.length;
    document.getElementById('atm_pending').textContent = pen.length ? pen.map(o => o.type+' @ '+o.price).join(', ') : 'Tidak ada pending';
    document.getElementById('atm_updated').textContent = d.last_update || '-';

    // Lot size selector
    const curLot = d.lot_size || 0.01;
    const lotOpts = d.lot_options || [0.01, 0.02, 0.03, 0.05, 0.10];
    const lotContainer = document.getElementById('atm_lot_selector');
    if (lotContainer) {
      lotContainer.innerHTML = lotOpts.map(l =>
        '<button onclick="setLotSize('+l+')" style="' +
        'padding:4px 10px;border:1px solid '+(l===curLot?'#3b82f6':'#334155')+';' +
        'border-radius:4px;background:'+(l===curLot?'rgba(59,130,246,0.2)':'transparent')+';' +
        'color:'+(l===curLot?'#60a5fa':'#94a3b8')+';cursor:pointer;font-size:11px;font-weight:'+(l===curLot?'700':'400')+'">' +
        (l < 1 ? l.toFixed(2) : l.toFixed(1)) +
        '</button>'
      ).join('');
    }

    // Manual tab monitor
    document.getElementById('atm_balance2').textContent = d.account?.balance != null ? d.account.balance.toFixed(2) : '-';
    document.getElementById('atm_equity2').textContent = d.account?.equity != null ? d.account.equity.toFixed(2) : '-';
    document.getElementById('atm_score2').textContent = sc;
    document.getElementById('atm_score2').style.color = sc >= 65 ? '#6ee7b7' : sc >= 50 ? '#facc15' : '#f87171';
    document.getElementById('atm_grade2').textContent = ss.grade || '-';
    document.getElementById('atm_dir2').textContent = ss.direction || '-';
    const actEl2 = document.getElementById('atm_action2');
    actEl2.textContent = act;
    actEl2.style.color = act === 'TRADE' ? '#6ee7b7' : '#f87171';
    document.getElementById('atm_pos_count2').textContent = pos.length;
    document.getElementById('atm_positions2').innerHTML = pos.length ? pos.map(p =>
      '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #0f172a">' +
        '<span class="'+(p.type==='BUY'?'green':'red')+'">'+p.type+'</span>' +
        '<span>'+p.volume+'</span>' +
        '<span>'+p.profit+'</span>' +
        '<span style="font-size:10px;color:#94a3b8">'+(p.open_time||'')+'</span>' +
        '<span style="font-size:10px;color:#94a3b8">'+(p.be?'BE ':'')+(p.ts?'TS ':'')+'</span>' +
      '</div>'
    ).join('') : '<div style="color:#64748b;padding:4px 0">Tidak ada posisi</div>';
    document.getElementById('atm_pend_count2').textContent = pen.length;
    document.getElementById('atm_pending2').textContent = pen.length ? pen.map(o => o.type+' @ '+o.price).join(', ') : 'Tidak ada pending';
    document.getElementById('atm_updated2').textContent = d.last_update || '-';
  } catch(e) { console.error('AT Monitor error:', e); }
}

// =====================================
// Scalping
// =====================================

async function fetchScalping() {
  try {
    const d = await fetchJson('/api/scalping', {performance:{},history:[],scalp_score:{}});
    const p = d.performance || {};

    const def = (v,fallback) => v!=null && v!==undefined ? v : fallback;
    document.getElementById('scalpingPerfBox').innerHTML = [
      {l:'Trades Today', v:def(p.trades,0)},
      {l:'Win Rate', v:def(p.wr,0)+'%'},
      {l:'Profit P&L', v:'<span class="'+(def(p.profit,0)>=0?'green':'red')+'">'+(def(p.profit,0)>=0?'+':'')+def(p.profit,0).toFixed(2)+'</span>'},
      {l:'Wins', v:'<span class=green>'+def(p.wins,0)+'</span>'},
      {l:'Losses', v:'<span class=red>'+def(p.losses,0)+'</span>'},
      {l:'BE', v:def(p.be,0)},
      {l:'Avg Win', v:'<span class=green>+'+def(p.avg_win,'0.00')+'</span>'},
      {l:'Avg Loss', v:'<span class=red>'+def(p.avg_loss,'0.00')+'</span>'},
      {l:'Best', v:'<span class=green>+'+def(p.best,'0.00')+'</span>'},
      {l:'Worst', v:'<span class=red>'+def(p.worst,'0.00')+'</span>'},
    ].map(x => '<div class="card"><div class="lbl">'+x.l+'</div><div class="val">'+x.v+'</div></div>').join('');

    const ss = d.scalp_score || {};
    const details = ss.details || {};
    const detailKeys = Object.keys(details);
    if (detailKeys.length) {
      document.getElementById('scalpingScoreDetail').innerHTML = detailKeys.map(k =>
        '<div class="card"><div class="lbl">'+k.replace(/_/g,' ')+'</div><div class="val">'+details[k]+'</div></div>'
      ).join('');
    }

    const fmtPnl = (p) => {
      if (p === null || p === undefined) return '<span style="color:#64748b">-</span>';
      return '<span class="'+(p>=0?'green':'red')+'">'+(p>=0?'+':'')+p.toFixed(2)+'</span>';
    };
    const hist = d.history || [];
    document.getElementById('scalpingHistory').innerHTML = hist.length
      ? hist.map(t => '<tr><td>'+t.time+'</td><td>'+t.ticket+'</td><td>'+t.symbol+'</td><td>'+fmtPnl(t.profit)+'</td><td style="color:#64748b;font-size:11px">'+(t.comment||'-')+'</td></tr>').join('')
      : '<tr><td colspan="5" style="text-align:center;color:#64748b">Tidak ada history</td></tr>';
  } catch(e) { console.error('Scalping error:', e); }
}

// Intraday
// =====================================

let hourlyChart = null;

async function fetchIntraday() {
  try {
    const d = await fetchJson('/api/intraday', {today:{},hourly:{},recent:[],account:{}});
    const t = d.today || {};
    document.getElementById('intradaySummary').innerHTML = [
      {l:'Balance', v:d.account?.balance?.toFixed(2)||'-'},
      {l:'Equity', v:d.account?.equity?.toFixed(2)||'-'},
      {l:'Trades Today', v:t.trades||0},
      {l:'Win Rate', v:(t.wr||0)+'%'},
      {l:'Wins', v:'<span class=green>'+t.wins+'</span>'},
      {l:'Losses', v:'<span class=red>'+t.losses+'</span>'},
      {l:'BE', v:t.be||0},
      {l:'P&L', v:'<span class="'+(t.profit>=0?'green':'red')+'">'+(t.profit>=0?'+':'')+t.profit+'</span>'},
    ].map(x => '<div class="card"><div class="lbl">'+x.l+'</div><div class="val">'+x.v+'</div></div>').join('');

    const hourly = d.hourly || {};
    const hLabels = Object.keys(hourly).sort();
    const hData = hLabels.map(k => hourly[k]);
    if (hourlyChart) hourlyChart.destroy();
    const ctx = document.getElementById('hourlyChart')?.getContext('2d');
    if (ctx) {
      hourlyChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: hLabels,
          datasets: [{
            label: 'Profit',
            data: hData,
            backgroundColor: hData.map(v => v >= 0 ? 'rgba(59,130,246,0.7)' : 'rgba(239,68,68,0.7)'),
            borderColor: hData.map(v => v >= 0 ? '#3b82f6' : '#ef4444'),
            borderWidth: 1,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { ticks: { color:'#94a3b8',font:{size:10} } } }
        }
      });
    }

    const trades = d.recent || [];
    document.getElementById('intradayTrades').innerHTML = trades.length
      ? trades.map(t => '<tr><td>'+t.time+'</td><td>'+t.ticket+'</td><td>'+t.symbol+'</td><td class="'+(t.profit>=0?'green':'red')+'">'+(t.profit>=0?'+':'')+t.profit+'</td><td style="color:#64748b;font-size:11px">'+(t.comment||'-')+'</td></tr>').join('')
      : '<tr><td colspan="5" style="text-align:center;color:#64748b">Tidak ada trade hari ini</td></tr>';
  } catch(e) { console.error('Intraday error:', e); }
}

// =====================================
// Grid & Pending Orders
// =====================================

async function fetchGridStatus() {
  try {
    const data = await fetchJson('/api/grid/status', {pending_orders:[],open_positions:[]});
    const pending = data.pending_orders || [];
    document.getElementById('pendingOrders').innerHTML = pending.map(o =>
      '<tr><td>'+o.ticket+'</td><td>'+o.type+'</td><td>'+o.volume+'</td><td>'+o.price+'</td><td>'+(o.sl||'-')+'</td><td>'+(o.tp||'-')+'</td><td>'+(o.comment||'-')+'</td></tr>'
    ).join('') || '<tr><td colspan="7" style="text-align:center;color:#64748b">Tidak ada pending order</td></tr>';
  } catch(e) { console.error('Grid status error:', e); }
}

async function fetchManagePositions() {
  try {
    const data = await fetchJson('/api/positions/manage', {positions:[],count:0});
    const pos = data.positions || [];
    document.getElementById('managePositions').innerHTML = pos.map(p =>
      '<tr><td>'+p.ticket+'</td><td class="'+(p.type==='BUY'?'green':'red')+'">'+p.type+'</td><td>'+p.volume+'</td><td>'+p.open_price+'</td><td>'+p.current_price+'</td><td class="'+(p.profit>=0?'green':'red')+'">'+(p.profit>=0?'+':'')+p.profit+'</td><td>'+(p.sl||'-')+'</td><td>'+(p.tp||'-')+'</td><td><button onclick="closePosition('+p.ticket+')" style="padding:2px 6px;background:#dc2626;color:#fff;border:none;border-radius:3px;cursor:pointer;font-size:10px">Close</button></td></tr>'
    ).join('') || '<tr><td colspan="9" style="text-align:center;color:#64748b">Tidak ada posisi</td></tr>';
  } catch(e) { console.error('Manage positions error:', e); }
}

async function placeGrid(dryRun) {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Placing...';
  const payload = {
    symbol: document.getElementById('gr_symbol').value || 'XAUUSDc',
    layers: parseInt(document.getElementById('gr_layers').value) || 3,
    spacing: parseFloat(document.getElementById('gr_spacing').value) || 3.0,
    lot: parseFloat(document.getElementById('gr_lot').value) || 0.01,
    sl_dist: parseFloat(document.getElementById('gr_sl').value) || 6.0,
    tp_dist: parseFloat(document.getElementById('gr_tp').value) || 8.0,
    dry_run: dryRun,
  };
  try {
    const res = await fetch('/api/grid/place', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.json());
    const el = document.getElementById('gr_result');
    if (res.success) {
      el.style.color = '#6ee7b7';
      el.textContent = 'Grid placed: ' + res.count + ' orders';
    } else {
      el.style.color = '#fca5a5';
      el.textContent = 'FAILED: ' + (res.error||'Unknown');
    }
    fetchGridStatus();
  } catch(e) {
    document.getElementById('gr_result').style.color = '#fca5a5';
    document.getElementById('gr_result').textContent = 'Error: ' + e.message;
  }
  btn.disabled = false;
  btn.textContent = dryRun ? 'Dry Run' : 'PLACE GRID';
}

async function cancelGrid() {
  const payload = { symbol: document.getElementById('gr_symbol').value || 'XAUUSDc' };
  try {
    const res = await fetch('/api/grid/cancel', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.json());
    document.getElementById('gr_result').style.color = '#6ee7b7';
    document.getElementById('gr_result').textContent = 'Cancelled: ' + (res.cancelled||0) + ' orders';
    fetchGridStatus();
  } catch(e) {
    document.getElementById('gr_result').style.color = '#fca5a5';
    document.getElementById('gr_result').textContent = 'Error: ' + e.message;
  }
}

async function closePosition(ticket) {
  if (!confirm('Close position '+ticket+'?')) return;
  try {
    const res = await fetch('/api/position/close', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket:ticket})}).then(r=>r.json());
    if (res.success) {
      fetchManagePositions();
      fetchGridStatus();
    } else {
      alert('Failed: '+(res.error||'Unknown'));
    }
  } catch(e) { alert('Error: '+e.message); }
}

function sendManualOrder(dryRun) {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Sending...';
  const payload = {
    symbol: document.getElementById('mo_symbol').value,
    signal: document.getElementById('mo_signal').value,
    volume: parseFloat(document.getElementById('mo_volume').value) || 0.01,
    entry: document.getElementById('mo_entry').value || null,
    sl: document.getElementById('mo_sl').value || null,
    tp1: document.getElementById('mo_tp1').value || null,
    tp2: document.getElementById('mo_tp2').value || null,
  };
  const url = dryRun ? '/api/order/dry-run' : '/api/order/manual';
  fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) })
    .then(r=>r.json())
    .then(data => {
      const el = document.getElementById('mo_result');
      if (data.success) {
        el.style.color = '#6ee7b7';
        const r = data.result;
        if (dryRun) {
          el.innerHTML = 'DRY RUN OK - ' + r.signal + ' ' + r.volume + ' lot @ ' + r.entry_price;
        } else {
          const t1 = r.result_1?.order || '-';
          const t2 = r.result_2?.order || '-';
          el.innerHTML = 'ORDER SENT - Ticket: ' + t1 + ' / ' + t2;
        }
        fetchLiveMarket();
        const entry = r.entry_price;
        const sl = r.stop_loss;
        const tp1 = r.take_profit1;
        const tp2 = r.take_profit2;
        fetchManualChart(entry, sl, tp1, tp2);
      } else {
        el.style.color = '#fca5a5';
        el.textContent = 'FAILED: ' + (data.error || 'Unknown error');
      }
    })
    .catch(err => {
      document.getElementById('mo_result').style.color = '#fca5a5';
      document.getElementById('mo_result').textContent = 'Error: ' + err.message;
    })
    .finally(() => { btn.disabled = false; btn.textContent = dryRun ? 'Dry Run' : 'KIRIM ORDER'; });
}

async function fetchLearningRecords() {
  try {
    const [res, fi, lp] = await Promise.all([
      fetch('/api/trades?limit=50').then(r=>r.json()),
      fetch('/api/analytics/feature_importance').then(r=>r.json()),
      fetch('/api/analytics/learning_progress').then(r=>r.json())
    ]);
    document.getElementById('learningRecords').innerHTML = res.map(t => '<tr><td>'+t.id+'</td><td><span class="badge '+(t.signal||'').toLowerCase()+'">'+t.signal+'</span></td><td>'+t.confidence+'%</td><td>'+(t.entry_price||'-')+'</td><td>'+(t.stop_loss||'-')+'</td><td class="'+(t.profit>0?'green':t.profit<0?'red':'')+'">'+((t.profit!=null)?'$'+t.profit.toFixed(2):'-')+'</td><td>'+t.status+'</td><td>'+(t.time?.split(' ')[1]||t.time)+'</td></tr>').join('');
    const entries = Object.entries(fi).filter(([k])=>k!=='_bias' && k!=='samples').sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).slice(0,12);
    document.getElementById('featureWeightsBox').innerHTML = entries.map(([k,v]) => '<div class="card"><div class="lbl">'+k+'</div><div class="val '+(v>=0?'green':'red')+'">'+(v>=0?'+':'')+v.toFixed(3)+'</div></div>').join('');
    if (lp.length > 0) {
      const labels = lp.map(p => p.time?.split('T')[0] || '');
      makeChart('learningProgressChart', 'line', labels, [
        { label:'Win Rate %', data:lp.map(p=>p.win_rate), borderColor:'#a78bfa', borderWidth:2, fill:true, backgroundColor:'rgba(167,139,250,0.1)', pointRadius:0, tension:0.3 }
      ], { plugins:{legend:{display:false}} });
    }
  } catch(e) { console.error('Learning records error:', e); }
}

fetchData();
fetchPublicUrl();
loadAutoTradeEnabled();
setInterval(fetchData, 15000);
setInterval(fetchPublicUrl, 30000);
setInterval(() => { if (analyticsLoaded && document.getElementById('tab-analytics').style.display !== 'none') fetchAnalytics(); }, 30000);
setInterval(() => { if (learningLoaded && document.getElementById('tab-learning').style.display !== 'none') fetchLearningRecords(); }, 45000);

// Grid tab auto-refresh every 1 detik
setInterval(() => {
  if (document.getElementById('tab-grid') && document.getElementById('tab-grid').style.display !== 'none') {
    fetchGridStatus();
    fetchManagePositions();
    fetchAutoTradeMonitor();
  }
}, 1000);

// Price chart refresh every 15 detik (di grid tab)
setInterval(() => {
  if (document.getElementById('tab-grid') && document.getElementById('tab-grid').style.display !== 'none') {
    fetchPriceChart('priceChartGrid');
  }
}, 15000);

// Manual chart + monitor refresh every 10 detik
setInterval(() => {
  if (document.getElementById('tab-manual') && document.getElementById('tab-manual').style.display !== 'none') {
    fetchLiveMarket();
    fetchAutoTradeMonitor();
    fetchManualChart();
  }
}, 10000);

// Scalping auto-refresh every 15 detik
setInterval(() => {
  if (document.getElementById('tab-scalping') && document.getElementById('tab-scalping').style.display !== 'none') {
    fetchScalping();
  }
}, 15000);

// Intraday auto-refresh every 15 detik
setInterval(() => {
  if (document.getElementById('tab-intraday') && document.getElementById('tab-intraday').style.display !== 'none') {
    fetchIntraday();
  }
}, 15000);

// Settings auto-refresh every 20 detik
setInterval(() => {
  if (document.getElementById('tab-settings') && document.getElementById('tab-settings').style.display !== 'none') {
    loadAccountStatus();
    loadSavedAccounts();
  }
}, 20000);

// Settings tab functions
async function loadAccountStatus() {
  const d = await fetchJson('/api/account/status', {connected:false, account:{}, active_config:{}});
  const el = id => document.getElementById(id);
  const connected = !!d.connected;
  el('acc_conn').textContent = connected ? 'TERHUBUNG' : 'TERPUTUS';
  el('acc_conn').style.color = connected ? '#22c55e' : '#ef4444';
  const a = d.account || {};
  el('acc_login').textContent = a.login ?? '-';
  el('acc_server').textContent = a.server ?? '-';
  el('acc_name').textContent = a.name ?? '-';
  el('acc_balance').textContent = a.balance != null ? a.balance.toLocaleString(undefined,{maximumFractionDigits:2}) + ' ' + (a.currency||'') : '-';
  el('acc_equity').textContent = a.equity != null ? a.equity.toLocaleString(undefined,{maximumFractionDigits:2}) + ' ' + (a.currency||'') : '-';
  el('acc_lev').textContent = a.leverage ? '1:' + a.leverage : '-';

  const symSel = el('acc_symbol_sel');
  if (symSel) {
    const symbols = d.symbols || ['XAUUSDc'];
    const active = d.symbol || 'XAUUSDc';
    symSel.innerHTML = symbols.map(s => '<option value="' + escapeHtml(s) + '"' + (s === active ? ' selected' : '') + '>' + escapeHtml(s) + '</option>').join('');
    const res = el('acc_symbol_result');
    if (res) res.textContent = 'Simbol aktif: ' + active + (symbols.length > 1 ? ' (dapat diganti)' : '');
  }
  const fillSel = (id, active) => {
    const sel = el(id);
    if (!sel) return;
    const symbols = d.symbols || ['XAUUSDc'];
    sel.innerHTML = symbols.map(s => '<option value="' + escapeHtml(s) + '"' + (s === active ? ' selected' : '') + '>' + escapeHtml(s) + '</option>').join('');
  };
  fillSel('mo_symbol', d.symbol || 'XAUUSDc');
  fillSel('gr_symbol', d.symbol || 'XAUUSDc');
  const gridTitle = el('gridSymbolTitle');
  if (gridTitle) gridTitle.textContent = d.symbol || 'XAUUSDc';
}
async function changeActiveSymbol() {
  const symSel = document.getElementById('acc_symbol_sel');
  const res = document.getElementById('acc_symbol_result');
  if (!symSel || !res) return;
  const symbol = symSel.value;
  res.style.color = '#fbbf24';
  res.textContent = 'Mengganti simbol ke ' + symbol + '...';
  try {
    const d = await fetch('/api/account/symbol', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({symbol})
    }).then(r => r.json());
    if (d.success) {
      res.style.color = '#6ee7b7';
      res.textContent = 'Simbol aktif: ' + d.symbol;
      showNotif('Engine restart ke simbol ' + d.symbol, '#22c55e');
      if (typeof refreshOverview === 'function') refreshOverview();
      if (typeof fetchPriceChart === 'function') fetchPriceChart('priceChartGrid');
      if (typeof fetchManualChart === 'function') fetchManualChart();
    } else {
      res.style.color = '#ef4444';
      res.textContent = 'Gagal: ' + (d.error || 'unknown');
    }
  } catch(e) {
    res.style.color = '#ef4444';
    res.textContent = 'Error: ' + e.message;
  }
}
async function reloadAccountStatus() {
  const btn = document.getElementById('accLoginResult') || document.getElementById('acc_login_result');
  try {
    const r = await fetch('/api/account/status');
    const d = await r.json();
    if (d && d.connected) {
      showNotif('Akun terhubung', '#22c55e');
    } else {
      showNotif('Akun terputus', '#ef4444');
    }
  } catch(e) {}
  await loadAccountStatus();
  await loadSavedAccounts();
}
function setAutoTradeAfterSwitch(enabled) {
  return fetch('/api/account/set-enabled', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({enabled: !!enabled})
  }).then(r => r.json()).then(d => {
    showNotif(d.enabled ? 'Auto-trade AKTIF' : 'Auto-trade MATI', d.enabled ? '#22c55e' : '#ef4444');
  }).catch(() => showNotif('Gagal set auto-trade', '#ef4444'));
}
async function connectAccount() {
  const resEl = document.getElementById('acc_login_result');
  resEl.style.color = '#fbbf24';
  resEl.textContent = 'Menghubungkan...';
  const login = document.getElementById('acc_login_in').value.trim();
  const pass = document.getElementById('acc_pass_in').value.trim();
  const server = document.getElementById('acc_server_in').value.trim();
  if (!login || !pass || !server) {
    resEl.style.color = '#ef4444';
    resEl.textContent = 'Login, password, dan server wajib diisi';
    return;
  }
  try {
    const r = await fetch('/api/account/login', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({login, password: pass, server})
    });
    const d = await r.json();
    if (d.success) {
      resEl.style.color = '#6ee7b7';
      resEl.textContent = 'Berhasil login ke ' + d.account.login + ' @ ' + d.account.server + ' (balance ' + d.account.balance.toLocaleString() + ')';
      showNotif('Akun berhasil diganti', '#22c55e');
      await loadAccountStatus();
      await loadSavedAccounts();
    } else {
      resEl.style.color = '#ef4444';
      resEl.textContent = 'Gagal: ' + (d.error || 'unknown');
      showNotif('Gagal login akun', '#ef4444');
    }
  } catch(e) {
    resEl.style.color = '#ef4444';
    resEl.textContent = 'Error: ' + e.message;
  }
}
async function saveAccountOnly() {
  const login = document.getElementById('acc_login_in').value.trim();
  const pass = document.getElementById('acc_pass_in').value.trim();
  const server = document.getElementById('acc_server_in').value.trim();
  const name = prompt('Nama untuk akun ini (mis. Real20):');
  if (!name) return;
  const d = await fetch('/api/account/saved', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, login, password: pass, server})
  }).then(r => r.json());
  if (d.success) {
    showNotif('Akun tersimpan', '#22c55e');
    loadSavedAccounts();
  } else {
    showNotif('Gagal simpan', '#ef4444');
  }
}
async function loadSavedAccounts() {
  const d = await fetchJson('/api/account/saved', {accounts:[]});
  const tbody = document.getElementById('savedAccountsBody');
  const accs = d.accounts || [];
  if (!accs.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#94a3b8">Belum ada akun tersimpan</td></tr>';
    return;
  }
  tbody.innerHTML = accs.map(a => `
    <tr>
      <td><b>${escapeHtml(a.name)}</b></td>
      <td>${escapeHtml(a.login)}</td>
      <td>${escapeHtml(a.server)}</td>
      <td>
        <button onclick="switchSavedAccount('${escapeJs(a.name)}')" style="padding:4px 10px;background:#3b82f6;color:#fff;border:none;border-radius:4px;cursor:pointer">Switch</button>
        <button onclick="deleteSavedAccount('${escapeJs(a.name)}')" style="padding:4px 10px;background:#334155;color:#ef4444;border:none;border-radius:4px;cursor:pointer">Hapus</button>
      </td>
    </tr>`).join('');
}
async function switchSavedAccount(name) {
  if (!confirm('Ganti ke akun "' + name + '"? Auto-trade akan dimatikan sementara.')) return;
  const d = await fetch('/api/account/saved/' + encodeURIComponent(name) + '/switch', {
    method: 'POST'
  }).then(r => r.json());
  if (d.success) {
    showNotif('Switch ke ' + d.account.login, '#22c55e');
    await loadAccountStatus();
  } else {
    showNotif('Gagal switch: ' + (d.error||''), '#ef4444');
  }
}
async function deleteSavedAccount(name) {
  if (!confirm('Hapus akun "' + name + '" dari daftar?')) return;
  const d = await fetch('/api/account/saved/' + encodeURIComponent(name), {
    method: 'DELETE'
  }).then(r => r.json());
  if (d.success) {
    showNotif('Akun dihapus', '#ef4444');
    loadSavedAccounts();
  }
}
async function addSavedAccount() {
  const name = document.getElementById('sv_name').value.trim();
  const login = document.getElementById('sv_login').value.trim();
  const pass = document.getElementById('sv_pass').value.trim();
  const server = document.getElementById('sv_server').value.trim();
  const resEl = document.getElementById('sv_result');
  if (!name || !login || !pass || !server) {
    resEl.style.color = '#ef4444';
    resEl.textContent = 'Semua field wajib diisi';
    return;
  }
  const d = await fetch('/api/account/saved', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, login, password: pass, server})
  }).then(r => r.json());
  if (d.success) {
    resEl.style.color = '#6ee7b7';
    resEl.textContent = 'Akun "' + name + '" tersimpan';
    document.getElementById('sv_name').value = '';
    document.getElementById('sv_login').value = '';
    document.getElementById('sv_pass').value = '';
    document.getElementById('sv_server').value = '';
    loadSavedAccounts();
  } else {
    resEl.style.color = '#ef4444';
    resEl.textContent = d.error || 'Gagal simpan';
  }
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function escapeJs(s) {
  return String(s).replace(/'/g, "\\'").replace(/"/g, '\\"');
}
</script>
</div>
</div>
</body>
</html>"""
