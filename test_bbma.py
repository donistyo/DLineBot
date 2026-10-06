"""Unit test sintetis strategi BBMA (analyze_from_df) + gate konfirmasi c4.

Jalankan: python test_bbma.py  (dari folder mana pun)

Gate c4 yang diuji:
  - c1: closed candle arah tren -> trigger instan
  - c3: forming berbalik -> butuh stabil >= bbma_confirm_min_seconds
  - flip-flop: pass lalu gagal -> pass_since di-reset (tak ada trigger)
  - blocked: radius OK tapi belum konfirmasi -> hold fields + state tertahan
  - released: sinyal hilang (anti-chase / radius lewat) saat menahan -> log
  - flag bbma_candle_confirm=0 -> perilaku lama (tanpa gate)
  - day-high: BUY posd > bbma_day_high_pos (0.80) -> blokir "puncak harian",
    SELL tidak kena (BUY-only), flag bbma_day_high_block=0 -> lolos
  - crash cooldown: bar crash (range > 3.0x ATR14 sebelumnya) dalam 3 bar
    tertutup terakhir -> blokir BUY & SELL, di luar jendela lolos,
    flag bbma_crash_cooldown=0 -> lolos
  - loss-streak cooldown: >= 2 ATR_EMERGENCY close searah beruntun (gap <= 60m)
    -> blokir arah itu 45m; unit _streak_until + integrasi analyze_from_df,
    flag bbma_loss_streak_block=0 -> lolos
"""
import json
import math
import os
import sys
import tempfile
import time

sys.path.insert(0, r"D:\Project\Wedd\DLineBot")

import pandas as pd

import app.config.settings as _settings

_settings.get_trade_config("bbma_min_slope")  # warm config cache
_settings._TRADE_CONFIG["bbma_candle_confirm"] = 1
_settings._TRADE_CONFIG["bbma_confirm_min_seconds"] = 0
_settings._TRADE_CONFIG["bbma_day_high_block"] = 1
_settings._TRADE_CONFIG["bbma_day_high_pos"] = 1.1  # default test: aturan posd tak kena
_settings._TRADE_CONFIG["bbma_crash_cooldown"] = 1
_settings._TRADE_CONFIG["bbma_crash_bars"] = 3
_settings._TRADE_CONFIG["bbma_crash_range_mult"] = 3.0
_settings._TRADE_CONFIG["bbma_loss_streak_block"] = 0  # default test: off (fetch MT5 deterministik)

from app.trading import bbma_strategy as BS
from app.trading.bbma_strategy import analyze_from_df

BS.GATE_LOG_PATH = None  # log dimatikan default test; skenario log nyalakan sementara

PASSED = 0
FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"PASS: {name}")
    else:
        FAILED += 1
        print(f"FAIL: {name} {detail}")


def fresh():
    BS.reset_gate_state()
    _settings._TRADE_CONFIG["bbma_candle_confirm"] = 1
    _settings._TRADE_CONFIG["bbma_confirm_min_seconds"] = 0
    _settings._TRADE_CONFIG["bbma_day_high_block"] = 1
    _settings._TRADE_CONFIG["bbma_day_high_pos"] = 1.1
    _settings._TRADE_CONFIG["bbma_crash_cooldown"] = 1
    _settings._TRADE_CONFIG["bbma_crash_bars"] = 3
    _settings._TRADE_CONFIG["bbma_crash_range_mult"] = 3.0
    _settings._TRADE_CONFIG["bbma_loss_streak_block"] = 0


def make_df(closes, spread=1.2):
    n = len(closes)
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) + spread for o, c in zip(opens, closes)]
    lows = [min(o, c) - spread for o, c in zip(opens, closes)]
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes})


def uptrend(n=100, drift=0.8, amp=0.6, pullback_last=0):
    closes = [4000 + i * drift + amp * math.sin(i) for i in range(n)]
    for k in range(pullback_last):
        closes[-(k + 1)] -= drift * (pullback_last - k)
    return closes


def downtrend(n=100, drift=0.8, amp=0.6, pullback_last=0):
    closes = [4000 - i * drift + amp * math.sin(i) for i in range(n)]
    for k in range(pullback_last):
        closes[-(k + 1)] += drift * (pullback_last - k)
    return closes


def confirm_buy_c3(closes):
    """Closed candle bearish jelas + forming berbalik naik (uji jalur c3)."""
    closes[-2] = closes[-3] - 0.8
    closes[-1] = closes[-2] + 0.35
    return closes


