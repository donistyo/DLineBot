import MetaTrader5 as mt5

mt5.initialize()

symbols = mt5.symbols_get()
if symbols:
    gold = [s.name for s in symbols if "GOLD" in s.name.upper() or "XAU" in s.name.upper()]
    print("Gold/XAU symbols:")
    for s in gold[:20]:
        print(f"  {s}")
else:
    print("No symbols")

mt5.shutdown()
