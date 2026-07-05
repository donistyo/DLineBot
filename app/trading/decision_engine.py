class DecisionEngine:
    """
    Mengubah hasil prediksi AI menjadi keputusan trading.
    """

    def __init__(
        self,
        confidence_threshold=0.70
    ):
        self.confidence_threshold = confidence_threshold

    def decide(self, prediction: dict) -> dict:

        signal = prediction["signal"]
        confidence = prediction["confidence"]

        if confidence < self.confidence_threshold:

            return {
                "action": "NO_TRADE",
                "reason": "Confidence terlalu rendah",
                "confidence": confidence
            }

        return {
            "action": signal,
            "reason": "AI Confidence memenuhi syarat",
            "confidence": confidence
        }