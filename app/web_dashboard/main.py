from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date
from pathlib import Path
import json
from app.database.session import db_session
from app.database.models import TradeLog, EquitySnapshot
from app.mt5.session import MT5Session
from app.mt5.parted_order import PartedOrder
from app.notification.telegram_notifier import TelegramNotifier
from app.trading.trade_learner import TradeLearner
from app.trading.analytics import Analytics
from app.trading.model_version import ModelVersionManager

app = FastAPI(title="DLineBot Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/trades")
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
    }


@app.get("/api/learning")
def get_learning():
    learner = TradeLearner()
    return learner.get_learning_stats()


@app.get("/api/scalping")
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
def api_win_rate():
    return analytics.win_rate()


@app.get("/api/analytics/monthly_profit")
def api_monthly_profit(months=6):
    return analytics.monthly_profit(months)


@app.get("/api/analytics/drawdown_curve")
def api_drawdown_curve(limit=100):
    return analytics.drawdown_curve(limit)


@app.get("/api/analytics/trade_distribution")
def api_trade_distribution():
    return analytics.trade_distribution()


@app.get("/api/analytics/signal_distribution")
def api_signal_distribution():
    return analytics.signal_distribution()


@app.get("/api/analytics/confidence_histogram")
def api_confidence_histogram():
    return analytics.confidence_histogram()


@app.get("/api/analytics/hour_performance")
def api_hour_performance():
    return analytics.hour_performance()


@app.get("/api/analytics/session_performance")
def api_session_performance():
    return analytics.session_performance()


@app.get("/api/analytics/heatmap")
def api_heatmap():
    return analytics.heatmap()


@app.get("/api/analytics/ai_accuracy")
def api_ai_accuracy():
    return analytics.ai_accuracy()


@app.get("/api/analytics/feature_importance")
def api_feature_importance():
    learner = TradeLearner()
    return learner.get_feature_importance()


@app.get("/api/analytics/learning_progress")
def api_learning_progress():
    return analytics.learning_progress()


@app.get("/api/model_version")
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
    return {"success": True, "result": result}


