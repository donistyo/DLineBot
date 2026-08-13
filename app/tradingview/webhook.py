"""
TradingView Webhook Receiver + Gating
=====================================
Menerima sinyal alert dari TradingView (strategy Pine Script),
memvalidasi payload + secret, mengecek status enabled (dashboard) &
status auto-trade, lalu mengeksekusi order di MT5 (Exness) via PartedOrder.

Gating:
  * WEBHOOK_SECRET wajib cocok (kalau diisi di .env)
  * Webhook harus ON (runtime/tv_webhook_enabled.json)
  * Autotrade harus ON (runtime/auto_trade_enabled.json)
  * Lot dipakai dari runtime/trade_config.json (kalau payload tidak set volume)

Format payload JSON (contoh):
{
    "secret": "<WEBHOOK_SECRET>",
    "symbol": "XAUUSDc",
    "signal": "BUY",          # BUY / SELL / CLOSE_BUY / CLOSE_SELL / CLOSE_ALL
    "volume": 0.01,           # opsional (kosong => pakai lot config)
    "entry": 0,               # opsional (0 => harga market)
    "stop_loss": 0,           # opsional (0 => hitung otomatis)
    "take_profit1": 0,        # opsional
    "take_profit2": 0,        # opsional
    "kinerja": "...",
    "tf": "5"
}
"""

import json
import time
import hmac
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("tradingview")

_RUNTIME = Path("runtime")


# =====================================
# Config helpers (shared dengan dashboard)
# =====================================

def _get_secret() -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        import os
        return os.getenv("WEBHOOK_SECRET", "").strip()
    except Exception:
        return ""


def is_webhook_enabled() -> bool:
    try:
        p = _RUNTIME / "tv_webhook_enabled.json"
        if p.exists():
            return bool(json.loads(p.read_text()).get("enabled", False))
    except Exception:
        pass
    return False


def is_auto_trade_enabled() -> bool:
    try:
        p = _RUNTIME / "auto_trade_enabled.json"
        if p.exists():
            return bool(json.loads(p.read_text()).get("enabled", True))
    except Exception:
        pass
    return True


def get_lot_from_config() -> float:
    try:
        p = _RUNTIME / "trade_config.json"
        if p.exists():
            lot = json.loads(p.read_text()).get("lot_size", 0.01)
            return max(0.01, float(lot))
    except Exception:
        pass
    return 0.01


def get_webhook_status() -> dict:
    return {
        "enabled": is_webhook_enabled(),
        "secret_set": bool(_get_secret()),
        "auto_trade_enabled": is_auto_trade_enabled(),
        "lot_size": get_lot_from_config(),
    }


# =====================================
# Signal log store
# =====================================

def _load_signals() -> list:
    p = _RUNTIME / "tv_signals.json"
    try:
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return []


def _save_signals(signals: list):
    _RUNTIME.mkdir(exist_ok=True)
    try:
        (_RUNTIME / "tv_signals.json").write_text(json.dumps(signals, indent=2))
    except Exception as e:
        logger.warning("Gagal simpan log sinyal: %s", e)


def append_signal(entry: dict, limit: int = 100):
    signals = _load_signals()
    signals.append(entry)
    signals = signals[-limit:]
    _save_signals(signals)


def get_signals(limit: int = 30) -> list:
    signals = _load_signals()
    return list(reversed(signals[-limit:]))


def set_webhook_enabled(enabled: bool):
    _RUNTIME.mkdir(exist_ok=True)
    (_RUNTIME / "tv_webhook_enabled.json").write_text(json.dumps({"enabled": bool(enabled)}))


# =====================================
# Rate limit anti-duplikat
# =====================================

def _rate_limit_ok() -> bool:
    path = _RUNTIME / "tv_webhook.json"
    now = time.time()
    state = {"last": 0, "times": []}
    try:
        if path.exists():
            state.update(json.loads(path.read_text()))
    except Exception:
        pass
    cutoff = now - 60
    state["times"] = [t for t in state.get("times", []) if t > cutoff]
    if now - state.get("last", 0) < 2.0:
        return False
    if len(state["times"]) >= 5:
        return False
    state["last"] = now
    state["times"].append(now)
    try:
        path.write_text(json.dumps(state))
    except Exception:
        pass
    return True


# =====================================
# Router
# =====================================

