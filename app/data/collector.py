from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from app.config.settings import (
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    DEFAULT_BARS,
    MT5_PATH,
)


MT5_TIMEFRAME = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 16385,
    "H4": 16388,
    "D1": 16408,
    "W1": 32769,
    "MN1": 49153,
}

# Interval yfinance per timeframe (fallback bila MT5 tidak tersedia)
YF_INTERVAL = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "1h",   # di-resample ke 4 jam
    "D1": "1d",
}

YF_PERIOD = {
    "M1": "7d",
    "M5": "1mo",
    "M15": "3mo",
    "M30": "6mo",
    "H1": "1y",
    "H4": "2y",
    "D1": "5y",
}

# Pola simbol broker -> ticker yfinance
YF_TICKER_RULES = (
    ("XAUUSD", "GC=F"),
    ("XAGUSD", "SI=F"),
    ("BTCUSD", "BTC-USD"),
    ("BTCUSDT", "BTC-USD"),
    ("ETHUSD", "ETH-USD"),
    ("ETHUSDT", "ETH-USD"),
)


class Collector:
    """Pengambil data OHLCV dari MetaTrader 5 (fallback: yfinance)."""

    def __init__(
        self,
        symbol=None,
        timeframe=None,
        bars=None
    ):
        self.symbol = symbol or DEFAULT_SYMBOL
        self.timeframe = timeframe or DEFAULT_TIMEFRAME
        self.bars = bars or DEFAULT_BARS

    # =====================================
    # Public API
    # =====================================

    def load(self, symbol=None, timeframe=None, bars=None):
        symbol = symbol or self.symbol
        timeframe = (timeframe or self.timeframe).upper()
        bars = bars or self.bars

        if timeframe not in MT5_TIMEFRAME:
            raise ValueError(
                f"Timeframe tidak didukung: {timeframe} "
                f"(pilihan: {', '.join(MT5_TIMEFRAME)})"
            )

        df = self._load_mt5(symbol, timeframe, bars)

        if df is None or df.empty:
            df = self._load_yfinance(symbol, timeframe, bars)

        if df is None or df.empty:
            raise RuntimeError(
                f"Data {symbol} {timeframe} tidak tersedia. "
                "Cek koneksi MT5 / koneksi internet."
            )

        return df.reset_index(drop=True)

    # =====================================
    # Sumber 1 : MetaTrader 5
    # =====================================

    def _load_mt5(self, symbol, timeframe, bars):
        try:
            import MetaTrader5 as mt5
        except Exception:
            return None

        if not self._mt5_connect(mt5):
            return None

        rates = mt5.copy_rates_from_pos(
            symbol,
            MT5_TIMEFRAME[timeframe],
            0,
            bars
        )

        if rates is None or len(rates) == 0:
            print(f"[WARN] MT5 tidak punya data {symbol} {timeframe}")
            return None

        df = pd.DataFrame(rates)

        df["time"] = pd.to_datetime(
            df["time"],
            unit="s",
            utc=True
        ).dt.tz_localize(None)

        for col in ("spread", "real_volume", "tick_volume"):
            if col in df.columns:
                df[col] = df[col].astype("int64")

        cols = [
            "time", "open", "high", "low", "close",
            "tick_volume", "spread", "real_volume"
        ]
        df = df[[c for c in cols if c in df.columns]]

        print(f"[OK] Data MT5 : {symbol} {timeframe} ({len(df)} bar)")

        return df.sort_values("time").reset_index(drop=True)

    def _mt5_connect(self, mt5):
        try:
            if mt5.terminal_info() is not None:
                return True
        except Exception:
            pass

        try:
            if MT5_PATH and Path(MT5_PATH).exists():
                if mt5.initialize(path=MT5_PATH, timeout=60000):
                    return True
        except Exception:
            pass

        try:
            if mt5.initialize(timeout=60000):
                return True
        except Exception:
            pass

        return False

    # =====================================
    # Sumber 2 : yfinance (fallback)
    # =====================================

    def _load_yfinance(self, symbol, timeframe, bars):
        ticker = self._yf_ticker(symbol)
        if not ticker:
            return None

        print(
            f"[WARN] MT5 tidak tersedia -> fallback yfinance: "
            f"{ticker} ({symbol} {timeframe})"
        )

        try:
            import yfinance as yf
        except Exception as e:
            print(f"[WARN] yfinance tidak tersedia : {e}")
            return None

        interval = YF_INTERVAL[timeframe]
        period = YF_PERIOD[timeframe]

        try:
            raw = yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False
            )
        except Exception as e:
            print(f"[WARN] Download {ticker} gagal : {e}")
            return None

        if raw is None or raw.empty:
            print(f"[WARN] Data {ticker} kosong")
            return None

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        # yfinance memakai kapitalisasi (Open/High/Low/Close/Volume)
        raw.columns = [str(col).lower() for col in raw.columns]

        df = raw.rename_axis("time").reset_index()

        if "time" not in df.columns and df.index.name:
            df = df.reset_index()

        if "volume" not in df.columns:
            df["volume"] = 0

        # yfinance tidak punya spread / real volume
        df["tick_volume"] = df["volume"].fillna(0).astype("int64")
        df["real_volume"] = df["volume"].fillna(0).astype("int64")
        df["spread"] = 0

        if timeframe == "H4":
            df = self._resample(df, "4h")

        cols = [
            "time", "open", "high", "low", "close",
            "tick_volume", "spread", "real_volume"
        ]
        df = df[[c for c in cols if c in df.columns]]

        df = df.dropna(subset=["open", "high", "low", "close"])
        df = df.tail(bars).reset_index(drop=True)

        print(f"[OK] Data yfinance : {ticker} {timeframe} ({len(df)} bar)")

        return df

    def _resample(self, df, rule):
        df = df.set_index("time")

        agg = df.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "tick_volume": "sum",
            "spread": "last",
            "real_volume": "sum",
        }).dropna(subset=["open", "close"])

        return agg.reset_index()

    @staticmethod
    def _yf_ticker(symbol):
        if not symbol:
            return None

        clean = symbol.upper()

        for pattern, ticker in YF_TICKER_RULES:
            if clean.startswith(pattern):
                return ticker

        return None
