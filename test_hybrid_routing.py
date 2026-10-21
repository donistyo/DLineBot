"""Unit test routing hybrid SCALP/ZONE + exit khusus zone.

Jalankan: python test_hybrid_routing.py  (dari folder repo)
"""
import json
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.trading.hybrid_routing import hybrid_strategy_state

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


print("=== Routing hybrid (hysteresis ADX) ===")
check("mode scalp -> scalp", hybrid_strategy_state("scalp", 10) == "scalp")
check("mode zone -> zone", hybrid_strategy_state("zone", 40) == "zone")
check("mode bbma -> bbma", hybrid_strategy_state("bbma", 30) == "bbma")

check("start ADX 30 -> scalp", hybrid_strategy_state("hybrid", 30) == "scalp")
check("start ADX 10 -> zone", hybrid_strategy_state("hybrid", 10) == "zone")

s = hybrid_strategy_state("hybrid", 30)
check("ADX 30 -> scalp", s == "scalp")
s = hybrid_strategy_state("hybrid", 22, s)
check("ADX 22 (antara) tetap scalp", s == "scalp", s)
s = hybrid_strategy_state("hybrid", 19, s)
check("ADX 19 -> zone", s == "zone", s)
s = hybrid_strategy_state("hybrid", 22, s)
check("ADX 22 (antara) tetap zone", s == "zone", s)
s = hybrid_strategy_state("hybrid", 26, s)
check("ADX 26 -> scalp", s == "scalp", s)

check("batas ADX 20 saat scalp tetap scalp",
      hybrid_strategy_state("hybrid", 20, "scalp") == "scalp")
check("batas ADX 20 saat zone tetap zone",
      hybrid_strategy_state("hybrid", 20, "zone") == "zone")
check("batas ADX 25 saat zone tetap zone",
      hybrid_strategy_state("hybrid", 25, "zone") == "zone")
check("batas ADX 25 saat scalp tetap scalp",
      hybrid_strategy_state("hybrid", 25, "scalp") == "scalp")

print("\n=== Config hybrid aktif ===")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime/trade_config.json")) as f:
    cfg = json.load(f)
check("entry_strategy = hybrid", cfg.get("entry_strategy") == "hybrid", cfg.get("entry_strategy"))
check("zone_regime_adx_max = 20", float(cfg.get("zone_regime_adx_max", 0)) == 20)
check("scalp_resume_adx = 25", float(cfg.get("scalp_resume_adx", 0)) == 25)
check("zone_magic beda dari magic scalp",
      int(cfg.get("zone_magic", 0)) != 10001, cfg.get("zone_magic"))
check("zone_sl_atr > 0", float(cfg.get("zone_sl_atr", 0)) > 0)
check("zone_time_exit_min > 0", float(cfg.get("zone_time_exit_min", 0)) > 0)

print("\n=== Exit khusus zone (ATRProtection) ===")
from app.trading.atr_protection import ATRProtectionManager


class _Ctl:
    def close(self, position, caller=None):
        return {"success": True, "caller": caller}


mgr = object.__new__(ATRProtectionManager)
mgr.zone_time_exit_min = 90.0
mgr.emergency_atr = 2.5
mgr.emergency_max_usd = 4.5
mgr.controller = _Ctl()
mgr.partial_close = False
mgr.loser_min_profit = 0.0
mgr._ever_profit = set()
mgr.recover_red_usd = 1.0
mgr.recover_close_usd = 0.25
mgr._real_red = set()
mgr.max_profit_usd = 0.0
mgr.fast_tp_usd = 1.0
mgr.tp_atr_mult = 0.0
mgr.be_lock_usd = 0.0
mgr.sl_plus_usd = 0.0


def _pos(age_min, profit=0.0):
    return SimpleNamespace(
        ticket=999, symbol="XAUUSDc", type=0, volume=0.01,
        price_open=3302.0, sl=3295.0, tp=3355.0,
        profit=profit, time=time.time() - age_min * 60.0,
        comment="DLineBot",
    )


fresh = mgr.process(_pos(5, profit=1.5), 5.0, 3302.0, is_zone=True)
check("zone profit > fast_tp tetap HOLD (bukan FAST_TP)",
      fresh["status"] == "HOLD" and fresh["action"] == "ZONE", fresh)
old = mgr.process(_pos(91, profit=0.3), 5.0, 3302.0, is_zone=True)
check("zone umur >= 90 menit -> ZONE_TIME_EXIT",
      old["status"] == "CLOSED" and old["action"] == "ZONE_TIME_EXIT", old)
nonzone = mgr.process(_pos(5, profit=1.5), 5.0, 3302.0, is_zone=False)
check("non-zone tetap pakai FAST_TP",
      nonzone["status"] == "CLOSED" and nonzone["action"] == "FAST_TP", nonzone)

print("\n========================================")
print(f"PASS: {passed}   FAIL: {failed}")
if failed == 0:
    print("SEMUA LULUS")
    sys.exit(0)
sys.exit(1)
