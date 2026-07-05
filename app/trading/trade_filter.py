from app.trading.session_filter import SessionFilter
from app.trading.spread_filter import SpreadFilter
from app.trading.volatility_filter import VolatilityFilter


class TradeFilter:

    def __init__(self):

        self.session_filter = SessionFilter()

        self.spread_filter = SpreadFilter()

        self.volatility_filter = VolatilityFilter()

    def allow(self, market):

        result = self.session_filter.allow()

        if not result["allowed"]:
            return result

        result = self.spread_filter.allow(market)

        if not result["allowed"]:
            return result

        result = self.volatility_filter.allow(market)

        if not result["allowed"]:
            return result

        return {
            "allowed": True,
            "reason": "Semua filter lolos."
        }