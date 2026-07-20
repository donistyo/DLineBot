from app.mt5.order_builder import OrderBuilder
from app.mt5.order_sender import OrderSender
from app.mt5.pending_order_manager import PendingOrderManager


class GridManager:

    def __init__(
        self,
        symbol="XAUUSDc",
        dry_run=True,
        grid_layers=3,
        grid_atr_multiplier=0.5,
        sl_atr_multiplier=1.0,
        rr_ratio=2.0,
        lot_size=0.01,
        magic=10002,
    ):
        self.symbol = symbol
        self.dry_run = dry_run
        self.grid_layers = grid_layers
        self.grid_atr_multiplier = grid_atr_multiplier
        self.sl_atr_multiplier = sl_atr_multiplier
        self.rr_ratio = rr_ratio
        self.lot_size = lot_size
        self.magic = magic

        self.order_builder = OrderBuilder()
        self.order_sender = OrderSender(dry_run=dry_run)
        self.pending_manager = PendingOrderManager(dry_run=dry_run)

        self.active_levels = []
        self.triggered_levels = []

    def place_grid(self, current_price, atr):
        self._clear_grid()

        if atr <= 0:
            atr = 1.0

        spacing = atr * self.grid_atr_multiplier
        sl_distance = atr * self.sl_atr_multiplier
        tp_distance = sl_distance * self.rr_ratio

        self.active_levels = []
        self.triggered_levels = []
        results = []

        for i in range(1, self.grid_layers + 1):
            offset = spacing * i
            sl_offset = sl_distance
            tp_offset = tp_distance

            buy_stop_price = round(current_price + offset, 2)
            buy_sl = round(buy_stop_price - sl_offset, 2)
            buy_tp = round(buy_stop_price + tp_offset, 2)

            request_buy = self.order_builder.buy_stop(
                symbol=self.symbol,
                volume=self.lot_size,
                stop_price=buy_stop_price,
                sl=buy_sl,
                tp=buy_tp,
                magic=self.magic,
                comment=f"DLineBot_Grid_BUY_{i}"
            )
            result_buy = self.order_sender.send(request_buy)
            results.append({
                "layer": i,
                "side": "BUY_STOP",
                "stop_price": buy_stop_price,
                "sl": buy_sl,
                "tp": buy_tp,
                "result": result_buy,
            })
            self.active_levels.append({
                "layer": i,
                "side": "BUY_STOP",
                "stop_price": buy_stop_price,
                "filled": False,
            })

            sell_stop_price = round(current_price - offset, 2)
            sell_sl = round(sell_stop_price + sl_offset, 2)
            sell_tp = round(sell_stop_price - tp_offset, 2)

            request_sell = self.order_builder.sell_stop(
                symbol=self.symbol,
                volume=self.lot_size,
                stop_price=sell_stop_price,
                sl=sell_sl,
                tp=sell_tp,
                magic=self.magic,
                comment=f"DLineBot_Grid_SELL_{i}"
            )
            result_sell = self.order_sender.send(request_sell)
            results.append({
                "layer": i,
                "side": "SELL_STOP",
                "stop_price": sell_stop_price,
                "sl": sell_sl,
                "tp": sell_tp,
                "result": result_sell,
            })
            self.active_levels.append({
                "layer": i,
                "side": "SELL_STOP",
                "stop_price": sell_stop_price,
                "filled": False,
            })

        return results

    def manage(self):
        active_pending = self.pending_manager.get_pending(self.symbol)
        active_pending_prices = {
            round(o.price, 2) for o in active_pending
        }

        for level in self.active_levels:
            if level["filled"]:
                continue

            sp = level["stop_price"]
            if sp not in active_pending_prices:
                level["filled"] = True
                self.triggered_levels.append(level)

        return {
            "active": len(active_pending),
            "triggered": len(self.triggered_levels),
            "levels": self.active_levels,
        }

    def _clear_grid(self):
        self.pending_manager.cancel_all(self.symbol)
        self.active_levels = []
        self.triggered_levels = []

    def get_status(self):
        pending = self.pending_manager.summary(self.symbol)
        return {
            "symbol": self.symbol,
            "dry_run": self.dry_run,
            "active_pending": pending,
            "active_count": len(pending),
            "triggered_count": len(self.triggered_levels),
            "triggered_levels": self.triggered_levels,
        }
