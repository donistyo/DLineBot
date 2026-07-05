import MetaTrader5 as mt5
from app.mt5.order_builder import OrderBuilder
from app.mt5.order_sender import OrderSender

class MT5Trader:

    def __init__(self):

        pass

    # ======================================
    # Symbol Information
    # ======================================

    def symbol_info(self, symbol):

        info = mt5.symbol_info(symbol)

        if info is None:
            raise RuntimeError(
                f"Symbol {symbol} tidak ditemukan."
            )

        return info

    # ======================================
    # Tick
    # ======================================

    def tick(self, symbol):

        tick = mt5.symbol_info_tick(symbol)

        if tick is None:
            raise RuntimeError(
                "Gagal mengambil harga."
            )

        return tick

    # ======================================
    # Open Position
    # ======================================

    def positions(self, symbol=None):

        if symbol:

            positions = mt5.positions_get(
                symbol=symbol
            )

        else:

            positions = mt5.positions_get()

        if positions is None:

            return []

        return list(positions)

    def __init__(self, dry_run=True):

        self.dry_run = dry_run
        self.sender = OrderSender(dry_run)

    def buy(
            self,
            symbol,
            volume,
            sl,
            tp
        ):

            tick = self.tick(symbol)

            order = OrderBuilder.buy(

                symbol=symbol,

                volume=volume,

                price=tick.ask,

                sl=sl,

                tp=tp

            )

            if self.dry_run:

                print()
                print("=" * 60)
                print("DRY RUN BUY")
                print("=" * 60)

                for k, v in order.items():
                    print(f"{k:<15}: {v}")

            return self.sender.send(order)

    def sell(
            self,
            symbol,
            volume,
            sl,
            tp
        ):

            tick = self.tick(symbol)

            order = OrderBuilder.sell(

                symbol=symbol,

                volume=volume,

                price=tick.bid,

                sl=sl,

                tp=tp

            )

            if self.dry_run:

                print()
                print("=" * 60)
                print("DRY RUN SELL")
                print("=" * 60)

                for k, v in order.items():
                    print(f"{k:<15}: {v}")

                return order

            return mt5.order_send(order)