import ta
import pandas as pd


class EMAIndicator:

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:

        df["EMA20"] = ta.trend.EMAIndicator(
            close=df["close"],
            window=20
        ).ema_indicator()

        df["EMA50"] = ta.trend.EMAIndicator(
            close=df["close"],
            window=50
        ).ema_indicator()

        df["EMA200"] = ta.trend.EMAIndicator(
            close=df["close"],
            window=200
        ).ema_indicator()

        return df