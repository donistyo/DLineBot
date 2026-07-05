from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


class FeatureImportance:

    def __init__(self):

        self.output_dir = Path("reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, model, feature_names):

        if not hasattr(model, "feature_importances_"):
            raise ValueError("Model tidak memiliki feature_importances_.")

        importance = model.feature_importances_

        df = pd.DataFrame({
            "Feature": feature_names,
            "Importance": importance
        })

        df = df.sort_values(
            by="Importance",
            ascending=True
        )

        plt.figure(figsize=(10, 7))

        plt.barh(
            df["Feature"],
            df["Importance"]
        )

        plt.title(
            "XGBoost Feature Importance",
            fontsize=15,
            fontweight="bold"
        )

        plt.xlabel("Importance Score")
        plt.ylabel("Feature")

        plt.grid(
            axis="x",
            linestyle="--",
            alpha=0.4
        )

        plt.tight_layout()

        output_file = self.output_dir / "feature_importance.png"

        plt.savefig(
            output_file,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close()

        return str(output_file)