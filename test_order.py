from pprint import pprint

from app.mt5.connection import MT5Connection
from app.mt5.trader import MT5Trader


def main():

    conn = MT5Connection()
    conn.connect()

    trader = MT5Trader(
        dry_run=True
    )

    buy_result = trader.buy(
        symbol="XAUUSD",
        volume=0.01,
        sl=3300,
        tp=3400
    )

    print()
    print("=" * 60)
    print("BUY RESULT")
    print("=" * 60)
    pprint(buy_result)

    sell_result = trader.sell(
        symbol="XAUUSD",
        volume=0.01,
        sl=3400,
        tp=3300
    )

    print()
    print("=" * 60)
    print("SELL RESULT")
    print("=" * 60)
    pprint(sell_result)

    conn.disconnect()


if __name__ == "__main__":
    main()