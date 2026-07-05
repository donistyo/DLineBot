from pathlib import Path

import matplotlib.pyplot as plt


class DrawdownChart:
    """
    Membuat grafik Drawdown berdasarkan
    history balance hasil backtesting.
    """

    def __init__(self):

        self.output_dir = Path("reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, report):

        balance = report.get("history", [])

        if not balance:
            raise ValueError("History balance kosong.")

        # ==========================================
        # Hitung Running Peak
        # ==========================================

        peak = balance[0]
        peaks = []

        for value in balance:

            peak = max(peak, value)
            peaks.append(peak)

        # ==========================================
        # Hitung Drawdown
        # ==========================================

        drawdown = []

        for current, peak in zip(balance, peaks):

            dd = ((current - peak) / peak) * 100
            drawdown.append(dd)

        max_drawdown = min(drawdown)

        # ==========================================
        # Plot
        # ==========================================

        plt.figure(figsize=(12, 6))

        plt.plot(
            drawdown,
            linewidth=2.5,
            color="crimson",
            label="Drawdown"
        )

        plt.fill_between(
            range(len(drawdown)),
            drawdown,
            0,
            alpha=0.3,
            color="red"
        )

        plt.axhline(
            y=0,
            color="black",
            linestyle="--"
        )

        # ==========================================
        # Info Box
        # ==========================================

        info = (
            f"Maximum Drawdown\n"
            f"{max_drawdown:.2f}%"
        )

        plt.text(
            0.02,
            0.98,
            info,
            transform=plt.gca().transAxes,
            fontsize=9,
            verticalalignment="top",
            bbox=dict(
                facecolor="white",
                edgecolor="gray",
                alpha=0.85
            )
        )

        # ==========================================
        # Layout
        # ==========================================

        plt.title(
            "DLineBot Drawdown Curve",
            fontsize=15,
            fontweight="bold"
        )

        plt.xlabel("Trade Number")
        plt.ylabel("Drawdown (%)")

        plt.grid(
            True,
            linestyle="--",
            alpha=0.5
        )

        plt.legend()

        plt.tight_layout()

        # ==========================================
        # Save
        # ==========================================

        output_file = self.output_dir / "drawdown_curve.png"

        plt.savefig(
            output_file,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close()

        return str(output_file)