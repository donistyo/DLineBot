"""API menu Settings: ubah parameter bot (dengan batas nilai, kunci fase uji, catatan perubahan) dan ringkasan proteksi."""
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config.settings import _trade_config_path

router = APIRouter()
RUNTIME = Path("runtime")
LOCK_FILE = RUNTIME / "config_lock.json"
LOG_FILE = RUNTIME / "config_changes.jsonl"
ENABLED_FILE = RUNTIME / "auto_trade_enabled.json"
NEWS_FLAG = RUNTIME / "news_off_active.json"
NEWS_CACHE = RUNTIME / "news_calendar_cache.json"
BOT_MAGICS = (10001, 10003)
# berita High USD: OFF 20 menit sebelum rilis, ON 10 menit sesudahnya (sama dengan news_auto_off.py)
NEWS_OFF_MIN, NEWS_ON_MIN = 20, 10

# (key, label, grup, min, max, langkah, perlu_restart)
SCHEMA = [
    ("max_trade", "Maks trade per hari", "Batas & Proteksi", 1, 50, 1, True),
    ("max_positions", "Maks posisi bersamaan", "Batas & Proteksi", 1, 3, 1, True),
    ("equity_floor", "Equity floor (bot berhenti di bawah ini)", "Batas & Proteksi", 0, 1000, 1, False),
    ("daily_max_loss", "Batas rugi harian (negatif)", "Batas & Proteksi", -200, 0, 1, True),
    ("daily_max_profit", "Batas untung harian", "Batas & Proteksi", 0, 200, 1, True),
    ("reentry_cooldown_min", "Jeda entry ulang (menit)", "Batas & Proteksi", 0, 120, 1, False),
    ("hard_sl_usd", "Hard SL (USD)", "Eksit", 1, 10, 0.1, False),
    ("emergency_max_usd", "ATR emergency (USD)", "Eksit", 1, 10, 0.1, True),
    ("fast_tp_usd", "FAST TP (USD)", "Eksit", 0.5, 10, 0.1, True),
    ("zone_trail_start_usd", "Trailing zona: mulai (USD)", "Eksit", 0.5, 5, 0.1, False),
    ("zone_trail_gap_usd", "Trailing zona: jarak (USD)", "Eksit", 0.3, 3, 0.1, False),
    ("sl_plus_usd", "SL+ : kunci di entry + (USD)", "Eksit", 0.1, 3, 0.1, True),
    ("sl_plus_buffer", "SL+ : buffer (USD)", "Eksit", 0, 1, 0.05, True),
    ("recover_red_usd", "RECOVERY: dianggap merah di (USD)", "Eksit", 0.3, 5, 0.1, True),
    ("recover_close_usd", "RECOVERY: tutup saat pulih ke (USD)", "Eksit", 0.05, 2, 0.05, True),
    ("never_green_close_usd", "NEVER GREEN: tutup di lonjakan (USD, 0 = mati)", "Eksit", 0, 5, 0.1, True),
    ("loser_seconds", "Loser exit setelah (detik)", "Eksit", 60, 7200, 30, True),
    ("loser_min_profit", "Loser exit: profit minimum (USD)", "Eksit", 0, 2, 0.1, True),
    ("zone_time_exit_min", "Time exit zona (menit)", "Eksit", 10, 360, 5, True),
    ("min_scalp_score", "Skor minimal scalp", "Entry", 40, 90, 1, False),
    ("min_early_score", "Skor minimal entry awal/sideways", "Entry", 40, 95, 1, False),
    ("sideways_penalty", "Tambahan skor saat sideways", "Entry", 0, 30, 1, False),
    ("exhaustion_atr_normal", "Exhaustion EMA50 mode normal (xATR)", "Entry", 1, 6, 0.1, False),
    ("momentum_exhaustion_atr", "Exhaustion mode momentum (xATR)", "Entry", 2, 10, 0.1, False),
    ("early_exhaustion_atr", "Exhaustion mode early (xATR)", "Entry", 2, 10, 0.1, False),
    ("rebound_pos_min", "Rebound edge: posisi minimum di range", "Entry", 0, 0.4, 0.01, False),
]
BY_KEY = {s[0]: s for s in SCHEMA}


def _load_cfg():
    return json.loads(_trade_config_path().read_text(encoding="utf-8"))


def _write_cfg(cfg):
    p = _trade_config_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.replace(tmp, p)  # atomik: pembaca (hot reload) tidak pernah melihat file setengah tertulis


def _lock():
    try:
        return json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"locked": False}


