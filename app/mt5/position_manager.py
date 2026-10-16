from app.mt5.session import MT5Session
import MetaTrader5 as mt5


class PositionManager:

    def __init__(self):
        MT5Session.ensure_connection()

    def get_positions(self, symbol=None, managed_only=False):

        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        # managed_only: hanya posisi milik sistem
        # (magic != 0). Order manual (magic 0) dibiarkan
        # sendiri - tidak dihitung & tidak dikelola engine.
        if managed_only:
            positions = [p for p in positions if getattr(p, "magic", 0) != 0]

        return list(positions)

    def count(self, symbol=None, managed_only=False):

        return len(self.get_positions(symbol, managed_only=managed_only))

    def has_position(self, symbol, managed_only=False):

        return self.count(symbol, managed_only=managed_only) > 0

    def has_buy(self, symbol, managed_only=False):

        positions = self.get_positions(symbol, managed_only=managed_only)

        return any(
            p.type == mt5.POSITION_TYPE_BUY
            for p in positions
        )

    def has_sell(self, symbol, managed_only=False):

        positions = self.get_positions(symbol, managed_only=managed_only)

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