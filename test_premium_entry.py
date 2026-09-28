# Test tier PREMIUM/FALLBACK + BasketGuard (offline, tanpa order).
# Jalankan: python test_premium_entry.py   (workdir: D:\Project\Wedd\DLineBot)

import json
import sys
import time
import datetime as dt
from types import SimpleNamespace

sys.path.insert(0, ".")

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


# =====================================
# 0. Config sanity
# =====================================
print("\n[0] Config sanity")
with open("runtime/trade_config.json") as f:
    cfg = json.load(f)
check("config layer_count=10", cfg.get("layer_count") == 10, str(cfg.get("layer_count")))
check("config basket_cut_usd=-10", cfg.get("basket_cut_usd") == -10, str(cfg.get("basket_cut_usd")))
check("config basket_timeout_min=15", cfg.get("basket_timeout_min") == 15, str(cfg.get("basket_timeout_min")))
check("config max_positions TIDAK berubah (2)", cfg.get("max_positions") == 2, str(cfg.get("max_positions")))
check("config entry_copies_mode TIDAK berubah (dual)", cfg.get("entry_copies_mode") == "dual", str(cfg.get("entry_copies_mode")))
check("config sl_atr_mult TIDAK berubah (0.7)", cfg.get("sl_atr_mult") == 0.7, str(cfg.get("sl_atr_mult")))

_src_hist = open("app/mt5/history_manager.py", encoding="utf-8").read()
check("sl_exits memfilter BASKET_CUT", "BASKET_CUT" in _src_hist)
_src_scalp = open("app/trading/smart_scalping.py", encoding="utf-8").read()
check("smart_scalping menyimpan tests60", 'momentum["tests60"]' in _src_scalp)


# =====================================
# 1. Tier gate: DecisionEngine
# =====================================
print("\n[1] Tier gate DecisionEngine")

from app.trading.decision_engine import DecisionEngine

engine = DecisionEngine(min_scalp_score=55)
REGIME_DOWN = {"trend": "DOWN", "mode": "TREND", "adx": 35}


def make_scalp(score=75.0, tests60=8, override=None, close=4130.0,
               lo=4100.0, hi=4160.0, direction="SELL", grade="A",
               with_tests=True):
    momentum = {"direction": direction, "trend_override": override,
                "last_body": direction, "bull_bodies": 1, "bear_bodies": 1}
    if with_tests:
        momentum["tests60"] = tests60
    return {
        "scalp_score": {"score": score, "direction": direction,
                        "grade": grade, "details": {}},
        "momentum": momentum,
        "liquidity": {"body": 1.0, "upper_wick": 0.3, "lower_wick": 0.3},
        "close": close, "range_high": hi, "range_low": lo,
        "ema20": close, "ema50": close, "atr": 2.0,
        "indicators": {"RSI": 50},
    }


r = engine.decide(None, make_scalp(), REGIME_DOWN)
check("sinyal dasar = SELL", r.get("action") == "SELL", str(r))
check("PREMIUM x10 (score75, tests8, pos50%)",
      r.get("entry_layers") == 10, str(r.get("entry_layers")) + " | " + str(r.get("tier_reason")))

r = engine.decide(None, make_scalp(tests60=15), REGIME_DOWN)
check("tests60=15 -> FALLBACK", r.get("entry_layers") == 2, str(r.get("tier_reason")))
check("tests60=15 tetap SELL (gate tier bukan blocker)",
      r.get("action") == "SELL", str(r.get("action")))

r = engine.decide(None, make_scalp(score=65, grade="B"), REGIME_DOWN)
check("score65 -> FALLBACK", r.get("entry_layers") == 2, str(r.get("tier_reason")))

r = engine.decide(None, make_scalp(override="M1_NO_PULLBACK_SELL"), REGIME_DOWN)
check("trend_override -> FALLBACK", r.get("entry_layers") == 2, str(r.get("tier_reason")))

r = engine.decide(None, make_scalp(close=4150.0), REGIME_DOWN)
check("pos 83% (di luar 30-70) -> FALLBACK", r.get("entry_layers") == 2, str(r.get("tier_reason")))

r = engine.decide(None, make_scalp(with_tests=False), REGIME_DOWN)
check("tests60 tidak tersedia -> FALLBACK", r.get("entry_layers") == 2, str(r.get("tier_reason")))

# Kill switch: layer_count < 5 -> semua FALLBACK
import app.config.settings as _S
_orig_get = _S.get_trade_config
try:
    _S.get_trade_config = lambda k, d=None: (0 if k == "layer_count" else _orig_get(k, d))
    r = engine.decide(None, make_scalp(), REGIME_DOWN)
    check("kill switch layer_count=0 -> FALLBACK", r.get("entry_layers") == 2, str(r.get("entry_layers")))
finally:
    _S.get_trade_config = _orig_get

# RSI overbought tetap NO_TRADE
r = engine.decide(None, make_scalp(direction="BUY", close=4130.0),
                  {"trend": "UP", "mode": "TREND", "adx": 35},
                  None, 0) if False else None
r = engine.decide(None, {**make_scalp(direction="BUY"), "indicators": {"RSI": 80}},
                  {"trend": "UP", "mode": "TREND", "adx": 35})
