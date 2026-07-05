class AccountView:

    @staticmethod
    def show(account):

        print()
        print("=" * 60)
        print("ACCOUNT INFORMATION")
        print("=" * 60)

        print(f"Login         : {account['login']}")
        print(f"Balance       : {account['balance']:.2f} {account['currency']}")
        print(f"Equity        : {account['equity']:.2f}")
        print(f"Profit        : {account['profit']:.2f}")
        print(f"Free Margin   : {account['free_margin']:.2f}")
        print(f"Margin Level  : {account['margin_level']:.2f}")
        print(f"Leverage      : 1:{account['leverage']}")