from app.mt5.session import MT5Session
from app.mt5.position_manager import PositionManager
from app.mt5.position_controller import PositionController

MT5Session.connect()

manager = PositionManager()
controller = PositionController()

positions = manager.get_positions("XAUUSD")

if not positions:

    print("Tidak ada posisi.")

else:

    pos = positions[0]

    result = controller.modify_sl(
        pos,
        pos.price_open
    )

    print(result)

MT5Session.disconnect()