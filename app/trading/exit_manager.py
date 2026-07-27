from app.mt5.position_controller import PositionController, _log_close


class ExitManager:

    def __init__(self, min_confidence=0.75):

        self.controller = PositionController()

        self.min_confidence = min_confidence

    def process(

        self,

        position,

        prediction

    ):

        signal = prediction["signal"]

        confidence = prediction["confidence"]

        current_type = "BUY" if position.type == 0 else "SELL"

        if signal == current_type:

            return {

                "status": "HOLD",

                "action": "NONE",

                "reason": "Posisi masih searah AI.",

                "ticket": position.ticket

            }

        if confidence < self.min_confidence:

            return {

                "status": "HOLD",

                "action": "NONE",

                "reason": "Reverse signal belum cukup kuat.",

                "ticket": position.ticket

            }

        if position.profit <= 0:

            return {

                "status": "HOLD",

                "action": "NONE",

                "reason": "Sinyal berlawanan tapi posisi masih loss, tunggu profit dulu.",

                "ticket": position.ticket

            }

        _log_close("EXIT_MANAGER(sinyal_flip)", position.ticket, position.symbol, position.profit)
        result = self.controller.close(position)

        return {

            "status": "CLOSED",

            "action": "CLOSE",

            "reason": "AI memberikan sinyal berlawanan.",

            "ticket": position.ticket,

            "result": result

        }