import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
p = ROOT / "runtime" / "trade_config.json"
cfg = json.loads(p.read_text(encoding="utf-8"))
cfg["reentry_cooldown_min"] = 10
p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
urllib.request.urlopen("http://localhost:8000/api/auto-trade/do-enable", timeout=10).read()
with open(ROOT / "logs" / "cooldown_restore.log", "a") as f:
    f.write("cooldown re-entry restored -> 10 menit\n")
print("reentry_cooldown_min = 10, config reloaded")
