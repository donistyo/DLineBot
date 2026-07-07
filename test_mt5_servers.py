import MetaTrader5 as mt5

print("Initializing MT5 without login...")
ok = mt5.initialize()
print(f"Initialize: {ok}")

if ok:
    servers = mt5.servers_list()
    if servers:
        exness = [s for s in servers if "Exness" in s or "exness" in s]
        print(f"\nExness servers found ({len(exness)}):")
        for s in exness:
            print(f"  {s}")
    else:
        print("No servers list available")
    mt5.shutdown()
else:
    print(f"Error: {mt5.last_error()}")
    print("\nPossible issues:")
    print("- MT5 terminal not installed or not running")
    print("- Try running terminal64.exe manually first")
    print("- Antivirus/firewall blocking")
