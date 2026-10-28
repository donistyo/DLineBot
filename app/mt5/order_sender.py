import MetaTrader5 as mt5

from app.mt5 import ea_bridge
from app.mt5.order_validator import OrderValidator
from app.mt5.response_parser import ResponseParser


class OrderSender:

    def __init__(self, dry_run=True):

        self.dry_run = dry_run

    def send(self, order):

        validation = OrderValidator.validate(order)

        if not validation["valid"]:

            return {

                "success": False,
                "errors": validation["errors"]

            }

        if self.dry_run:

            return {

                "success": True,
                "dry_run": True,
                "order": order

            }

        if ea_bridge.enabled():
            # Entry: tanpa fallback langsung. EA mungkin sudah mengeksekusi,
            # jadi cek posisi (id di request_id) sebelum kirim ulang.
            res = ea_bridge.execute(order)
            return res or {"success": False, "message": "EA tidak merespons; cek posisi sebelum kirim ulang"}

        result = mt5.order_send(order)

        return ResponseParser.parse(result)