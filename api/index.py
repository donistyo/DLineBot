import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI()

_data = {
    "signal": "-",
    "balance": 0,
    "equity": 0,
    "trades_today": 0,
    "profit_today": 0,
    "open_count": 0,
    "spread": 0,
    "server_time": "-",
    "trades": [],
    "equity_snapshots": [],
    "learning": {"total": 0, "win": 0, "loss": 0, "win_rate": 0},
    "scalping": None,
    "parted_orders": []
}

_pending_orders = []

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,user-scalable=no">
<title>DLineBot AI Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;padding:16px;font-size:14px}
h1{font-size:20px;margin-bottom:12px;color:#f97316}
h2{font-size:14px;margin:16px 0 6px;color:#94a3b8;border-left:3px solid #f97316;padding-left:8px}
.card{background:#1e293b;border-radius:8px;padding:10px 14px;margin:4px 0}
.row{display:flex;flex-wrap:wrap;gap:6px}
.col{flex:1;min-width:100px}
.lbl{font-size:11px;color:#64748b}
.val{font-size:18px;font-weight:700}
.green{color:#6ee7b7}
.red{color:#fca5a5}
.orange{color:#f97316}
.tab-bar{display:flex;gap:4px;margin-bottom:10px;flex-wrap:nowrap}
.tab-btn{background:#1e293b;border:none;color:#94a3b8;cursor:pointer;font-size:11px;padding:5px 10px;border-radius:3px;touch-action:manipulation;white-space:nowrap}
.tab-btn.active{background:#f97316;color:#fff;font-weight:600}
.tab-btn:first-child{width:90px}
.tab-btn:nth-child(2){width:100px}
@media(max-width:480px){.tab-bar{flex-wrap:wrap}.tab-btn{width:auto!important;padding:8px 16px;font-size:14px;border-radius:6px}}
canvas{max-height:200px}
input,select,button{width:100%;padding:8px;background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:4px;font-size:14px;touch-action:manipulation}
label{font-size:11px;color:#94a3b8}
table{width:100%;border-collapse:collapse;font-size:12px}
th{color:#94a3b8;text-align:left;padding:4px}
td{padding:4px;border-bottom:1px solid #1e293b}
@media(max-width:480px){body{padding:10px;font-size:13px}.val{font-size:16px}.col{min-width:70px}}
</style>
</head>
<body>

<h1>DLine AI Dashboard</h1>

<div class="tab-bar">
<button class="tab-btn active" onclick="switchTab('main',this)">Overview</button>
<button class="tab-btn" onclick="switchTab('manual',this)">Manual Order</button>
</div>

<div id="tab-main">
<div class="card" id="statsBox"></div>
<h2>Equity Curve</h2>
<div class="card"><canvas id="eqChart"></canvas></div>
<div style="display:flex;flex-wrap:wrap;gap:6px">
<div style="flex:1;min-width:200px"><h2>Drawdown</h2><div class="card"><canvas id="ddChart"></canvas></div></div>
<div style="flex:1;min-width:200px"><h2>Win / Loss</h2><div class="card"><canvas id="wlChart" style="max-height:200px"></canvas></div></div>
</div>
<h2>Trades</h2>
<div class="card" id="tradesList"><div style="color:#64748b">Loading...</div></div>
</div>

<div id="tab-manual" style="display:none">
<h2>Manual Order - SL, TP1, TP2</h2>
<div style="background:#1e293b;border-radius:6px;padding:16px;max-width:500px">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    <div><label>Symbol</label><br><input id="mo_symbol" value="XAUUSDc"></div>
    <div><label>Signal</label><br>
      <select id="mo_signal"><option value="BUY">BUY</option><option value="SELL">SELL</option></select>
    </div>
    <div><label>Lot</label><br><input id="mo_volume" value="0.01"></div>
    <div><label>Entry (kosong=auto)</label><br><input id="mo_entry"></div>
    <div><label>Stop Loss</label><br><input id="mo_sl"></div>
    <div><label>Take Profit 1</label><br><input id="mo_tp1"></div>
    <div style="grid-column:span 2"><label>Take Profit 2</label><br><input id="mo_tp2"></div>
  </div>
  <div style="margin-top:12px;display:flex;gap:8px">
    <button onclick="sendManualOrder(false)" style="flex:1;padding:8px;background:#f97316;color:#fff;border:none;border-radius:4px;font-weight:600;cursor:pointer">KIRIM ORDER</button>
    <button onclick="sendManualOrder(true)" style="padding:8px;background:#334155;color:#94a3b8;border:none;border-radius:4px;cursor:pointer">Dry Run</button>
  </div>
  <div id="mo_result" style="margin-top:12px;font-size:13px;color:#6ee7b7"></div>
</div>
<h2>Parted Order History (klik baris untuk isi form)</h2>
<table><thead><tr><th>Time</th><th>Sym</th><th>Sig</th><th>Entry</th><th>SL</th><th>TP</th><th>Lot</th><th>Status</th></tr></thead><tbody id="partedOrders"></tbody></table>
</div>
<script>
var _partedOrders = [];

function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active')});
  if(btn) btn.classList.add('active');
  document.querySelectorAll('[id^="tab-"]').forEach(function(el){el.style.display='none'});
  var t = document.getElementById('tab-'+name);
  if(t) t.style.display = 'block';
}

function fetchData() {
  var xhr = new XMLHttpRequest();
  xhr.open('GET', '/api/overview', true);
  xhr.onload = function() {
    if(xhr.status != 200) return;
    var d = JSON.parse(xhr.responseText);
    renderData(d);
  };
  xhr.onerror = function() { console.log('Fetch failed'); };
  xhr.send();
}

function renderData(d) {
  var stats = [
    ['Signal', d.signal||'-', d.signal=='BUY'?'green':d.signal=='SELL'?'red':''],
    ['Balance', '$'+(d.balance||0).toFixed(2), 'green'],
    ['Equity', '$'+(d.equity||0).toFixed(2), 'orange'],
    ['Open', (d.open_count||0)+' pos', ''],
    ['Today', (d.trades_today||0)+' trade | '+(d.profit_today>=0?'+':'')+'$'+(d.profit_today||0).toFixed(2), d.profit_today>=0?'green':'red'],
    ['Spread', d.spread||0, ''],
    ['Time', d.server_time||'-', ''],
  ];
  document.getElementById('statsBox').innerHTML = '<div class="row">' + stats.map(function(s){return '<div class="col"><div class="lbl">'+s[0]+'</div><div class="val '+(s[2]||'')+'">'+s[1]+'</div></div>'}).join('') + '</div>';

  var eq = d.equity_snapshots||[];
  var l = eq.map(function(e,i){return i+1});
  var v = eq.map(function(e){return e.equity||0});
  var ctx = document.getElementById('eqChart').getContext('2d');
  if(window._eqChart) window._eqChart.destroy();
  window._eqChart = new Chart(ctx, {type:'line', data:{labels:l, datasets:[{label:'Equity', data:v, borderColor:'#f97316', borderWidth:2, fill:false, pointRadius:0, tension:0.3}]}, options:{plugins:{legend:{display:false}}, scales:{x:{display:true,grid:{color:'#334155'}},y:{display:true,grid:{color:'#334155'}}}, responsive:true, maintainAspectRatio:true}});

  var dd = eq.map(function(e){return e.drawdown||0});
  var ctx2 = document.getElementById('ddChart').getContext('2d');
  if(window._ddChart) window._ddChart.destroy();
  window._ddChart = new Chart(ctx2, {type:'line', data:{labels:l, datasets:[{label:'Drawdown', data:dd, borderColor:'#fca5a5', backgroundColor:'rgba(252,165,165,0.1)', borderWidth:2, fill:true, pointRadius:0, tension:0.3}]}, options:{plugins:{legend:{display:false}}, scales:{x:{display:true,grid:{color:'#334155'}},y:{display:true,grid:{color:'#334155'}}}, responsive:true, maintainAspectRatio:true}});

  var tr = d.trades||[];
  var wins = tr.filter(function(t){return t.profit>0}).length;
  var losses = tr.filter(function(t){return t.profit<0}).length;
  var ctx3 = document.getElementById('wlChart').getContext('2d');
  if(window._wlChart) window._wlChart.destroy();
  window._wlChart = new Chart(ctx3, {type:'doughnut', data:{labels:['Win','Loss'], datasets:[{data:[wins,losses], backgroundColor:['#6ee7b7','#fca5a5'], borderWidth:0}]}, options:{plugins:{legend:{position:'bottom',labels:{color:'#94a3b8'}}}, responsive:true, maintainAspectRatio:true}});
  var el = document.getElementById('tradesList');
  if(!tr.length) {
    el.innerHTML = '<div style="color:#64748b">No trades</div>';
  } else {
    el.innerHTML = tr.slice(-20).reverse().map(function(t){
      var p = t.profit||0;
      return '<div style="padding:2px 0;border-bottom:1px solid #334155">'+t.symbol+' <span class="'+(p>=0?'green':'red')+'">'+(p>=0?'+':'')+'$'+p.toFixed(2)+'</span> | '+t.signal+' | '+(t.time||'')+'</div>';
    }).join('');
  }

  var po = d.parted_orders||[];
  _partedOrders = po;
  var pEl = document.getElementById('partedOrders');
  if(po.length==0) {
    pEl.innerHTML = '<tr><td colspan="8" style="color:#64748b;padding:8px">No orders</td></tr>';
  } else {
    pEl.innerHTML = po.slice(-20).reverse().map(function(t,i){
      return '<tr data-idx="' + i + '" style="cursor:pointer">' +
        '<td>'+(t.time||'-')+'</td>' +
        '<td>'+t.symbol+'</td>' +
        '<td style="color:'+(t.signal=='BUY'?'#6ee7b7':'#fca5a5')+'">'+t.signal+'</td>' +
        '<td>'+(t.entry_price||'-')+'</td>' +
        '<td>'+(t.stop_loss||'-')+'</td>' +
        '<td>'+(t.take_profit||'-')+'</td>' +
        '<td>'+t.lot_size+'</td>' +
        '<td>'+(t.status||'-')+'</td></tr>';
    }).join('');
    pEl.onclick = function(e) {
      var tr = e.target.closest('tr');
      if(!tr || !tr.dataset.idx) return;
      var t = _partedOrders[parseInt(tr.dataset.idx)];
      if(!t) return;
      document.getElementById('mo_signal').value = t.signal=='BUY'?'BUY':'SELL';
      document.getElementById('mo_volume').value = parseFloat(t.lot_size)||0.01;
      document.getElementById('mo_entry').value = t.entry_price||'';
      document.getElementById('mo_sl').value = t.stop_loss||'';
      document.getElementById('mo_tp1').value = t.take_profit||'';
      document.getElementById('mo_tp2').value = '';
      document.getElementById('mo_result').style.color = '#94a3b8';
      document.getElementById('mo_result').textContent = 'Form diisi dari order';
      switchTab('manual', document.querySelector('.tab-btn[onclick*="manual"]'));
    };
  }
}

function sendManualOrder(dryRun) {
  var btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Sending...';
  var payload = {
    symbol: document.getElementById('mo_symbol').value,
    signal: document.getElementById('mo_signal').value,
    volume: parseFloat(document.getElementById('mo_volume').value)||0.01,
    entry: document.getElementById('mo_entry').value || null,
    sl: document.getElementById('mo_sl').value || null,
    tp1: document.getElementById('mo_tp1').value || null,
    tp2: document.getElementById('mo_tp2').value || null,
  };
  var url = dryRun ? '/api/order/dry-run' : '/api/order/manual';
  var xhr = new XMLHttpRequest();
  xhr.open('POST', url, true);
  xhr.setRequestHeader('Content-Type','application/json');
  xhr.onload = function() {
    var data = JSON.parse(xhr.responseText);
    var el = document.getElementById('mo_result');
    if(data.success) {
      el.style.color = '#6ee7b7';
      if(dryRun) {
        el.innerHTML = 'DRY RUN OK';
      } else {
        el.innerHTML = 'ORDER QUEUED';
      }
    } else {
      el.style.color = '#fca5a5';
      el.textContent = 'FAILED: '+(data.error||'');
    }
  };
  xhr.onerror = function() {
    document.getElementById('mo_result').style.color = '#fca5a5';
    document.getElementById('mo_result').textContent = 'Network error';
  };
  xhr.send(JSON.stringify(payload));
  btn.disabled = false;
  btn.textContent = dryRun ? 'Dry Run' : 'KIRIM ORDER';
}

fetchData();
setInterval(fetchData, 5000);
</script>
</body>
</html>"""


@app.get("/")
def index():
    return HTMLResponse(HTML)


@app.get("/api/overview")
def overview():
    return _data


@app.post("/api/push")
async def push(request: Request):
    global _data
    body = await request.json()
    for k in _data:
        if k in body:
            _data[k] = body[k]
    return {"ok": True}


@app.post("/api/order/manual")
async def api_manual_order(request: Request):
    body = await request.json()
    body["dry_run"] = False
    body["id"] = len(_pending_orders) + 1
    _pending_orders.append(body)
    return {"success": True, "result": body}


@app.post("/api/order/dry-run")
async def api_dry_run(request: Request):
    body = await request.json()
    return {
        "success": True,
        "result": {
            "signal": body.get("signal"),
            "volume": body.get("volume", 0.01),
            "entry_price": body.get("entry") or "AUTO",
            "sl": body.get("sl") or "AUTO",
            "tp1": body.get("tp1") or "AUTO",
            "tp2": body.get("tp2") or "AUTO"
        }
    }


@app.get("/api/order/pending")
def api_pending_orders():
    orders = list(_pending_orders)
    _pending_orders.clear()
    return {"orders": orders}


@app.get("/api/order/parted")
def api_partend_orders():
    return _data.get("parted_orders", [])
