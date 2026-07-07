from datetime import datetime
import json
from pathlib import Path


class ModelVersionManager:

    def __init__(self, version_file="models/version.json"):
        self.version_file = Path(version_file)
        self.version_file.parent.mkdir(exist_ok=True)
        self._data = self._load()

    def _load(self):
        if self.version_file.exists():
            try:
                with open(self.version_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "current_version": "v1.0.0",
            "history": [],
            "created_at": datetime.now().isoformat()
        }

    def _save(self):
        with open(self.version_file, "w") as f:
            json.dump(self._data, f, indent=2)

    def get_current(self):
        return self._data.get("current_version", "v1.0.0")

    def get_info(self):
        current = self._data.get("current_version", "v1.0.0")
        history = self._data.get("history", [])
        last = history[-1] if history else {}
        return {
            "current_version": current,
            "accuracy": last.get("accuracy", 0),
            "dataset_size": last.get("dataset_size", 0),
            "training_date": last.get("training_date", "-"),
            "status": last.get("status", "Unknown"),
            "features_used": last.get("features_used", 0),
            "history": history[-5:] if history else []
        }

    def record_training(self, accuracy, dataset_size, features_used=0, status="Production"):
        version = self._bump_version()
        now = datetime.now()
        record = {
            "version": version,
            "accuracy": accuracy,
            "dataset_size": dataset_size,
            "features_used": features_used,
            "training_date": now.strftime("%Y-%m-%d %H:%M"),
            "status": status,
            "timestamp": now.isoformat()
        }
        self._data["current_version"] = version
        self._data["history"].append(record)
        self._save()
        return version

    def _bump_version(self):
        current = self._data.get("current_version", "v1.0.0")
        parts = current.replace("v", "").split(".")
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
        else:
            parts = ["1", "0", "1"]
        return "v" + ".".join(parts)

    def get_history(self, limit=10):
        return self._data.get("history", [])[-limit:]
