class RiskView:

    @staticmethod
    def show(risk=None):

        print()
        print("=" * 60)
        print("POSITION SIZING AI")
        print("=" * 60)

        if risk is None:
            print("Tidak ada transaksi.")
            return

        print(f"Entry        : {risk['entry_price']:.2f}")
        print(f"Lot Size     : {risk['lot_size']}")
        print(f"Stop Loss    : {risk['stop_loss']:.2f}")
        print(f"Take Profit  : {risk['take_profit']:.2f}")
        print(f"Risk Amount  : ${risk['risk_amount']:.2f}")

        if "confidence_mult" in risk:
            print()
            print("Multipliers:")
            print(f"  Confidence : {risk['confidence_mult']:.2f}")
            print(f"  Regime     : {risk['regime_mult']:.2f}")
            print(f"  Volatility : {risk['volatility_mult']:.2f}")
            print(f"  Spread     : {risk['spread_penalty']:.2f}")