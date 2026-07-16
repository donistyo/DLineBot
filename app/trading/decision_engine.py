class DecisionEngine:

    def __init__(self, min_scalp_score=25):
        self.min_scalp_score = min_scalp_score
        self.trend_map = {"UP": "BUY", "DOWN": "SELL", "SIDEWAYS": None}

    def decide(self, prediction=None, scalp_result=None, regime=None) -> dict:
        if scalp_result is None or regime is None:
            return {"action": "NO_TRADE", "reason": "Data tidak tersedia", "confidence": 0}

        score_data = scalp_result.get("scalp_score", {})
        score = score_data.get("score", 0)
        direction = score_data.get("direction", "NEUTRAL")
        grade = score_data.get("grade", "D")

        if score < self.min_scalp_score:
            return {
                "action": "NO_TRADE",
                "reason": f"Scalp score terlalu rendah ({score}/100, {grade})",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        if direction in ("NEUTRAL", "WAIT"):
            return {
                "action": "NO_TRADE",
                "reason": f"Scalp arah netral ({score}/100, {grade})",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        trend = regime.get("trend", "SIDEWAYS") if regime else "SIDEWAYS"
        expected_dir = self.trend_map.get(trend)

        if expected_dir and direction != expected_dir:
            return {
                "action": direction,
                "reason": f"MANUAL: Scalp {direction} vs trend {trend} (score {score}/100 {grade})",
                "confidence": score / 100,
                "score": score,
                "grade": grade,
                "manual": True
            }

        return {
            "action": direction,
            "reason": f"Scalp {grade} ({score}/100) searah trend {trend}",
            "confidence": score / 100,
            "score": score,
            "grade": grade
        }