import pandas as pd


class Predictor:
    """
    Prediction Engine AI
    """

    # Label dataset: 0 = SELL, 1 = HOLD, 2 = BUY (lihat labeler)
    SIGNAL_MAP = {
        0: "SELL",
        1: "HOLD",
        2: "BUY",
    }

    def __init__(self, model):
        self.model = model

    def predict(self, X: pd.DataFrame) -> dict:

        last_data = X.tail(1)

        prediction = self.model.predict(last_data)[0]
        proba = self.model.predict_proba(last_data)[0]

        n_classes = len(proba)
        if n_classes == 3:
            prob = {
                "SELL": float(proba[0]),
                "HOLD": float(proba[1]),
                "BUY": float(proba[2]),
            }
            signal = self.SIGNAL_MAP.get(prediction, "HOLD")
        else:
            # Model 2-kelas: 0 = SELL, 1 = BUY (tanpa HOLD)
            prob = {
                "SELL": float(proba[0]) if 0 < len(proba) else 0.0,
                "HOLD": 0.0,
                "BUY": float(proba[1]) if 1 < len(proba) else 0.0,
            }
            signal = {0: "SELL", 1: "BUY"}.get(prediction, "HOLD")

        return {
            "time": last_data.index[-1],
            "signal": signal,
            "class": int(prediction),
            "confidence": float(proba.max()),
            "probability": prob,
        }