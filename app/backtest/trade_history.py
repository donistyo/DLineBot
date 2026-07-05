from pathlib import Path


class TradeHistory:

    def __init__(self):
        self.folder = Path("history")
        self.folder.mkdir(exist_ok=True)

    def save(self, trades):

        path = self.folder / "trade_history.csv"

        trades.to_csv(
            path,
            index=False
        )

        return str(path)