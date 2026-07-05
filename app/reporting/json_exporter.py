import json
from pathlib import Path
from datetime import datetime


class JsonExporter:

    def __init__(self):
        self.output_dir = Path("reports")
        self.output_dir.mkdir(exist_ok=True)

    def export(
        self,
        data,
        filename
    ):

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        file = self.output_dir / f"{filename}_{timestamp}.json"

        with open(
            file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=4
            )

        # WAJIB ADA
        return str(file)