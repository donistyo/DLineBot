from sklearn.metrics import accuracy_score
from sklearn.metrics import classification_report
from sklearn.metrics import confusion_matrix

from app.core.logger import logger


class Evaluator:

    def evaluate(
        self,
        model,
        X,
        y,
        title="Validation"
    ):

        pred = model.predict(X)

        accuracy = accuracy_score(
            y,
            pred
        )

        print()

        print("=" * 50)
        print(title)
        print("=" * 50)

        print(f"Accuracy : {accuracy:.4f}")

        print()

        print("Classification Report")

        print(
            classification_report(
                y,
                pred
            )
        )

        print("Confusion Matrix")

        print(
            confusion_matrix(
                y,
                pred
            )
        )

        logger.info(
            f"{title} Accuracy : {accuracy:.4f}"
        )

        return accuracy