"""Unit test zone strategy + routing decision ZONE.

Jalankan: python test_zone.py  (dari folder repo)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from app.trading import zone_strategy as ZS
from app.trading.decision_engine import DecisionEngine

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {detail}")


def make_df(price=3320.0, last_open=3300.0, last_close=3302.0,
            last_high=3304.0, last_low=3299.0, rsi=40.0):
    n = 60
    rows = []
    for i in range(n):
        rows.append({
            "open": price, "high": price + 5.0, "low": price - 5.0,
            "close": price, "RSI": 50.0, "ATR": 5.0,
        })
    rows[46] = {"open": 3308.0, "high": 3312.0, "low": 3300.0,
                "close": 3305.0, "RSI": 50.0, "ATR": 5.0}
    rows[30] = {"open": 3402.0, "high": 3410.0, "low": 3400.0,
                "close": 3405.0, "RSI": 50.0, "ATR": 5.0}
    rows[-1] = {"open": last_open, "high": last_high, "low": last_low,
                "close": last_close, "RSI": rsi, "ATR": 5.0}
    return pd.DataFrame(rows)


print("=== Zone analyze: BUY di support ===")
buy_df = make_df()
z_buy = ZS.analyze_from_dfs(buy_df, buy_df)
check("BUY terdeteksi", z_buy["direction"] == "BUY" and z_buy["trigger"], z_buy)
check("range_mid terisi", z_buy.get("range_mid") is not None, z_buy.get("range_mid"))
check("close tercatat", z_buy.get("close") == 3302.0, z_buy.get("close"))
check("zone support <= close", (z_buy.get("zone") or {}).get("lo", 9999) < 3302.0,
      z_buy.get("zone"))

print("\n=== Zone analyze: SELL di resistance ===")
sell_df = make_df(price=3320.0, last_open=3410.0, last_close=3408.0,
                  last_high=3412.0, last_low=3406.0, rsi=60.0)
z_sell = ZS.analyze_from_dfs(sell_df, sell_df)
check("SELL terdeteksi", z_sell["direction"] == "SELL" and z_sell["trigger"], z_sell)
check("mid-range di bawah entry (SELL)",
      (z_sell.get("range_mid") or 9999) < z_sell.get("close", 0), z_sell.get("range_mid"))

print("\n=== Decision zone: routing + TP mid-range ===")
de = DecisionEngine(min_scalp_score=60)
d_buy = de.decide(None, {"zone": z_buy}, None, strategy="zone")
check("decision BUY", d_buy["action"] == "BUY", d_buy.get("reason"))
check("entry_strategy zone", d_buy.get("entry_strategy") == "zone")
from app.trading.decision_engine import _min_entry_layers as _mel
check("entry_layers sesuai config", d_buy.get("entry_layers") == _mel())
check("zone_lo diteruskan", d_buy.get("zone_lo") is not None)
check("range_mid diteruskan", d_buy.get("range_mid") == z_buy.get("range_mid"))

d_sell = de.decide(None, {"zone": z_sell}, None, strategy="zone")
check("decision SELL", d_sell["action"] == "SELL", d_sell.get("reason"))

z_close = dict(z_buy)
z_close["range_mid"] = 3302.5
d_close = de.decide(None, {"zone": z_close}, None, strategy="zone")
check("TP mid-range terlalu dekat -> NO_TRADE",
      d_close["action"] == "NO_TRADE" and "mid-range" in d_close.get("reason", "").lower(),
      d_close.get("reason"))
check("alasan TP tercatat di checks",
      any("TP mid-range" in c.get("label", "") and not c.get("ok")
          for c in d_close.get("checks", [])))

print("\n=== Decision scalp tetap menandai entry_strategy ===")
d_scalp = de.decide(None, {"scalp_score": {"score": 10, "direction": "BUY", "grade": "D"}},
                    {"trend": "UP", "mode": "TREND", "adx": 30})
check("scalp reject punya entry_strategy=scalp",
      d_scalp.get("entry_strategy") == "scalp", d_scalp)

print("\n========================================")
print(f"PASS: {passed}   FAIL: {failed}")
if failed == 0:
    print("SEMUA LULUS")
    sys.exit(0)
sys.exit(1)