router = APIRouter(prefix="/api/tradingview", tags=["tradingview"])


@router.get("/status")
def tv_status():
    return get_webhook_status()


@router.post("/enable")
def tv_enable(data: dict = None):
    data = data or {}
    enabled = bool(data.get("enabled", True))
    set_webhook_enabled(enabled)
    return get_webhook_status()


@router.get("/signals")
def tv_signals(limit: int = 30):
    return {"signals": get_signals(limit)}


@router.get("/multi-tf")
def tv_multi_tf():
    """Alignment arah M1 / M5 / M15 (dipakai panel 'Sinyal Saat Ini')."""
    try:
        from app.mt5.account_store import get_active_symbol
        symbol = get_active_symbol()
    except Exception:
        symbol = "XAUUSDc"

    import MetaTrader5 as mt5
    from app.mt5.session import MT5Session
    from app.indicators.engine import IndicatorEngine
    import pandas as pd

    MT5Session.ensure_connection()
    engine = IndicatorEngine()

    tf_map = [("M1", mt5.TIMEFRAME_M1, 300), ("M5", mt5.TIMEFRAME_M5, 200), ("M15", mt5.TIMEFRAME_M15, 200)]

    results = {}
    for tf, tfm, bars in tf_map:
        try:
            rates = mt5.copy_rates_from_pos(symbol, tfm, 0, bars)
            if rates is None or len(rates) < 30:
                results[tf] = {"trend": "NA", "adx": 0, "close": 0, "ema20": 0, "ema50": 0}
                continue
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df = engine.calculate(df)
            df = df.dropna()
            if df.empty:
                results[tf] = {"trend": "NA", "adx": 0, "close": 0, "ema20": 0, "ema50": 0}
                continue
            last = df.iloc[-1]
            adx = float(last["ADX"]) if pd.notna(last["ADX"]) else 0
            if adx < 20:
                trend = "SIDEWAYS"
            elif last["close"] > last["EMA20"] > last["EMA50"]:
                trend = "UP"
            elif last["close"] < last["EMA20"] < last["EMA50"]:
                trend = "DOWN"
            else:
                trend = "SIDEWAYS"
            results[tf] = {
                "trend": trend,
                "adx": round(adx, 1),
                "close": round(float(last["close"]), 2),
                "ema20": round(float(last["EMA20"]), 2),
                "ema50": round(float(last["EMA50"]), 2),
            }
        except Exception as e:
            results[tf] = {"trend": "NA", "adx": 0, "close": 0, "ema20": 0, "ema50": 0, "error": str(e)}

    return {"symbol": symbol, "tfs": results}


@router.post("/webhook")
async def tradingview_webhook(request: Request):
    raw = await request.body()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON tidak valid"})

    if not isinstance(data, dict):
        return JSONResponse(status_code=400, content={"error": "Payload harus object"})

    # ---- validasi secret ----
    secret = _get_secret()
    if secret:
        body_secret = str(data.get("secret", "")).strip()
        if not hmac.compare_digest(body_secret, secret):
            _log_rejected(data, "Secret tidak valid")
            return JSONResponse(status_code=401, content={"error": "Secret tidak valid"})

    signal = str(data.get("signal", "")).upper()
    if signal not in ("BUY", "SELL", "CLOSE_BUY", "CLOSE_SELL", "CLOSE_ALL"):
        return JSONResponse(status_code=400, content={"error": f"Signal tidak dikenal: {signal}"})

    # ---- gating: webhook ON ? ----
    if not is_webhook_enabled():
        _log_rejected(data, "Webhook OFF di dashboard")
        return JSONResponse(status_code=403, content={"error": "Webhook disabled"})

    # ---- gating: autotrade ON ? (CLOSE diperbolehkan saat OFF agar bisa emergency) ----
    allow_close = signal.startswith("CLOSE")
    if not allow_close and not is_auto_trade_enabled():
        _log_rejected(data, "Autotrade OFF")
        return JSONResponse(status_code=403, content={"error": "Autotrade disabled"})

    if not _rate_limit_ok():
        _log_rejected(data, "Rate limit")
        return JSONResponse(status_code=429, content={"error": "Rate limit"})

    try:
        result = _execute(data, signal)
    except Exception as e:
        logger.exception("TradingView webhook gagal dieksekusi")
        return JSONResponse(status_code=500, content={"error": str(e)})

    _log_accepted(data, result)
    return JSONResponse(content={"success": True, "result": result})


