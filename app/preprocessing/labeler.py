import pandas as pd

from app.core.logger import logger


class LabelGenerator:
    """
    Membuat label BUY / HOLD / SELL
    """

    def __init__(
        self,
        future_bars: int = 5,
        threshold: float = 5.0
    ):
        self.future_bars = future_bars
        self.threshold = threshold

    def generate(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:

        logger.info("Generate Label AI")

        # Harga penutupan masa depan
        df["future_close"] = (
            df["close"]
            .shift(-self.future_bars)
        )

        # Selisih harga
        df["price_diff"] = (
            df["future_close"]
            - df["close"]
        )

        labels = []

        for diff in df["price_diff"]:

            if pd.isna(diff):
                labels.append(None)

            elif diff > self.threshold:
                labels.append(2)      # BUY

            elif diff < -self.threshold:
                labels.append(0)      # SELL

            else:
                labels.append(1)      # HOLD

        df["label"] = labels

        df = df.dropna().reset_index(drop=True)

        df["label"] = df["label"].astype(int)

        logger.info("Label selesai dibuat")

        return df