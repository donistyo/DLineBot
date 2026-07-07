import MetaTrader5 as mt5

print("Connecting to running terminal...")
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
        print("No account info")
    mt5.shutdown()
else:
    print(f"Error: {mt5.last_error()}")

    servers = mt5.servers_list()
    if servers:
        exness = [s for s in servers if "exness" in s.lower()]
        print(f"\nExness servers ({len(exness)}):")
        for s in exness:
            print(f"  {s}")
    else:
        print("\nNo server list available")
