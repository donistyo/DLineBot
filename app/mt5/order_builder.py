import MetaTrader5 as mt5


class OrderBuilder:

    @staticmethod
    def buy(
        symbol,
        volume,
        price,
        sl,
        tp,
        magic=10001,
        comment="DLineBot"
    ):

        return {

            "action": mt5.TRADE_ACTION_DEAL,

            "symbol": symbol,

            "volume": volume,

            "type": mt5.ORDER_TYPE_BUY,

            "price": price,

            "sl": sl,

            "tp": tp,

            "deviation": 20,

            "magic": magic,

            "comment": comment,

            "type_time": mt5.ORDER_TIME_GTC,

            "type_filling": mt5.ORDER_FILLING_IOC

        }

    @staticmethod
    def sell(
        symbol,
        volume,
        price,
        sl,
        tp,
        magic=10001,
        comment="DLineBot"
    ):

        return {

            "action": mt5.TRADE_ACTION_DEAL,

            "symbol": symbol,

            "volume": volume,

            "type": mt5.ORDER_TYPE_SELL,

            "price": price,

            "sl": sl,

            "tp": tp,

            "deviation": 20,

            "magic": magic,

            "comment": comment,

            "type_time": mt5.ORDER_TIME_GTC,

            "type_filling": mt5.ORDER_FILLING_IOC

        }

    @staticmethod
    def buy_stop(
        symbol,
        volume,
        stop_price,
        sl,
        tp,
        magic=10001,
        comment="DLineBot_Grid"
    ):

        return {

            "action": mt5.TRADE_ACTION_PENDING,

            "symbol": symbol,

            "volume": volume,

            "type": mt5.ORDER_TYPE_BUY_STOP,

            "price": stop_price,

            "sl": sl,

            "tp": tp,

            "deviation": 20,

            "magic": magic,

            "comment": comment,

            "type_time": mt5.ORDER_TIME_GTC,

            "type_filling": mt5.ORDER_FILLING_IOC

        }

    @staticmethod
    def sell_stop(
        symbol,
        volume,
        stop_price,
        sl,
        tp,
        magic=10001,
        comment="DLineBot_Grid"
    ):

        return {

            "action": mt5.TRADE_ACTION_PENDING,

            "symbol": symbol,

            "volume": volume,

            "type": mt5.ORDER_TYPE_SELL_STOP,

            "price": stop_price,

            "sl": sl,

            "tp": tp,

            "deviation": 20,

            "magic": magic,

            "comment": comment,

            "type_time": mt5.ORDER_TIME_GTC,

            "type_filling": mt5.ORDER_FILLING_IOC

        }