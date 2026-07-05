class VolatilityFilter:

    def __init__(self, min_atr=5):

        self.min_atr = min_atr

    def allow(self, market):

        atr = market.get("ATR")

        if atr is None:

            return {
                "allowed": False,
                "reason": "Kolom ATR tidak ditemukan."
            }

        if atr >= self.min_atr:

            return {
                "allowed": True,
                "reason": "Volatilitas cukup."
            }

        return {
            "allowed": False,
            "reason": f"ATR terlalu kecil ({atr:.2f})."
        }