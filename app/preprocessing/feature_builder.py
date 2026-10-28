import numpy as np
import pandas as pd

# Fitur relatif/stasioner. Terpisah dari app.config.features.FEATURE_COLUMNS
# supaya model live lama (dilatih dengan 21 fitur itu) tidak rusak.
EXTRA_FEATURES = [
    "ret_1", "ret_5", "ret_15", "ret_60",
    "d_ema20", "d_ema50", "d_ema200", "ema20_50", "ema50_slope",
    "RSI", "ADX", "STO_K", "STO_D", "macd_hist_atr",
    "bb_pos", "bb_width",
    "atr_pct", "atr_rel",
    "hour_sin", "hour_cos",
    "spread_atr", "vol_rel",
    "body_atr", "upper_wick_atr", "lower_wick_atr",
    "d_high_1d", "d_low_1d",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Tambah EXTRA_FEATURES. Hanya memakai data masa lalu (tanpa look-ahead)."""

    df = df.copy()
    c, o, h, l, atr = df["close"], df["open"], df["high"], df["low"], df["ATR"]

    for n in (1, 5, 15, 60):
        df[f"ret_{n}"] = c.pct_change(n) * 100

    df["d_ema20"] = (c - df["EMA20"]) / atr
    df["d_ema50"] = (c - df["EMA50"]) / atr
    df["d_ema200"] = (c - df["EMA200"]) / atr
    df["ema20_50"] = (df["EMA20"] - df["EMA50"]) / atr
    df["ema50_slope"] = (df["EMA50"] - df["EMA50"].shift(10)) / atr

    df["macd_hist_atr"] = df["MACD_HIST"] / atr

    band = (df["BB_UPPER"] - df["BB_LOWER"]).replace(0, np.nan)
    df["bb_pos"] = (c - df["BB_LOWER"]) / band
    df["bb_width"] = band / c * 100

    df["atr_pct"] = atr / c * 100
    df["atr_rel"] = atr / atr.rolling(100).mean()

    hour = pd.to_datetime(df["time"]).dt.hour + pd.to_datetime(df["time"]).dt.minute / 60
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)

    df["spread_atr"] = df["spread"] * 0.001 / atr  # shortcut: point XAUUSDc Exness; ambil dari symbol_info jika multi-simbol
    df["vol_rel"] = df["tick_volume"] / df["tick_volume"].rolling(50).mean()

    df["body_atr"] = (c - o) / atr
    df["upper_wick_atr"] = (h - np.maximum(c, o)) / atr
    df["lower_wick_atr"] = (np.minimum(c, o) - l) / atr

    # 1440 bar M1 = 1 hari
    df["d_high_1d"] = (h.rolling(1440).max() - c) / atr
    df["d_low_1d"] = (c - l.rolling(1440).min()) / atr

    df = df.replace([np.inf, -np.inf], np.nan)
    return df.dropna(subset=EXTRA_FEATURES).reset_index(drop=True)
