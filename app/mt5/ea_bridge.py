import os
import time
import uuid
from pathlib import Path

from app.config.settings import get_trade_config

DONE = 10009  # mt5.TRADE_RETCODE_DONE


def enabled():
    return get_trade_config("execution_mode", "direct") == "ea"


def _base():
    d = get_trade_config("ea_bridge_dir")
    if d:
        return Path(d)
    return Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "dline"


def execute(request):
    """Kirim request MT5 apa adanya ke EA, tunggu ack.

    Return dict seperti ResponseParser.parse, atau None bila EA tidak
    menjawab dalam batas waktu (caller yang memutuskan: entry jangan kirim
    ulang buta, exit boleh fallback langsung).
    """
    base = _base()
    (base / "cmd").mkdir(parents=True, exist_ok=True)
    (base / "ack").mkdir(parents=True, exist_ok=True)

    cid = uuid.uuid4().hex
    lines = [f"id={cid}", f"ts={int(time.time())}"]
    lines += [f"{k}={v}" for k, v in request.items() if v is not None]
    tmp = base / "cmd" / f"{cid}.tmp"
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, base / "cmd" / f"{cid}.req")  # atomik: EA hanya melihat *.req (bukan .cmd, ditolak MQL5)

    ack = base / "ack" / f"{cid}.ack"
    deadline = time.time() + int(get_trade_config("ea_ack_timeout_ms", 3000)) / 1000.0
    while time.time() < deadline:
        if ack.exists():
            kv = dict(l.split("=", 1) for l in ack.read_text(encoding="utf-8").splitlines() if "=" in l)
            ack.unlink(missing_ok=True)
            retcode = int(kv.get("retcode", 0))
            return {
                "success": retcode == DONE,
                "retcode": retcode,
                "order": int(kv.get("order", 0)),
                "deal": int(kv.get("deal", 0)),
                "volume": float(kv.get("volume", 0)),
                "price": float(kv.get("price", 0)),
                "comment": kv.get("comment", ""),
                "request_id": cid,
            }
        time.sleep(0.05)
    return None
