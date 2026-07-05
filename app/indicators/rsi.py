import ta
import pandas as pd


class RSIIndicator:

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:

        df["RSI"] = ta.momentum.RSIIndicator(
            close=df["close"],
            window=14
        ).rsi()

        return df