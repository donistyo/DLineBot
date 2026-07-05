class SpreadFilter:

    def __init__(self, max_spread=80):

        self.max_spread = max_spread

    def allow(self, market):

        spread = market["spread"]

        if spread <= self.max_spread:

            return {
                "allowed": True,
                "reason": "Spread normal."
            }

        return {
            "allowed": False,
            "reason": f"Spread terlalu besar ({spread})."
        }