def confirm_buy_c1(closes):
    """Closed candle bullish + forming turun (uji jalur c1 instan)."""
    closes[-2] = closes[-3] + 0.4
    closes[-1] = closes[-2] - 0.9
    return closes


def confirm_sell_c3(closes):
    closes[-2] = closes[-3] + 0.5
    closes[-1] = closes[-2] - 1.0
    return closes


def nobuy_confirm(closes):
    """Closed bearish + forming turun: tak ada konfirmasi BUY."""
    closes[-2] = closes[-3] - 0.8
    closes[-1] = closes[-2] - 0.4
    return closes


def crash_at(df, idx=-4, wick=15.0):
    """Suntik wick crash pada bar idx (range bar jadi ~18 >> 3x ATR ~3.5).

    idx=-4 = bar tertutup terdalam dalam jendela K=3 (window = -4,-3,-2;
    -1 = forming, dikecualikan oleh aturan).
    """
    df = df.copy()
    df.loc[df.index[idx], "low"] = df.loc[df.index[idx], "low"] - wick
    return df


M15UP = make_df(uptrend(n=80, amp=0.5))
M15DN = make_df(downtrend(n=80, amp=0.5))

# --- 1. Uptrend + pullback + konfirmasi c3 -> BUY trigger ---
fresh()
r = analyze_from_df(
    make_df(confirm_buy_c3(uptrend(pullback_last=4))),
    M15UP,
)
check("uptrend+pullback+konfirmasi c3 -> BUY trigger",
      r["direction"] == "BUY" and r["trigger"] is True, str(r))
check("hold fields ikut tercatat", "confirm_hold_s" in r and "confirm_hold_cycles" in r, str(r))
check("reason memuat konfirmasi OK", "konfirmasi OK" in r.get("reason", ""), r.get("reason"))
check("slope_strength positif & tercatat", r["slope_strength"] > 0, str(r["slope_strength"]))
check("dist_mid_atr tercatat <= 1.5", 0 < r["dist_mid_atr"] <= 1.5, str(r["dist_mid_atr"]))
check("m5 & m15 searah", r["m5_trend"] == r["m15_trend"] == "BUY", str(r))

# --- 1b. c1 instan: closed bullish + forming TURUN, T=120 tetap trigger ---
fresh()
_settings._TRADE_CONFIG["bbma_confirm_min_seconds"] = 120
r = analyze_from_df(
    make_df(confirm_buy_c1(uptrend(pullback_last=4))),
    M15UP,
)
check("c1 instan (closed bullish, forming turun) -> trigger walau T=120",
      r["trigger"] is True and "c1" in r.get("confirm_how", ""), str(r))
check("c1 hold cycles >= 1", r.get("confirm_hold_cycles", 0) >= 1, str(r))
_settings._TRADE_CONFIG["bbma_confirm_min_seconds"] = 0

# --- 2. Uptrend tanpa pullback -> anti-chase ---
fresh()
r = analyze_from_df(make_df(uptrend()), M15UP)
check("uptrend tanpa pullback -> anti-chase", r["direction"] == "BUY" and r["trigger"] is False, str(r))
check("anti-chase dist > 2 ATR", r["dist_mid_atr"] > 2.0, str(r["dist_mid_atr"]))
check("alasan mengandung anti-chase", "anti-chase" in r["reason"], r["reason"])

# --- 3. M5 up, M15 down -> wajib searah ---
fresh()
r = analyze_from_df(make_df(confirm_buy_c3(uptrend(pullback_last=4))), M15DN)
check("M15 lawan -> NEUTRAL", r["direction"] == "NEUTRAL" and r["trigger"] is False, str(r))
check("alasan wajib searah", "wajib searah" in r["reason"], r["reason"])

# --- 4. Sideways -> NEUTRAL ---
fresh()
flat = make_df([4000 + 0.3 * math.sin(i) for i in range(100)])
r = analyze_from_df(flat, flat)
check("flat -> trend lemah NEUTRAL", r["direction"] == "NEUTRAL" and r["trigger"] is False, str(r))

# --- 5. Data tidak cukup ---
fresh()
r = analyze_from_df(pd.DataFrame(), None)
check("data kurang -> NEUTRAL + alasan", r["direction"] == "NEUTRAL" and "tidak cukup" in r["reason"], str(r))

# --- 6. Downtrend + pullback + konfirmasi -> SELL trigger ---
fresh()
r = analyze_from_df(
    make_df(confirm_sell_c3(downtrend(pullback_last=6))),
    M15DN,
)
check("downtrend+pullback+konfirmasi -> SELL trigger",
      r["direction"] == "SELL" and r["trigger"] is True, str(r))
