from app.mt5.session import MT5Session
import MetaTrader5 as mt5


class PositionManager:

    MT5Session.ensure_connection()

    def get_positions(self, symbol=None):

        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        return list(positions)

    def count(self, symbol=None):

        return len(self.get_positions(symbol))

    def has_position(self, symbol):

        return self.count(symbol) > 0

    def has_buy(self, symbol):

        positions = self.get_positions(symbol)

        return any(
            p.type == mt5.POSITION_TYPE_BUY
            for p in positions
        )

    def has_sell(self, symbol):

        positions = self.get_positions(symbol)

        return any(
            p.type == mt5.POSITION_TYPE_SELL
            for p in positions
        )

    def summary(self, symbol):

        positions = self.get_positions(symbol)

        result = []

        for p in positions:

            result.append({

                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit

            })

        return result