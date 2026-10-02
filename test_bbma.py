"""Unit test sintetis strategi BBMA (analyze_from_df).

Jalankan: python test_bbma.py  (dari folder mana pun)
"""
import math
import sys

sys.path.insert(0, r"D:\Project\Wedd\DLineBot")

import pandas as pd

from app.trading.bbma_strategy import analyze_from_df

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


# --- 1. Uptrend M5+M15 + pullback ke mid -> BUY trigger ---
r = analyze_from_df(
    make_df(uptrend(pullback_last=4)),
    make_df(uptrend(n=80, amp=0.5)),
)
check("uptrend+pullback -> BUY trigger", r["direction"] == "BUY" and r["trigger"] is True, str(r))
check("slope_strength positif & tercatat", r["slope_strength"] > 0, str(r["slope_strength"]))
check("dist_mid_atr tercatat <= 1.5", 0 < r["dist_mid_atr"] <= 1.5, str(r["dist_mid_atr"]))
check("m5 & m15 searah", r["m5_trend"] == r["m15_trend"] == "BUY", str(r))

# --- 2. Uptrend tanpa pullback -> anti-chase (harga jauh dari mid) ---
r = analyze_from_df(make_df(uptrend()), make_df(uptrend(n=80, amp=0.5)))
check("uptrend tanpa pullback -> anti-chase", r["direction"] == "BUY" and r["trigger"] is False, str(r))
check("anti-chase dist > 2 ATR", r["dist_mid_atr"] > 2.0, str(r["dist_mid_atr"]))
check("alasan mengandung anti-chase", "anti-chase" in r["reason"], r["reason"])

# --- 3. M5 up, M15 down -> NEUTRAL (wajib searah) ---
r = analyze_from_df(
    make_df(uptrend(pullback_last=4)),
    make_df(downtrend()),
)
check("M15 lawan -> NEUTRAL", r["direction"] == "NEUTRAL" and r["trigger"] is False, str(r))
check("alasan wajib searah", "wajib searah" in r["reason"], r["reason"])
check("trend tercatat M5 BUY / M15 SELL", r["m5_trend"] == "BUY" and r["m15_trend"] == "SELL", str(r))

# --- 4. Sideways -> NEUTRAL ---
flat = make_df([4000 + 0.3 * math.sin(i) for i in range(100)])
r = analyze_from_df(flat, flat)
check("flat -> trend lemah NEUTRAL", r["direction"] == "NEUTRAL" and r["trigger"] is False, str(r))

# --- 5. Data tidak cukup ---
r = analyze_from_df(pd.DataFrame(), None)
check("data kurang -> NEUTRAL + alasan", r["direction"] == "NEUTRAL" and "tidak cukup" in r["reason"], str(r))

# --- 6. Downtrend M5+M15 + pullback ke mid -> SELL trigger ---
r = analyze_from_df(
    make_df(downtrend(pullback_last=6)),
    make_df(downtrend(n=80, amp=0.5)),
)
check("downtrend+pullback -> SELL trigger", r["direction"] == "SELL" and r["trigger"] is True, str(r))
check("slope_strength negatif (SELL)", r["slope_strength"] < 0, str(r["slope_strength"]))

# --- 7. M15 datar -> NEUTRAL ---
m15_flat = make_df([4000 + 0.3 * math.sin(i) for i in range(80)])
r = analyze_from_df(make_df(uptrend(pullback_last=4)), m15_flat)
check("M15 datar -> NEUTRAL", r["direction"] == "NEUTRAL" and r["trigger"] is False, str(r))

print(f"\n{PASSED}/{PASSED + FAILED} passed")
sys.exit(1 if FAILED else 0)
