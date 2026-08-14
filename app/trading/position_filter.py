from app.mt5.position_manager import PositionManager


class PositionFilter:

    def __init__(self, max_positions=5, max_same_direction=3):

        self.position_manager = PositionManager()
        self.max_positions = max_positions
        self.max_same_direction = max_same_direction

    def allow(self, symbol="XAUUSD", direction=None):

        positions = self.position_manager.get_positions(symbol) or []
        count = len(positions)

        if direction == "BUY":
            if self.position_manager.has_sell(symbol):
                return {
                    "allowed": False,
                    "reason": "Ada posisi SELL berlawanan arah.",
                    "position_count": count
                }
        elif direction == "SELL":
            if self.position_manager.has_buy(symbol):
                return {
                    "allowed": False,
                    "reason": "Ada posisi BUY berlawanan arah.",
                    "position_count": count
                }

        if count >= self.max_positions:
            return {
                "allowed": False,
                "reason": f"Max posisi ({self.max_positions}) tercapai.",
                "position_count": count
            }

        if direction in ("BUY", "SELL"):
            same = sum(
                1 for p in positions
                if (direction == "BUY" and p.type == 0) or
                   (direction == "SELL" and p.type == 1)
            )
            if same >= self.max_same_direction:
                return {
                    "allowed": False,
                    "reason": f"Max {self.max_same_direction} posisi {direction} searah tercapai.",
                    "position_count": count,
                    "same_direction": same
                }

        # =====================================
        # Anti averaging-down: jangan buka posisi
        # searah baru jika posisi searah yang
        # masih ada sedang floating loss.
        # =====================================
        if direction in ("BUY", "SELL"):
            loss_same = sum(
                1 for p in positions
                if (((direction == "BUY" and p.type == 0) or
                     (direction == "SELL" and p.type == 1)) and
                    (p.profit < 0))
            )
            if loss_same > 0:
                return {
                    "allowed": False,
                    "reason": f"Posisi {direction} searah masih floating loss ({loss_same}) - tunggu pulih atau SL.",
                    "position_count": count,
                    "loss_same_direction": loss_same
                }

        return {
            "allowed": True,
            "reason": f"Posisi {count}/{self.max_positions}.",
            "position_count": count
        }