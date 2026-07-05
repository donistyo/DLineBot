from app.mt5.connection import MT5Connection
from app.mt5.trader import MT5Trader


def main():

    conn = MT5Connection()

    conn.connect()

    trader = MT5Trader()

    info = trader.symbol_info("XAUUSD")

    print()

    print("=" * 60)
    print("SYMBOL INFO")
    print("=" * 60)

    print(info.name)
    print(info.trade_contract_size)
    print(info.point)

    print()

    positions = trader.positions("XAUUSD")

    print("=" * 60)
    print("OPEN POSITION")
    print("=" * 60)

    print(len(positions))

    conn.disconnect()


if __name__ == "__main__":
    main()