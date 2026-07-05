from pathlib import Path
from datetime import datetime


class ReportExporter:

    def __init__(self):

        self.output_dir = Path("reports")
        self.output_dir.mkdir(exist_ok=True)

    def export(self, report):

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = self.output_dir / (
            f"trade_history_{timestamp}.csv"
        )

        report["trades"].to_csv(
            filename,
            index=False
        )

        return filename