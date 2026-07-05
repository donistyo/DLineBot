from __future__ import annotations

import pandas as pd
from sklearn.model_selection import train_test_split

from app.core.logger import logger


class DataSplitter:
    """
    Membagi dataset menjadi:
    - Training
    - Validation
    - Testing

    Default:
        Train      : 70%
        Validation : 15%
        Test       : 15%
    """

    def __init__(
        self,
        train_size: float = 0.70,
        validation_size: float = 0.15,
        test_size: float = 0.15,
        shuffle: bool = False,
        random_state: int = 42
    ):
        self.train_size = train_size
        self.validation_size = validation_size
        self.test_size = test_size
        self.shuffle = shuffle
        self.random_state = random_state

    def split(
        self,
        df: pd.DataFrame
    ):

        logger.info("=" * 50)
        logger.info("MEMULAI SPLIT DATASET")
        logger.info("=" * 50)

        # ==================================
        # Pisahkan Feature & Target
        # ==================================

        from app.config.features import FEATURE_COLUMNS

        X = df[FEATURE_COLUMNS]

        y = df["label"]

        logger.info(f"Jumlah Feature : {X.shape[1]}")
        logger.info(f"Jumlah Dataset : {len(df)}")

        # ==================================
        # Split Train & Temp
        # ==================================

        X_train, X_temp, y_train, y_temp = train_test_split(
            X,
            y,
            train_size=self.train_size,
            shuffle=self.shuffle,
            random_state=self.random_state
        )

        # ==================================
        # Split Validation & Test
        # ==================================

        valid_ratio = (
            self.validation_size /
            (self.validation_size + self.test_size)
        )

        X_valid, X_test, y_valid, y_test = train_test_split(
            X_temp,
            y_temp,
            train_size=valid_ratio,
            shuffle=self.shuffle,
            random_state=self.random_state
        )

        # ==================================
        # Logging
        # ==================================

        logger.info("Split Dataset Berhasil")

        logger.info(f"Train      : {X_train.shape}")
        logger.info(f"Validation : {X_valid.shape}")
        logger.info(f"Test       : {X_test.shape}")

        logger.info("=" * 50)

        return (
            X_train,
            X_valid,
            X_test,
            y_train,
            y_valid,
            y_test
        )

    def summary(
        self,
        X_train,
        X_valid,
        X_test,
        y_train,
        y_valid,
        y_test
    ):
        """
        Menampilkan ringkasan dataset.
        """

        print("\n" + "=" * 50)
        print("DATA SPLIT SUMMARY")
        print("=" * 50)

        print(f"Train      : {X_train.shape}")
        print(f"Validation : {X_valid.shape}")
        print(f"Test       : {X_test.shape}")

        print()

        print(f"y_train    : {y_train.shape}")
        print(f"y_valid    : {y_valid.shape}")
        print(f"y_test     : {y_test.shape}")

        print("=" * 50)