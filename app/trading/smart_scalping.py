import numpy as np
import pandas as pd
from datetime import datetime


class SmartScalpingEngine:

    def __init__(self):
        self._last_5 = None
        self._prev_high = None
        self._prev_low = None

    def analyze(self, df, last):

        result = {}

        candles = df.tail(10)
        self._last_5 = df.tail(5) if len(df) >= 5 else df

        if len(df) >= 2:
            self._prev_high = float(df.iloc[-2]["high"])
            self._prev_low = float(df.iloc[-2]["low"])

        # =====================================
        # 1. Momentum Engine
        # =====================================
        momentum = self._momentum(candles)
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

        return result

    # =====================================
    # 1. Momentum Engine
    # =====================================

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
            score = 95
        elif ratio >= 1.5:
            level = "FAST"
            score = 80
        elif ratio >= 1.0:
            level = "NORMAL"
            score = 60
        elif ratio >= 0.5:
            level = "SLOW"
            score = 40
        else:
            level = "VERY_SLOW"
            score = 20

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
            "lower_wick": round(lower_wick, 2)
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

        atr = float(last.get("ATR", 0))
        spread = float(last.get("spread", 0))

        body_ratio = curr_body / max(avg_body, 0.01)
        vol_ratio = curr_vol / max(avg_vol, 0.01)
        spread_ok = spread < atr * 0.3 if atr > 0 else True

        impulse = body_ratio >= 1.8 and vol_ratio >= 1.5 and spread_ok
        strength = int(min(100,
            min(body_ratio, 3) / 3 * 40 +
            min(vol_ratio, 3) / 3 * 30 +
            (30 if spread_ok else 0) +
            (10 if body_ratio >= 2.5 else 0)
        ))

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

        if final_score >= 85:
            grade = "A+"
        elif final_score >= 75:
            grade = "A"
        elif final_score >= 65:
            grade = "B"
        elif final_score >= 55:
            grade = "C"
        else:
            grade = "D"

        momentum = engines.get("momentum", {})
        direction = momentum.get("direction", "NEUTRAL")

        return {
            "score": final_score,
            "grade": grade,
            "direction": direction,
            "details": details,
            "action": "TRADE" if final_score >= 65 else "WAIT"
        }
