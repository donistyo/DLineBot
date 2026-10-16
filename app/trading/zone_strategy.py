"""
Zone/Reversal entry strategy (pengganti scalp trend-following).

Entry saat harga menyentuh zona support/resistance hasil deteksi
swing (M15 primer, M5 sekunder) dengan konfirmasi RSI + candle
rejection. TIDAK butuh tren - dirancang untuk kondisi ranging
yang menyebabkan scalp engine 0 entry seharian.

Proteksi yang DIPERTAHANKAN:
- RSI keras: BUY diblokir RSI > zone_rsi_hard (80), SELL < 20
- Zona tembus (close melewati tepi zona > zone_pierce_atr) -> zona dibuang
- Chase: bounce dari zona sudah > zone_chase_atr -> telat, skip
- Posisi range ekstrem (pos > zone_pos_max utk BUY) -> blokir
- Daily risk, equity floor, session, margin bebas, max positions,
  cooldown re-entry, spacing searah: TETAP dari pipeline lama
- Layer entry: dual 2 fixed (konservatif)
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Zone:
    kind: str          # "SUPPORT" | "RESISTANCE"
    lo: float
    hi: float
    idx: int           # index bar asal (untuk urutan recency)


def _cfg(key, default):
    try:
        from app.config.settings import get_trade_config
        v = get_trade_config(key, default)
        return float(v) if v is not None else float(default)
    except Exception:
        return float(default)


def find_zones(df, atr, lookback=40, band_atr=0.30, merge_atr=0.8, violate_atr=0.6):
    """
    Deteksi zona S/R dari swing fractal N bar terakhir.
    Swing high: high[i] >= high tetangga 2 bar kiri & kanan.
    Zona = [swing - band*atr, swing + band*atr]; merge yang overlap.
    Zona yang sudah ditembus close melewati > violate*atr dibuang.
    Return: (supports, resistances) urut paling baru.
    """
    if df is None or len(df) < lookback // 2 or atr <= 0:
        return [], []

    highs = [float(x) for x in df["high"].tolist()[-lookback:]]
    lows = [float(x) for x in df["low"].tolist()[-lookback:]]
    n = len(highs)
    band = band_atr * atr

    raw_sup, raw_res = [], []
    for i in range(2, n - 2):
        if highs[i] >= max(highs[i - 2], highs[i - 1]) and highs[i] >= max(highs[i + 1], highs[i + 2]):
            raw_res.append(Zone("RESISTANCE", highs[i] - band, highs[i] + band, i))
        if lows[i] <= min(lows[i - 2], lows[i - 1]) and lows[i] <= min(lows[i + 1], lows[i + 2]):
            raw_sup.append(Zone("SUPPORT", lows[i] - band, lows[i] + band, i))

    def _merge(zones):
        zones.sort(key=lambda z: z.lo)
        merged = []
        for z in zones:
            if merged and z.lo <= merged[-1].hi + merge_atr * atr:
                merged[-1] = Zone(z.kind, merged[-1].lo, max(merged[-1].hi, z.hi), max(merged[-1].idx, z.idx))
            else:
                merged.append(z)
        return merged

    close_last = float(df["close"].iloc[-1])
    out_sup, out_res = [], []
    for z in _merge(raw_sup):
        if close_last < z.lo - violate_atr * atr:
            continue  # support tembus -> tidak valid
        out_sup.append(z)
    for z in _merge(raw_res):
        if close_last > z.hi + violate_atr * atr:
            continue  # resistansi tembus -> tidak valid
        out_res.append(z)

    out_sup.sort(key=lambda z: z.idx, reverse=True)
    out_res.sort(key=lambda z: z.idx, reverse=True)
    return out_sup[:2], out_res[:2]


def analyze_from_dfs(df_m5, df_m15):
    """
    Keputusan zone dari dataframe M5/M15 yang sudah berindikator.
    Return dict: direction, trigger, reason, zone, rsi, atr, dist_atr,
    bounce_atr, pos_pct, entry_mode="zone".
    """
    lookback = int(_cfg("zone_lookback", 40))
    band_atr = _cfg("zone_band_atr", 0.30)
    touch_atr = _cfg("zone_touch_atr", 0.35)
    pierce_atr = _cfg("zone_pierce_atr", 0.5)
    chase_atr = _cfg("zone_chase_atr", 1.5)
    rsi_buy_max = _cfg("zone_rsi_buy_max", 45)
    rsi_sell_min = _cfg("zone_rsi_sell_min", 55)
    pos_max = _cfg("zone_pos_max", 0.80)
    pos_min = _cfg("zone_pos_min", 0.20)

    base = {
        "direction": "NEUTRAL",
        "trigger": False,
        "entry_mode": "zone",
        "zone": None,
        "rsi": None,
        "atr": None,
        "dist_atr": None,
        "bounce_atr": None,
        "pos_pct": None,
    }

    try:
        last = df_m5.iloc[-1]
        close = float(last["close"])
        op = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])
        rsi = float(last.get("RSI", 50) or 50)
        atr = float(last.get("ATR", 0) or 0)
        if atr <= 0 and df_m15 is not None and len(df_m15):
            atr = float(df_m15.iloc[-1].get("ATR", 0) or 0)
        base["rsi"] = rsi
        base["atr"] = atr
        if atr <= 0:
            base["reason"] = "ATR tidak tersedia"
            return base

        sup, res = find_zones(df_m15, atr, lookback=lookback, band_atr=band_atr)
        sup5, res5 = find_zones(df_m5, atr, lookback=lookback, band_atr=band_atr)
        supports = sup + sup5
        resistances = res + res5

        # posisi harga dalam range swing M15
        try:
            hh = float(df_m15["high"].tail(lookback).max())
            ll = float(df_m15["low"].tail(lookback).min())
            pos_pct = (close - ll) / max(hh - ll, 0.01)
        except Exception:
            pos_pct = None
        base["pos_pct"] = round(pos_pct, 3) if pos_pct is not None else None

        body = abs(close - op)
        lower_wick = min(op, close) - low
        upper_wick = high - max(op, close)
        bull_candle = close > op
        bear_candle = close < op

        best = None  # (priority, setup_dict)

        for z in supports:
            dist = (close - z.hi) / atr          # <=0 saat menyentuh/di bawah tepi atas
            if dist > touch_atr:
                continue                          # belum sampai
            if dist < -pierce_atr:
                continue                          # tembus jauh ke bawah
            bounce = (close - z.lo) / atr
            if bounce > chase_atr:
                continue                          # sudah memantul jauh -> telat
            if rsi > rsi_buy_max:
                continue                          # RSI belum oversold cukup
            if pos_pct is not None and pos_pct > pos_max:
                continue                          # terlalu dekat high range
            confirm = bull_candle or (body > 0 and lower_wick >= body)
            if not confirm:
                continue
            setup = {
                "direction": "BUY",
                "trigger": True,
                "zone": {"kind": z.kind, "lo": round(z.lo, 2), "hi": round(z.hi, 2)},
                "dist_atr": round(dist, 2),
                "bounce_atr": round(bounce, 2),
                "reason": (
                    f"Zone {z.kind} {z.lo:.2f}-{z.hi:.2f} disentuh (dist {dist:.2f}xATR), "
                    f"RSI {rsi:.1f}, candle {'bull' if bull_candle else 'reject bawah'}"
                ),
            }
            pri = abs(dist)
            if best is None or pri < best[0]:
                best = (pri, setup)

        for z in resistances:
            dist = (z.lo - close) / atr          # <=0 saat menyentuh/di atas tepi bawah
            if dist > touch_atr:
                continue
            if dist < -pierce_atr:
                continue                          # tembus jauh ke atas
            bounce = (z.hi - close) / atr
            if bounce > chase_atr:
                continue
            if rsi < rsi_sell_min:
                continue
            if pos_pct is not None and pos_pct < pos_min:
                continue
            confirm = bear_candle or (body > 0 and upper_wick >= body)
            if not confirm:
                continue
            setup = {
                "direction": "SELL",
                "trigger": True,
                "zone": {"kind": z.kind, "lo": round(z.lo, 2), "hi": round(z.hi, 2)},
                "dist_atr": round(dist, 2),
                "bounce_atr": round(bounce, 2),
                "reason": (
                    f"Zone {z.kind} {z.lo:.2f}-{z.hi:.2f} disentuh (dist {dist:.2f}xATR), "
                    f"RSI {rsi:.1f}, candle {'bear' if bear_candle else 'reject atas'}"
                ),
            }
            pri = abs(dist)
            if best is None or pri < best[0]:
                best = (pri, setup)

        if best is None:
            sup_n, res_n = len(supports), len(resistances)
            base["reason"] = (
                f"Tidak ada zona tersentuh (support {sup_n}, resistance {res_n}, "
                f"RSI {rsi:.1f}, pos {pos_pct:.0%}*)" if pos_pct is not None else
                f"Tidak ada zona tersentuh (RSI {rsi:.1f})"
            )
            return base

        base.update(best[1])
        return base

    except Exception as e:
        base["reason"] = f"Zone analyze gagal: {e}"
        return base


def analyze(symbol=None):
    """Load M5/M15 + indikator, lalu analyze_from_dfs."""
    from app.data.collector import Collector
    from app.indicators.engine import IndicatorEngine
    from app.preprocessing.cleaner import DataCleaner

    collector = Collector()
    indicator = IndicatorEngine()
    cleaner = DataCleaner()

    def _load(tf):
        # 300 bar: EMA200 warmup dibuang cleaner, sisa ~100 bar
        # cukup untuk lookback zone 40.
        df = collector.load(symbol=symbol, timeframe=tf, bars=300)
        df = indicator.calculate(df)
        df = cleaner.clean(df)
        return df

    df_m5 = _load("M5")
    df_m15 = _load("M15")
    return analyze_from_dfs(df_m5, df_m15)
