import json
from pathlib import Path

ENABLED_FILE = Path(r"C:\Users\ADSS\AI-XAU-BOT\runtime\auto_trade_enabled.json")
FLAG_FILE = Path(r"C:\Users\ADSS\AI-XAU-BOT\runtime\wait_flat_off.json")

ENABLED_FILE.write_text(json.dumps({"enabled": True}))
if FLAG_FILE.exists():
    FLAG_FILE.unlink()
print("auto_trade_enabled -> true (autotrade ON, sesi besok pagi)")