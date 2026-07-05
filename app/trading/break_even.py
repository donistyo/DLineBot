from app.mt5.position_controller import PositionController


class BreakEvenManager:

    def __init__(self, trigger_profit=10.0):

        self.trigger_profit = trigger_profit
        self.controller = PositionController()

    def process(self, position):

        # ======================================
        # Belum profit
        # ======================================

        if position.profit <= 0:

            return {
                "status": "WAITING",
                "action": "NONE",
                "reason": "Posisi belum profit."
            }

        # ======================================
        # Profit belum mencapai trigger
        # ======================================

        if position.profit < self.trigger_profit:

            return {
                "status": "WAITING",
                "action": "NONE",
                "reason": f"Profit belum mencapai {self.trigger_profit}."
            }

        # ======================================
        # SL belum ada
        # ======================================

        if position.sl == 0:

            result = self.controller.modify_sl(
                position,
                position.price_open
            )

            return {

                "status": "UPDATED",

                "action": "MOVE_SL",

                "reason": "Break Even diaktifkan.",

                "new_stop_loss": position.price_open,

                "result": result

            }

        # ======================================
        # Sudah Break Even
        # ======================================

        if abs(position.sl - position.price_open) < 0.01:

            return {

                "status": "SKIPPED",

                "action": "NONE",

                "reason": "Break Even sudah aktif."

            }

        # ======================================
        # Geser SL ke Entry
        # ======================================

        result = self.controller.modify_sl(
            position,
            position.price_open
        )

        return {

            "status": "UPDATED",

            "action": "MOVE_SL",

            "reason": "Stop Loss dipindahkan ke Break Even.",

            "new_stop_loss": position.price_open,

            "result": result

        }