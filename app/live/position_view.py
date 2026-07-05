class PositionView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("OPEN POSITION")
        print("=" * 60)

        if not result["has_position"]:

            print("Tidak ada posisi terbuka.")
            return

        print(f"Total : {result['count']}")

        for p in result["positions"]:

            print("-" * 60)

            print(f"Ticket     : {p['ticket']}")
            print(f"Type       : {p['type']}")
            print(f"Volume     : {p['volume']}")
            print(f"Open Price : {p['price_open']:.2f}")
            print(f"Current    : {p['price_current']:.2f}")
            print(f"Profit     : {p['profit']:.2f}")
            print(f"SL         : {p['sl']:.2f}")
            print(f"TP         : {p['tp']:.2f}")