check("slope_strength negatif (SELL)", r["slope_strength"] < 0, str(r["slope_strength"]))

# --- 7. M15 datar -> NEUTRAL ---
fresh()
m15_flat = make_df([4000 + 0.3 * math.sin(i) for i in range(80)])
r = analyze_from_df(make_df(confirm_buy_c3(uptrend(pullback_last=4))), m15_flat)
check("M15 datar -> NEUTRAL", r["direction"] == "NEUTRAL" and r["trigger"] is False, str(r))

# --- 8. BLOCKED: radius OK tapi belum konfirmasi ---
fresh()
r = analyze_from_df(make_df(nobuy_confirm(uptrend(pullback_last=4))), M15UP)
check("belum konfirmasi -> blocked (reason konfirmasi candle)",
      r["trigger"] is False and "konfirmasi candle belum ada" in r["reason"], str(r))
check("blocked -> hold fields terisi (cycles >= 1)",
      r.get("confirm_hold_cycles", 0) >= 1 and r.get("confirm_hold_s", -1) >= 0, str(r))
check("blocked -> state tertahan (1 key)", len(BS._gate_state) == 1, str(BS._gate_state))

# --- 9. FLIP-FLOP: pass 1 cycle lalu gagal -> pass_since di-reset ---
fresh()
r = analyze_from_df(make_df(nobuy_confirm(uptrend(pullback_last=4))), M15UP)  # baseline blocked
key = list(BS._gate_state.keys())[0]
_settings._TRADE_CONFIG["bbma_confirm_min_seconds"] = 120
r = analyze_from_df(make_df(confirm_buy_c3(uptrend(pullback_last=4))), M15UP)  # c3 pass
st = BS._gate_state.get(key)
check("flip-flop: c3 pass pertama -> blocked 'belum stabil', pass_since terisi",
      r["trigger"] is False and "belum stabil" in r["reason"] and st and st["pass_since"] is not None,
      str(r) + str(st))
r = analyze_from_df(make_df(nobuy_confirm(uptrend(pullback_last=4))), M15UP)  # c3 gagal
st = BS._gate_state.get(key)
check("flip-flop: c3 gagal -> pass_since di-reset (None), tak trigger",
      r["trigger"] is False and st is not None and st["pass_since"] is None, str(st))
_settings._TRADE_CONFIG["bbma_confirm_min_seconds"] = 120
r = analyze_from_df(make_df(confirm_buy_c3(uptrend(pullback_last=4))), M15UP)  # pass lagi
st = BS._gate_state.get(key)
check("flip-flop: c3 pass ulang -> pass_since BARU (tak lanjut dari awal)",
      r["trigger"] is False and st is not None and st["pass_since"] is not None
      and (time.time() - st["pass_since"]) < 2, str(st))
check("flip-flop: hold cycles akumulasi >= 3", st and st["cycles"] >= 3, str(st))

# --- 10. STABILITY: pass bertahan >= T -> trigger ---
st["pass_since"] = time.time() - 130
r = analyze_from_df(make_df(confirm_buy_c3(uptrend(pullback_last=4))), M15UP)
check("stability: pass 130s >= T120 -> trigger",
      r["trigger"] is True and "stabil" in r.get("confirm_how", ""), str(r))
check("stability: state bersih setelah trigger", len(BS._gate_state) == 0, str(BS._gate_state))
_settings._TRADE_CONFIG["bbma_confirm_min_seconds"] = 0

# --- 11. FLAG OFF: bbma_candle_confirm=0 -> tanpa gate ---
fresh()
_settings._TRADE_CONFIG["bbma_candle_confirm"] = 0
r = analyze_from_df(make_df(nobuy_confirm(uptrend(pullback_last=4))), M15UP)
check("flag off -> trigger tanpa konfirmasi (perilaku lama)",
      r["trigger"] is True and r.get("confirm_hold_s") == 0, str(r))
_settings._TRADE_CONFIG["bbma_candle_confirm"] = 1

# --- 12. RELEASE: radius lewat saat menahan -> log released ---
fresh()
tmp_log = os.path.join(tempfile.gettempdir(), "bbma_gate_test.jsonl")
if os.path.exists(tmp_log):
    os.remove(tmp_log)
