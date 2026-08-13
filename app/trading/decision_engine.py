class DecisionEngine:

    def __init__(self, min_scalp_score=55):
        self.min_scalp_score = min_scalp_score
        self.sideways_penalty = 15
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

        momentum = {}
        if scalp_result:
            momentum = scalp_result.get("momentum", {}) or {}
            if not momentum and isinstance(scalp_result.get("scalp_score"), dict):
                momentum = scalp_result["scalp_score"].get("details", {}) or {}

        last_body = momentum.get("last_body", "NEUT")
        accel = momentum.get("acceleration", 0)
        accel_opposing = (
            (direction == "BUY" and last_body == "SELL" and accel < 0
             and abs(accel) >= 0.5) or
            (direction == "SELL" and last_body == "BUY" and accel > 0
             and accel >= 0.5)
        )
        if accel_opposing:
            return {
                "action": "NO_TRADE",
                "reason": f"Momentum candle terakhir melawan ({last_body}, akselerasi {accel:.2f}) - rawan gerakan tajam",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        # =====================================
        # Wick rejection: blokir entry saat candle terakhir
        # rejection (wick panjang di sisi arah entry = kejar puncak/lembah)
        # =====================================
        liquidity = {}
        if scalp_result:
            liquidity = scalp_result.get("liquidity", {}) or {}
        body = float(liquidity.get("body", 0) or 0)
        upper_wick = float(liquidity.get("upper_wick", 0) or 0)
        lower_wick = float(liquidity.get("lower_wick", 0) or 0)

        wick_mult = 2.0
        try:
            from app.config.settings import load_trade_config, get_trade_config
            wick_mult = float(get_trade_config("wick_reject_mult", 2.0))
        except Exception:
            pass

        if body > 0:
            if direction == "BUY" and upper_wick >= wick_mult * body:
                return {
                    "action": "NO_TRADE",
                    "reason": f"Wick atas {upper_wick:.2f} >= {wick_mult:.0f}x body {body:.2f} - candle rejection atas, rawan kejar puncak",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }
            if direction == "SELL" and lower_wick >= wick_mult * body:
                return {
                    "action": "NO_TRADE",
                    "reason": f"Wick bawah {lower_wick:.2f} >= {wick_mult:.0f}x body {body:.2f} - candle rejection bawah, rawan kejar lembah",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }

        # =====================================
        # Extension guard: harga sudah jauh/extended dari range terbaru
        # -> jangan entry mengejar gerakan yang sudah terlalu jauh
        # =====================================
        if direction == "BUY" and liquidity.get("extended_up"):
            return {
                "action": "NO_TRADE",
                "reason": "Harga extended di atas range M5 terbaru - jangan kejar puncak",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }
        if direction == "SELL" and liquidity.get("extended_down"):
            return {
                "action": "NO_TRADE",
                "reason": "Harga extended di bawah range M5 terbaru - jangan kejar lembah",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        if prediction:
            ai_signal = prediction.get("signal", "WAIT")
            ai_conf = prediction.get("confidence", 0)
            if ai_signal in ("BUY", "SELL") and ai_conf >= 55 and direction != ai_signal:
                return {
                    "action": "NO_TRADE",
                    "reason": f"Scalp {direction} vs AI {ai_signal} ({ai_conf:.0f}%) - berlawanan arah",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }

        trend = regime.get("trend", "SIDEWAYS") if regime else "SIDEWAYS"
        expected_dir = self.trend_map.get(trend)

        if expected_dir is None:
            if score < self.min_scalp_score + self.sideways_penalty:
                return {
                    "action": "NO_TRADE",
                    "reason": f"Trend SIDEWAYS, butuh skor >= {self.min_scalp_score + self.sideways_penalty} (dapat {score}/100 {grade})",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }

        if expected_dir and direction != expected_dir:
            return {
                "action": "NO_TRADE",
                "reason": f"Scalp {direction} tidak searah trend {trend} - tunggu sinyal stabil",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        return {
            "action": direction,
            "reason": f"Scalp {grade} ({score}/100) searah trend {trend}",
            "confidence": score / 100,
            "score": score,
            "grade": grade
        }