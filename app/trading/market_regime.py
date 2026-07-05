class MarketRegimeDetector:

    def __init__(self, adx_trend=25, adx_strong=30):
        self.adx_trend = adx_trend
        self.adx_strong = adx_strong

    def detect(self, last):

        close = last["close"]
        ema20 = last["EMA20"]
        ema50 = last["EMA50"]
        ema200 = last["EMA200"]
        adx = last["ADX"]
        macd = last["MACD"]
        macd_signal = last["MACD_SIGNAL"]

        # -------------------------------
        # Trend Direction
        # -------------------------------

        if close > ema20 > ema50 > ema200:
            trend = "UP"
        elif close < ema20 < ema50 < ema200:
            trend = "DOWN"
        elif close > ema20 and ema20 > ema50:
            trend = "UP"
        elif close < ema20 and ema20 < ema50:
            trend = "DOWN"
        else:
            trend = "SIDEWAYS"

        # -------------------------------
        # Strength
        # -------------------------------

        if adx >= self.adx_strong:
            strength = "Strong"
        elif adx >= self.adx_trend:
            strength = "Weak"
        else:
            strength = "Neutral"

        # -------------------------------
        # Mode
        # -------------------------------

        if adx >= self.adx_trend:
            mode = "TREND"
        else:
            mode = "RANGING"

        return {
            "trend": trend,
            "strength": strength,
            "mode": mode,
            "adx": adx
        }
