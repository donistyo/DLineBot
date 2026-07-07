from app.data.collector import Collector
from app.indicators.engine import IndicatorEngine
from app.preprocessing.cleaner import DataCleaner


class MultiTimeframeConfirmation:

    def __init__(
        self,
        symbol="XAUUSD",
        primary_tf="M1",
        higher_tfs=None,
        bars=500
    ):
        self.symbol = symbol
        self.primary_tf = primary_tf
        self.higher_tfs = higher_tfs or ["M5", "M15"]
        self.bars = bars
        self.collector = Collector()
        self.indicator = IndicatorEngine()
        self.cleaner = DataCleaner()

    def _load_tf(self, timeframe):
        df = self.collector.load(
            symbol=self.symbol,
            timeframe=timeframe,
            bars=self.bars
        )
        df = self.indicator.calculate(df)
        df = self.cleaner.clean(df)
        return df

    def _trend_at_bar(self, row):
        close = row["close"]
        ema20 = row["EMA20"]
        ema50 = row["EMA50"]
        ema200 = row["EMA200"]
        adx = row["ADX"]

        if close > ema20 > ema50:
            trend = "UP"
        elif close < ema20 < ema50:
            trend = "DOWN"
        else:
            trend = "SIDEWAYS"

        return trend

    def confirm(self, prediction, last_primary=None):

        signal = prediction.get("signal", "HOLD")
        confidence = prediction.get("confidence", 0)

        tf_results = {}
        aligned = 0
        total = 0

        for tf in self.higher_tfs:
            try:
                df = self._load_tf(tf)
                if df.empty:
                    continue
                last = df.iloc[-1]
                trend = self._trend_at_bar(last)
                tf_results[tf] = {
                    "trend": trend,
                    "close": last["close"],
                    "ema20": last["EMA20"],
                    "ema50": last["EMA50"],
                    "adx": last["ADX"]
                }

                if signal == "BUY" and trend == "UP":
                    aligned += 1
                elif signal == "SELL" and trend == "DOWN":
                    aligned += 1
                elif signal == "HOLD":
                    aligned += 1
                else:
                    pass

                total += 1

            except Exception as e:
                tf_results[tf] = {"error": str(e)}

        if total == 0:
            return {
                "allowed": True,
                "reason": "Tidak ada data timeframe lain.",
                "alignment": 0,
                "details": tf_results
            }

        alignment_pct = aligned / total if total > 0 else 0

        tf_confirmed = alignment_pct >= 0.5

        if not tf_confirmed:
            reason = (
                f"Higher TF menolak ({aligned}/{total} searah)"
            )
        elif alignment_pct == 1.0:
            reason = "Semua timeframe searah."
        else:
            reason = f"{aligned}/{total} timeframe searah."

        return {
            "allowed": tf_confirmed,
            "reason": reason,
            "alignment": round(alignment_pct, 2),
            "aligned_count": aligned,
            "total_count": total,
            "details": tf_results
        }
