from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


class SignalDistribution:

    def __init__(self):

        self.output_dir = Path("reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, report):

        trades = report["trades"]

        if isinstance(trades, pd.DataFrame):
            signal_count = trades["signal"].value_counts()
        else:
            raise ValueError("Trade history harus berupa DataFrame.")

        labels = signal_count.index.tolist()
        values = signal_count.values.tolist()

        plt.figure(figsize=(8, 5))

        bars = plt.bar(
            labels,
            values
        )

        # Tambahkan jumlah di atas bar
        for bar in bars:
            height = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                height,
                f"{int(height)}",
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold"
            )

        plt.title(
            "AI Signal Distribution",
            fontsize=14,
            fontweight="bold"
        )

        plt.xlabel("Signal")
        plt.ylabel("Total")

        plt.grid(
            axis="y",
            linestyle="--",
            alpha=0.4
        )

        plt.tight_layout()

        output_file = self.output_dir / "signal_distribution.png"

        plt.savefig(
            output_file,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close()

        return str(output_file)