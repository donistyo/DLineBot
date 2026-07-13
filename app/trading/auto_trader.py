from app.mt5.session import MT5Session

from app.mt5.position_manager import PositionManager
from app.mt5.order_builder import OrderBuilder
from app.mt5.order_sender import OrderSender


class AutoTrader:

    def __init__(self, dry_run=True):

        self.dry_run = dry_run

        self.position_manager = PositionManager()
        self.order_builder = OrderBuilder()
        self.order_sender = OrderSender(dry_run=dry_run)

    def execute(
        self,
        decision,
        risk=None,
        symbol="XAUUSD"
    ):

        # ======================================
        # Pastikan koneksi MT5 tersedia
        # ======================================

        MT5Session.ensure_connection()

        # ======================================
        # Tidak ada sinyal
        # ======================================

        if decision["action"] == "NO_TRADE":

            return {
                "status": "SKIPPED",
                "reason": decision["reason"]
            }

        # ======================================
        # Risk belum dihitung
        # ======================================

        if risk is None:

            return {
                "status": "SKIPPED",
                "reason": "Risk Management belum tersedia."
            }

        # ======================================
        # Sudah ada posisi terbuka
        # ======================================

        if self.position_manager.has_position(symbol):

            return {
                "status": "SKIPPED",
                "reason": "Masih ada posisi terbuka."
            }

        # ======================================
        # Build Order Request
        # ======================================

        signal = decision["action"]
        if signal == "BUY":
            request = self.order_builder.buy(
                symbol, risk["lot_size"], risk["entry_price"],
                risk["stop_loss"], risk["take_profit"]
            )
        elif signal == "SELL":
            request = self.order_builder.sell(
                symbol, risk["lot_size"], risk["entry_price"],
                risk["stop_loss"], risk["take_profit"]
            )
        else:
            return {"status": "SKIPPED", "reason": f"Unknown signal: {signal}"}

        # ======================================
        # Dry Run
        # ======================================

        if self.dry_run:

            return {

                "status": "DRY_RUN",

                "request": request

            }

        # ======================================
        # Real Order
        # ======================================

        result = self.order_sender.send(request)

        return {

            "status": "SUCCESS" if result else "FAILED",

            "result": result

        }