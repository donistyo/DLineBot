from pathlib import Path

import pandas as pd


class TradeLogger:

    def __init__(self):

        self.output_dir = Path("logs")
        self.output_dir.mkdir(exist_ok=True)

        self.file = self.output_dir / "live_trade_log.csv"

    def log(

        self,

        prediction,

        decision,

        result,

        market,

        risk=None

    ):

        row = {

            "time": market["time"],

            "symbol": "XAUUSD",

            "signal": prediction["signal"],

            "confidence": prediction["confidence"],

            "action": decision["action"],

            "status": result.get("status"),

            "reason": result.get("reason"),

            "entry_price": None,

            "stop_loss": None,

            "take_profit": None,

            "lot_size": None

        }

        if risk is not None:

            row["entry_price"] = risk["entry_price"]
            row["stop_loss"] = risk["stop_loss"]
            row["take_profit"] = risk["take_profit"]
            row["lot_size"] = risk["lot_size"]

        df = pd.DataFrame([row])

        if self.file.exists():

            df.to_csv(

                self.file,

                mode="a",

                header=False,

                index=False

            )

        else:

            df.to_csv(

                self.file,

                index=False

            )

        return str(self.file)