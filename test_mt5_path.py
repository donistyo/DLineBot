import MetaTrader5 as mt5

path = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"

print(f"Initialize MT5 with path...")
ok = mt5.initialize(path=path, timeout=120000)
print(f"Initialize: {ok}")

if ok:
    servers = mt5.servers_list()
    if servers:
        exness = [s for s in servers if "Exness" in s.lower()]
        print(f"\nExness servers:")
        for s in exness:
            print(f"  {s}")
    else:
        print("No servers list")
    mt5.shutdown()
else:
    print(f"Error: {mt5.last_error()}")
