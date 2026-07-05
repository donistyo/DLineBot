from app.mt5.session import MT5Session
from app.mt5.position_manager import PositionManager
from app.trading.break_even import BreakEvenManager

MT5Session.connect()

manager = PositionManager()
be = BreakEvenManager(trigger_profit=5)

positions = manager.get_positions("XAUUSD")

if not positions:

    print("Tidak ada posisi.")

else:

    result = be.process(positions[0])

    print(result)

MT5Session.disconnect()