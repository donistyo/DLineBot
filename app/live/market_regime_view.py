class MarketRegimeView:

    @staticmethod
    def show(regime):

        print()
        print("=" * 60)
        print("MARKET REGIME")
        print("=" * 60)
        print()
        print(f"Trend    : {regime['trend']}")
        print()
        print(f"Strength : {regime['strength']}")
        print()
        print(f"Mode     : {regime['mode']}")
