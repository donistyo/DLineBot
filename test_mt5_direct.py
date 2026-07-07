import MetaTrader5 as mt5

print("Initializing MT5...")
ok = mt5.initialize()
print(f"Initialize: {ok}")

if ok:
    acc = mt5.account_info()
    if acc:
        print(f"Login   : {acc.login}")
        print(f"Server  : {acc.server}")
        print(f"Balance : {acc.balance:.2f} {acc.currency}")
        print(f"Equity  : {acc.equity:.2f}")
    else:
        print("Account info: None")
        print(f"Last error: {mt5.last_error()}")
    mt5.shutdown()
else:
    print(f"Last error: {mt5.last_error()}")
