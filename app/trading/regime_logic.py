"""
Logika regime classification 3-tingkat (SIDEWAYS / WEAK / TREND)
+ multi-TF alignment dengan bobot untuk decision_engine.py

Menggantikan klasifikasi biner ADX>=30 (TREND) vs ADX<30 (SIDEWAYS)
yang membuang informasi arah dari struktur EMA saat ADX masih rendah.
"""

from dataclasses import dataclass
from typing import Optional

# ── Ambang batas ──────────────────────────────────────────────
ADX_WEAK_MIN = 15    # di bawah ini: EMA order diabaikan, selalu SIDEWAYS
ADX_TREND_MIN = 30   # di atas/sama ini: TREND penuh (perilaku lama)
                      # di antara keduanya: WEAK (baru)


@dataclass
class Regime:
    mode: str                 # "SIDEWAYS" | "WEAK" | "TREND"
    trend: Optional[str]      # "UP" | "DOWN" | None
    adx: float


def classify_regime(close: float, ema20: float, ema50: float, adx: float) -> Regime:
    """
    Klasifikasi regime per timeframe, gabungan struktur EMA + kekuatan ADX.
    EMA menentukan ARAH, ADX menentukan KEKUATAN/TINGKAT KEPERCAYAAN.
    """
    if close > ema20 > ema50:
        ema_dir = "UP"
    elif close < ema20 < ema50:
        ema_dir = "DOWN"
    else:
        ema_dir = None  # EMA belum tersusun rapi -> tidak ada arah jelas

    # ADX sangat rendah: abaikan EMA, anggap noise
    if adx < ADX_WEAK_MIN:
        return Regime(mode="SIDEWAYS", trend=None, adx=adx)

    # EMA tidak jelas arahnya -> tetap SIDEWAYS berapapun ADX-nya
    if ema_dir is None:
        return Regime(mode="SIDEWAYS", trend=None, adx=adx)

    # ADX kuat + arah jelas -> TREND penuh (perilaku lama, tidak berubah)
    if adx >= ADX_TREND_MIN:
        return Regime(mode="TREND", trend=ema_dir, adx=adx)

    # Di antara ADX_WEAK_MIN dan ADX_TREND_MIN, arah EMA jelas -> WEAK (baru)
    return Regime(mode="WEAK", trend=ema_dir, adx=adx)


def strong_trend(regime_m5: Regime, signal_direction: str) -> bool:
    """
    Dipakai bersama oleh guard EMA50, Liquidity guard, dan Rebound guard.
    Tetap M5-only, tidak berubah dari kesepakatan sebelumnya.
    """
    return regime_m5.mode == "TREND" and regime_m5.trend == signal_direction


# ── Multi-TF alignment dengan bobot ──────────────────────────
# Skor per timeframe:
#   TREND searah  -> 1.0
#   WEAK searah   -> 0.5
#   SIDEWAYS      -> 0.0
#   TREND/WEAK melawan arah sinyal -> 0.0 (tetap wajib searah, tidak ada exception)

def _tf_score(regime: Regime, signal_direction: str) -> float:
    if regime.trend != signal_direction:
        return 0.0
    if regime.mode == "TREND":
        return 1.0
    if regime.mode == "WEAK":
        return 0.5
    return 0.0


def multi_tf_decision(regime_m5: Regime, regime_m15: Regime, signal_direction: str):
    """
    Return: (allow: bool, alignment_score: float, reason: str)

    Aturan:
    - Total skor (M5 + M15) >= 1.0 -> izinkan
        Kombinasi yang lolos: TREND+TREND (2.0), TREND+WEAK (1.5), WEAK+TREND (1.5),
        WEAK+WEAK (1.0)
    - Total skor < 1.0 -> block
        Hanya diblokir jika salah satu TF SIDEWAYS atau melawan arah.
    - Salah satu TF melawan arah sinyal -> skor TF itu 0, hampir pasti
      total < 1.0 -> block (tidak ada exception untuk WEAK yang melawan arah)
    """
    score_m5 = _tf_score(regime_m5, signal_direction)
    score_m15 = _tf_score(regime_m15, signal_direction)
    total = score_m5 + score_m15

    allow = total >= 1.0

    reason = (
        f"M5={regime_m5.mode}({regime_m5.trend},adx={regime_m5.adx:.1f}) "
        f"M15={regime_m15.mode}({regime_m15.trend},adx={regime_m15.adx:.1f}) "
        f"score={total:.1f}/2.0"
    )

    return allow, total, reason
