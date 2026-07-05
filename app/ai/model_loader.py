from pathlib import Path

import joblib


class ModelLoader:

    def __init__(self):

        self.model_dir = Path("models")

    def load(self, filename):

        path = self.model_dir / filename

        if not path.exists():
            raise FileNotFoundError(f"Model tidak ditemukan: {path}")

        model = joblib.load(path)

        print(f"✓ Model berhasil dimuat : {path}")

        return model