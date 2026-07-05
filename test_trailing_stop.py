from app.mt5.session import MT5Session
from app.mt5.position_manager import PositionManager
from app.trading.trailing_stop_manager import TrailingStopManager

MT5Session.connect()

manager = PositionManager()
trailing = TrailingStopManager(distance=10)

positions = manager.get_positions("XAUUSD")

if not positions:

    print("Tidak ada posisi.")

else:

    result = trailing.process(positions[0])

    print(result)

MT5Session.disconnect()