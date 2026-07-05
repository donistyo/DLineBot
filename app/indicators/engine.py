import pandas as pd

from app.indicators.ema import EMAIndicator
from app.indicators.rsi import RSIIndicator
from app.indicators.macd import MACDIndicator
from app.indicators.atr import ATRIndicator
from app.indicators.bollinger import BollingerIndicator
from app.indicators.adx import ADXIndicator
from app.indicators.stochastic import StochasticIndicator


class IndicatorEngine:

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:

        df = EMAIndicator.calculate(df)
        df = RSIIndicator.calculate(df)
        df = MACDIndicator.calculate(df)
        df = ATRIndicator.calculate(df)
        df = BollingerIndicator.calculate(df)
        df = ADXIndicator.calculate(df)
        df = StochasticIndicator.calculate(df)

        return df