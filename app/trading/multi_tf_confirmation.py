from app.data.collector import Collector
from app.indicators.engine import IndicatorEngine
from app.preprocessing.cleaner import DataCleaner
from app.trading.regime_logic import classify_regime, multi_tf_decision


class MultiTimeframeConfirmation:

    def __init__(
        self,
        symbol="XAUUSD",
        primary_tf="M1",
        higher_tfs=None,
        bars=500,
        min_adx=30,
    ):
        self.symbol = symbol
        self.primary_tf = primary_tf
        self.higher_tfs = higher_tfs or ["M5", "M15"]
        self.bars = bars
        self.min_adx = min_adx
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

    def confirm(self, prediction, last_primary=None, signal=None):

        if signal is None:
            signal = prediction.get("signal", "HOLD") if prediction else "HOLD"
        confidence = prediction.get("confidence", 0) if prediction else 0

        tf_results = {}
        regimes = {}

        for tf in self.higher_tfs:
            try:
                df = self._load_tf(tf)
                if df.empty:
                    continue
                last = df.iloc[-1]
                regime = classify_regime(
                    close=last["close"],
                    ema20=last["EMA20"],
                    ema50=last["EMA50"],
                    adx=last["ADX"]
                )
                regimes[tf] = regime
                tf_results[tf] = {
                    "trend": regime.mode,
                    "ema_trend": regime.trend or "SIDEWAYS",
                    "mode": regime.mode,
                    "close": last["close"],
                    "ema20": last["EMA20"],
                    "ema50": last["EMA50"],
                    "adx": last["ADX"]
                }
            except Exception as e:
                tf_results[tf] = {"error": str(e)}

        if len(regimes) < 2:
            return {
                "allowed": True,
                "reason": "Tidak ada data timeframe lain.",
                "alignment": 0,
                "details": tf_results
            }

        regime_m5 = regimes.get("M5")
        regime_m15 = regimes.get("M15")

        if regime_m5 is None or regime_m15 is None:
            return {
                "allowed": True,
                "reason": "Data M5/M15 tidak lengkap.",
                "alignment": 0,
                "details": tf_results
            }

        signal_map = {"BUY": "UP", "SELL": "DOWN"}
        tf_signal = signal_map.get(signal, signal)
        allow, alignment_score, reason = multi_tf_decision(
            regime_m5, regime_m15, tf_signal
        )

        return {
            "allowed": allow,
            "reason": reason,
            "alignment": round(alignment_score / 2.0, 2),
            "aligned_count": int(alignment_score),
            "total_count": 2,
            "alignment_score": alignment_score,
            "details": tf_results
        }
