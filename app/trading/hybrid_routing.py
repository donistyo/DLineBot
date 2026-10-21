"""Routing strategi SCALP/ZONE untuk mode hybrid.

Dipisah sebagai fungsi murni supaya routing + hysteresis ADX bisa
dites tanpa menginisialisasi LiveEngine/MT5.
"""


def hybrid_strategy_state(mode, adx, state=None, zone_max=20.0, scalp_resume=25.0):
    """Tentukan strategi efektif.

    - mode selain 'hybrid' -> mode apa adanya.
    - ADX < zone_max        -> ZONE (market ranging).
    - ADX > scalp_resume    -> SCALP (trend layak ditradingkan).
    - di antara dua ambang  -> pertahankan state terakhir (hysteresis).
    - belum ada state       -> SCALP jika ADX >= scalp_resume, selain itu ZONE.
    """
    mode = str(mode or "scalp").lower()
    if mode != "hybrid":
        return mode
    adx = float(adx or 0)
    if state not in ("scalp", "zone"):
        return "scalp" if adx >= scalp_resume else "zone"
    if state == "scalp" and adx < zone_max:
        return "zone"
    if state == "zone" and adx > scalp_resume:
        return "scalp"
    return state
