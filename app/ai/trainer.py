from xgboost import XGBClassifier

from app.core.logger import logger


class XGBoostTrainer:

    def __init__(self):

        self.model = XGBClassifier(

            objective="multi:softmax",

            num_class=3,

            n_estimators=200,

            learning_rate=0.05,

            max_depth=6,

            subsample=0.8,

            colsample_bytree=0.8,

            random_state=42,

            eval_metric="mlogloss"
        )

    def train(
        self,
        X_train,
        y_train
    ):

        logger.info("Training XGBoost...")

        self.model.fit(
            X_train,
            y_train
        )

        logger.info("Training selesai")

        return self.model