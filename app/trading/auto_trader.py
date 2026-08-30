from app.mt5.session import MT5Session

from app.mt5.position_manager import PositionManager
from app.mt5.order_builder import OrderBuilder
from app.mt5.order_sender import OrderSender
from app.mt5.pending_order_manager import PendingOrderManager
import json
import os
from datetime import datetime

# Counter untuk entry mix (2 → 1 → 2 → 1 → ...)
_entry_counter = 0

SIGNAL_HISTORY_PATH = "runtime/signal_history.json"

def _save_signal_history(signal, price, sl, tp, score=0, grade="-"):
    """Simpan history signal ke file untuk ditampilkan di chart."""
    try:
        history = []
        if os.path.exists(SIGNAL_HISTORY_PATH):
            with open(SIGNAL_HISTORY_PATH) as f:
                history = json.load(f)
        entry = {
            "signal": signal,
            "price": round(price, 5),
            "sl": round(sl, 5) if sl else None,
            "tp": round(tp, 5) if tp else None,
            "score": score,
            "grade": grade,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": int(datetime.now().timestamp()),
        }
        history.append(entry)
        # Simpan max 50 signal terakhir
        history = history[-50:]
        with open(SIGNAL_HISTORY_PATH, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass


class AutoTrader:

    def __init__(self, dry_run=True):

        self.dry_run = dry_run

        self.position_manager = PositionManager()
        self.order_builder = OrderBuilder()
        self.order_sender = OrderSender(dry_run=dry_run)
        self.pending_manager = PendingOrderManager(dry_run=dry_run)

    def _entry_copies(self):
        global _entry_counter
        try:
            import json
            with open("runtime/trade_config.json") as f:
                cfg = json.load(f)
            mode = cfg.get("entry_copies_mode", "mixed")
            if mode == "mixed":
                # 2 → 1 → 2 → 1 → ...
                _entry_counter += 1
                return 2 if _entry_counter % 2 == 1 else 1
            else:
                return max(1, int(cfg.get("entry_copies", 1)))
        except Exception:
            return 1

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
        # Build Order Request
        # ======================================

        signal = decision["action"]
        copies = self._entry_copies()
        requests = []
        for i in range(copies):
            comment = f"DLineBot #{i + 1}" if copies > 1 else "DLineBot"
            if signal == "BUY":
                requests.append(self.order_builder.buy(
                    symbol, risk["lot_size"], risk["entry_price"],
                    risk["stop_loss"], risk["take_profit"], comment=comment
                ))
            elif signal == "SELL":
                requests.append(self.order_builder.sell(
                    symbol, risk["lot_size"], risk["entry_price"],
                    risk["stop_loss"], risk["take_profit"], comment=comment
                ))
            else:
                return {"status": "SKIPPED", "reason": f"Unknown signal: {signal}"}

        # ======================================
        # Dry Run
        # ======================================

        if self.dry_run:

            return {

                "status": "DRY_RUN",

                "request": requests if copies > 1 else requests[0]

            }

        # ======================================
        # Real Order
        # ======================================

        results = []
        for request in requests:
            result = self.order_sender.send(request)
            success = isinstance(result, dict) and result.get("success", False)
            results.append({
                "success": success,
                "result": result,
                "reason": "" if success else str(result.get("errors", result))
            })

        all_success = all(r["success"] for r in results)
        # Simpan signal history jika order berhasil
        if all_success:
            _save_signal_history(
                signal=signal,
                price=risk.get("entry_price", 0),
                sl=risk.get("stop_loss"),
                tp=risk.get("take_profit"),
                score=risk.get("score", 0),
                grade=risk.get("grade", "-"),
            )
        return {

            "status": "SUCCESS" if all_success else "FAILED",

            "results": results,
            "reason": "" if all_success else "; ".join(
                r["reason"] for r in results if not r["success"]
            )

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