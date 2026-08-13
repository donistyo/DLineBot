import json
import os
import time
from pathlib import Path

import MetaTrader5 as mt5

RUNTIME = Path(r"C:\Users\ADSS\AI-XAU-BOT\runtime")
SYMBOL = "XAUUSDc"
ENABLED_FILE = RUNTIME / "auto_trade_enabled.json"
FLAG_FILE = RUNTIME / "wait_flat_off.json"


def set_enabled(flag):
    ENABLED_FILE.write_text(json.dumps({"enabled": flag}))
    print(f"[watcher] auto_trade_enabled -> {flag}")


def main():
    mt5.initialize()
    saw_open = False
    while True:
        try:
            if FLAG_FILE.exists() and not FLAG_FILE.read_text().strip():
                pass
            positions = mt5.positions_get(symbol=SYMBOL) or []
            if positions:
                saw_open = True
            elif saw_open:
                set_enabled(False)
                print("[watcher] Semua posisi sudah tertutup. Autotrade OFF.")
                FLAG_FILE.write_text(json.dumps({"done": True, "off_time": time.strftime("%H:%M")}))
                break
        except Exception as e:
            print(f"[watcher] error: {e}")
        time.sleep(5)

    mt5.shutdown()


if __name__ == "__main__":
    main()