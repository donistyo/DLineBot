class PerformanceView:

    @staticmethod
    def show(data):

        print()
        print("=" * 60)
        print("PERFORMANCE")
        print("=" * 60)

        print(f"Total Trade    : {data['total_trade']}")
        print(f"Win            : {data['win']}")
        print(f"Loss           : {data['loss']}")

        print()

        print(f"Win Rate       : {data['win_rate']:.2f}%")

        print()

        print(f"Gross Profit   : {data['gross_profit']:.2f}")
        print(f"Gross Loss     : {data['gross_loss']:.2f}")
        print(f"Net Profit     : {data['net_profit']:.2f}")

        print()

        print(f"Profit Factor  : {data['profit_factor']:.2f}")

        print()

        print(f"Average Win    : {data['avg_win']:.2f}")
        print(f"Average Loss   : {data['avg_loss']:.2f}")

        print()

        print(f"Largest Win    : {data['largest_win']:.2f}")
        print(f"Largest Loss   : {data['largest_loss']:.2f}")