# =====================================
# Execution
# =====================================

def _active_symbol() -> str:
    try:
        from app.mt5.account_store import get_active_symbol
        return get_active_symbol()
    except Exception:
        return "XAUUSDc"


def _execute(data: dict, signal: str) -> dict:
    symbol = str(data.get("symbol") or _active_symbol())
    volume = float(data.get("volume")) if data.get("volume") else get_lot_from_config()
    entry = float(data["entry"]) if data.get("entry") else None
    sl = float(data["stop_loss"]) if data.get("stop_loss") else None
    tp1 = float(data["take_profit1"]) if data.get("take_profit1") else None
    tp2 = float(data["take_profit2"]) if data.get("take_profit2") else None

    comment = "TV-" + str(data.get("tf", "5")).upper()

    if signal.startswith("CLOSE"):
        return _close_positions(symbol, signal, comment)

    from app.mt5.parted_order import PartedOrder
    order = PartedOrder(dry_run=False)
    result = order.execute(
        symbol, signal, volume,
        entry_price=entry,
        stop_loss=sl,
        take_profit1=tp1,
        take_profit2=tp2,
        magic=10003,
        comment=comment,
    )
    try:
        order.notify_telegram(result)
    except Exception:
        pass
    return result


def _close_positions(symbol: str, signal: str, comment: str) -> dict:
    import MetaTrader5 as mt5
    from app.mt5.session import MT5Session
    from app.mt5.position_controller import PositionController, _log_close

    MT5Session.ensure_connection()
    positions = mt5.positions_get(symbol=symbol)
    closed = []
    for p in (positions or []):
        if signal == "CLOSE_BUY" and p.type != mt5.POSITION_TYPE_BUY:
            continue
        if signal == "CLOSE_SELL" and p.type != mt5.POSITION_TYPE_SELL:
            continue
        _log_close("TV_WEBHOOK", p.ticket, p.symbol, p.profit)
        res = PositionController().close(p, caller="TV_WEBHOOK")
        closed.append({"ticket": p.ticket, "result": res})
    return {"signal": signal, "symbol": symbol, "closed": closed, "count": len(closed)}


# =====================================
# Logging
# =====================================

def _log_rejected(data: dict, reason: str):
    symbol = str(data.get("symbol")) if isinstance(data.get("symbol"), str) else _active_symbol()
    append_signal({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "signal": str(data.get("signal", "")).upper(),
        "status": "REJECTED",
        "reason": reason,
        "volume": data.get("volume"),
        "price": data.get("entry"),
    })


def _log_accepted(data: dict, result: dict):
    symbol = str(data.get("symbol")) if isinstance(data.get("symbol"), str) else _active_symbol()
    ok1 = isinstance(result, dict) and result.get("result_1", {}).get("success", False)
    status = "EXECUTED" if signal_is_executed(result) else "DONE"
    append_signal({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "signal": str(data.get("signal", "")).upper(),
        "status": "EXECUTED" if ok1 or data.get("signal", "").upper().startswith("CLOSE") else "FAILED",
        "reason": status,
        "volume": result.get("volume") if isinstance(result, dict) else None,
        "price": result.get("entry_price") if isinstance(result, dict) else None,
        "ticket": result.get("result_1", {}).get("order") if isinstance(result, dict) else None,
    })
    try:
        from app.database.db_logger import DatabaseLogger
        DatabaseLogger().log_trade({
            "symbol": symbol,
            "signal": str(data.get("signal", "")).upper(),
            "confidence": 1.0,
            "action": "TV_WEBHOOK",
            "status": "SUCCESS",
            "reason": "Sinyal TradingView dieksekusi",
            "entry_price": result.get("entry_price") if isinstance(result, dict) else None,
            "stop_loss": result.get("stop_loss") if isinstance(result, dict) else None,
            "take_profit": result.get("take_profit1") if isinstance(result, dict) else None,
            "lot_size": result.get("volume") if isinstance(result, dict) else None,
            "ticket": None,
        })
    except Exception as e:
        logger.warning("Gagal log ke DB: %s", e)


def signal_is_executed(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if "closed" in result:
        return result.get("count", 0) > 0
    return result.get("result_1", {}).get("success", False)
