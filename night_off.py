import json
from datetime import datetime
from pathlib import Path

ENABLED_FILE = Path(r"C:\Project\Bot\DLineBot\runtime\auto_trade_enabled.json")
ENABLED_FILE.write_text(json.dumps({"enabled": False}))
print(f"[night-off] {datetime.now():%Y-%m-%d %H:%M:%S} auto_trade_enabled -> false (jadwal 23:00 WIB)")
