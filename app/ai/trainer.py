from xgboost import XGBClassifier

from app.core.logger import logger


class XGBoostTrainer:

    def __init__(self):

        self.model = XGBClassifier(

            # objective tidak diset: XGBoost memilih multi:softprob otomatis untuk 3 kelas
            n_estimators=200,

            learning_rate=0.05,

            # dangkal + min_child_weight: data M1 sangat noisy, pohon dalam cepat overfit
            max_depth=4,

            min_child_weight=5,

            subsample=0.8,

            colsample_bytree=0.8,

            random_state=42
        )

    def train(
        self,
        X_train,
        y_train,
        sample_weight=None
    ):

        logger.info("Training XGBoost...")

        self.model.fit(
            X_train,
            y_train,
            sample_weight=sample_weight
        )

        logger.info("Training selesai")

        return self.model