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

    def close(self, position, caller=None):
        _log_close("POSITION_CONTROLLER", position.ticket, position.symbol, position.profit)
        if not caller:
            import sys
            stack = traceback.format_stack()[:-1]
            with open("runtime/close_trace.log", "a") as f:
                f.write("===== STACK DUMP =====\n")
                for i, ln in enumerate(stack):
                    f.write(f"[{i}] {ln.strip()[-120:]}\n")
            for line in stack:
                lower = line.lower()
                if "emergency_exit" in lower:
                    caller = "EMERGENCY_EXIT"; break
                if "ai_exit" in lower:
                    caller = "AI_EXIT"; break
                if "exit_manager" in lower:
                    caller = "EXIT_MANAGER"; break
                if "smart_position" in lower:
                    caller = "SMART_POSITION"; break
                if "time_exit" in lower:
                    caller = "TIME_EXIT"; break
                if "close_partial" in lower:
                    caller = "CLOSE_PARTIAL"; break
                if "dashboard_manual" in lower or "api_position_close" in lower:
                    caller = "DASHBOARD_MANUAL"; break
                if "recovery" in lower:
                    caller = "RECOVERY"; break
                if "telegram_closeall" in lower:
                    caller = "TELEGRAM_CLOSEALL"; break
                if "close_all" in lower or "close_pos1" in lower:
                    caller = "SCRIPT"; break
        if not caller:
            caller = "UNKNOWN"
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

            "comment": f"{caller} CLOSE",

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