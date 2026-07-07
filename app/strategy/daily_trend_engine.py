class DailyTrendEngine:

    def __init__(self):
        self._data = None

    def update(self, bias="NEUTRAL", confidence=0, score=0, reasons=None):
        self._data = {
            "bias": bias.upper(),
            "confidence": confidence,
            "score": score,
            "reasons": reasons or []
        }

    def get(self):
        return self._data

    def analyze(self):
        return self._data or {
            "bias": "NEUTRAL",
            "confidence": 0,
            "score": 0,
            "reasons": []
        }

    @property
    def bias_multiplier(self):
        if not self._data:
            return 1.0
        bias = self._data["bias"]
        if bias in ("STRONG BULLISH", "BULLISH"):
            return 1.3
        elif bias in ("STRONG BEARISH", "BEARISH"):
            return 1.3
        return 1.0

    @property
    def trend_bias(self):
        if not self._data:
            return "NEUTRAL"
        return self._data["bias"]
