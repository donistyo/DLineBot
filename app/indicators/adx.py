import ta
import pandas as pd


class ADXIndicator:

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:

        adx = ta.trend.ADXIndicator(
            high=df["high"],
            low=df["low"],
            close=df["close"]
        )

        df["ADX"] = adx.adx()

        return df