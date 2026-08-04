import MetaTrader5 as mt5
import numpy as np


class ATRHelper:

    def __init__(self, symbol="XAUUSDc", timeframe=mt5.TIMEFRAME_M5):
        self.symbol = symbol
        self.timeframe = timeframe

    def _atr_series(self, bars=50):
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, bars)
        if rates is None or len(rates) < 15:
            return None
        high = rates["high"]
        low = rates["low"]
        close = rates["close"]
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]
        tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
        atr = np.empty(len(tr))
        atr[0] = tr[0]
        for i in range(1, len(tr)):
            atr[i] = (atr[i - 1] * 13 + tr[i]) / 14
        return atr

    def current_atr(self, bars=50):
        atr = self._atr_series(bars)
        if atr is None:
            return 0.0
        return float(atr[-1])

    def atr_stats(self, bars=50, lookback=20):
        atr = self._atr_series(bars)
        if atr is None or len(atr) < 15 + lookback:
            return None
        current = float(atr[-1])
        past = atr[-1 - lookback:-1]
        avg = float(np.mean(past)) if len(past) else current
        ratio = current / avg if avg > 0 else 1.0
        return {
            "current": current,
            "avg_20": avg,
            "ratio": ratio,
        }

    def volatility_ok(self, max_mult=2.0, min_mult=0.5, bars=50, lookback=20):
        stats = self.atr_stats(bars, lookback)
        if stats is None:
            return True, None
        ratio = stats["ratio"]
        if ratio > max_mult:
            return False, f"Volatilitas terlalu tinggi ({ratio:.2f}x rata2 ATR)"
        if ratio < min_mult:
            return False, f"Volatilitas terlalu sepi ({ratio:.2f}x rata2 ATR)"
        return True, None
