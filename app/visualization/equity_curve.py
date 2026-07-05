from pathlib import Path

import matplotlib.pyplot as plt


class EquityCurve:
    """
    Membuat grafik perkembangan equity (balance)
    selama proses backtesting.
    """

    def __init__(self):

        self.output_dir = Path("reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, report):

        balance = report.get("history", [])

        if not balance:
            raise ValueError("History balance kosong.")

        initial_balance = balance[0]
        ending_balance = balance[-1]

        plt.figure(figsize=(12, 6))

        # ==========================================
        # Equity Curve
        # ==========================================

        plt.plot(
            balance,
            linewidth=2.5,
            color="royalblue",
            label="Equity Curve"
        )

        # ==========================================
        # Initial Balance
        # ==========================================

        plt.axhline(
            y=initial_balance,
            color="gray",
            linestyle="--",
            linewidth=1.5,
            alpha=0.7,
            label="Initial Balance"
        )

        # ==========================================
        # Start Point
        # ==========================================

        plt.scatter(
            0,
            initial_balance,
            color="green",
            s=80,
            zorder=5,
            label="Start"
        )

        # ==========================================
        # End Point
        # ==========================================

        plt.scatter(
            len(balance) - 1,
            ending_balance,
            color="red",
            s=80,
            zorder=5,
            label="End"
        )

        # ==========================================
        # Statistik
        # ==========================================

        info = (
            f"Start Balance : ${initial_balance:.2f}\n"
            f"End Balance   : ${ending_balance:.2f}\n"
            f"Trades        : {len(balance)}"
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
            "DLineBot Equity Curve",
            fontsize=15,
            fontweight="bold"
        )

        plt.xlabel("Trade Number")
        plt.ylabel("Account Balance ($)")

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

        output_file = self.output_dir / "equity_curve.png"

        plt.savefig(
            output_file,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close()

        return str(output_file)