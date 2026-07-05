from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.database.session import SessionLocal
from app.database.models import TradeLog, EquitySnapshot

app = FastAPI(title="DLineBot Dashboard")


@app.get("/api/trades")
def get_trades(limit: int = 50):
    db = SessionLocal()
    trades = (
        db.query(TradeLog)
        .order_by(TradeLog.id.desc())
        .limit(limit)
        .all()
    )
    db.close()
    return [
        {
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
def get_equity(limit: int = 100):
    db = SessionLocal()
    snapshots = (
        db.query(EquitySnapshot)
        .order_by(EquitySnapshot.id.desc())
        .limit(limit)
        .all()
    )
    db.close()
    return [
        {
            "time": str(s.time),
            "balance": s.balance,
            "equity": s.equity,
            "floating_pl": s.floating_pl,
            "drawdown": s.drawdown,
        }
        for s in snapshots
    ]


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(HTML_PAGE)


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DLineBot Dashboard</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI',sans-serif; background:#0f172a; color:#e2e8f0; padding:20px; }
h1 { font-size:24px; margin-bottom:20px; color:#38bdf8; }
h2 { font-size:18px; margin:20px 0 10px; color:#94a3b8; }
table { width:100%; border-collapse:collapse; background:#1e293b; border-radius:8px; overflow:hidden; }
th { background:#334155; text-align:left; padding:10px; font-size:13px; color:#94a3b8; text-transform:uppercase; }
td { padding:10px; border-top:1px solid #334155; font-size:14px; }
tr:hover { background:#1e3a5f; }
.badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:600; }
.buy { background:#065f46; color:#6ee7b7; }
.sell { background:#7f1d1d; color:#fca5a5; }
.hold { background:#451a03; color:#fdba74; }
.ok { color:#6ee7b7; }
.ng { color:#fca5a5; }
.stats { display:flex; gap:15px; margin-bottom:20px; flex-wrap:wrap; }
.card { background:#1e293b; padding:15px 20px; border-radius:8px; min-width:150px; }
.card .label { font-size:12px; color:#64748b; }
.card .value { font-size:22px; font-weight:700; margin-top:4px; }
.auto-refresh { font-size:12px; color:#64748b; margin-bottom:10px; }
</style>
</head>
<body>

<h1>DLineBot Dashboard</h1>

<div class="stats" id="stats"></div>

<div class="auto-refresh">Auto-refresh setiap 10 detik</div>

<h2>Trade Log</h2>
<table>
<thead><tr>
<th>Time</th><th>Signal</th><th>Conf</th><th>Action</th><th>Status</th><th>Entry</th><th>SL</th><th>TP</th><th>Lot</th><th>Reason</th>
</tr></thead>
<tbody id="trades"></tbody>
</table>

<h2>Equity</h2>
<table>
<thead><tr><th>Time</th><th>Balance</th><th>Equity</th><th>Floating P/L</th><th>Drawdown</th></tr></thead>
<tbody id="equity"></tbody>
</table>

<script>
async function fetchData() {
    const [trades, equity] = await Promise.all([
        fetch('/api/trades?limit=50').then(r=>r.json()),
        fetch('/api/equity?limit=20').then(r=>r.json())
    ]);

    const last = equity[0] || {};
    document.getElementById('stats').innerHTML = `
        <div class="card"><div class="label">Balance</div><div class="value">$${last.balance?.toFixed(2) || '-'}</div></div>
        <div class="card"><div class="label">Equity</div><div class="value">$${last.equity?.toFixed(2) || '-'}</div></div>
        <div class="card"><div class="label">Floating P/L</div><div class="value ${(last.floating_pl||0)>=0?'ok':'ng'}">${(last.floating_pl||0)>=0?'+':''}${last.floating_pl?.toFixed(2) || '-'}</div></div>
        <div class="card"><div class="label">Drawdown</div><div class="value">${last.drawdown?.toFixed(1) || '0'}%</div></div>
        <div class="card"><div class="label">Trades Today</div><div class="value">${trades.length}</div></div>
    `;

    document.getElementById('trades').innerHTML = trades.map(t => `
        <tr>
            <td>${t.time}</td>
            <td><span class="badge ${t.signal.toLowerCase()}">${t.signal}</span></td>
            <td>${t.confidence}%</td>
            <td>${t.action}</td>
            <td>${t.status}</td>
            <td>${t.entry_price || '-'}</td>
            <td>${t.stop_loss || '-'}</td>
            <td>${t.take_profit || '-'}</td>
            <td>${t.lot_size || '-'}</td>
            <td style="font-size:12px;color:#94a3b8">${t.reason || ''}</td>
        </tr>
    `).join('');

    document.getElementById('equity').innerHTML = equity.map(s => `
        <tr>
            <td>${s.time}</td>
            <td>$${s.balance?.toFixed(2)}</td>
            <td>$${s.equity?.toFixed(2)}</td>
            <td class="${(s.floating_pl||0)>=0?'ok':'ng'}">${(s.floating_pl||0)>=0?'+':''}$${s.floating_pl?.toFixed(2)}</td>
            <td>${s.drawdown?.toFixed(1)}%</td>
        </tr>
    `).join('');
}
fetchData();
setInterval(fetchData, 10000);
</script>

</body>
</html>"""
