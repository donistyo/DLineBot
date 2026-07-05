import pandas as pd


class Predictor:
    """
    Prediction Engine AI
    """

    SIGNAL_MAP = {
        0: "SELL",
        1: "HOLD",
        2: "BUY"
    }

    def __init__(self, model):
        self.model = model

    def predict(self, X: pd.DataFrame) -> dict:
        """
        Melakukan prediksi pada candle terakhir.

        Parameters
        ----------
        X : pd.DataFrame
            Feature dataset.

        Returns
        -------
        dict
            Hasil prediksi AI.
        """

        # Gunakan hanya candle terakhir
        last_data = X.tail(1)

        prediction = self.model.predict(last_data)[0]
        probability = self.model.predict_proba(last_data)[0]

        return {
            "time": last_data.index[-1],
            "signal": self.SIGNAL_MAP[prediction],
            "class": int(prediction),
            "confidence": float(probability.max()),
            "probability": {
                "SELL": float(probability[0]),
                "HOLD": float(probability[1]),
                "BUY": float(probability[2]),
            },
        }