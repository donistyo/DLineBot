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

import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ta.volatility import BollingerBands

# =====================================
# Gate konfirmasi candle (c4):
#   c1 = candle TERAKHIR TERTUTUP arah tren (flip-proof, instan)
#   c3 = candle terbentuk sedang berbalik (forming) - butuh stabil
#        >= bbma_confirm_min_seconds agar tidak kena flip-flop wick
# (flare c3 flip-flop: 23-26% candle M5 pass lalu tutup melawan).
# State + event log premium: runtime/bbma_gate_log.jsonl
#   blocked   = mulai menahan sinyal (snapshot dist/slope)
#   triggered = lolos gate (held_s / held_cycles = lama menahan)
#   released  = sinyal hilang saat menahan (radius lewat / trend dll)
# =====================================
GATE_LOG_PATH = os.path.join("runtime", "bbma_gate_log.jsonl")

_gate_state = {}


def reset_gate_state():
    """Bersihkan state gate (dipakai test & restart)."""
    _gate_state.clear()


def _log_gate(evt):
    if not GATE_LOG_PATH:
        return
    try:
        with open(GATE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _release_state(reason="", dist=None, slope=None):
    """Lepas semua state tertahan -> event released (data premium)."""
    now = time.time()
    for key in list(_gate_state.keys()):
        st = _gate_state.pop(key)
        _log_gate({
            "t": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "released",
            "dir": key[0],
            "ref": key[1],
            "held_s": round(now - st["start"], 1),
            "held_cycles": st["cycles"],
            "reason": reason,
            "dist": dist,
            "slope": slope,
        })


def _confirm_gate(m5, direction, out):
    """Gate konfirmasi candle c4. Mengisi out (trigger/blocked + hold fields)."""
    now = time.time()
    dist = out.get("dist_mid_atr")
    slope = out.get("slope_strength")
    confirm_on = _cfg("bbma_candle_confirm", 1) > 0
    if not confirm_on:
        _release_state("bbma_candle_confirm=0 (flag dimatikan)", dist, slope)
        out["trigger"] = True
        out["confirm_hold_s"] = 0.0
        out["confirm_hold_cycles"] = 0
        return out

    closed = m5.iloc[-2]
    forming = m5.iloc[-1]
    ref = int(closed["time"]) if "time" in m5.columns else int(m5.index[-2])
    key = (direction, ref)
    T = _cfg("bbma_confirm_min_seconds", 120)

    # Evict state lain (arah/ref bar berubah) -> released
    for k in list(_gate_state.keys()):
        if k != key:
            st = _gate_state.pop(k)
            _log_gate({
                "t": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": "released",
                "dir": k[0],
                "ref": k[1],
                "held_s": round(now - st["start"], 1),
                "held_cycles": st["cycles"],
                "reason": "konteks berubah (arah/ref bar)",
                "dist": dist,
                "slope": slope,
            })

    st = _gate_state.get(key)
    if st is None:
        st = {"start": now, "pass_since": None, "cycles": 0}
        _gate_state[key] = st
        _log_gate({
            "t": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "blocked",
            "dir": direction,
            "ref": ref,
            "held_s": 0.0,
            "held_cycles": 0,
            "reason": "mulai menahan: radius reentry OK, tunggu konfirmasi candle",
            "dist": dist,
            "slope": slope,
        })
        # Batasi jumlah state tertahan
        if len(_gate_state) > 8:
            oldest = min(_gate_state, key=lambda k: _gate_state[k]["start"])
            stx = _gate_state.pop(oldest)
            _log_gate({
                "t": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": "released",
                "dir": oldest[0],
                "ref": oldest[1],
                "held_s": round(now - stx["start"], 1),
                "held_cycles": stx["cycles"],
                "reason": "state evicted (kapasitas)",
                "dist": dist,
                "slope": slope,
            })
    st["cycles"] += 1

    up = direction == "BUY"
    c1 = (closed["close"] > closed["open"]) if up else (closed["close"] < closed["open"])
    c3 = (forming["close"] > closed["close"]) if up else (forming["close"] < closed["close"])

    def _fire(how):
        held = round(now - st["start"], 1)
        _gate_state.pop(key, None)
        _log_gate({
            "t": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "triggered",
            "dir": direction,
            "ref": ref,
            "held_s": held,
            "held_cycles": st["cycles"],
            "reason": how,
            "dist": dist,
            "slope": slope,
        })
        out["trigger"] = True
        out["confirm_hold_s"] = held
        out["confirm_hold_cycles"] = st["cycles"]
        out["confirm_how"] = how
        return out

    if c1:
        return _fire("closed candle arah tren (c1)")

    if c3:
        if st["pass_since"] is None:
            st["pass_since"] = now
        pass_dur = now - st["pass_since"]
        if T <= 0 or pass_dur >= T:
            return _fire(f"forming berbalik stabil {pass_dur:.0f}s (c3)")
        out["reason"] = (
            f"BBMA: konfirmasi candle belum stabil (forming berbalik {pass_dur:.0f}s "
            f"dari {T:.0f}s) - tunggu"
        )
        out["_keep_state"] = True
        out["confirm_hold_s"] = round(now - st["start"], 1)
        out["confirm_hold_cycles"] = st["cycles"]
        return out

    st["pass_since"] = None
    out["reason"] = (
        f"BBMA: konfirmasi candle belum ada - closed candle terakhir "
        f"{'bearish' if up else 'bullish'} dan forming belum berbalik "
        f"arah {direction} - tunggu M5 konfirmasi"
    )
    out["_keep_state"] = True
    out["confirm_hold_s"] = round(now - st["start"], 1)
    out["confirm_hold_cycles"] = st["cycles"]
    return out


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


def _day_position(m5):
    """Posisi harga (0..1) dalam high-low hari sesi (tanggal UTC bar terakhir).

    Dipakai aturan blokir BUY di puncak harian (bbma_day_high_pos).
    Return None jika data hari tidak memadai (mis. sesi baru buka <5 bar).
    """
    try:
        if "time" in m5.columns:
            tcol = m5["time"]
            if tcol.dtype.kind in "iu":
                t = pd.to_datetime(tcol, unit="s")
            else:
                t = pd.to_datetime(tcol)
            day = m5[t.dt.date == t.iloc[-1].date()]
        else:
            day = m5
        if len(day) < 5:
            return None
        hi = float(day["high"].max())
        lo = float(day["low"].min())
        if hi <= lo:
            return None
        px = float(m5["close"].iloc[-1])
        return (px - lo) / (hi - lo)
    except Exception:
        return None


def _crash_cooldown(m5):
    """Deteksi bar crash dalam jendela K bar TERTUTUP terakhir (varian A).

    Trip: range bar > bbma_crash_range_mult x ATR14 Wilder (RMA) yang
    berakhir di bar SEBELUM bar tsb. Bar terakhir (forming) dikecualikan.
    Berlaku BUY & SELL. Tervalidasi 14 hari / 5000 bar M5: menangkap
    tepat 1 entry loser (whipsaw pasca flash-crash) dengan nol winner
    tertangkap; jendela aktif hanya 1,8% bar.
    Return (blocked, max_ratio) - max_ratio = rasio tertinggi di jendela.
    """
    try:
        if _cfg("bbma_crash_cooldown", 1) <= 0:
            return False, None
        k = int(_cfg("bbma_crash_bars", 3))
        mult = _cfg("bbma_crash_range_mult", 3.0)
        n = len(m5)
        if k <= 0 or n < k + 30:
            return False, None
        h = m5["high"].to_numpy(dtype=float)
        lo = m5["low"].to_numpy(dtype=float)
        c = m5["close"].to_numpy(dtype=float)
        pc = np.empty(n)
        pc[0] = c[0]
        pc[1:] = c[:-1]
        tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))
        atr_prev = np.empty(n)
        atr_prev[0] = np.nan
        a = tr[0]
        for i in range(1, n):
            atr_prev[i] = a          # ATR14 Wilder s/d bar i-1
            a = (a * 13.0 + tr[i]) / 14.0
        rng = h - lo
        best = None
        for i in range(n - k - 1, n - 1):   # K bar tertutup terakhir (bar -1 = forming)
            if i < 1 or not np.isfinite(atr_prev[i]) or atr_prev[i] <= 0:
                continue
            ratio = rng[i] / atr_prev[i]
            if best is None or ratio > best:
                best = ratio
        if best is None:
            return False, None
        return best > mult, round(best, 2)
    except Exception:
        return False, None


