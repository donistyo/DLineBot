class ConfidenceManager:

    def __init__(self, min_confidence=0.70):
        self.min_confidence = min_confidence

    def allow(self, prediction):

        signal = prediction["signal"]
        confidence = prediction["confidence"]

        if confidence < self.min_confidence:

            return {
                "allowed": False,
                "signal": signal,
                "confidence": confidence,
                "min_confidence": self.min_confidence,
                "reason": "Confidence太低"
            }

        return {
            "allowed": True,
            "signal": signal,
            "confidence": confidence,
            "min_confidence": self.min_confidence,
            "reason": "Confidence memenuhi syarat"
        }