BS.GATE_LOG_PATH = tmp_log
r = analyze_from_df(make_df(nobuy_confirm(uptrend(pullback_last=4))), M15UP)  # menahan
check("release setup: state tertahan", len(BS._gate_state) == 1, str(BS._gate_state))
r = analyze_from_df(make_df(uptrend(pullback_last=2)), M15UP)  # radius 1.5-2.0 -> reentry belum
st_before = len(BS._gate_state)
events = []
if os.path.exists(tmp_log):
    with open(tmp_log, encoding="utf-8") as f:
        events = [json.loads(x) for x in f if x.strip()]
rel = [e for e in events if e.get("event") == "released"]
check("radius lewat -> state released (state kosong)", st_before == 0, str(st_before))
check("released event terlog", len(rel) == 1, str(events))
check("released reason = radius/reentry",
      rel and ("reentry" in rel[0]["reason"] or "anti-chase" in rel[0]["reason"]),
      str(rel))
check("released event bawa held_s/kycles",
      rel and rel[0].get("held_s", -1) >= 0 and rel[0].get("held_cycles", -1) >= 1, str(rel))

# --- 13. RELEASE: anti-chase saat menahan -> log released ---
fresh()
r = analyze_from_df(make_df(nobuy_confirm(uptrend(pullback_last=4))), M15UP)
r = analyze_from_df(make_df(uptrend()), M15UP)  # dist > 2 -> anti-chase
events = []
if os.path.exists(tmp_log):
    with open(tmp_log, encoding="utf-8") as f:
        events = [json.loads(x) for x in f if x.strip()]
rel_last = [e for e in events if e.get("event") == "released"][-1:]
check("anti-chase saat menahan -> released", len(BS._gate_state) == 0 and rel_last
      and "anti-chase" in rel_last[0]["reason"], str(rel_last))
BS.GATE_LOG_PATH = None
if os.path.exists(tmp_log):
    os.remove(tmp_log)

# --- 14. DAY-HIGH: BUY di puncak harian -> blocked (posd > 0.80) ---
fresh()
_settings._TRADE_CONFIG["bbma_day_high_pos"] = 0.80
r = analyze_from_df(make_df(confirm_buy_c3(uptrend(pullback_last=4))), M15UP)
check("posd>0.80 -> blocked 'puncak harian'",
      r["trigger"] is False and "puncak harian" in r["reason"], str(r))
check("posd tercatat di day_pos_pct", r.get("day_pos_pct") is not None and r["day_pos_pct"] > 0.80,
      str(r.get("day_pos_pct")))
check("posd block -> state gate kosong (released)", len(BS._gate_state) == 0, str(BS._gate_state))

# --- 15. DAY-HIGH: flag off -> lolos (perilaku lama) ---
fresh()
_settings._TRADE_CONFIG["bbma_day_high_block"] = 0
_settings._TRADE_CONFIG["bbma_day_high_pos"] = 0.80
r = analyze_from_df(make_df(confirm_buy_c3(uptrend(pullback_last=4))), M15UP)
check("flag bbma_day_high_block=0 -> trigger tanpa blokir puncak",
      r["trigger"] is True and "puncak" not in r["reason"], str(r))

# --- 16. DAY-HIGH: BUY-only - SELL tak kena aturan ini ---
fresh()
_settings._TRADE_CONFIG["bbma_day_high_pos"] = 0.80
r = analyze_from_df(make_df(confirm_sell_c3(downtrend(pullback_last=6))), M15DN)
check("SELL di dasar hari TIDAK kena blokir puncak (BUY-only)",
      r["trigger"] is True and "puncak" not in r["reason"], str(r))

# --- 17. CRASH COOLDOWN: bar crash di jendela K=3 -> blokir BUY & SELL ---
fresh()
r = analyze_from_df(crash_at(make_df(confirm_buy_c3(uptrend(pullback_last=4)))), M15UP)
check("crash bar (jendela K=3) -> blokir BUY",
      r["trigger"] is False and "crash" in r["reason"], str(r))
check("crash_ratio tercatat > 3.0", (r.get("crash_ratio") or 0) > 3.0, str(r.get("crash_ratio")))
check("crash block -> state gate kosong (released)", len(BS._gate_state) == 0, str(BS._gate_state))
r = analyze_from_df(crash_at(make_df(confirm_sell_c3(downtrend(pullback_last=6)))), M15DN)
check("crash bar -> blokir SELL (berlaku dua arah)",
      r["trigger"] is False and "crash" in r["reason"], str(r))

