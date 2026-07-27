from app.mt5.session import MT5Session

from app.mt5.position_manager import PositionManager
from app.mt5.order_builder import OrderBuilder
from app.mt5.order_sender import OrderSender
from app.mt5.pending_order_manager import PendingOrderManager


class AutoTrader:

    def __init__(self, dry_run=True):

        self.dry_run = dry_run

        self.position_manager = PositionManager()
        self.order_builder = OrderBuilder()
        self.order_sender = OrderSender(dry_run=dry_run)
        self.pending_manager = PendingOrderManager(dry_run=dry_run)

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
        success = isinstance(result, dict) and result.get("success", False)

        return {

            "status": "SUCCESS" if success else "FAILED",

            "result": result,
            "reason": "" if success else str(result.get("errors", result))

        }

    def execute_pending(
        self,
        decision,
        risk=None,
        symbol="XAUUSD",
        order_type="BUY_STOP",
        stop_price=None,
    ):

        MT5Session.ensure_connection()

        if decision["action"] == "NO_TRADE":
            return {
                "status": "SKIPPED",
                "reason": decision["reason"]
            }

        if risk is None:
            return {
                "status": "SKIPPED",
                "reason": "Risk Management belum tersedia."
            }

        if stop_price is None:
            stop_price = risk["entry_price"]

        if order_type == "BUY_STOP":
            request = self.order_builder.buy_stop(
                symbol=symbol,
                volume=risk["lot_size"],
                stop_price=stop_price,
                sl=risk["stop_loss"],
                tp=risk["take_profit"],
                magic=10001,
                comment="DLineBot_Pending"
            )
        elif order_type == "SELL_STOP":
            request = self.order_builder.sell_stop(
                symbol=symbol,
                volume=risk["lot_size"],
                stop_price=stop_price,
                sl=risk["stop_loss"],
                tp=risk["take_profit"],
                magic=10001,
                comment="DLineBot_Pending"
            )
        else:
            return {"status": "SKIPPED", "reason": f"Unknown order_type: {order_type}"}

        if self.dry_run:
            return {
                "status": "DRY_RUN",
                "request": request
            }

        result = self.order_sender.send(request)

        return {
            "status": "SUCCESS" if result else "FAILED",
            "result": result
        }