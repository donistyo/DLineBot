from app.mt5.position_manager import PositionManager


class PositionMonitor:

    def __init__(self):

        self.manager = PositionManager()

    def monitor(self, symbol="XAUUSD"):

        positions = self.manager.get_positions(symbol)

        if not positions:

            return {
                "has_position": False,
                "count": 0,
                "positions": []
            }

        data = []

        for pos in positions:

            data.append({

                "ticket": pos.ticket,

                "type": "BUY" if pos.type == 0 else "SELL",

                "volume": pos.volume,

                "price_open": pos.price_open,

                "price_current": pos.price_current,

                "profit": pos.profit,

                "sl": pos.sl,

                "tp": pos.tp

            })

        return {

            "has_position": True,

            "count": len(data),

            "positions": data

        }