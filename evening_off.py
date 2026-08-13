import json
import time
from datetime import datetime
from pathlib import Path

import MetaTrader5 as mt5

SYMBOL = "XAUUSDc"
ENABLED_FILE = Path(r"C:\Users\ADSS\AI-XAU-BOT\runtime\auto_trade_enabled.json")
OFF_H = 18
OFF_M = 30
CLOSE_H = 19
CLOSE_M = 0

mt5.initialize()


def set_enabled(flag):
    ENABLED_FILE.write_text(json.dumps({"enabled": flag}))
    print(f"[jadwal] {datetime.now():%H:%M:%S} auto_trade_enabled -> {flag}")


def close_all():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        print(f"[jadwal] {datetime.now():%H:%M:%S} tidak ada posisi, skip close.")
        return
    closed = 0
    for p in positions:
        close_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(p.symbol).bid if p.type == 0 else mt5.symbol_info_tick(p.symbol).ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "position": p.ticket,
            "price": price,
            "deviation": 20,
            "magic": 1001,
            "comment": "close all news",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode == 10009:
            closed += 1
            print(f"[jadwal] {datetime.now():%H:%M:%S} close #{p.ticket} profit={p.profit:.2f} OK")
        else:
            print(f"[jadwal] close #{p.ticket} GAGAL retcode={result.retcode} {result.comment}")
    print(f"[jadwal] {datetime.now():%H:%M:%S} selesai close {closed} posisi.")


def target_today(h, m):
    now = datetime.now()
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def main():
    off_done = False
    close_done = False
    while True:
        now = datetime.now()
        t_off = target_today(OFF_H, OFF_M)
        t_close = target_today(CLOSE_H, CLOSE_M)
        if not off_done and now >= t_off:
            set_enabled(False)
            off_done = True
        if not close_done and now >= t_close:
            close_all()
            close_done = True
        if off_done and close_done:
            print(f"[jadwal] {now:%H:%M:%S} selesai (off + close), exit.")
            break
        time.sleep(20)
    mt5.shutdown()


if __name__ == "__main__":
    main()
