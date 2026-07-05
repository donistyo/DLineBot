class EquityView:

    @staticmethod
    def show(equity):

        if equity is None:
            return

        print()
        print("=" * 60)
        print("ACCOUNT EQUITY")
        print("=" * 60)

        floating = equity["floating_pl"]
        sign = "+" if floating >= 0 else ""

        print()
        print(f"Balance      : {equity['balance']:.2f}")
        print()
        print(f"Equity       : {equity['equity']:.2f}")
        print()
        print(f"Floating P/L : {sign}{floating:.2f}")
        print()
        print(f"Drawdown     : {equity['drawdown']:.1f}%")
        print()
        print(f"Status       : {equity['status']}")
