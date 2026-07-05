import MetaTrader5 as mt5


class ResponseParser:

    @staticmethod
    def parse(result):

        if result is None:

            return {

                "success": False,
                "message": "Order gagal dikirim.",

            }

        success = (
            result.retcode ==
            mt5.TRADE_RETCODE_DONE
        )

        return {

            "success": success,

            "retcode": result.retcode,

            "order": result.order,

            "deal": result.deal,

            "volume": result.volume,

            "price": result.price,

            "comment": result.comment,

            "request_id": result.request_id

        }