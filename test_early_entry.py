"""Unit test Mode A - Early Entry (regime_logic + decision_engine).

Jalankan: python test_early_entry.py  (dari folder repo)

Yang diuji:
  multi_tf_decision (regime_logic):
  - normal: M5 TREND + M15 TREND searah -> "normal"
  - early: M5 TREND adx>=25 + M15 WEAK searah -> "early"
  - early: M5 WEAK adx 26 (>=25, EMA searah) + M15 WEAK searah -> "early"
  - M5 adx 20 (<25) + M15 WEAK -> block
  - M15 SIDEWAYS + M5 TREND, flag off -> block
  - M15 SIDEWAYS + M5 TREND adx>=25, flag on -> "early_sideways"
  - M15 SIDEWAYS + M5 WEAK, flag on -> block (M5 harus TREND/kuat)
  - M15 melawan arah -> block
  - M5 melawan arah -> block

  decision_engine (scalp path):
  - _early_entry -> exhaustion threshold pakai early_exhaustion_atr (4.5)
  - _early_sideways -> M1 momentum harus searah eksplisit (reject NEUTRAL)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.trading.regime_logic import Regime, classify_regime, multi_tf_decision

PASS = 0
FAIL = 0


def check(name, cond, got=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  got={got!r}")


print("== Test 1: normal M5 TREND + M15 TREND searah ==")
allow, score, reason, mode = multi_tf_decision(
    Regime("TREND", "UP", 35), Regime("TREND", "UP", 32), "UP"
)
check("allow=True mode=normal", allow and mode == "normal", (allow, mode))

print("\n== Test 2: early M5 TREND adx>=25 + M15 WEAK searah ==")
allow, score, reason, mode = multi_tf_decision(
    Regime("TREND", "UP", 31), Regime("WEAK", "UP", 20), "UP"
)
check("allow=True mode=early", allow and mode == "early", (allow, mode))

print("\n== Test 3: early M5 WEAK adx 26 (>=25, EMA searah) + M15 WEAK searah ==")
allow, score, reason, mode = multi_tf_decision(
    Regime("WEAK", "UP", 26), Regime("WEAK", "UP", 18), "UP"
)
check("allow=True mode=early (M5 WEAK adx 26)", allow and mode == "early", (allow, mode))

print("\n== Test 4: M5 adx 20 (<25) + M15 WEAK -> block ==")
allow, score, reason, mode = multi_tf_decision(
    Regime("WEAK", "UP", 20), Regime("WEAK", "UP", 18), "UP"
)
check("allow=False mode=block", (not allow) and mode == "block", (allow, mode))

print("\n== Test 5: M15 SIDEWAYS + M5 TREND, flag off -> block ==")
allow, score, reason, mode = multi_tf_decision(
    Regime("TREND", "UP", 35), Regime("SIDEWAYS", None, 12), "UP"
)
check("allow=False mode=block (flag off)", (not allow) and mode == "block", (allow, mode))

print("\n== Test 6: M15 SIDEWAYS + M5 TREND adx>=25, flag on -> early_sideways ==")
allow, score, reason, mode = multi_tf_decision(
    Regime("TREND", "UP", 33), Regime("SIDEWAYS", None, 14), "UP",
    early_sideways=True
)
check("allow=True mode=early_sideways", allow and mode == "early_sideways", (allow, mode))

print("\n== Test 7: M15 SIDEWAYS + M5 WEAK, flag on -> block (M5 harus TREND) ==")
allow, score, reason, mode = multi_tf_decision(
    Regime("WEAK", "UP", 26), Regime("SIDEWAYS", None, 14), "UP",
    early_sideways=True
)
check("allow=False mode=block (M5 WEAK)", (not allow) and mode == "block", (allow, mode))

print("\n== Test 8: M15 melawan arah -> block ==")
allow, score, reason, mode = multi_tf_decision(
    Regime("TREND", "UP", 35), Regime("TREND", "DOWN", 32), "UP"
)
check("allow=False (M15 melawan)", not allow, allow)

print("\n== Test 9: M5 melawan arah -> block ==")
allow, score, reason, mode = multi_tf_decision(
    Regime("TREND", "DOWN", 35), Regime("TREND", "UP", 32), "UP"
)
check("allow=False (M5 melawan)", not allow, allow)

print("\n== Test 10: classify_regime boundary adx 25-29 -> WEAK (bukan TREND) ==")
r = classify_regime(close=100.5, ema20=100.0, ema50=99.0, adx=26)
check("adx=26 EMA up -> WEAK trend UP", r.mode == "WEAK" and r.trend == "UP", (r.mode, r.trend))
r = classify_regime(close=100.5, ema20=100.0, ema50=99.0, adx=31)
check("adx=31 EMA up -> TREND trend UP", r.mode == "TREND" and r.trend == "UP", (r.mode, r.trend))

print("\n== Test 11: decision_engine - exhaustion threshold early (4.5) ==")
import app.config.settings as _settings
_settings.get_trade_config("fast_tp_usd")  # warm cache
_settings._TRADE_CONFIG["entry_strategy"] = "scalp"
_settings._TRADE_CONFIG["momentum_entry"] = 0  # matikan momentum mode utk uji threshold early murni
from app.trading.decision_engine import DecisionEngine

de = DecisionEngine(min_scalp_score=55)

def make_scalp(close=4130.0, atr=2.0, direction="SELL", ema50=None, **extra):
    if ema50 is None:
        ema50 = close  # dist 0 -> tidak kena exhaustion utk unit threshold
    sc = {
        "scalp_score": {"score": 75.0, "direction": direction, "grade": "A", "details": {}},
        "momentum": {"direction": direction, "trend_override": None,
                     "last_body": direction, "bull_bodies": 1, "bear_bodies": 1,
                     "tests60": 8, "rng_pos_m1": 0.4, "chase3_m1": 0.1},
        "liquidity": {"body": 1.0, "upper_wick": 0.3, "lower_wick": 0.3},
        "close": close, "range_high": close + 30, "range_low": close - 30,
        "ema20": close, "ema50": ema50, "atr": atr,
        "indicators": {"RSI": 50},
    }
    sc.update(extra)
    return sc

REGIME_DOWN = {"trend": "DOWN", "mode": "TREND", "adx": 35}

# dist 3.5xATR: < early 4.5 (lolos) tapi > normal 3.0 (akan reject tanpa flag)
_close = 4130.0
_atr = 2.0
_ema50 = _close - 3.5 * _atr  # dist = 3.5 ATR

r = de.decide(None, make_scalp(close=_close, atr=_atr, ema50=_ema50), REGIME_DOWN)
check("tanpa _early_entry: dist 3.5 ATR -> REJECT exhaustion",
      r.get("action") == "NO_TRADE" and "extended" in str(r.get("reason", "")), str(r.get("reason"))[:120])

r = de.decide(None, make_scalp(close=_close, atr=_atr, ema50=_ema50, _early_entry=True), REGIME_DOWN)
check("dgn _early_entry: dist 3.5 ATR < 4.5 -> tidak kena exhaustion",
      r.get("action") != "NO_TRADE" or "Exhaustion" not in str(r.get("reason", "")), str(r.get("reason"))[:120])

print("\n== Test 12: decision_engine - M1 momentum early_sideways (harus searah eksplisit) ==")
# M1 momentum NEUTRAL (direction None) + _early_sideways -> reject
r = de.decide(None, make_scalp(direction="SELL", _early_sideways=True,
                               m1_momentum={"direction": None}), REGIME_DOWN)
check("early_sideways + M1 None -> REJECT",
      r.get("action") == "NO_TRADE" and "M1" in str(r.get("reason", "")), str(r.get("reason"))[:120])

# M1 momentum SELL (searah) + _early_sideways -> lolos M1 gate
r = de.decide(None, make_scalp(direction="SELL", _early_sideways=True,
                               m1_momentum={"direction": "SELL"}), REGIME_DOWN)
check("early_sideways + M1 SELL searah -> lolos M1",
      r.get("action") != "NO_TRADE" or "M1" not in str(r.get("reason", "")), str(r.get("reason"))[:120])

# M1 momentum BUY (melawan) tanpa flag -> reject juga (gate lama)
r = de.decide(None, make_scalp(direction="SELL",
                               m1_momentum={"direction": "BUY"}), REGIME_DOWN)
check("tanpa flag + M1 melawan -> REJECT (gate lama)",
      r.get("action") == "NO_TRADE" and "M1" in str(r.get("reason", "")), str(r.get("reason"))[:120])

print("\n========================================")
print(f"PASS: {PASS}   FAIL: {FAIL}")
if FAIL == 0:
    print("SEMUA LULUS")
    sys.exit(0)
sys.exit(1)
