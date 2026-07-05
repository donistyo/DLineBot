import MetaTrader5 as mt5

from app.mt5.session import MT5Session


class PositionController:

    def __init__(self):

        MT5Session.ensure_connection()

    # ======================================
    # Close Position
    # ======================================

    def close(self, position):

        tick = mt5.symbol_info_tick(position.symbol)

        if tick is None:

            return {
                "success": False,
                "message": "Tick tidak tersedia."
            }

        price = (
            tick.bid
            if position.type == mt5.POSITION_TYPE_BUY
            else tick.ask
        )

        request = {

            "action": mt5.TRADE_ACTION_DEAL,

            "position": position.ticket,

            "symbol": position.symbol,

            "volume": position.volume,

            "type": (
                mt5.ORDER_TYPE_SELL
                if position.type == mt5.POSITION_TYPE_BUY
                else mt5.ORDER_TYPE_BUY
            ),

            "price": price,

            "deviation": 20,

            "magic": 10001,

            "comment": "DLineBot CLOSE",

            "type_time": mt5.ORDER_TIME_GTC,

            "type_filling": mt5.ORDER_FILLING_IOC

        }

        result = mt5.order_send(request)

        return {

            "success": result.retcode == mt5.TRADE_RETCODE_DONE,

            "retcode": result.retcode,

            "comment": result.comment

        }

    # ======================================
    # Modify Stop Loss
    # ======================================

    def modify_sl(self, position, stop_loss):

        request = {

            "action": mt5.TRADE_ACTION_SLTP,

            "position": position.ticket,

            "symbol": position.symbol,

            "sl": stop_loss,

            "tp": position.tp

        }

        result = mt5.order_send(request)

        return {

            "success": result.retcode == mt5.TRADE_RETCODE_DONE,

            "retcode": result.retcode,

            "comment": result.comment

        }

    # ======================================
    # Modify Take Profit
    # ======================================

    def modify_tp(self, position, take_profit):

        request = {

            "action": mt5.TRADE_ACTION_SLTP,

            "position": position.ticket,

            "symbol": position.symbol,

            "sl": position.sl,

            "tp": take_profit

        }

        result = mt5.order_send(request)

        return {

            "success": result.retcode == mt5.TRADE_RETCODE_DONE,

            "retcode": result.retcode,

            "comment": result.comment

        }

    # ======================================
    # Modify SL dan TP
    # ======================================

    def modify_sl_tp(
        self,
        position,
        stop_loss,
        take_profit
    ):

        request = {

            "action": mt5.TRADE_ACTION_SLTP,

            "position": position.ticket,

            "symbol": position.symbol,

            "sl": stop_loss,

            "tp": take_profit

        }

        result = mt5.order_send(request)

        return {

            "success": result.retcode == mt5.TRADE_RETCODE_DONE,

            "retcode": result.retcode,

            "comment": result.comment

        }