def _fetch_emergency_exits(lookback_s):
    """ATR_EMERGENCY close dalam lookback detik -> [(epoch, dir)] ascending.

    dir = arah POSISI = kebalikan tipe deal OUT (posisi BUY ditutup deal SELL
    dan sebaliknya). Dipanggil dari _loss_streak_block; gagal fetch -> [].
    """
    import MetaTrader5 as mt5

    now = time.time()
    frm = datetime.fromtimestamp(now - lookback_s, timezone.utc).replace(tzinfo=None)
    to = datetime.fromtimestamp(now, timezone.utc).replace(tzinfo=None)
    deals = mt5.history_deals_get(frm, to) or []
    out = []
    for d in deals:
        if d.entry != mt5.DEAL_ENTRY_OUT:
            continue
        if "EMERGENCY" not in (d.comment or "").upper():
            continue
        dirn = "SELL" if d.type == mt5.DEAL_TYPE_BUY else "BUY"
        out.append((int(d.time), dirn))
    out.sort()
    return out


def _streak_until(exits, direction, count, window_s, block_s):
    """block_until (epoch) untuk direction dari urutan emergency exits.

    Trigger: >= count emergency searah beruntun, gap antar exit <= window_s
    (streak = run searah; exit beda arah / gap lewat -> run reset).
    Blokir arah tsb s/d exit terakhir streak + block_s. State murni fungsi
    exits (deterministik, dipakai unit test dgn exits sintetis).
    Return (until, cnt_streak) - cnt = panjang run terakhir utk reason.
    """
    until = 0
    cnt = 0
    run_dir, run_n, run_last = None, 0, 0
    for t, d in exits:
        if d == run_dir and t - run_last <= window_s:
            run_n += 1
        else:
            run_dir, run_n = d, 1
        run_last = t
        if run_n >= count and d == direction:
            until = max(until, t + block_s)
            cnt = run_n
    return until, cnt


