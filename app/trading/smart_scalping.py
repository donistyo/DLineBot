import numpy as np
import pandas as pd
from datetime import datetime


class SmartScalpingEngine:

    def __init__(self, symbol="XAUUSDc", direction_tf="M5"):
        self._last_5 = None
        self._prev_high = None
        self._prev_low = None
        self.symbol = symbol
        self.direction_tf = direction_tf

    def analyze(self, df, last):

        result = {}

        candles = df.tail(10)
        self._last_5 = df.tail(5) if len(df) >= 5 else df

        if len(df) >= 2:
            self._prev_high = float(df.iloc[-2]["high"])
            self._prev_low = float(df.iloc[-2]["low"])

        # =====================================
        # 1. Momentum Engine
        #    Arah sinyal utama diambil dari timeframe lebih besar (M5
        #    default) supaya arah market terbaca lebih stabil, bukan hanya
        #    dari 3 candle M1 yang noise. M1 dipakai engine lain utk timing.
        #    Fallback ke M1 jika data timeframe besar tidak tersedia.
        # =====================================
        momentum = self._momentum_htf() or self._momentum(candles)
        momentum["tf"] = self.direction_tf

        # =====================================
        # Trend Alignment Check
        # Paksa arah sinyal searah trend jika ADX cukup kuat
        # Ambil EMA dari timeframe sama (M5 default)
        # =====================================
        try:
            import MetaTrader5 as mt5
            tf_map = {
                "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            }
            tf_code = tf_map.get(self.direction_tf, mt5.TIMEFRAME_M5)
            rates = mt5.copy_rates_from_pos(self.symbol, tf_code, 0, 200)
            if rates is not None and len(rates) >= 50:
                import pandas as _pd
                htf = _pd.DataFrame(rates)
                htf["close"] = htf["close"].astype(float)
                htf["EMA20"] = htf["close"].ewm(span=20).mean()
                htf["EMA50"] = htf["close"].ewm(span=50).mean()

                htf["diff"] = htf["high"] - htf["low"]
                htf["plus_dm"] = 0.0
                htf["minus_dm"] = 0.0
                for i in range(1, len(htf)):
                    up = htf.iloc[i]["high"] - htf.iloc[i-1]["high"]
                    down = htf.iloc[i-1]["low"] - htf.iloc[i]["low"]
                    htf.iloc[i, htf.columns.get_loc("plus_dm")] = up if up > down and up > 0 else 0
                    htf.iloc[i, htf.columns.get_loc("minus_dm")] = down if down > up and down > 0 else 0
                htf["ATR"] = htf["diff"].ewm(span=14).mean()
                htf["plus_di"] = 100 * (htf["plus_dm"].ewm(span=14).mean() / htf["ATR"])
                htf["minus_di"] = 100 * (htf["minus_dm"].ewm(span=14).mean() / htf["ATR"])
                dx = abs(htf["plus_di"] - htf["minus_di"]) / (htf["plus_di"] + htf["minus_di"]) * 100
                htf["ADX"] = dx.ewm(span=14).mean()

                htf_row = htf.iloc[-1]
                adx = float(htf_row["ADX"])
                close = float(htf_row["close"])
                ema20 = float(htf_row["EMA20"])
                ema50 = float(htf_row["EMA50"])

                if adx > 20 and ema20 > 0 and ema50 > 0:
                    ema_bearish = close < ema20 < ema50
                    ema_bullish = close > ema20 > ema50
                    raw_dir = momentum.get("direction", "NEUTRAL")

                    if ema_bearish and raw_dir == "BUY":
                        momentum["direction"] = "SELL"
                        momentum["trend_override"] = "EMA_BEARISH"
                    elif ema_bullish and raw_dir == "SELL":
                        momentum["direction"] = "BUY"
                        momentum["trend_override"] = "EMA_BULLISH"
        except Exception:
            pass

        result["momentum"] = momentum

        # =====================================
        # 2. Speed Detector
        # =====================================
        speed = self._speed(candles, last)
        result["speed"] = speed

        # =====================================
        # 3. Liquidity Detector
        # =====================================
        liquidity = self._liquidity(candles, last)
        result["liquidity"] = liquidity

        # =====================================
        # 4. Fake Breakout Detector
        # =====================================
        fake_breakout = self._fake_breakout(candles, last)
        result["fake_breakout"] = fake_breakout

        # =====================================
        # 5. Session Detector
        # =====================================
        session = self._session()
        result["session"] = session

        # =====================================
        # 6. Impulse Detector
        # =====================================
        impulse = self._impulse(candles, last)
        result["impulse"] = impulse

        # =====================================
        # 7. Scalping Score
        # =====================================
        score = self._scalping_score(result)
        result["scalp_score"] = score

        # =====================================
        # Referensi harga/trend untuk guard
        # anti-exhaustion (pakai di decision engine)
        # =====================================
        try:
            result["close"] = float(last.get("close", 0) or 0)
            result["ema50"] = float(last.get("EMA50", 0) or 0)
            result["atr"] = float(last.get("ATR", 0) or 0)
        except Exception:
            pass

        # =====================================
        # Range 20 candle terakhir (untuk guard
        # rebound di decision engine)
        # =====================================
        try:
            recent20 = df.tail(20)
            result["range_high"] = float(recent20["high"].max())
            result["range_low"] = float(recent20["low"].min())
        except Exception:
            pass

        # =====================================
        # M1 momentum (wajib konfirmasi searah
        # dengan sinyal di decision engine)
        # =====================================
        try:
            result["m1_momentum"] = self._momentum_m1()
        except Exception:
            pass

        return result

    # =====================================
    # 1. Momentum Engine
    # =====================================

    def _momentum_htf(self, bars=10):
        try:
            import MetaTrader5 as mt5
            tf_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1,
                "H4": mt5.TIMEFRAME_H4,
                "D1": mt5.TIMEFRAME_D1,
            }
            tf = tf_map.get(self.direction_tf)
            if tf is None:
                return None
            rates = mt5.copy_rates_from_pos(self.symbol, tf, 0, bars)
            if rates is None or len(rates) < 3:
                return None
            import pandas as _pd
            htf = _pd.DataFrame(rates)
            htf["open"] = htf["open"].astype(float)
            htf["close"] = htf["close"].astype(float)
            return self._momentum(htf)
        except Exception:
            return None

    def _momentum_m1(self, bars=10):
        try:
            import MetaTrader5 as mt5
            rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, bars)
            if rates is None or len(rates) < 3:
                return None
            import pandas as _pd
            m1 = _pd.DataFrame(rates)
            m1["open"] = m1["open"].astype(float)
            m1["close"] = m1["close"].astype(float)
            return self._momentum(m1)
        except Exception:
            return None

    def _momentum(self, candles):
        if len(candles) < 3:
            return {"direction": "NEUTRAL", "strength": 0, "score": 50}

        bodies = []
        for i in range(len(candles)):
            o = float(candles.iloc[i]["open"])
            c = float(candles.iloc[i]["close"])
            bodies.append(c - o)

        recent = bodies[-3:]
        avg_body = np.mean([abs(b) for b in bodies]) if bodies else 0

        bull_count = sum(1 for b in recent if b > 0)
        bear_count = sum(1 for b in recent if b < 0)

        if avg_body == 0:
            body_ratio = 0
        else:
            body_ratio = abs(recent[-1]) / avg_body if avg_body > 0 else 0

        accel = 0
        if len(bodies) >= 3:
            accel = abs(bodies[-1]) - abs(bodies[-2])

        if bull_count >= 2 and recent[-1] > 0:
            strength = min(100, int(abs(recent[-1]) / max(avg_body, 0.01) * 50 + bull_count * 10 + accel * 5))
            direction = "BUY"
        elif bear_count >= 2 and recent[-1] < 0:
            strength = min(100, int(abs(recent[-1]) / max(avg_body, 0.01) * 50 + bear_count * 10 + abs(accel) * 5))
            direction = "SELL"
        else:
            direction = "NEUTRAL"
            strength = 50

        return {
            "direction": direction,
            "strength": strength,
            "score": strength,
            "body_ratio": round(body_ratio, 2),
            "acceleration": round(accel, 2),
            "accel_sign": "POS" if accel > 0 else ("NEG" if accel < 0 else "NEUT"),
            "last_body": "BUY" if bodies and bodies[-1] > 0 else ("SELL" if bodies and bodies[-1] < 0 else "NEUT"),
            "bull_bodies": bull_count,
            "bear_bodies": bear_count
        }

    # =====================================
    # 2. Speed Detector
    # =====================================

    def _speed(self, candles, last):
        if len(candles) < 3:
            return {"level": "UNKNOWN", "bars": 0, "score": 50}

        closes = [float(candles.iloc[i]["close"]) for i in range(len(candles))]
        changes = [abs(closes[i] - closes[i-1]) for i in range(1, len(closes))]

        avg_speed = np.mean(changes) if changes else 0
        last_speed = changes[-1] if changes else 0

        if avg_speed == 0:
            ratio = 0
        else:
            ratio = last_speed / avg_speed

        if ratio >= 2.0:
            level = "VERY_FAST"
            score = 90
        elif ratio >= 1.5:
            level = "FAST"
            score = 75
        elif ratio >= 1.0:
            level = "NORMAL"
            score = 65
        elif ratio >= 0.5:
            level = "SLOW"
            score = 55
        else:
            level = "VERY_SLOW"
            score = 45

        return {
            "level": level,
            "speed": round(last_speed, 2),
            "avg_speed": round(avg_speed, 2),
            "ratio": round(ratio, 2),
            "score": score
        }

    # =====================================
    # 3. Liquidity Detector
    # =====================================

    def _liquidity(self, candles, last):
        if len(candles) < 3:
            return {"signal": "NEUTRAL", "score": 50}

        highs = [float(candles.iloc[i]["high"]) for i in range(len(candles))]
        lows = [float(candles.iloc[i]["low"]) for i in range(len(candles))]
        closes = [float(candles.iloc[i]["close"]) for i in range(len(candles))]
        opens = [float(candles.iloc[i]["open"]) for i in range(len(candles))]

        recent_high = max(highs[-3:])
        recent_low = min(lows[-3:])
        current_close = closes[-1]
        current_open = opens[-1]

        closed_highs = highs[-4:-1]
        closed_lows = lows[-4:-1]
        closed_high3 = max(closed_highs) if closed_highs else recent_high
        closed_low3 = min(closed_lows) if closed_lows else recent_low
        atr_ref = float(last.get("ATR", 0) or 0)
        ext_gap = atr_ref * 0.5
        extended_up = atr_ref > 0 and current_close > closed_high3 + ext_gap
        extended_down = atr_ref > 0 and current_close < closed_low3 - ext_gap

        spread = float(last.get("spread", 0))
        volume = float(last.get("tick_volume", 0))
        avg_volume = np.mean([float(candles.iloc[i].get("tick_volume", 0)) for i in range(len(candles))]) or 1

        vol_ratio = volume / avg_volume

        upper_wick = highs[-1] - max(closes[-1], opens[-1])
        lower_wick = min(closes[-1], opens[-1]) - lows[-1]
        body = abs(closes[-1] - opens[-1])

        stop_hunt = False
        liquidity_grab = False

        if body > 0:
            if lower_wick > body * 1.5 and current_close >= opens[-1]:
                stop_hunt = True
            if upper_wick > body * 1.5 and current_close <= opens[-1]:
                stop_hunt = True

        if len(candles) >= 5:
            prev_highs = [float(candles.iloc[i]["high"]) for i in range(-5, -1)]
            prev_lows = [float(candles.iloc[i]["low"]) for i in range(-5, -1)]
            if current_close > max(prev_highs) and current_close < recent_high - body:
                liquidity_grab = True
            if current_close < min(prev_lows) and current_close > recent_low + body:
                liquidity_grab = True

        score = 50
        if stop_hunt and current_close > opens[-1]:
            score = 85
            signal = "BUY"
        elif stop_hunt and current_close < opens[-1]:
            score = 85
            signal = "SELL"
        elif liquidity_grab and current_close > opens[-1]:
            score = 80
            signal = "BUY"
        elif liquidity_grab and current_close < opens[-1]:
            score = 80
            signal = "SELL"
        else:
            score = int(min(100, 50 + vol_ratio * 10))
            signal = "NEUTRAL"

        return {
            "signal": signal,
            "score": score,
            "stop_hunt": stop_hunt,
            "liquidity_grab": liquidity_grab,
            "vol_ratio": round(vol_ratio, 2),
            "upper_wick": round(upper_wick, 2),
            "lower_wick": round(lower_wick, 2),
            "body": round(body, 2),
            "extended_up": extended_up,
            "extended_down": extended_down
        }

    # =====================================
    # 4. Fake Breakout Detector
    # =====================================

    def _fake_breakout(self, candles, last):
        if len(candles) < 3 or self._prev_high is None:
            return {"signal": "NEUTRAL", "score": 50}

        current_high = float(candles.iloc[-1]["high"])
        current_low = float(candles.iloc[-1]["low"])
        current_close = float(candles.iloc[-1]["close"])
        current_open = float(candles.iloc[-1]["open"])

        body = abs(current_close - current_open)

        broke_above = current_high > self._prev_high
        broke_below = current_low < self._prev_low

        rejected_above = broke_above and current_close < self._prev_high
        rejected_below = broke_below and current_close > self._prev_low

        signal = "NEUTRAL"
        score = 50

        if rejected_above:
            score = 90
            signal = "SELL"
        elif rejected_below:
            score = 90
            signal = "BUY"
        elif broke_above:
            score = 70
            signal = "BUY"
        elif broke_below:
            score = 70
            signal = "SELL"

        return {
            "signal": signal,
            "score": score,
            "fake_breakout": rejected_above or rejected_below,
            "breakout_above": broke_above,
            "breakout_below": broke_below
        }

    # =====================================
    # 5. Session Detector
    # =====================================

    def _session(self):
        h = datetime.now().hour
        m = datetime.now().minute
        minute_of_day = h * 60 + m

        sessions = []

        asia_start = 0 * 60
        asia_end = 9 * 60
        london_start = 8 * 60
        london_end = 17 * 60
        ny_start = 13 * 60
        ny_end = 22 * 60

        if asia_start <= minute_of_day < asia_end:
            sessions.append("Asia")
        if london_start <= minute_of_day < london_end:
            sessions.append("London")
        if ny_start <= minute_of_day < ny_end:
            sessions.append("New York")

        is_overlap = len(sessions) > 1
        primary = sessions[-1] if sessions else "Asia"

        session_scores = {
            "Asia": 50,
            "London": 80,
            "New York": 75,
            "Overlap": 90
        }

        label = "Overlap" if is_overlap else primary
        score = session_scores.get(label, 50)

        return {
            "session": label,
            "sessions": sessions,
            "is_overlap": is_overlap,
            "score": score
        }

    # =====================================
    # 6. Impulse Detector
    # =====================================

    def _impulse(self, candles, last):
        if len(candles) < 3:
            return {"impulse": False, "score": 50}

        closes = [float(candles.iloc[i]["close"]) for i in range(len(candles))]
        opens = [float(candles.iloc[i]["open"]) for i in range(len(candles))]
        volumes = [float(candles.iloc[i].get("tick_volume", 0)) for i in range(len(candles))]

        curr_body = abs(closes[-1] - opens[-1])
        prev_body = abs(closes[-2] - opens[-2])
        avg_body = np.mean([abs(closes[i] - opens[i]) for i in range(-5, -1)]) if len(candles) >= 2 else curr_body

        curr_vol = volumes[-1] if volumes else 0
        avg_vol = np.mean(volumes[-5:-1]) if len(volumes) >= 5 else curr_vol

        body_ratio = curr_body / max(avg_body, 0.01)
        vol_ratio = curr_vol / max(avg_vol, 0.01)
        spread_ok = True

        impulse = body_ratio >= 1.8 and vol_ratio >= 1.5 and spread_ok
        strength = int(min(100, max(45,
            min(body_ratio, 3) / 3 * 40 +
            min(vol_ratio, 3) / 3 * 30 +
            (30 if spread_ok else 0) +
            (10 if body_ratio >= 2.5 else 0)
        )))

        signal = "NEUTRAL"
        if impulse:
            signal = "BUY" if closes[-1] > opens[-1] else "SELL"

        return {
            "impulse": impulse,
            "signal": signal,
            "score": strength,
            "body_ratio": round(body_ratio, 2),
            "vol_ratio": round(vol_ratio, 2),
            "spread_ok": spread_ok
        }

    # =====================================
    # 7. Scalping Score
    # =====================================

    def _scalping_score(self, engines):

        weights = {
            "momentum": 0.20,
            "speed": 0.15,
            "liquidity": 0.15,
            "fake_breakout": 0.10,
            "session": 0.10,
            "impulse": 0.20,
            "spread": 0.10
        }

        details = {}
        total = 0.0

        for key, weight in weights.items():
            if key == "spread":
                continue
            engine_data = engines.get(key)
            if engine_data:
                s = engine_data.get("score", 50)
                details[key] = s
                total += s * weight
            else:
                details[key] = 50
                total += 50 * weight

        spread_ok = engines.get("impulse", {}).get("spread_ok", True)
        spread_score = 100 if spread_ok else 30
        details["spread"] = spread_score
        total += spread_score * weights["spread"]

        raw_score = round(total, 1)
        max_possible = sum(weights.values()) * 100
        final_score = round(raw_score / max_possible * 100, 1) if max_possible > 0 else 0

        if final_score >= 80:
            grade = "A+"
        elif final_score >= 70:
            grade = "A"
        elif final_score >= 60:
            grade = "B"
        elif final_score >= 50:
            grade = "C"
        else:
            grade = "D"

        momentum = engines.get("momentum", {})
        direction = momentum.get("direction", "NEUTRAL")
        trend_override = momentum.get("trend_override")

        result = {
            "score": final_score,
            "grade": grade,
            "direction": direction,
            "details": details,
            "action": "TRADE" if final_score >= 50 else "WAIT"
        }
        if trend_override:
            result["trend_override"] = trend_override
        return result
