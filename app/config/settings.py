from dotenv import load_dotenv
import os

load_dotenv()

APP_NAME = os.getenv("APP_NAME")

MT5_LOGIN = os.getenv("MT5_LOGIN")
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/dlinebot.db")

DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "XAUUSD")
DEFAULT_TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME", "H1")
DEFAULT_BARS = int(os.getenv("DEFAULT_BARS", 1000))