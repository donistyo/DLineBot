import ta
import pandas as pd


class StochasticIndicator:

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:

        stoch = ta.momentum.StochasticOscillator(
            high=df["high"],
            low=df["low"],
            close=df["close"]
        )

        df["STO_K"] = stoch.stoch()
        df["STO_D"] = stoch.stoch_signal()

        return df