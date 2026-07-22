from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date
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
                     "sl": p.sl or 0, "tp": p.tp or 0, "comment": p.comment}
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
        rates = mt5.copy_rates_from_pos("XAUUSDc", mt5.TIMEFRAME_M1, 0, 2000)
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


app = FastAPI(title="DLineBot Dashboard")


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


@app.get("/api/scalping")
@cached(ttl=5)
def get_scalping():
    path = Path("runtime/scalping.json")
    if not path.exists():
        return {
            "scalp_score": {"score": 0, "grade": "-", "direction": "WAIT", "action": "WAIT"},
            "momentum": {},
            "speed": {},
            "liquidity": {},
            "fake_breakout": {},
            "session": {},
            "impulse": {}
        }
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"error": "Gagal membaca scalping snapshot."}


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
# Manual Order API
# =====================================

@app.post("/api/order/manual")
def api_manual_order(data: dict):
    symbol = data.get("symbol", "XAUUSDc")
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
    symbol = data.get("symbol", "XAUUSDc")
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
    symbol = data.get("symbol", "XAUUSDc")
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
    symbol = data.get("symbol", "XAUUSDc")
    dry_run = data.get("dry_run", False)

    mgr = PendingOrderManager(dry_run=dry_run)
    count = mgr.cancel_all(symbol)
    return {"success": True, "cancelled": count}


