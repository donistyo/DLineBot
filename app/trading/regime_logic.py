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
    # Strict EMA: close > ema20 > ema50 -> UP, close < ema20 < ema50 -> DOWN
    if close > ema20 > ema50:
        ema_dir = "UP"
    elif close < ema20 < ema50:
        ema_dir = "DOWN"
    elif adx >= 40 and ema20 > ema50:
        # ADX sangat kuat + EMA20 > EMA50 -> UP (pullback tapi trend masih up)
        ema_dir = "UP"
    elif adx >= 40 and ema20 < ema50:
        # ADX sangat kuat + EMA20 < EMA50 -> DOWN (pullback tapi trend masih down)
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


def multi_tf_decision(
    regime_m5: Regime,
    regime_m15: Regime,
    signal_direction: str,
    gate_normal: float = 2.0,
    gate_early: float = 1.5,
    early_min_m5_adx: float = 25.0,
    early_sideways: bool = False,
):
    """
    Return: (allow: bool, alignment_score: float, reason: str, entry_mode: str)
    entry_mode: "normal" | "early" | "early_sideways" | "block"

    Aturan:
    - JALUR NORMAL: total skor (M5 + M15) >= gate_normal (2.0) -> allow
        Hanya lolos: TREND+TREND (kedua TF ADX>=30 searah sinyal)
    - JALUR ENTRY AWAL (Mode A): M5 ADX >= early_min_m5_adx (25) + EMA M5
        tersusun searah sinyal + M15 WEAK searah sinyal (EMA20/50 tersusun)
        -> allow dengan entry_mode "early" (skor entry naik ke
        min_early_score di live_engine; exhaustion pakai
        early_exhaustion_atr di decision_engine)
    - JALUR EARLY-SIDEWAYS (eksperimen, flag early_sideways_entry):
        M15 SIDEWAYS + M5 TREND searah + ADX >= early_min_m5_adx -> allow
        entry_mode "early_sideways" (butuh M1 momentum searah eksplisit
        + skor >= min_early_score)
    - TF MELAWAN arah sinyal -> block keras
    - Sisanya -> block
    """
    score_m5 = _tf_score(regime_m5, signal_direction)
    score_m15 = _tf_score(regime_m15, signal_direction)
    total = score_m5 + score_m15

    def _melawan(regime: Regime) -> bool:
        return regime.trend is not None and regime.trend != signal_direction

    blocked = _melawan(regime_m5) or _melawan(regime_m15)

    if not blocked and total >= gate_normal:
        allow = True
        entry_mode = "normal"
    elif (
        not blocked
        and regime_m5.trend == signal_direction
        and regime_m5.adx >= early_min_m5_adx
        and regime_m15.mode == "WEAK"
        and regime_m15.trend == signal_direction
    ):
        allow = True
        entry_mode = "early"
    elif (
        early_sideways
        and not blocked
        and regime_m5.mode == "TREND"
        and regime_m5.trend == signal_direction
        and regime_m5.adx >= early_min_m5_adx
        and regime_m15.mode == "SIDEWAYS"
        and regime_m15.trend is None
    ):
        allow = True
        entry_mode = "early_sideways"
    else:
        allow = False
        entry_mode = "block"

    if entry_mode == "early":
        _tag = " [ENTRY AWAL]"
    elif entry_mode == "early_sideways":
        _tag = " [EARLY-SIDEWAYS]"
    else:
        _tag = ""

    reason = (
        f"M5={regime_m5.mode}({regime_m5.trend},adx={regime_m5.adx:.1f}) "
        f"M15={regime_m15.mode}({regime_m15.trend},adx={regime_m15.adx:.1f}) "
        f"score={total:.1f}/{gate_normal:.1f}{_tag}"
    )

    return allow, total, reason, entry_mode
