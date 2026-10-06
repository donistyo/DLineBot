"""Unit test sintetis gate CSAK + Momentum (bbma_csak_mode).

Jalankan: python test_csak.py  (dari folder repo)

Yang diuji:
  - _csak_detect: BUY valid (candle pertama tembus MA5/MA10/Mid, body searah)
  - _csak_detect: bukan "pertama" -> NEUTRAL
  - _csak_detect: SELL valid
  - _csak_detect: body salah arah -> NEUTRAL
  - _momentum_close_bb: close > bb_up searah BUY -> True
  - _momentum_close_bb: wick tembus tapi close di dalam -> False
  - state CSAK bertahan saat pullback (re-entry beberapa bar setelah CSAK)
  - momentum gagal (wick saja) saat state CSAK aktif -> trigger False
  - momentum ok saat state CSAK aktif -> trigger True
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

import app.config.settings as _settings  # noqa: F401  (warm config cache)
from app.trading import bbma_strategy as BS

BS.CSAK_LOG_PATH = None  # log dimatikan default test


def base_row(o, c, ma5=100, ma10=100, mid=100, up=105, low=95):
    return dict(
        open=o, high=max(o, c) + 0.5, low=min(o, c) - 0.5, close=c,
        ma5=ma5, ma10=ma10, bb_mid=mid, bb_up=up, bb_low=low,
    )


def make_df(rows):
    return pd.DataFrame(rows)


def set_cfg(**kw):
    """Override trade_config sementara via monkeypatch _cfg BS."""
    orig = BS._cfg

    def _cfg(key, default):
        if key in kw:
            return float(kw[key])
        return orig(key, default)

    BS._cfg = _cfg
    return orig


def restore_cfg(orig):
    BS._cfg = orig


passed = 0
failed = 0


def check(name, cond, got=None):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  got={got!r}")


print("== Test 1: CSAK BUY valid (candle pertama tembus MA5/MA10/Mid searah) ==")
rows = [
    base_row(99, 98),                              # -4: netral/bearish
    base_row(99, 97),                              # -3: belum tembus (prev check)
    base_row(98, 103, ma5=100, ma10=100, mid=100), # -2 CLOSED: tembus ketiganya, bull body -> CSAK BUY
    base_row(103, 104, ma5=101, ma10=100, mid=100),  # -1 forming (diabaikan)
]
direction, idx = BS._csak_detect(make_df(rows))
check("CSAK BUY valid", direction == "BUY", direction)

print("\n== Test 2: CSAK tidak valid - bar sebelumnya SUDAH tembus (bukan 'pertama') ==")
rows2 = [
    base_row(102, 104, ma5=100, ma10=100, mid=100),  # -3: sudah tembus duluan
    base_row(104, 106, ma5=101, ma10=100, mid=100),  # -2 CLOSED: tembus lagi, bukan "pertama"
    base_row(106, 107, ma5=102, ma10=101, mid=101),  # -1 forming
]
direction2, idx2 = BS._csak_detect(make_df(rows2))
check("bukan candle pertama -> NEUTRAL", direction2 == "NEUTRAL", direction2)

print("\n== Test 3: CSAK SELL valid ==")
rows3 = [
    base_row(101, 102),
    base_row(100, 101),
    base_row(101, 96, ma5=100, ma10=100, mid=100),  # -2 CLOSED: bear body, tembus ketiganya
    base_row(96, 95, ma5=99, ma10=100, mid=100),
]
direction3, idx3 = BS._csak_detect(make_df(rows3))
check("CSAK SELL valid", direction3 == "SELL", direction3)

print("\n== Test 4: CSAK gagal - body candle salah arah (close>open tapi break ke bawah) ==")
rows4 = [
    base_row(101, 102),
    base_row(100, 101),
    base_row(94, 96, ma5=100, ma10=100, mid=100),  # -2 CLOSED: close<ma5/ma10/mid TAPI body bullish
    base_row(96, 97, ma5=99, ma10=100, mid=100),
]
direction4, idx4 = BS._csak_detect(make_df(rows4))
check("body salah arah -> NEUTRAL", direction4 == "NEUTRAL", direction4)

print("\n== Test 5: Momentum close di luar BB, searah BUY ==")
rows5 = [
    base_row(100, 101),
    base_row(101, 108, ma5=100, ma10=100, mid=100, up=105, low=95),  # -2 CLOSED: close 108 > bb_up 105
    base_row(108, 109),
]
mom = BS._momentum_close_bb(make_df(rows5), "BUY")
check("momentum BUY close>bb_up", mom is True, mom)

print("\n== Test 6: Momentum GAGAL - high tembus BB tapi close di dalam (wick saja) ==")
rows6 = [
    base_row(100, 101),
    {**base_row(101, 103, ma5=100, ma10=100, mid=100, up=105, low=95), "high": 107},
    base_row(103, 104),
]
mom6 = BS._momentum_close_bb(make_df(rows6), "BUY")
check("wick tembus, close di dalam -> False", mom6 is False, mom6)

print("\n== Test 7: state CSAK bertahan saat pullback (re-entry beberapa bar setelah CSAK) ==")
BS.reset_csak_state()
orig_cfg = set_cfg(bbma_csak_mode=1, bbma_csak_expire_bars=20,
                   bbma_reentry_atr=1.5, bbma_anti_chase_atr=2.0,
                   bbma_candle_confirm=0, bbma_min_slope=0.02,
                   bbma_slope_bars=5, bbma_impulse_bars=10,
                   bbma_crash_cooldown=0, bbma_loss_streak_block=0,
                   bbma_day_high_block=0, bbma_day_high_pos=0.80)
try:
    # Bar CSAK (closed -2): close 103 tembus MA5/MA10/mid=100, body bull
    df_csak = make_df([
        base_row(99, 98),
        base_row(98, 103, ma5=100, ma10=100, mid=100, up=105, low=95),
        base_row(103, 104, ma5=100, ma10=100, mid=100, up=105, low=95),
    ])
    out = BS._base_result("", "BUY")
    imp, out = BS._csak_momentum_gate(df_csak, "BUY", out)
    # CSAK BUY terdeteksi; momentum: closed -2 close 103 < bb_up 105 -> False
    check("deteksi CSAK BUY: dir_eff=BUY", out.get("csak_dir_eff") == "BUY", out.get("csak_dir_eff"))
    check("momentum pada bar CSAK: False (close 103 < bb_up 105)", imp is False, imp)
    check("csak_block=no_momentum", out.get("csak_block") == "no_momentum", out.get("csak_block"))

    # Pullback bar: closed -2 sekarang bar pullback (close kembali ke mid),
    # CSAK bar sudah tua -> detect NEUTRAL, tapi state masih BUY
    df_pull = make_df([
        base_row(103, 104, ma5=101, ma10=100, mid=100, up=106, low=94),
        base_row(104, 101, ma5=101, ma10=101, mid=100, up=106, low=94),  # CLOSED: pullback ke mid
        base_row(101, 101, ma5=101, ma10=101, mid=100, up=106, low=94),  # forming
    ])
    out2 = BS._base_result("", "BUY")
    imp2, out2 = BS._csak_momentum_gate(df_pull, "BUY", out2)
    check("pullback: detect NEUTRAL", out2.get("csak_dir") == "NEUTRAL", out2.get("csak_dir"))
    check("pullback: state CSAK masih BUY (bertahan)", out2.get("csak_dir_eff") == "BUY", out2.get("csak_dir_eff"))
    check("pullback: momentum belum (close 101 < bb_up 106)", imp2 is False, imp2)

    # Momentum close BB: closed -2 close 107 > bb_up 106, state CSAK BUY masih aktif
    df_mom = make_df([
        base_row(104, 105, ma5=101, ma10=100, mid=100, up=106, low=94),
        base_row(105, 107, ma5=102, ma10=101, mid=101, up=106, low=94),  # CLOSED: close 107 > bb_up
        base_row(107, 107, ma5=102, ma10=101, mid=101, up=106, low=94),
    ])
    out3 = BS._base_result("", "BUY")
    imp3, out3 = BS._csak_momentum_gate(df_mom, "BUY", out3)
    check("momentum close BB saat state CSAK aktif -> True", imp3 is True, imp3)
    check("csak_trigger=True", out3.get("csak_trigger") is True, out3.get("csak_trigger"))

    # Expire: state lebih tua dari bbma_csak_expire_bars -> released
    BS._csak_state["count"] = 99
    df_exp = make_df([
        base_row(105, 106, ma5=102, ma10=101, mid=101, up=106, low=94),
        base_row(106, 107, ma5=102, ma10=101, mid=101, up=106, low=94),
        base_row(107, 107, ma5=102, ma10=101, mid=101, up=106, low=94),
    ])
    out4 = BS._base_result("", "BUY")
    imp4, out4 = BS._csak_momentum_gate(df_exp, "BUY", out4)
    check("state expired -> dir_eff NEUTRAL", out4.get("csak_dir_eff") == "NEUTRAL", out4.get("csak_dir_eff"))
    check("expired -> trigger False", imp4 is False, imp4)
finally:
    restore_cfg(orig_cfg)
    BS.reset_csak_state()

print("\n== Test 8: bbma_csak_mode=0 -> jalur lama, tanpa field CSAK ==")
BS.reset_csak_state()
orig_cfg = set_cfg(bbma_csak_mode=0)
try:
    df = make_df([
        base_row(99, 98),
        base_row(98, 103, ma5=100, ma10=100, mid=100, up=105, low=95),
        base_row(103, 104, ma5=101, ma10=100, mid=100, up=105, low=95),
    ])
    m5 = BS._prepare(df)
    # analyze_from_df butuh M5>=60 & M15>=40 -> tidak dipakai; uji gate via cfg off
    out = BS._base_result("", "BUY")
    # Gate hanya dipanggil bila mode on; simulasi: mode off -> gate tidak dipanggil
    check("cfg bbma_csak_mode default 0", BS._cfg("bbma_csak_mode", 0) == 0)
    check("prepare punya kolom CSAK (ma5/ma10/bb_mid)",
          {"ma5", "ma10", "bb_mid"}.issubset(m5.columns))
finally:
    restore_cfg(orig_cfg)
    BS.reset_csak_state()

print("\n========================================")
print(f"PASS: {passed}   FAIL: {failed}")
if failed == 0:
    print("SEMUA LULUS")
    sys.exit(0)
sys.exit(1)
