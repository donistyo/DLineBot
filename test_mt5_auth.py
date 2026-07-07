import MetaTrader5 as mt5

login = 160040915
password = "@Maluku2024"
server = "Exness-MT5Real20"

print(f"Connecting to {login} @ {server}...")
ok = mt5.initialize(login=login, password=password, server=server, timeout=30000)
print(f"Initialize: {ok}")

if ok:
    acc = mt5.account_info()
    if acc:
        print(f"Login   : {acc.login}")
        print(f"Server  : {acc.server}")
        print(f"Balance : {acc.balance:.2f} {acc.currency}")
        print(f"Equity  : {acc.equity:.2f}")
    else:
        print(f"Account info error: {mt5.last_error()}")
    mt5.shutdown()
else:
    print(f"Error: {mt5.last_error()}")
