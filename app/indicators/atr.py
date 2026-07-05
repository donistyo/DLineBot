import ta
import pandas as pd


class ATRIndicator:

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:

        atr = ta.volatility.AverageTrueRange(
            high=df["high"],
            low=df["low"],
            close=df["close"]
        )

        df["ATR"] = atr.average_true_range()

        return df