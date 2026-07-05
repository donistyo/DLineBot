import ta
import pandas as pd


class BollingerIndicator:

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:

        bb = ta.volatility.BollingerBands(
            close=df["close"]
        )

        df["BB_UPPER"] = bb.bollinger_hband()
        df["BB_MIDDLE"] = bb.bollinger_mavg()
        df["BB_LOWER"] = bb.bollinger_lband()

        return df