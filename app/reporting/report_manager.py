from .report_exporter import ReportExporter
from .summary_report import SummaryReport
from .metadata_report import MetadataReport
from .json_exporter import JsonExporter


class ReportManager:

    def __init__(self):

        self.csv = ReportExporter()
        self.summary = SummaryReport()
        self.metadata = MetadataReport()
        self.json = JsonExporter()

    def export_all(
        self,
        report,
        symbol,
        timeframe
    ):

        csv_file = self.csv.export(report)

        summary = self.summary.create(report)

        metadata = self.metadata.create(
            symbol=symbol,
            timeframe=timeframe
        )

        summary_json = self.json.export(
            summary,
            "summary"
        )

        metadata_json = self.json.export(
            metadata,
            "metadata"
        )

        return {

            "csv": csv_file,
            "summary": summary_json,
            "metadata": metadata_json

        }