@app.get("/api/order/parted")
def api_get_parted_orders(limit=20):
    with db_session() as db:
        trades = (
            db.query(TradeLog)
            .filter(TradeLog.action.like("%TP%"))
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
            "action": t.action,
            "entry_price": t.entry_price,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "lot_size": t.lot_size,
            "status": t.status,
            "ticket": t.ticket,
        }
        for t in trades
    ]


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
h1 { font-size:20px; margin-bottom:12px; color:#38bdf8; display:flex; align-items:center; gap:10px; }
h1 small { font-size:13px; color:#64748b; font-weight:400; }
h2 { font-size:14px; margin:16px 0 6px; color:#94a3b8; border-left:3px solid #38bdf8; padding-left:8px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(130px,1fr)); gap:6px; margin-bottom:8px; }
.card { background:#1e293b; padding:8px 10px; border-radius:6px; }
.card .lbl { font-size:10px; color:#64748b; text-transform:uppercase; }
.card .val { font-size:16px; font-weight:700; margin-top:2px; }
.chart-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px; }
@media(max-width:900px) { .chart-grid { grid-template-columns:1fr; } }
.chart-container { background:#1e293b; border-radius:6px; padding:8px; }
.green { color:#6ee7b7; }
.red { color:#fca5a5; }
.blue { color:#38bdf8; }
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
.tab-btn.active { background:#38bdf8; color:#0f172a; font-weight:600; }
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
    <button onclick="sendManualOrder(false)" style="flex:1;padding:8px;background:#38bdf8;color:#0f172a;border:none;border-radius:4px;font-weight:600;cursor:pointer">KIRIM ORDER</button>
    <button onclick="sendManualOrder(true)" style="padding:8px;background:#334155;color:#94a3b8;border:none;border-radius:4px;cursor:pointer">Dry Run</button>
  </div>
  <div id="mo_result" style="margin-top:12px;font-size:12px;color:#6ee7b7"></div>
</div>

<h2>Parted Order History (TP1/TP2)</h2>
<table><thead><tr>
  <th>Time</th><th>Sym</th><th>Sig</th><th>Action</th><th>Entry</th><th>SL</th><th>TP</th><th>Lot</th><th>Status</th><th>Ticket</th>
</tr></thead><tbody id="partedOrders"></tbody></table>

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

async function fetchJson(url, fallback, timeoutMs=2500) {
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
    const [overview, trades, equity, learning, scalping] = await Promise.all([
      fetchJson('/api/overview', {balance:0,equity:0,floating_pl:0,drawdown:0,trades_today:0,open_count:0,open_positions:[],server_time:'loading...'}),
      fetchJson('/api/trades?limit=20', []),
      fetchJson('/api/equity?limit=50', []),
      fetchJson('/api/learning', {total:0,win:0,loss:0,win_rate:0}),
      fetchJson('/api/scalping', {scalp_score:{score:0,grade:'-',direction:'WAIT',action:'WAIT'}})
    ]);

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
      <div class="card"><div class="lbl">Total Samples</div><div class="val">${learning.total}</div></div>
      <div class="card"><div class="lbl">Win</div><div class="val green">${learning.win}</div></div>
      <div class="card"><div class="lbl">Loss</div><div class="val red">${learning.loss}</div></div>
      <div class="card"><div class="lbl">Win Rate</div><div class="val yellow">${learning.win_rate}%</div></div>
    `;

    if (equity.length > 0) {
      makeChart('equityChart', 'line', equity.map(e=>(e.time?.split(' ')[1]||'').slice(0,5)), [
        { label:'Balance', data:equity.map(e=>e.balance), borderColor:'#6ee7b7', borderWidth:2, fill:false, pointRadius:0, tension:0.3 },
        { label:'Equity', data:equity.map(e=>e.equity), borderColor:'#38bdf8', borderWidth:2, fill:false, pointRadius:0, tension:0.3 }
      ], { scales:{ y:{ ticks:{ font:{size:9} } } } });
    } else {
      destroyChart('equityChart');
    }

  } catch(e) { console.error('Overview error:', e); }
}

async function fetchAnalytics() {
  try {
    const wr = await fetch('/api/analytics/win_rate').then(r=>r.json());
    const monthly = await fetch('/api/analytics/monthly_profit?months=6').then(r=>r.json());
    const dd = await fetch('/api/analytics/drawdown_curve?limit=100').then(r=>r.json());
    const td = await fetch('/api/analytics/trade_distribution').then(r=>r.json());
    const sd = await fetch('/api/analytics/signal_distribution').then(r=>r.json());
    const ch = await fetch('/api/analytics/confidence_histogram').then(r=>r.json());
    const hp = await fetch('/api/analytics/hour_performance').then(r=>r.json());
    const sp = await fetch('/api/analytics/session_performance').then(r=>r.json());
    const acc = await fetch('/api/analytics/ai_accuracy').then(r=>r.json());
    const lp = await fetch('/api/analytics/learning_progress').then(r=>r.json());
    const mv = await fetch('/api/model_version').then(r=>r.json());
    const hm = await fetch('/api/analytics/heatmap').then(r=>r.json());

    document.getElementById('winRateBox').innerHTML = `
      <div class="card"><div class="lbl">Total Trades</div><div class="val">${wr.total}</div></div>
      <div class="card"><div class="lbl">Win</div><div class="val green">${wr.win}</div></div>
      <div class="card"><div class="lbl">Loss</div><div class="val red">${wr.loss}</div></div>
      <div class="card"><div class="lbl">Win Rate</div><div class="val yellow">${wr.win_rate}%</div></div>
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
      { data:[sd.buy, sd.sell], backgroundColor:['rgba(56,189,248,0.7)','rgba(167,139,250,0.7)'], borderColor:['#38bdf8','#a78bfa'], borderWidth:1 }
    ], { plugins:{legend:{position:'bottom'}} });

    const histLabels = Object.keys(ch);
    makeChart('confidenceHistChart', 'bar', histLabels, [
      { label:'Count', data:histLabels.map(k=>ch[k]), backgroundColor:'rgba(56,189,248,0.7)', borderColor:'#38bdf8', borderWidth:1 }
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
      <div class="card"><div class="lbl">AI Accuracy</div><div class="val ${acc.accuracy>=50?'green':'red'}">${acc.accuracy}%</div></div>
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

async function fetchPartedOrders() {
  try {
    const data = await fetchJson('/api/order/parted?limit=20', []);
    document.getElementById('partedOrders').innerHTML = data.map(t => '<tr><td style="font-size:10px">'+(t.time?.split(' ')[1]||t.time)+'</td><td>'+t.symbol+'</td><td><span class="badge '+(t.signal||'').toLowerCase()+'">'+t.signal+'</span></td><td>'+t.action+'</td><td>'+(t.entry_price||'-')+'</td><td>'+(t.stop_loss||'-')+'</td><td>'+(t.take_profit||'-')+'</td><td>'+t.lot_size+'</td><td>'+(t.status||'-')+'</td><td>'+(t.ticket||'-')+'</td></tr>').join('');
  } catch(e) { console.error('Parted orders error:', e); }
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
setInterval(fetchData, 10000);
setInterval(() => { if (analyticsLoaded) fetchAnalytics(); }, 15000);
setInterval(() => { if (learningLoaded) fetchLearningRecords(); }, 20000);
</script>
</body>
</html>"""
