from app.mt5.session import MT5Session

ok = MT5Session.connect()

if ok:
    from app.mt5.account_manager import AccountManager
    acc = AccountManager().get_info()
    if acc:
        print(f"Login   : {acc['login']}")
        print(f"Server  : {acc['server']}")
        print(f"Balance : {acc['balance']:.2f} {acc['currency']}")
        print(f"Equity  : {acc['equity']:.2f}")
        print(f"Leverage: 1:{acc['leverage']}")
    MT5Session.disconnect()
else:
    print("Gagal konek ke MT5")