def _loss_streak_block(direction, exits=None, now=None):
    """Loss-streak cooldown: blokir re-entry arah streak setelah >= count
    emergency close searah beruntun dalam window (mis. 2x SELL emergency
    <= 60 menit) -> cooldown arah itu (mis. 45 menit, > reentry normal 10m).

    Validasi 20 hari / 170 pair (2 Okt - 6 Okt era BBMA dominan): 2 streak
    aktual, simulasi B=30/45/60 semuanya net positif (+6.2 / +3.5 / +10.0),
    korban max 1 winner (+2.7). fail-open (lolos) bila fetch/gagal hitung.
    Return (blocked, until, cnt).
    """
    try:
        if _cfg("bbma_loss_streak_block", 1) <= 0:
            return False, 0, 0
        count = int(_cfg("bbma_loss_streak_count", 2))
        win_min = _cfg("bbma_loss_streak_window_min", 60)
        blk_min = _cfg("bbma_loss_streak_cooldown_min", 45)
        if count < 2 or win_min <= 0 or blk_min <= 0:
            return False, 0, 0
        now = time.time() if now is None else float(now)
        if exits is None:
            exits = _fetch_emergency_exits((win_min + blk_min + 10) * 60)
        until, cnt = _streak_until(exits, direction, count, win_min * 60, blk_min * 60)
        return (until > now), until, cnt
    except Exception:
        return False, 0, 0


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
            out = _base_result(reason)
        elif m15_trend == "NEUTRAL":
            reason = "BBMA: M15 tidak konfirmasi (mid BB M15 datar/posisi ambigu)"
            out = _base_result(reason)
        elif m5_trend != m15_trend:
            reason = f"BBMA: M5 {m5_trend} vs M15 {m15_trend} - wajib searah"
            out = _base_result(reason)
            out["m5_trend"] = m5_trend
            out["m15_trend"] = m15_trend
            out["slope_strength"] = round(float(slope5), 4)
            out["dist_mid_atr"] = round(float(dist_mid_atr), 3)
        else:
            direction = m5_trend
            impulse = impulse_up if direction == "BUY" else impulse_dn
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
            elif not impulse:
                out["reason"] = (
                    f"BBMA: belum ada impulse {direction} menyentuh BB "
                    f"dalam {impulse_bars} bar terakhir - tunggu momentum dulu"
                )
            elif dist_mid_atr > reentry_atr:
                out["impulse"] = True
                out["reason"] = (
                    f"BBMA reentry belum: harga {dist_mid_atr:.1f}xATR dari mid BB "
                    f"(<= {reentry_atr:.1f} ATR) - tunggu pullback ke MA"
                )
            else:
                crashed, crash_ratio = _crash_cooldown(m5)
                if crashed:
                    out["impulse"] = True
                    out["crash_ratio"] = crash_ratio
                    out["reason"] = (
                        f"BBMA: crash bar dalam {int(_cfg('bbma_crash_bars', 3))} bar "
                        f"terakhir (range {crash_ratio:.1f}x ATR14 sebelumnya > "
                        f"{_cfg('bbma_crash_range_mult', 3.0):.1f}) - tunggu pasar stabil"
                    )
                else:
                    st_blk, st_until, st_cnt = _loss_streak_block(direction)
                    if st_blk:
                        out["impulse"] = True
                        out["loss_streak"] = st_cnt
                        out["reason"] = (
                            f"BBMA: loss-streak {st_cnt}x emergency {direction} beruntun "
                            f"(window {int(_cfg('bbma_loss_streak_window_min', 60))}m) - "
                            f"cooldown {int(_cfg('bbma_loss_streak_cooldown_min', 45))}m "
                            f"s/d {time.strftime('%H:%M:%S', time.localtime(st_until))}"
                        )
                    else:
                        posd = _day_position(m5) if direction == "BUY" else None
                        out["day_pos_pct"] = round(posd, 3) if posd is not None else None
                        if (posd is not None and _cfg("bbma_day_high_block", 1)
                                and posd > _cfg("bbma_day_high_pos", 0.80)):
                            out["impulse"] = True
                            out["reason"] = (
                                f"BBMA: harga di puncak harian (pos {posd * 100:.0f}% rentang "
                                f"high-low hari) - tunggu pullback"
                            )
                        else:
                            # Lolos semua gate pasar -> gate konfirmasi candle (c4)
                            out["impulse"] = True
                            out = _confirm_gate(m5, direction, out)
                            if out.get("trigger"):
                                hold = out.get("confirm_hold_s", 0.0)
                                how = out.get("confirm_how", "")
                                out["reason"] = (
                                    f"BBMA reentry {direction}: M5/M15 searah, impulse terdeteksi, "
                                    f"harga {dist_mid_atr:.1f}xATR dari mid BB, "
                                    f"slope {out['slope_strength']:+.2f} ATR/bar, "
                                    f"konfirmasi OK ({how}"
                                    + (f", tahan {hold:.0f}s/{out.get('confirm_hold_cycles', 0)} cycle"
                                       if hold > 0 else "")
                                    + ")"
                                )

        # Sinyal hilang saat menahan konfirmasi -> released (kecuali state
        # memang sedang ditahan oleh gate konfirmasi sendiri / baru dibuat)
        if not out.get("trigger") and not out.pop("_keep_state", False):
            _release_state(
                out.get("reason", ""),
                out.get("dist_mid_atr"),
                out.get("slope_strength"),
            )
        return out
    except Exception as exc:
        # Gangguan sistem (fetch/komputasi) bukan alasan pasar:
        # state tertahan TIDAK dirilis agar hold tidak reset sia-sia.
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
