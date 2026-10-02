"""BBMA (Bollinger Bands + Moving Average) Oma Ally style.

Strategi utama mode ``entry_strategy = "bbma"``.

Arah      : kemiringan mid BB (MA) M5 + alignment MA5/MA10,
            WAJIB M15 searah (slope mid BB M15 + posisi harga vs mid M15).
Trigger   : reentry - harga sempat menyentuh/menembus BB (impulse) dalam
            N bar terakhir, lalu pullback ke dekat mid BB (<= threshold ATR).
Anti-chase: harga terlalu jauh dari mid BB (> threshold ATR) = belum reentry.

Data riset per entry: ``slope_strength`` (kemiringan mid BB per bar,
dinormalisasi ATR, bertanda: positif = naik) dan ``dist_mid_atr``
(|close - mid BB| / ATR).
"""

import pandas as pd

from ta.volatility import BollingerBands


def _cfg(key, default):
    try:
        from app.config.settings import get_trade_config
        val = get_trade_config(key, default)
        return float(val) if val is not None else float(default)
    except Exception:
        return float(default)


def _bb(close):
    bb = BollingerBands(close=close, window=20, window_dev=2)
    return bb.bollinger_mavg(), bb.bollinger_hband(), bb.bollinger_lband()


def _atr(df, period=14):
    pc = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - pc).abs(),
            (df["low"] - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period).mean()


def _base_result(reason, direction="NEUTRAL"):
    return {
        "direction": direction,
        "trigger": False,
        "slope_strength": 0.0,
        "dist_mid_atr": 0.0,
        "m5_trend": "NEUTRAL",
        "m15_trend": "NEUTRAL",
        "impulse": False,
        "reason": reason,
    }


def _prepare(df):
    df = df.copy()
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["bb_mid"], df["bb_up"], df["bb_low"] = _bb(df["close"])
    df["atr"] = _atr(df)
    return df


def _trend_state(df, slope_bars, min_slope, price_vs_mid=True):
    """Arah dari kemiringan mid BB + alignment MA5/MA10 (+ posisi harga vs mid)."""
    close = float(df["close"].iloc[-1])
    mid_now = float(df["bb_mid"].iloc[-1])
    atr_now = float(df["atr"].iloc[-1])
    if not (mid_now > 0 and atr_now > 0):
        return "NEUTRAL", 0.0, close, mid_now, atr_now
    slope_raw = (float(df["bb_mid"].iloc[-1]) - float(df["bb_mid"].iloc[-1 - slope_bars])) / slope_bars
    slope_strength = slope_raw / max(atr_now, 0.01)
    ma5 = float(df["ma5"].iloc[-1])
    ma10 = float(df["ma10"].iloc[-1])

    up = slope_strength > min_slope and ma5 > ma10
    down = slope_strength < -min_slope and ma5 < ma10
    if price_vs_mid:
        up = up and close >= mid_now
        down = down and close <= mid_now
    if up:
        return "BUY", slope_strength, close, mid_now, atr_now
    if down:
        return "SELL", slope_strength, close, mid_now, atr_now
    return "NEUTRAL", slope_strength, close, mid_now, atr_now


def analyze_from_df(df_m5, df_m15):
    """Hitung state BBMA dari dataframe M5 & M15 (kolom ohlc dari MT5 rates)."""
    reentry_atr = _cfg("bbma_reentry_atr", 1.5)
    anti_chase_atr = _cfg("bbma_anti_chase_atr", 2.0)
    impulse_bars = int(_cfg("bbma_impulse_bars", 10))
    slope_bars = int(_cfg("bbma_slope_bars", 5))
    min_slope = _cfg("bbma_min_slope", 0.02)

    if df_m5 is None or df_m15 is None or len(df_m5) < 60 or len(df_m15) < 40:
        return _base_result("BBMA: data M5/M15 tidak cukup")

    try:
        m5 = _prepare(df_m5)
        m15 = _prepare(df_m15)

        m5_trend, slope5, close5, mid5, atr5 = _trend_state(m5, slope_bars, min_slope, price_vs_mid=True)
        m15_trend, _slope15, close15, mid15, atr15 = _trend_state(m15, slope_bars, min_slope, price_vs_mid=True)

        dist_mid_atr = abs(close5 - mid5) / max(atr5, 0.01)

        # Impulse: bar terakhir menyentuh/menembus band luar (momen sebelum reentry)
        tail = m5.tail(impulse_bars)
        impulse_up = bool((tail["high"] >= tail["bb_up"]).any())
        impulse_dn = bool((tail["low"] <= tail["bb_low"]).any())

        if m5_trend == "NEUTRAL":
            reason = f"BBMA: trend M5 lemah (slope {slope5:+.2f} ATR/bar)"
            return _base_result(reason)
        if m15_trend == "NEUTRAL":
            reason = "BBMA: M15 tidak konfirmasi (mid BB M15 datar/posisi ambigu)"
            return _base_result(reason)
        if m5_trend != m15_trend:
            reason = f"BBMA: M5 {m5_trend} vs M15 {m15_trend} - wajib searah"
            out = _base_result(reason)
            out["m5_trend"] = m5_trend
            out["m15_trend"] = m15_trend
            out["slope_strength"] = round(float(slope5), 4)
            out["dist_mid_atr"] = round(float(dist_mid_atr), 3)
            return out

        direction = m5_trend
        out = _base_result("", direction)
        out["m5_trend"] = m5_trend
        out["m15_trend"] = m15_trend
        out["slope_strength"] = round(float(slope5), 4)
        out["dist_mid_atr"] = round(float(dist_mid_atr), 3)

        if dist_mid_atr > anti_chase_atr:
            out["reason"] = (
                f"BBMA anti-chase: harga {dist_mid_atr:.1f}xATR dari mid BB "
                f"(>{anti_chase_atr:.1f}) - tunggu pullback"
            )
            return out

        impulse = impulse_up if direction == "BUY" else impulse_dn
        out["impulse"] = impulse
        if not impulse:
            out["reason"] = (
                f"BBMA: belum ada impulse {direction} menyentuh BB "
                f"dalam {impulse_bars} bar terakhir - tunggu momentum dulu"
            )
            return out

        if dist_mid_atr > reentry_atr:
            out["reason"] = (
                f"BBMA reentry belum: harga {dist_mid_atr:.1f}xATR dari mid BB "
                f"(<= {reentry_atr:.1f} ATR) - tunggu pullback ke MA"
            )
            return out

        out["trigger"] = True
        out["reason"] = (
            f"BBMA reentry {direction}: M5/M15 searah, impulse terdeteksi, "
            f"harga {dist_mid_atr:.1f}xATR dari mid BB, "
            f"slope {out['slope_strength']:+.2f} ATR/bar"
        )
        return out
    except Exception as exc:
        return _base_result(f"BBMA: hitung gagal ({exc})")


def analyze(symbol=None):
    """Ambil data MT5 (M5 + M15) lalu hitung state BBMA."""
    import MetaTrader5 as mt5

    if symbol is None:
        try:
            from app.config.settings import get_trade_config
            symbol = get_trade_config("symbol", "XAUUSDc")
        except Exception:
            symbol = "XAUUSDc"

    try:
        rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 200)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
    except Exception as exc:
        return _base_result(f"BBMA: fetch MT5 gagal ({exc})")

    df_m5 = pd.DataFrame(rates_m5) if rates_m5 is not None else None
    df_m15 = pd.DataFrame(rates_m15) if rates_m15 is not None else None
    return analyze_from_df(df_m5, df_m15)
