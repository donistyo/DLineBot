"""Test CandleStream logika (bucket bar, format pesan) - tanpa MT5 live."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tradingview.candle_stream import (
    TF_SECONDS, apply_tick, next_bar_time, positions_hash, rate_to_bar,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {detail}")


# =====================================
# next_bar_time
# =====================================
print("=== next_bar_time ===")
check("bucket pertama dari tick", next_bar_time(None, 1000, 60) == 960)
check("tick di dalam bar -> bar sama",
      next_bar_time(960, 990, 60) == 960)
check("tick lewat batas -> bar baru",
      next_bar_time(960, 1020, 60) == 1020)
check("gap besar -> lompat ke bucket tepat",
      next_bar_time(960, 960 + 300, 300) == 1260)
check("M5 alignment (kelipatan 300)", next_bar_time(None, 1792504574, 300) == 1792504574 - (1792504574 % 300))

# =====================================
# apply_tick
# =====================================
print("=== apply_tick ===")
bars = []
msgs = apply_tick(bars, 4100.0, 1000, 60)
check("bar pertama dibuat", len(bars) == 1 and bars[0]["open"] == 4100.0)
check("pesan new", msgs[0]["event"] == "new")

# update dalam bar yang sama
msgs = apply_tick(bars, 4105.0, 1010, 60)
check("update high", bars[0]["high"] == 4105.0 and msgs[0]["event"] == "update")
msgs = apply_tick(bars, 4095.0, 1015, 60)
check("update low", bars[0]["low"] == 4095.0)
check("update close", bars[0]["close"] == 4095.0)

# tick tanpa perubahan harga -> tidak ada pesan
msgs = apply_tick(bars, 4095.0, 1020 - 1, 60)
check("tanpa perubahan -> []", msgs == [])

# bar baru
msgs = apply_tick(bars, 4110.0, 1020, 60)
check("bar baru dibuat", len(bars) == 2)
check("bar baru open = tick", bars[1]["open"] == 4110.0 and bars[1]["time"] == 1020)
check("pesan new bar", msgs[0]["event"] == "new")

# format bar (field wajib Lightweight Charts)
b = bars[1]
check("format bar {time,open,high,low,close}",
      set(b.keys()) == {"time", "open", "high", "low", "close"})

# =====================================
# rate_to_bar
# =====================================
print("=== rate_to_bar ===")
r = (1792504500, 4100.5, 4110.0, 4090.0, 4105.25, 100)
bar = rate_to_bar(r)
check("konversi rate MT5", bar == {"time": 1792504500, "open": 4100.5,
                                    "high": 4110.0, "low": 4090.0, "close": 4105.25})

# =====================================
# positions_hash
# =====================================
print("=== positions_hash ===")
p1 = [{"ticket": 1, "type": "BUY", "open_price": 4100, "sl": 0, "tp": 4110, "profit": 0}]
p2 = [{"ticket": 1, "type": "BUY", "open_price": 4100, "sl": 0, "tp": 4110, "profit": 1.5}]
p3 = [{"ticket": 2, "type": "SELL", "open_price": 4100, "sl": 0, "tp": 4110, "profit": 0}]
check("hash sama jika identik", positions_hash(p1) == positions_hash(p1))
check("hash beda jika profit berubah", positions_hash(p1) != positions_hash(p2))
check("hash beda jika ticket berbeda", positions_hash(p1) != positions_hash(p3))
check("hash kosong stabil", positions_hash([]) == positions_hash([]))

# =====================================
# TF map
# =====================================
print("=== TF_SECONDS ===")
check("TF lengkap M1/M5/M15", set(TF_SECONDS.keys()) == {"M1", "M5", "M15"})
check("nilai detik benar", TF_SECONDS["M1"] == 60 and TF_SECONDS["M5"] == 300 and TF_SECONDS["M15"] == 900)

print()
print("=" * 40)
print(f"PASS: {PASS}   FAIL: {FAIL}")
if FAIL == 0:
    print("SEMUA LULUS")
else:
    print("ADA GAGAL")
    sys.exit(1)
