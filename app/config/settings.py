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