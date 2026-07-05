from pprint import pprint

from app.mt5.connection import MT5Connection
from app.mt5.position_manager import PositionManager


def main():

    conn = MT5Connection()
    conn.connect()

    manager = PositionManager()

    print()
    print("=" * 60)
    print("POSITION MANAGER")
    print("=" * 60)

    print(f"Total Position : {manager.count()}")

    print(f"Has Position   : {manager.has_position('XAUUSD')}")

    print(f"Has BUY        : {manager.has_buy('XAUUSD')}")

    print(f"Has SELL       : {manager.has_sell('XAUUSD')}")

    print()

    pprint(manager.summary("XAUUSD"))

    conn.disconnect()


if __name__ == "__main__":
    main()