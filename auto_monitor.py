import MetaTrader5 as mt5
import time
import datetime

PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
LOGIN = 160040915
SERVER = "Exness-MT5Real20"
PASSWORD = "@Maluku2024"

mt5.initialize(path=PATH, login=LOGIN, server=SERVER, password=PASSWORD)

print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Auto-monitor started")

while True:
    try:
        positions = mt5.positions_get()
        if positions:
            for p in positions:
                if p.symbol != "XAUUSDc":
                    continue
                profit = p.profit
                ticket = p.ticket
                # Aturan: tembus 3-4pt ambil langsung, atau TP 1.0-2.0
                if profit >= 3.0:
                    result = mt5.Close(ticket=ticket)
                    msg = f"[CLOSE] Ticket {ticket} | Profit: +{profit:.2f} (tembus 3pt)"
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
                elif profit >= 2.0 and profit < 3.0:
                    result = mt5.Close(ticket=ticket)
                    msg = f"[CLOSE] Ticket {ticket} | Profit: +{profit:.2f} (TP 2pt)"
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
    except Exception as e:
        print(f"[ERROR] {e}")

    time.sleep(3)
