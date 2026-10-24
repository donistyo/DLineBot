import json
import sys
from datetime import datetime
from pathlib import Path

ENABLED_FILE = Path(r"C:\Project\Bot\DLineBot\runtime\auto_trade_enabled.json")
FLAG_FILE = Path(r"C:\Project\Bot\DLineBot\runtime\wait_flat_off.json")

if datetime.now().weekday() >= 5 and "--force" not in sys.argv:
    print("[guard] Sabtu/Minggu - market tutup, autotrade TIDAK diaktifkan "
          "(pakai --force untuk memaksa).")
    sys.exit(0)

ENABLED_FILE.write_text(json.dumps({"enabled": True}))
if FLAG_FILE.exists():
    FLAG_FILE.unlink()
print("auto_trade_enabled -> true (autotrade ON, sesi besok pagi)")
