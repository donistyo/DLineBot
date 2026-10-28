import numpy as np
import pandas as pd

from app.core.logger import logger


class LabelGenerator:
    """
    Membuat label BUY / HOLD / SELL
    threshold: nilai harga mutlak, atau
    atr_multiplier: jika diisi, threshold = atr_multiplier * ATR (adaptif per simbol)

    Mode triple-barrier (aktif jika tp_atr & sl_atr diisi): label = barrier yang kena
    duluan dalam max_bars bar ke depan (TP = tp_atr*ATR, SL = sl_atr*ATR).
    BUY(2) jika TP long kena sebelum SL long dan sebelum TP short; SELL(0) sebaliknya;
    selain itu HOLD(1). SL & TP di bar yang sama -> SL dianggap duluan (konservatif).
    """

    def __init__(
        self,
        future_bars: int = 5,
        threshold: float = 0.5,
        atr_multiplier: float = None,
        tp_atr: float = None,
        sl_atr: float = None,
        max_bars: int = 30
    ):
        self.future_bars = future_bars
        self.threshold = threshold
        self.atr_multiplier = atr_multiplier
        self.tp_atr = tp_atr
        self.sl_atr = sl_atr
        self.max_bars = max_bars

    def _triple_barrier(self, df: pd.DataFrame) -> pd.DataFrame:

        n = len(df)
        close = df["close"].to_numpy(float)
        high = df["high"].to_numpy(float)
        low = df["low"].to_numpy(float)
        atr = df["ATR"].to_numpy(float)
        h = self.max_bars

        labels = np.full(n, np.nan)

        def first(mask):
            idx = np.flatnonzero(mask)
            return idx[0] if idx.size else h + 1

        # shortcut: loop O(n*max_bars), cukup sampai puluhan ribu bar; vektorkan jika lebih
        for i in range(n - h):

            if not atr[i] > 0:
                continue

            tp = self.tp_atr * atr[i]
            sl = self.sl_atr * atr[i]
            hi = high[i + 1:i + h + 1]
            lo = low[i + 1:i + h + 1]

            long_tp = first(hi >= close[i] + tp)
            long_sl = first(lo <= close[i] - sl)
            short_tp = first(lo <= close[i] - tp)
            short_sl = first(hi >= close[i] + sl)

            long_win = long_tp < long_sl
            short_win = short_tp < short_sl

            if long_win and (not short_win or long_tp < short_tp):
                labels[i] = 2
            elif short_win and (not long_win or short_tp < long_tp):
                labels[i] = 0
            else:
                labels[i] = 1

        df["future_close"] = df["close"].shift(-h)
        df["price_diff"] = df["future_close"] - df["close"]
        df["label"] = labels

        df = df.dropna().reset_index(drop=True)
        df["label"] = df["label"].astype(int)

        logger.info(
            f"Label triple-barrier selesai (TP {self.tp_atr}xATR, SL {self.sl_atr}xATR, {h} bar)."
        )

        return df

    def generate(
        self,
        df: pd.DataFrame
    ) -> pd.DataFrame:

        logger.info("Generate Label AI")

        if self.tp_atr is not None and self.sl_atr is not None:
            return self._triple_barrier(df)

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