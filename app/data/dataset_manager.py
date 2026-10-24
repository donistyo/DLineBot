from datetime import datetime
from pathlib import Path

import pandas as pd


class DatasetManager:
    """Menyimpan dan menampilkan info dataset hasil preprocessing."""

    def __init__(self, base_dir="datasets"):
        self.base_dir = Path(base_dir)

    def save(self, df: pd.DataFrame, symbol: str, timeframe: str):
        self.base_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{symbol}_{timeframe}_{stamp}.csv"

        path = self.base_dir / filename

        df.to_csv(path, index=False)

        return str(path)

    def info(self, df: pd.DataFrame):
        print(f"Baris       : {len(df)}")
        print(f"Kolom       : {len(df.columns)}")
        print(f"Memori      : {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

        print("\nTipe Data")
        print("-" * 60)
        print(df.dtypes.to_string())
