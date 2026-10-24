from pathlib import Path

import joblib


class ModelManager:
    """Menyimpan dan memuat model AI ke folder models/."""

    def __init__(self, model_dir="models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def save(self, model, filename: str):
        path = self.model_dir / filename

        joblib.dump(model, path)

        return str(path)

    def load(self, filename: str):
        path = self.model_dir / filename

        if not path.exists():
            raise FileNotFoundError(f"Model tidak ditemukan: {path}")

        return joblib.load(path)