# --- 18. CRASH COOLDOWN: bar crash di luar jendela (-5) -> lolos ---
fresh()
r = analyze_from_df(crash_at(make_df(confirm_buy_c3(uptrend(pullback_last=4))), idx=-5), M15UP)
check("crash bar di luar jendela K=3 -> lolos (trigger)",
      r["trigger"] is True and "crash" not in r["reason"], str(r))

# --- 19. CRASH COOLDOWN: flag off -> lolos ---
fresh()
_settings._TRADE_CONFIG["bbma_crash_cooldown"] = 0
r = analyze_from_df(crash_at(make_df(confirm_buy_c3(uptrend(pullback_last=4)))), M15UP)
check("flag bbma_crash_cooldown=0 -> trigger tanpa blokir crash",
      r["trigger"] is True and "crash" not in r["reason"], str(r))

# --- 20. LOSS-STREAK: state murni _streak_until (unit) ---
fresh()
W = 60 * 60       # window 60 menit
B = 45 * 60       # cooldown 45 menit
T0 = 1_700_000_000
u, c = BS._streak_until([(T0, "SELL"), (T0 + 600, "SELL")], "SELL", 2, W, B)
check("2x SELL emergency gap 10m -> block SELL s/d exit+45m",
      u == T0 + 600 + B and c == 2, f"until={u} cnt={c}")
u, _ = BS._streak_until([(T0, "SELL"), (T0 + 600, "SELL")], "BUY", 2, W, B)
check("streak SELL tidak blokir BUY", u == 0, str(u))
u, _ = BS._streak_until([(T0, "SELL"), (T0 + 4200, "SELL")], "SELL", 2, W, B)
check("gap 70m > window 60m -> tidak trigger", u == 0, str(u))
u, _ = BS._streak_until([(T0, "SELL"), (T0 + 600, "BUY"), (T0 + 1200, "SELL")],
                        "SELL", 2, W, B)
check("exit beda arah di tengah -> run reset, tidak trigger", u == 0, str(u))
u, c = BS._streak_until([(T0, "SELL"), (T0 + 900, "SELL"), (T0 + 1800, "SELL")],
                        "SELL", 2, W, B)
check("run 3x beruntun -> block s/d exit ke-3 + 45m, cnt=3",
      u == T0 + 1800 + B and c == 3, f"until={u} cnt={c}")

# --- 21. LOSS-STREAK: _loss_streak_block (expiry + flag off) ---
ex = [(T0, "SELL"), (T0 + 600, "SELL")]
_settings._TRADE_CONFIG["bbma_loss_streak_block"] = 1
blk, until, cnt = BS._loss_streak_block("SELL", exits=ex, now=T0 + 3000)
check("masih dalam cooldown (exit+40m < +45m) -> blocked",
      blk is True and cnt == 2, f"blk={blk} cnt={cnt}")
blk, _, _ = BS._loss_streak_block("SELL", exits=ex, now=T0 + 600 + B + 1)
check("setelah cooldown berakhir -> lolos", blk is False, str(blk))
blk, _, _ = BS._loss_streak_block("BUY", exits=ex, now=T0 + 3000)
check("arah lain tidak kena blokir", blk is False, str(blk))
_settings._TRADE_CONFIG["bbma_loss_streak_block"] = 0
blk, _, _ = BS._loss_streak_block("SELL", exits=ex, now=T0 + 3000)
check("flag bbma_loss_streak_block=0 -> selalu lolos", blk is False, str(blk))

# --- 22. LOSS-STREAK: integrasi analyze_from_df (fetch di-patch) ---
fresh()
_settings._TRADE_CONFIG["bbma_loss_streak_block"] = 1
_orig_fetch = BS._fetch_emergency_exits
BS._fetch_emergency_exits = lambda s: [
    (time.time() - 1200, "SELL"), (time.time() - 600, "SELL")]
r = analyze_from_df(make_df(confirm_sell_c3(downtrend(pullback_last=6))), M15DN)
check("streak 2x SELL -> blokir entry SELL (reason loss-streak)",
      r["trigger"] is False and "loss-streak" in r["reason"], str(r))
check("streak block -> state gate kosong (released)",
      len(BS._gate_state) == 0, str(BS._gate_state))
r = analyze_from_df(make_df(confirm_buy_c3(uptrend(pullback_last=4))), M15UP)
check("streak SELL tidak pengaruhi BUY (tetap trigger)",
      r["trigger"] is True and "loss-streak" not in r["reason"], str(r))
BS._fetch_emergency_exits = _orig_fetch

fresh()
print(f"\n{PASSED}/{PASSED + FAILED} passed")
sys.exit(1 if FAILED else 0)
