class RiskView:

    @staticmethod
    def show(risk=None):

        print()
        print("=" * 60)
        print("LIVE RISK")
        print("=" * 60)

        if risk is None:
            print("Tidak ada transaksi.")
            return

        print(f"Entry Price : {risk['entry_price']:.2f}")
        print(f"Lot Size    : {risk['lot_size']}")
        print(f"Stop Loss   : {risk['stop_loss']:.2f}")
        print(f"Take Profit : {risk['take_profit']:.2f}")