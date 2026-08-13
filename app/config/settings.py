from dotenv import load_dotenv
import os
import socket

load_dotenv()

def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

APP_NAME = os.getenv("APP_NAME")

MT5_LOGIN = os.getenv("MT5_LOGIN")
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/dlinebot.db")

_local_ip = _get_local_ip()
DASHBOARD_URL = os.getenv("DASHBOARD_URL")
if not DASHBOARD_URL:
    DASHBOARD_URL = f"http://{_local_ip}:8000"

BROKER = os.getenv("BROKER", "").lower()

DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "XAUUSDc")
DEFAULT_TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME", "H1")
DEFAULT_BARS = int(os.getenv("DEFAULT_BARS", 1000))
TRADE_LOT_SIZE = float(os.getenv("TRADE_LOT_SIZE", "0.01"))

# =====================================
# Per-Symbol Configuration
# =====================================

# Simbol kripto (tidak punya berita negara, market 24/7)
CRYPTO_SYMBOLS = {"BTCUSDTc", "BTCUSDc", "ETHUSDc", "ETHBTCc"}

# Prefix nama file model AI per simbol
SYMBOL_MODEL_PREFIX = {
    "XAUUSDc": "xauusd",
    "BTCUSDTc": "btcusdtc",
    "BTCUSDc": "btcusdtc",
}

# Parameter trading per simbol
SYMBOL_TRADE_PARAMS = {
    "XAUUSDc": {
        "max_spread": 500,     # dalam poin (efektif exness scalp)
        "min_atr": 0.5,        # dalam poin harga
        "session": (0, 23),    # jam UTC
        "model_prefix": "xauusd",
        "point": 0.001,        # ukuran point harga simbol
        "sl_points": 3000,     # jarak default SL manual (poin); lebar, tdk kena noise (3.0)
        "tp1_points": 8000,    # jarak default TP1 manual (poin); jauh, biar trailing yg mengunci
        "tp2_points": 12000,   # jarak default TP2 manual (poin)
    },
    "BTCUSDTc": {
        "max_spread": 3000,    # dalam poin
        "min_atr": 8,          # dalam poin harga
        "session": (0, 23),    # 24/7
        "model_prefix": "btcusdtc",
        "point": 0.01,         # ukuran point harga simbol
        "sl_points": 2000,     # jarak default SL manual (poin); <2000 ditolak broker
        "tp1_points": 2000,    # jarak default TP1 manual (poin)
        "tp2_points": 3000,    # jarak default TP2 manual (poin)
    },
    "BTCUSDc": {
        "max_spread": 3000,    # dalam poin
        "min_atr": 8,          # dalam poin harga
        "session": (0, 23),    # 24/7
        "model_prefix": "btcusdtc",
        "point": 0.01,         # ukuran point harga simbol
        "sl_points": 2000,     # jarak default SL manual (poin); <2000 ditolak broker
        "tp1_points": 2000,    # jarak default TP1 manual (poin)
        "tp2_points": 3000,    # jarak default TP2 manual (poin)
    },
}


def get_symbol_params(symbol):
    return SYMBOL_TRADE_PARAMS.get(symbol, SYMBOL_TRADE_PARAMS.get("XAUUSDc", {}))


def is_crypto_symbol(symbol):
    return symbol in CRYPTO_SYMBOLS


def get_model_prefix(symbol):
    params = get_symbol_params(symbol)
    return params.get("model_prefix") or SYMBOL_MODEL_PREFIX.get(symbol, "xauusd")


# Threshold label AI berbasis ATR (dalam unit ATR, bukan harga mutlak)
LABEL_ATR_MULTIPLIER = float(os.getenv("LABEL_ATR_MULTIPLIER", "0.3"))

# =====================================
# Runtime Trade Config
# =====================================

_TRADE_CONFIG = {}


def load_trade_config():
    """Muat runtime/trade_config.json (lot_size, max_trade, max_positions)."""
    global _TRADE_CONFIG
    _TRADE_CONFIG = {}
    try:
        from pathlib import Path
        path = Path("runtime/trade_config.json")
        if path.exists():
            import json
            with open(path, "r", encoding="utf-8") as f:
                _TRADE_CONFIG = json.load(f)
    except Exception:
        _TRADE_CONFIG = {}
    return _TRADE_CONFIG


def get_trade_config(key, default=None):
    if not _TRADE_CONFIG:
        load_trade_config()
    return _TRADE_CONFIG.get(key, default)