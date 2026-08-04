import pandas as pd

from app.core.logger import logger


class LabelGenerator:
    """
    Membuat label BUY / HOLD / SELL
    threshold: nilai harga mutlak, atau
    atr_multiplier: jika diisi, threshold = atr_multiplier * ATR (adaptif per simbol)
    """

    def __init__(
        self,
        future_bars: int = 5,
        threshold: float = 0.5,
        atr_multiplier: float = None
    ):
        self.future_bars = future_bars
        self.threshold = threshold
        self.atr_multiplier = atr_multiplier

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

        # Threshold adaptif berbasis ATR
        if self.atr_multiplier is not None and "ATR" in df.columns:
            thresholds = self.atr_multiplier * df["ATR"]
            logger.info(
                f"Label threshold berbasis ATR ({self.atr_multiplier} x ATR)."
            )
        else:
            thresholds = self.threshold
            logger.info(
                f"Label threshold tetap ({self.threshold})."
            )

        labels = []

        for i, diff in enumerate(df["price_diff"]):

            thr = float(thresholds.iloc[i]) if hasattr(thresholds, "iloc") else thresholds

            if pd.isna(diff) or pd.isna(thr):
                labels.append(None)

            elif diff > thr:
                labels.append(2)      # BUY

            elif diff < -thr:
                labels.append(0)      # SELL

            else:
                labels.append(1)      # HOLD

        df["label"] = labels

        df = df.dropna().reset_index(drop=True)

        df["label"] = df["label"].astype(int)

        logger.info("Label selesai dibuat")

        return df