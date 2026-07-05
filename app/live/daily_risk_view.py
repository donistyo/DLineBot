class DailyRiskView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("DAILY RISK MANAGER")
        print("=" * 60)

        print(f"Allowed       : {result['allowed']}")
        print(f"Reason        : {result['reason']}")

        if "trade_today" in result:

            print(f"Trade Today   : {result['trade_today']}")

        if "profit_today" in result:

            print(f"Profit Today  : {result['profit_today']:.2f}")