def _log(key, old, new, revert_of=None):
    RUNTIME.mkdir(exist_ok=True)
    row = {"id": int(time.time() * 1000), "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "key": key, "old": old, "new": new, "revert_of": revert_of}
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def _history(n=40):
    try:
        rows = [json.loads(x) for x in LOG_FILE.read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError:
        return []
    return rows[-n:][::-1]


def _check(key, val, cfg):
    if key not in BY_KEY:
        return None, f"{key}: tidak boleh diubah dari dashboard"
    _, label, _, lo, hi, _, _ = BY_KEY[key]
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None, f"{label}: bukan angka"
    if not lo <= v <= hi:
        return None, f"{label}: harus {lo} sampai {hi}"
    return (int(v) if isinstance(cfg.get(key), int) and v.is_integer() else v), None


@router.get("/api/settings/config")
def get_config():
    cfg = _load_cfg()
    fields = [{"key": k, "label": lb, "group": g, "min": lo, "max": hi, "step": st, "restart": rs, "value": cfg.get(k)}
              for k, lb, g, lo, hi, st, rs in SCHEMA]
    return {"fields": fields, "lock": _lock(), "history": _history()}


@router.post("/api/settings/config")
def save_config(data: dict):
    if _lock().get("locked"):
        return JSONResponse({"ok": False, "error": "Pengaturan sedang dikunci (fase uji). Buka kunci dulu."}, status_code=423)
    cfg, clean, errs = _load_cfg(), {}, []
    for k, raw in (data.get("changes") or {}).items():
        v, err = _check(k, raw, cfg)
        if err:
            errs.append(err)
        elif v != cfg.get(k):
            clean[k] = v
    if errs:
        return JSONResponse({"ok": False, "error": "; ".join(errs)}, status_code=400)
    for k, v in clean.items():
        _log(k, cfg.get(k), v)
        cfg[k] = v
    if clean:
        _write_cfg(cfg)
    return {"ok": True, "changed": clean, "restart_needed": [k for k in clean if BY_KEY[k][6]]}


@router.post("/api/settings/revert")
def revert(data: dict):
    if _lock().get("locked"):
        return JSONResponse({"ok": False, "error": "Pengaturan sedang dikunci (fase uji)."}, status_code=423)
    rid = data.get("id")
    row = next((r for r in _history(500) if r["id"] == rid), None)
    if not row:
        return JSONResponse({"ok": False, "error": "Catatan tidak ditemukan"}, status_code=404)
    cfg = _load_cfg()
    v, err = _check(row["key"], row["old"], cfg)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    _log(row["key"], cfg.get(row["key"]), v, revert_of=rid)
    cfg[row["key"]] = v
    _write_cfg(cfg)
    return {"ok": True, "key": row["key"], "value": v, "restart_needed": BY_KEY[row["key"]][6]}


@router.post("/api/settings/lock")
def set_lock(data: dict):
    RUNTIME.mkdir(exist_ok=True)
    LOCK_FILE.write_text(json.dumps({"locked": bool(data.get("locked")),
                                     "since": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                     "note": str(data.get("note", ""))[:120]}), encoding="utf-8")
    return _lock()


def _next_news(now):
    try:
        events = json.loads(NEWS_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    best = None
    for e in events:
        if e.get("country") != "USD" or e.get("impact") != "High":
            continue
        try:
            t = datetime.fromisoformat(e["date"]).astimezone().replace(tzinfo=None)
        except (KeyError, ValueError):
            continue
        if t > now and (best is None or t < best[0]):
            best = (t, e.get("title", ""))
    if not best:
        return None
    t, title = best
    return {"title": title, "time": t.strftime("%a %d/%m %H:%M"),
            "off_at": (t - timedelta(minutes=NEWS_OFF_MIN)).strftime("%H:%M"),
            "on_at": (t + timedelta(minutes=NEWS_ON_MIN)).strftime("%H:%M")}


@router.get("/api/settings/protection")
def protection():
    cfg, now = _load_cfg(), datetime.now()
    try:
        auto = bool(json.loads(ENABLED_FILE.read_text()).get("enabled"))
    except (OSError, ValueError):
        auto = False
    out = {"autotrade": auto, "news_off_active": NEWS_FLAG.exists(), "next_news": _next_news(now),
           "off_schedule": "23:00", "start_schedule": "05:50",
           "equity_floor": cfg.get("equity_floor"), "daily_max_loss": cfg.get("daily_max_loss"),
           "daily_max_profit": cfg.get("daily_max_profit"), "max_trade": cfg.get("max_trade")}
    try:
        acc = mt5.account_info()
        out["equity"], out["balance"] = acc.equity, acc.balance
        out["to_floor"] = round(acc.equity - float(cfg.get("equity_floor") or 0), 2)
        out["positions"] = mt5.positions_total()
        midnight = datetime(now.year, now.month, now.day)
        # waktu deal MT5 = epoch berlabel UTC; WIB = +7 jam, jadi tengah malam WIB = epoch lokal - 7 jam
        start = int((midnight - datetime(1970, 1, 1)).total_seconds()) - 7 * 3600
        deals = [d for d in (mt5.history_deals_get(midnight - timedelta(days=1), now + timedelta(days=1)) or [])
                 if d.magic in BOT_MAGICS and d.entry == 1 and d.time >= start]
        out["today_trades"] = len(deals)
        out["today_pnl"] = round(sum(d.profit for d in deals), 2)
    except Exception as e:
        out["mt5_error"] = str(e)
    return out
