"""Uji bridge dengan EA tiruan (thread). Tanpa terminal MT5, tanpa order nyata."""
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import MetaTrader5 as mt5
from app.mt5 import ea_bridge, order_sender, position_controller

tmp = Path(tempfile.mkdtemp())
CFG = {"execution_mode": "ea", "ea_bridge_dir": str(tmp), "ea_ack_timeout_ms": 600}
get = lambda k, d=None: CFG.get(k, d)
stop = False
seen = set()


def fake_ea():
    (tmp / "cmd").mkdir(parents=True, exist_ok=True)
    while not stop:
        for f in (tmp / "cmd").glob("*.req"):
            kv = dict(l.split("=", 1) for l in f.read_text().splitlines())
            f.unlink()
            if kv["id"] in seen:
                continue
            seen.add(kv["id"])
            (tmp / "ack").mkdir(exist_ok=True)
            (tmp / "ack" / f"{kv['id']}.ack").write_text(
                f"retcode=10009\ncomment=ok\norder=777\ndeal=888\nvolume={kv['volume']}\nprice={kv['price']}\n")
        time.sleep(0.02)


order = {"action": mt5.TRADE_ACTION_DEAL, "symbol": "XAUUSDc", "volume": 0.01, "type": mt5.ORDER_TYPE_BUY,
         "price": 2000.5, "sl": 1990.0, "tp": 2005.0, "deviation": 20, "magic": 10001, "comment": "DLineBot"}
modify = {"action": mt5.TRADE_ACTION_SLTP, "position": 777, "symbol": "XAUUSDc", "sl": 1995.0, "tp": 2005.0,
          "volume": 0, "price": 0}
fails = []


def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


class Fake:
    retcode = 10009
    comment = "direct"


with patch.object(ea_bridge, "get_trade_config", get), \
     patch.object(order_sender.OrderValidator, "validate", lambda o: {"valid": True, "errors": []}):
    threading.Thread(target=fake_ea, daemon=True).start()

    r = order_sender.OrderSender(dry_run=False).send(order)
    check("entry lewat EA: bentuk hasil sama dengan ResponseParser",
          r["success"] and r["order"] == 777
          and {"retcode", "deal", "volume", "price", "comment", "request_id"} <= set(r))

    with patch.object(position_controller.mt5, "order_send", side_effect=AssertionError("tidak boleh direct")):
        res = position_controller._order_send(modify)
    check("modify SL lewat EA, tanpa order_send langsung", res.retcode == 10009)

    stop = True
    time.sleep(0.1)  # EA mati
    r = order_sender.OrderSender(dry_run=False).send(order)
    check("EA mati: entry gagal, TIDAK fallback direct",
          r.get("success") is False and "EA tidak merespons" in r["message"])

    with patch.object(position_controller.mt5, "order_send", return_value=Fake()) as m:
        res = position_controller._order_send(modify)
    check("EA mati: exit fallback ke direct", m.called and res.comment == "direct")

CFG["execution_mode"] = "direct"
with patch.object(ea_bridge, "get_trade_config", get), \
     patch.object(position_controller.mt5, "order_send", return_value=Fake()) as m:
    position_controller._order_send({"action": 1})
check("mode direct: perilaku lama utuh", m.called)
print("ALL PASS" if not fails else f"GAGAL: {fails}")
