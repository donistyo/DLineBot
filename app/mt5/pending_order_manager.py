import MetaTrader5 as mt5

from app.mt5.session import MT5Session


class PendingOrderManager:

    def __init__(self, dry_run=True):
        self.dry_run = dry_run

    def get_pending(self, symbol=None):
        MT5Session.ensure_connection()

        if symbol:
            orders = mt5.orders_get(symbol=symbol)
        else:
            orders = mt5.orders_get()

        if orders is None:
            return []

        return [
            o for o in orders
            if o.type in (mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP)
        ]

    def cancel_pending(self, ticket):
        MT5Session.ensure_connection()

        if self.dry_run:
            return {"success": True, "dry_run": True, "action": "CANCEL", "ticket": ticket}

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }

        result = mt5.order_send(request)
        if result is None:
            return {"success": False, "message": "Gagal cancel pending order."}

        return {
            "success": result.retcode == mt5.TRADE_RETCODE_DONE,
            "retcode": result.retcode,
            "ticket": ticket,
        }

    def cancel_all(self, symbol=None):
        cancelled = []
        pending = self.get_pending(symbol)

        for order in pending:
            result = self.cancel_pending(order.ticket)
            cancelled.append(result)

        return cancelled

    def modify_pending(self, ticket, price=None, sl=None, tp=None, stop_price=None):
        MT5Session.ensure_connection()

        if self.dry_run:
            return {"success": True, "dry_run": True, "action": "MODIFY", "ticket": ticket}

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "order": ticket,
        }

        if price is not None:
            request["price"] = price
        if sl is not None:
            request["sl"] = sl
        if tp is not None:
            request["tp"] = tp

        result = mt5.order_send(request)
        if result is None:
            return {"success": False, "message": "Gagal modify pending order."}

        return {
            "success": result.retcode == mt5.TRADE_RETCODE_DONE,
            "retcode": result.retcode,
            "ticket": ticket,
        }

    def summary(self, symbol=None):
        pending = self.get_pending(symbol)
        result = []

        for o in pending:
            order_type = "BUY_STOP" if o.type == mt5.ORDER_TYPE_BUY_STOP else "SELL_STOP"
            result.append({
                "ticket": o.ticket,
                "symbol": o.symbol,
                "type": order_type,
                "volume": o.volume,
                "price": o.price,
                "sl": o.sl,
                "tp": o.tp,
                "magic": o.magic,
                "comment": o.comment,
                "time": str(o.time_setup),
            })

        return result
