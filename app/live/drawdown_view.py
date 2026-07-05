class DrawdownView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("DRAWDOWN MANAGER")
        print("=" * 60)

        print()
        print(f"Peak Balance  : {result['peak_balance']:.2f}")
        print()
        print(f"Current       : {result['current_balance']:.2f}")
        print()
        print(f"Drawdown      : {result['drawdown']:.2f}%")
        print()
        print(f"Max DD        : {result['max_dd']:.0f}%")
        print()
        print(f"Current DD    : {result['drawdown']:.2f}%")

        if result["allowed"]:
            print()
            print(f"Trading       : ALLOWED")
        else:
            print()
            print(f"Trading       : BLOCKED")
