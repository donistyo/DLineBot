from app.mt5.connection import MT5Connection
from app.mt5.position_manager import PositionManager
from app.mt5.position_controller import PositionController


def main():

    conn = MT5Connection()
    conn.connect()

    manager = PositionManager()
    controller = PositionController()

    positions = manager.get_positions("XAUUSD")

    print()
    print("=" * 60)
    print("POSITION CONTROLLER")
    print("=" * 60)

    if not positions:

        print("Tidak ada posisi terbuka.")

    else:

        pos = positions[0]

        print(f"Ticket : {pos.ticket}")
        print(f"Type   : {'BUY' if pos.type == 0 else 'SELL'}")
        print(f"Volume : {pos.volume}")
        print(f"Profit : {pos.profit}")

        # Jangan aktifkan dulu
        # result = controller.close(pos)
        # print(result)

    conn.disconnect()


if __name__ == "__main__":
    main()