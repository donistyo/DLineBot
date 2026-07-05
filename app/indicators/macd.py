import ta
import pandas as pd


class MACDIndicator:

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:

        macd = ta.trend.MACD(df["close"])

        df["MACD"] = macd.macd()
        df["MACD_SIGNAL"] = macd.macd_signal()
        df["MACD_HIST"] = macd.macd_diff()

        return df