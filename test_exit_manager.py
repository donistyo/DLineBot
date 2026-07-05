from app.mt5.session import MT5Session
from app.mt5.position_manager import PositionManager
from app.trading.exit_manager import ExitManager

MT5Session.connect()

manager = PositionManager()

positions = manager.get_positions("XAUUSD")

if not positions:

    print("Tidak ada posisi.")

else:

    prediction = {
        "signal": "SELL"
    }

    result = ExitManager().process(
        positions[0],
        prediction
    )

    print(result)

MT5Session.disconnect()