import pandas as pd

from app.core.logger import logger


class DataCleaner:
    """
    Membersihkan dataset sebelum digunakan AI
    """

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:

        logger.info("Memulai proses cleaning dataset")

        before = len(df)

        # Hapus baris yang memiliki nilai kosong
        df = df.dropna().copy()

        after = len(df)

        logger.info(
            f"Data sebelum: {before} | sesudah: {after}"
        )

        # Reset index
        df.reset_index(drop=True, inplace=True)

        return df