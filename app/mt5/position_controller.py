import traceback
import datetime
import MetaTrader5 as mt5

from app.mt5.session import MT5Session


CLOSE_LOG = "runtime/close_trace.log"


def _log_close(caller, ticket, symbol, profit):
    try:
        now = datetime.datetime.now().strftime("%H:%M:%S")
        stack = traceback.format_stack()[:-1]
        with open(CLOSE_LOG, "a") as f:
            f.write(f"\n[{now}] CLOSE by {caller} | ticket={ticket} {symbol} profit={profit}\n")
            for line in stack:
                f.write(line)
    except:
        pass


class PositionController:

    def __init__(self):

        MT5Session.ensure_connection()

    # ======================================
    # Close Position
    # ======================================

    def close(self, position):
        _log_close("POSITION_CONTROLLER", position.ticket, position.symbol, position.profit)
        import sys
        stack = traceback.format_stack()[:-1]
        caller = "UNKNOWN"
        for line in stack:
            if "EMERGENCY_EXIT" in line:
                caller = "EMERGENCY_EXIT"; break
            if "AI_EXIT" in line:
                caller = "AI_EXIT"; break
            if "EXIT_MANAGER" in line:
                caller = "EXIT_MANAGER"; break
            if "SMART_POSITION" in line:
                caller = "SMART_POSITION"; break
            if "TIME_EXIT" in line:
                caller = "TIME_EXIT"; break
            if "CLOSE_PARTIAL" in line:
                caller = "CLOSE_PARTIAL"; break
            if "DASHBOARD_MANUAL" in line:
                caller = "DASHBOARD_MANUAL"; break
            if "close_all" in line or "close_pos1" in line:
                caller = "SCRIPT"; break
        with open("runtime/close_trace.log", "a") as f:
            f.write(f"CALLER={caller}\n")

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
    # Close Partial Position
    # ======================================

    def close_partial(self, position, volume):
        _log_close("CLOSE_PARTIAL", position.ticket, position.symbol, position.profit)

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

            "volume": volume,

            "type": (
                mt5.ORDER_TYPE_SELL
                if position.type == mt5.POSITION_TYPE_BUY
                else mt5.ORDER_TYPE_BUY
            ),

            "price": price,

            "deviation": 20,

            "magic": 10001,

            "comment": "DLineBot SCALE OUT",

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