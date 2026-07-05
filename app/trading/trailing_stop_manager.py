from app.mt5.position_controller import PositionController


class TrailingStopManager:

    def __init__(

        self,

        activation_profit=20.0,

        distance=10.0

    ):

        self.activation_profit = activation_profit
        self.distance = distance

        self.controller = PositionController()

    def process(self, position):

        # ======================================
        # Trailing belum aktif
        # ======================================

        if position.profit < self.activation_profit:

            return {

                "status": "WAITING",

                "action": "NONE",

                "reason": f"Profit belum mencapai {self.activation_profit}."

            }

        # ======================================
        # BUY
        # ======================================

        if position.type == 0:

            new_sl = position.price_current - self.distance

            if position.sl != 0 and new_sl <= position.sl:

                return {

                    "status": "WAITING",

                    "action": "NONE",

                    "reason": "Stop Loss sudah optimal."

                }

        # ======================================
        # SELL
        # ======================================

        else:

            new_sl = position.price_current + self.distance

            if position.sl != 0 and new_sl >= position.sl:

                return {

                    "status": "WAITING",

                    "action": "NONE",

                    "reason": "Stop Loss sudah optimal."

                }

        # ======================================
        # Update Stop Loss
        # ======================================

        result = self.controller.modify_sl(
            position,
            new_sl
        )

        return {

            "status": "UPDATED",

            "action": "TRAILING",

            "reason": "Trailing Stop berhasil diperbarui.",

            "new_stop_loss": new_sl,

            "result": result

        }