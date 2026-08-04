from app.trading.session_filter import SessionFilter
from app.trading.spread_filter import SpreadFilter
from app.trading.volatility_filter import VolatilityFilter


class TradeFilter:

    def __init__(self, max_spread=80, min_atr=5, start_hour=7, end_hour=21, windows=None):

        self.session_filter = SessionFilter(
            start_hour=start_hour, end_hour=end_hour, windows=windows
        )

        self.spread_filter = SpreadFilter(max_spread=max_spread)

        self.volatility_filter = VolatilityFilter(min_atr=min_atr)

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