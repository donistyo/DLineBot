from app.mt5.position_controller import PositionController, _log_close


class AIExit:

    def __init__(self, min_exit_confidence=0.80, lookback=3):
        self.controller = PositionController()
        self.min_exit_confidence = min_exit_confidence
        self.lookback = lookback
        self._consecutive_reversals = {}

    def process(self, position, prediction, market=None):
        ticket = position.ticket
        signal = prediction.get("signal", "HOLD")
        confidence = prediction.get("confidence", 0)
        pos_type = "BUY" if position.type == 0 else "SELL"

        if signal == "HOLD" or signal == pos_type:
            self._consecutive_reversals[ticket] = 0
            return {"status": "HOLD", "action": "NONE",
                    "reason": f"AI masih searah ({signal}).",
                    "ticket": ticket, "confidence": confidence}

        reversal_count = self._consecutive_reversals.get(ticket, 0) + 1
        self._consecutive_reversals[ticket] = reversal_count

        if reversal_count >= self.lookback:
            if position.profit <= 0:
                return {"status": "HOLD", "action": "WATCH",
                        "reason": f"AI reversal {reversal_count}x tapi posisi loss, tunggu profit.",
                        "ticket": ticket, "confidence": confidence,
                        "reversal_count": reversal_count}
            _log_close("AI_EXIT(reversal)", ticket, position.symbol, position.profit)
            result = self.controller.close(position)
            self._consecutive_reversals.pop(ticket, None)
            return {"status": "CLOSED", "action": "AI_EXIT",
                    "reason": f"AI Exit: {reversal_count}x reversal, conf {confidence:.0%}.",
                    "ticket": ticket, "result": result,
                    "reversal_count": reversal_count}

        if confidence >= self.min_exit_confidence:
            if position.profit <= 0:
                return {"status": "HOLD", "action": "WATCH",
                        "reason": f"High confidence reversal ({confidence:.0%}) tapi loss, tunggu profit.",
                        "ticket": ticket, "confidence": confidence,
                        "reversal_count": reversal_count}
            _log_close("AI_EXIT(high_conf)", ticket, position.symbol, position.profit)
            result = self.controller.close(position)
            self._consecutive_reversals.pop(ticket, None)
            return {"status": "CLOSED", "action": "AI_EXIT",
                    "reason": f"AI Exit: High confidence reversal ({confidence:.0%}).",
                    "ticket": ticket, "result": result,
                    "reversal_count": reversal_count}

        remaining = self.lookback - reversal_count
        return {"status": "HOLD", "action": "WATCH",
                "reason": f"AI reversal {reversal_count}x, butuh {remaining}x lagi.",
                "ticket": ticket, "confidence": confidence,
                "reversal_count": reversal_count}

    def cleanup(self, active_tickets):
        for tid in list(self._consecutive_reversals.keys()):
            if tid not in active_tickets:
                del self._consecutive_reversals[tid]