@app.get("/api/grid/status")
def api_grid_status():
    symbol = "XAUUSDc"
    pending = get_cached_pending(symbol)
    positions = get_cached_positions(symbol)
    return {
        "pending_orders": pending,
        "pending_count": len(pending),
        "open_positions": positions,
    }


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
    result = controller.close(position)
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


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(HTML_PAGE)


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>DLineBot AI - Quant Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',sans-serif; background:#0f172a; color:#e2e8f0; padding:12px; }
h1 { font-size:20px; margin-bottom:12px; color:#f97316; display:flex; align-items:center; gap:10px; }
h1 small { font-size:13px; color:#64748b; font-weight:400; }
h2 { font-size:14px; margin:16px 0 6px; color:#94a3b8; border-left:3px solid #f97316; padding-left:8px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(130px,1fr)); gap:6px; margin-bottom:8px; }
.card { background:#1e293b; padding:8px 10px; border-radius:6px; }
.card .lbl { font-size:10px; color:#64748b; text-transform:uppercase; }
.card .val { font-size:16px; font-weight:700; margin-top:2px; }
.chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px; }
@media(max-width:900px) { .chart-grid { grid-template-columns:1fr; } }
.chart-container { background:#1e293b; border-radius:6px; padding:8px; }
.green { color:#6ee7b7; }
.red { color:#fca5a5; }
.orange { color:#f97316; }
.yellow { color:#fbbf24; }
.purple { color:#a78bfa; }
table { width:100%; border-collapse:collapse; background:#1e293b; border-radius:6px; overflow:hidden; font-size:11px; }
th { background:#334155; text-align:left; padding:4px 6px; color:#94a3b8; text-transform:uppercase; font-size:10px; }
td { padding:4px 6px; border-top:1px solid #334155; }
tr:hover { background:#1e3a5f; }
.badge { display:inline-block; padding:1px 5px; border-radius:3px; font-size:10px; font-weight:600; }
.buy { background:#065f46; color:#6ee7b7; }
.sell { background:#7f1d1d; color:#fca5a5; }
.hold { background:#451a03; color:#fdba74; }
.status-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:4px; }
.status-running { background:#6ee7b7; }
.status-stopped { background:#fca5a5; }
.heatmap-grid { display:grid; grid-template-columns:repeat(24,1fr); gap:1px; font-size:8px; }
.heatmap-cell { padding:2px 0; text-align:center; border-radius:1px; }
.heatmap-label { font-size:8px; color:#64748b; }
.auto-refresh { font-size:10px; color:#64748b; margin-bottom:6px; }
.tab-bar { display:flex; gap:4px; margin-bottom:10px; }
.tab-btn { padding:6px 14px; border-radius:4px; border:none; background:#1e293b; color:#94a3b8; cursor:pointer; font-size:12px; }
.tab-btn.active { background:#f97316; color:#fff; font-weight:600; }
.tab-btn:hover { background:#334155; }
@media(max-width:600px) {
  .grid { grid-template-columns:repeat(2,1fr); }
  .chart-grid { grid-template-columns:1fr; }
  body { padding:6px; }
  h1 { font-size:16px; }
  .card .val { font-size:14px; }
  .heatmap-grid { grid-template-columns:repeat(12,1fr); }
}
</style>
</head>
<body>

<h1>
  DLineBot AI
  <small id="serverTime"></small>
  <span style="margin-left:auto;font-size:11px;color:#64748b" id="refreshStatus">Auto 5s</span>
</h1>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('main',this)">Overview</button>
  <button class="tab-btn" onclick="switchTab('analytics',this)">Analytics</button>
  <button class="tab-btn" onclick="switchTab('learning',this)">AI Learning</button>
  <button class="tab-btn" onclick="switchTab('manual',this)">Manual Order</button>
  <button class="tab-btn" onclick="switchTab('grid',this)">Grid & Pending</button>
</div>

<div id="tab-main">

<div class="grid" id="stats"></div>

<h2>AI Signal</h2>
<div class="grid" id="signalBox"></div>

<h2>Smart Scalping Engine</h2>
<div class="grid" id="scalpingScoreBox"></div>
<div class="grid" id="scalpingEngineBox"></div>

<h2>Open Position</h2>
<div id="positionInfo" style="margin-bottom:6px;font-size:12px;"></div>
<table><thead><tr>
  <th>Ticket</th><th>Type</th><th>Vol</th><th>Entry</th><th>Current</th><th>Profit</th><th>SL</th><th>TP</th>
</tr></thead><tbody id="positions"></tbody></table>

<h2>Equity Curve</h2>
<div class="chart-container">
  <canvas id="equityChart" height="180"></canvas>
</div>

<h2>Trade History</h2>
<table><thead><tr>
  <th>Time</th><th>Sig</th><th>Conf</th><th>Action</th><th>Status</th><th>Entry</th><th>Profit</th><th>Lot</th>
</tr></thead><tbody id="trades"></tbody></table>

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

<h2>Manual Order - SL, TP1, TP2</h2>
<div style="background:#1e293b;border-radius:6px;padding:16px;max-width:500px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div><label style="font-size:11px;color:#94a3b8">Symbol</label><br><input id="mo_symbol" value="XAUUSDc" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
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
    <button onclick="sendManualOrder(false)" style="flex:1;padding:8px;background:#f97316;color:#fff;border:none;border-radius:4px;font-weight:600;cursor:pointer">KIRIM ORDER</button>
    <button onclick="sendManualOrder(true)" style="padding:8px;background:#334155;color:#94a3b8;border:none;border-radius:4px;cursor:pointer">Dry Run</button>
  </div>
  <div id="mo_result" style="margin-top:12px;font-size:12px;color:#6ee7b7"></div>
</div>

<h2>Parted Order History (TP1/TP2)</h2>
<table><thead><tr>
  <th>Time</th><th>Sym</th><th>Sig</th><th>Action</th><th>Entry</th><th>SL</th><th>TP</th><th>Lot</th><th>Status</th><th>Ticket</th>
</tr></thead><tbody id="partedOrders"></tbody></table>

</div>

<div id="tab-grid" style="display:none">

<h2>Grid Order (Buy Stop / Sell Stop)</h2>
<div style="background:#1e293b;border-radius:6px;padding:16px;max-width:500px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div><label style="font-size:11px;color:#94a3b8">Symbol</label><br><input id="gr_symbol" value="XAUUSDc" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Layers</label><br><input id="gr_layers" value="3" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Spacing (pt)</label><br><input id="gr_spacing" value="3.0" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">Lot per level</label><br><input id="gr_lot" value="0.01" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">SL Distance (pt)</label><br><input id="gr_sl" value="6.0" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
    <div><label style="font-size:11px;color:#94a3b8">TP Distance (pt)</label><br><input id="gr_tp" value="8.0" style="width:100%;padding:6px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px"></div>
  </div>
  <div style="margin-top:12px;display:flex;gap:8px">
    <button onclick="placeGrid(false)" style="flex:1;padding:8px;background:#f97316;color:#fff;border:none;border-radius:4px;font-weight:600;cursor:pointer">PLACE GRID</button>
    <button onclick="placeGrid(true)" style="padding:8px;background:#334155;color:#94a3b8;border:none;border-radius:4px;cursor:pointer">Dry Run</button>
    <button onclick="cancelGrid()" style="padding:8px;background:#dc2626;color:#fff;border:none;border-radius:4px;cursor:pointer">Cancel All</button>
  </div>
  <div id="gr_result" style="margin-top:12px;font-size:12px;color:#6ee7b7"></div>
</div>

<h2>Pending Orders</h2>
<table><thead><tr>
  <th>Ticket</th><th>Type</th><th>Vol</th><th>Price</th><th>SL</th><th>TP</th><th>Comment</th>
</tr></thead><tbody id="pendingOrders"></tbody></table>

<h2>Open Positions</h2>
<table><thead><tr>
  <th>Ticket</th><th>Type</th><th>Vol</th><th>Entry</th><th>Current</th><th>Profit</th><th>SL</th><th>TP</th><th>Action</th>
</tr></thead><tbody id="managePositions"></tbody></table>

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
<table><thead><tr>
  <th>ID</th><th>Signal</th><th>Conf</th><th>Entry</th><th>Exit</th><th>Profit</th><th>Status</th><th>Time</th>
</tr></thead><tbody id="learningRecords"></tbody></table>

</div>

<script>
let charts = {};
let analyticsLoaded = false;
let learningLoaded = false;

function switchTab(name, el) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('[id^="tab-"]').forEach(t => t.style.display = 'none');
  document.getElementById('tab-' + name).style.display = 'block';
  (el || event.target).classList.add('active');
  if (name === 'analytics' && !analyticsLoaded) {
    analyticsLoaded = true;
    fetchAnalytics();
  }
  if (name === 'manual') {
    fetchPartedOrders();
  }
  if (name === 'grid') {
    fetchGridStatus();
    fetchManagePositions();
  }
  if (name === 'learning' && !learningLoaded) {
    learningLoaded = true;
    fetchLearningRecords();
  }
}

function destroyChart(name) {
  if (charts[name]) { charts[name].destroy(); delete charts[name]; }
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
      <div class="card"><div class="lbl">Equity</div><div class="val orange">$${(overview.equity||0).toFixed(2)}</div></div>
      <div class="card"><div class="lbl">Floating</div><div class="val ${(overview.floating_pl||0) >= 0 ? 'green' : 'red'}">${(overview.floating_pl||0) >= 0 ? '+' : ''}$${(overview.floating_pl||0).toFixed(2)}</div></div>
      <div class="card"><div class="lbl">Drawdown</div><div class="val yellow">${(overview.drawdown||0).toFixed(1)}%</div></div>
      <div class="card"><div class="lbl">Trades Today</div><div class="val">${overview.trades_today||0}</div></div>
      <div class="card"><div class="lbl">Open Positions</div><div class="val">${overview.open_count||0}</div></div>
    `;

    document.getElementById('positionInfo').innerHTML = (overview.open_count||0) > 0
      ? '<span class="status-dot status-running"></span> ' + overview.open_count + ' posisi aktif'
      : '<span class="status-dot" style="background:#64748b"></span> Tidak ada posisi';

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
      <div class="card"><div class="lbl">Grade</div><div class="val orange">${ss.grade||'-'}</div></div>
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
        { label:'Equity', data:equity.map(e=>e.equity), borderColor:'#f97316', borderWidth:2, fill:false, pointRadius:0, tension:0.3 }
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
      { data:[sd.buy, sd.sell], backgroundColor:['rgba(249,115,22,0.7)','rgba(167,139,250,0.7)'], borderColor:['#f97316','#a78bfa'], borderWidth:1 }
    ], { plugins:{legend:{position:'bottom'}} });

    const histLabels = Object.keys(ch);
    makeChart('confidenceHistChart', 'bar', histLabels, [
      { label:'Count', data:histLabels.map(k=>ch[k]), backgroundColor:'rgba(249,115,22,0.7)', borderColor:'#f97316', borderWidth:1 }
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
      <div class="card"><div class="lbl">Model</div><div class="val orange">${mv.current_version||'-'}</div><div class="lbl">${mv.training_date||'-'}</div></div>
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

async function fetchPartedOrders() {
  try {
    const data = await fetchJson('/api/order/parted?limit=20', []);
    document.getElementById('partedOrders').innerHTML = data.map(t => {
      const sym = (t.symbol||'XAUUSDc').replace(/'/g,'');
      const sig = (t.signal||'').replace(/'/g,'');
      const vol = t.lot_size||0.01;
      const entry = t.entry_price||'';
      const sl = t.stop_loss||'';
      const tp = t.take_profit||'';
      return '<tr style="cursor:pointer" data-sym="'+sym+'" data-sig="'+sig+'" data-vol="'+vol+'" data-entry="'+entry+'" data-sl="'+sl+'" data-tp="'+tp+'"><td style="font-size:10px">'+(t.time?.split(' ')[1]||t.time)+'</td><td>'+sym+'</td><td><span class="badge '+sig.toLowerCase()+'">'+sig+'</span></td><td>'+(t.action||'-')+'</td><td>'+entry+'</td><td>'+sl+'</td><td>'+tp+'</td><td>'+vol+'</td><td>'+(t.status||'-')+'</td><td>'+(t.ticket||'-')+'</td></tr>';
    }).join('');
  } catch(e) { console.error('Parted orders error:', e); }
}

document.getElementById('partedOrders').addEventListener('click', function(e) {
  const tr = e.target.closest('tr');
  if (!tr) return;
  const sym = tr.dataset.sym || 'XAUUSDc';
  const sig = tr.dataset.sig || 'BUY';
  const vol = '0.01';
  const entry = tr.dataset.entry || '';
  const entryVal = parseFloat(entry);
  let sl = '', tp1 = '';
  if (!isNaN(entryVal) && entryVal > 0) {
    if (sig === 'BUY') {
      sl = (entryVal - 6).toFixed(1);
      tp1 = (entryVal + 2).toFixed(1);
    } else {
      sl = (entryVal + 6).toFixed(1);
      tp1 = (entryVal - 2).toFixed(1);
    }
  }
  document.getElementById('mo_symbol').value = sym;
  document.getElementById('mo_signal').value = sig;
  document.getElementById('mo_volume').value = vol;
  document.getElementById('mo_entry').value = entry;
  document.getElementById('mo_sl').value = sl;
  document.getElementById('mo_tp1').value = tp1;
  document.getElementById('mo_tp2').value = '';
  document.getElementById('mo_result').textContent = 'SL 6pt / TP target 1.0-2.0 (otomatis)';
  window.scrollTo(0, document.getElementById('tab-manual').offsetTop - 10);
});

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
        fetchPartedOrders();
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
setInterval(fetchData, 15000);
setInterval(() => { if (analyticsLoaded && document.getElementById('tab-analytics').style.display !== 'none') fetchAnalytics(); }, 30000);
setInterval(() => { if (learningLoaded && document.getElementById('tab-learning').style.display !== 'none') fetchLearningRecords(); }, 45000);

// Grid tab auto-refresh every 3 detik
setInterval(() => {
  if (document.getElementById('tab-grid') && document.getElementById('tab-grid').style.display !== 'none') {
    fetchGridStatus();
    fetchManagePositions();
  }
}, 3000);
</script>
</body>
</html>"""