check("RSI 80 BUY tetap NO_TRADE (guard lama utuh)", r.get("action") == "NO_TRADE", str(r.get("action")))


# =====================================
# 2. resolve_entry_copies
# =====================================
print("\n[2] resolve_entry_copies")
from app.trading.auto_trader import resolve_entry_copies

check("decision entry_layers=10 -> 10", resolve_entry_copies({"entry_layers": 10}, 2) == 10)
check("decision tanpa tier -> fallback 2", resolve_entry_copies({}, 2) == 2)
check("decision entry_layers=1 -> fallback", resolve_entry_copies({"entry_layers": 1}, 2) == 2)
check("decision None -> fallback", resolve_entry_copies(None, 2) == 2)
check("decision entry_layers string -> 10", resolve_entry_copies({"entry_layers": "10"}, 2) == 10)


# =====================================
# 3. BasketGuard
# =====================================
print("\n[3] BasketGuard")
from app.trading.basket_guard import BasketGuard, _epoch


class FakeController:
    def __init__(self):
        self.closed = []

    def close(self, p, caller=None):
        self.closed.append((p.ticket, caller))
        return {"success": True}


def P(ticket, typ, profit, t, comment=None):
    return SimpleNamespace(
        ticket=ticket, type=typ, profit=profit, time=t,
        comment=comment or f"DLineBot #{ticket}",
    )


SELL, BUY = 1, 0
now = time.time()

# A. 10 layer floating -10.5 -> cut semua
g, c = BasketGuard(), FakeController()
pos = [P(i, SELL, -1.05, now - (10 - i)) for i in range(10)]
res = g.process(pos, symbol="XAUUSDc", controller=c)
check("A: cut -10.5 <= -10 -> 10 close", len(res) == 10 and len(c.closed) == 10, str(len(res)))
check("A: caller BASKET_CUT", all(x[1] == "BASKET_CUT" for x in c.closed), str(c.closed[:2]))

# B. floating -5 -> tidak dipotong
g, c = BasketGuard(), FakeController()
pos = [P(i, SELL, -0.5, now - (10 - i)) for i in range(10)]
res = g.process(pos, symbol="XAUUSDc", controller=c)
check("B: floating -5 > -10 -> 0 close", len(res) == 0 and not c.closed, str(len(res)))

# C. proporsional: 7 sudah TP -> sisa 3 cut di -3
g, c = BasketGuard(), FakeController()
t0 = now - 300
pos_full = [P(i, SELL, 0.0, t0 + i * 0.5) for i in range(10)]
r1 = g.process(pos_full, symbol="XAUUSDc", controller=c)
check("C1: basket baru 10 sehat -> 0 close", len(r1) == 0)
pos3 = [P(i, SELL, -0.9, t0 + i * 0.5) for i in range(3)]
r2 = g.process(pos3, symbol="XAUUSDc", controller=c)
check("C2: sisa 3, -2.7 > cut-efektif -3 -> 0 close", len(r2) == 0, str(len(r2)))
pos3b = [P(i, SELL, -1.05, t0 + i * 0.5) for i in range(3)]
r3 = g.process(pos3b, symbol="XAUUSDc", controller=c)
check("C3: sisa 3, -3.15 <= cut-efektif -3 -> 3 close", len(r3) == 3, str(len(r3)))

# D. fallback dual (2 layer) tidak kena basket guard
g, c = BasketGuard(), FakeController()
pos = [P(i, SELL, -7.5, now - 10 + i) for i in range(2)]
res = g.process(pos, symbol="XAUUSDc", controller=c)
check("D: batch 2 layer diabaikan (tetap SL per-layer)", len(res) == 0, str(len(res)))

# E. timeout 16 menit (pakai datetime untuk uji konversi _epoch)
g, c = BasketGuard(), FakeController()
te = dt.datetime.now() - dt.timedelta(seconds=960)
pos = [P(i, BUY, -0.1, te) for i in range(10)]
res = g.process(pos, symbol="XAUUSDc", controller=c)
check("E: umur 16 mnt -> 10 close BASKET_TIME",
      len(res) == 10 and all(x[1] == "BASKET_TIME" for x in c.closed), str(len(res)))

# F. posisi bot lain (Dark Venus) tidak disentuh
g, c = BasketGuard(), FakeController()
pos = [P(i, SELL, -20.0, now - 5, comment="Dark Venus 123") for i in range(10)]
res = g.process(pos, symbol="XAUUSDc", controller=c)
check("F: komentar non-DLineBot diabaikan", len(res) == 0, str(len(res)))

# G. campur arah tidak digabung (3+3 = kalau salah gabung jadi 6 = premium)
g, c = BasketGuard(), FakeController()
pos = [P(i, SELL, -3.0, now - 5) for i in range(3)] + \
      [P(100 + i, BUY, -3.0, now - 4) for i in range(3)]
res = g.process(pos, symbol="XAUUSDc", controller=c)
check("G: arah beda tidak membentuk batch premium", len(res) == 0, str(len(res)))

try:
    import os
    os.remove("runtime/basket_status.json")
except Exception:
    pass


# =====================================
print("\n" + "=" * 40)
print(f"PASS: {len(PASS)}   FAIL: {len(FAIL)}")
if FAIL:
    print("Gagal:")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("SEMUA LULUS")
