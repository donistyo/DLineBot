import MetaTrader5 as mt5


class OrderValidator:

    @staticmethod
    def validate(order):

        errors = []

        if order["volume"] <= 0:
            errors.append("Volume harus lebih besar dari 0.")

        if order["price"] <= 0:
            errors.append("Harga tidak valid.")

        if order["sl"] is not None and order["sl"] < 0:
            errors.append("Stop Loss tidak valid (negatif).")

        if order["tp"] is not None and order["tp"] < 0:
            errors.append("Take Profit tidak valid (negatif).")

        if order["symbol"] == "":
            errors.append("Symbol kosong.")

        info = mt5.symbol_info(order["symbol"])

        if info is None:
            errors.append("Symbol tidak ditemukan.")

        return {

            "valid": len(errors) == 0,
            "errors": errors

        }