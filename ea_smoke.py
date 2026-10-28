"""Uji jalur EA tanpa mengubah apa pun: kirim MODIFY dengan SL/TP yang sama ke posisi bot.

Jalankan SETELAH DLineExecutor terpasang di chart. Hasil yang benar: retcode 10025
(No changes) atau 10009, dalam sekitar 1 detik. None = EA tidak menjawab.
"""
import time

import MetaTrader5 as mt5
from app.mt5 import ea_bridge

mt5.initialize()
pos = [p for p in (mt5.positions_get() or []) if p.magic in (10001, 10002, 10003)]
if not pos:
    raise SystemExit("Tidak ada posisi milik bot untuk diuji.")
p = pos[0]
t0 = time.time()
r = ea_bridge.execute({"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": p.symbol,
                       "sl": p.sl, "tp": p.tp})
print(f"ticket={p.ticket} sl={p.sl} tp={p.tp}")
print(f"balasan dalam {time.time() - t0:.2f}s:", r)
