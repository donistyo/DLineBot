class TradeFilterView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("TRADE FILTER")
        print("=" * 60)

        print(f"Allowed : {result['allowed']}")
        print(f"Reason  : {result['reason']}")