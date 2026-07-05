class HistoryView:

    @staticmethod
    def show(data):

        print()
        print("=" * 60)
        print("TODAY HISTORY")
        print("=" * 60)

        print(f"Trade          : {data['trade']}")
        print(f"Win            : {data['win']}")
        print(f"Loss           : {data['loss']}")
        print(f"Win Rate       : {data['win_rate']:.2f}%")

        print()

        print(f"Profit         : {data['profit']:.2f}")
        print(f"Gross Profit   : {data['gross_profit']:.2f}")
        print(f"Gross Loss     : {data['gross_loss']:.2f}")

        print()

        print(f"Profit Factor  : {data['profit_factor']:.2f}")
        print(f"Largest Win    : {data['largest_win']:.2f}")
        print(f"Largest Loss   : {data['largest_loss']:.2f}")