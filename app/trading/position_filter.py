from app.mt5.position_manager import PositionManager


class PositionFilter:

    def __init__(self):

        self.position_manager = PositionManager()

    def allow(self, symbol="XAUUSD"):

        # ===========================
        # Masih ada posisi?
        # ===========================

        if self.position_manager.has_position(symbol):

            positions = self.position_manager.get_positions(symbol)

            if positions:

                pos = positions[0]

                trade_type = "BUY" if pos.type == 0 else "SELL"

                return {

                    "allowed": False,

                    "reason": f"Masih ada posisi {trade_type}.",

                    "position_type": trade_type,

                    "ticket": pos.ticket,

                    "volume": pos.volume

                }

            return {

                "allowed": False,

                "reason": "Masih ada posisi terbuka."

            }

        # ===========================
        # Tidak ada posisi
        # ===========================

        return {

            "allowed": True,

            "reason": "Tidak ada posisi terbuka."

        }