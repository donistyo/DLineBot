from datetime import datetime
import json
import pandas as pd
import numpy as np
from pathlib import Path

from app.config.features import FEATURE_COLUMNS
from app.trading.model_version import ModelVersionManager
from app.ai.trainer import XGBoostTrainer
from app.ai.model_loader import ModelLoader
from app.preprocessing.cleaner import DataCleaner
from app.preprocessing.labeler import LabelGenerator


class TradeLearner:

    def __init__(self, model_name="xgboost_xauusd_m1.joblib", min_trades=20):
        self.model_name = model_name
        self.min_trades = min_trades
        self.trainer = XGBoostTrainer()
        self.cleaner = DataCleaner()
        self.labeler = LabelGenerator()
        self.learning_dir = Path("learning_data")
        self.learning_dir.mkdir(exist_ok=True)
        self.weights_file = self.learning_dir / "feature_weights.json"
        self._load_weights()

    # =====================================
    # Adaptive Weight Management
    # =====================================

    def _load_weights(self):
        if self.weights_file.exists():
            with open(self.weights_file) as f:
                self.feature_weights = json.load(f)
        else:
            self.feature_weights = {}

    def _save_weights(self):
        with open(self.weights_file, "w") as f:
            json.dump(self.feature_weights, f, indent=2)

    def adjust_weights(self, features, confidence, profit):
        feature_list = list(features.keys())
        intensity = abs(profit) / max(abs(profit), 1)
        if profit > 0:
            adjustment = confidence * intensity * 0.1
        else:
            adjustment = -confidence * intensity * 0.15

        for col in feature_list:
            if col not in FEATURE_COLUMNS:
                continue
            current = self.feature_weights.get(col, 1.0)
            self.feature_weights[col] = round(current + adjustment, 4)

        self.feature_weights["_bias"] = round(
            self.feature_weights.get("_bias", 1.0) + adjustment * 0.5, 4
        )

        mn = min(v for k, v in self.feature_weights.items() if isinstance(v, (int, float)))
        mx = max(v for k, v in self.feature_weights.items() if isinstance(v, (int, float)))
        if mx > mn:
            for k in self.feature_weights:
                v = self.feature_weights[k]
                if isinstance(v, (int, float)):
                    self.feature_weights[k] = round(0.5 + (v - mn) / (mx - mn), 4)

        self._save_weights()

    def get_feature_importance(self):
        return dict(self.feature_weights)

    def _compute_sample_weights(self, df):
        if not self.feature_weights:
            return None

        weights = np.ones(len(df))
        for i, (_, row) in enumerate(df.iterrows()):
            w = self.feature_weights.get("_bias", 1.0)
            for col in FEATURE_COLUMNS:
                if col in row and col in self.feature_weights:
                    val = row[col]
                    if isinstance(val, (int, float)) and not pd.isna(val):
                        w += self.feature_weights[col] * abs(val)
            weights[i] = max(0.1, w / len(FEATURE_COLUMNS))
        return weights

    # =====================================
    # Core Methods
    # =====================================

    def save_trade_features(self, features, outcome):
        record = features.copy()
        record["outcome"] = outcome
        record["saved_at"] = datetime.now().isoformat()

        path = self.learning_dir / "trade_features.csv"
        df_new = pd.DataFrame([record])
        if path.exists():
            df_old = pd.read_csv(path)
            df_all = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_all = df_new
        df_all.to_csv(path, index=False)
        return len(df_all)

    def retrain(self):
        path = self.learning_dir / "trade_features.csv"
        if not path.exists():
            return {"status": "SKIP", "reason": "Belum ada data learning."}

        df = pd.read_csv(path)
        if len(df) < self.min_trades:
            return {
                "status": "SKIP",
                "reason": f"Data kurang ({len(df)}/{self.min_trades})"
            }

        available = [c for c in FEATURE_COLUMNS if c in df.columns]
        if not available:
            return {"status": "SKIP", "reason": "Tidak ada feature column."}

        df = df.dropna(subset=available + ["outcome"]).copy()
        if len(df) < self.min_trades:
            return {
                "status": "SKIP",
                "reason": f"Setelah dropna: {len(df)}/{self.min_trades}"
            }

        df["label"] = df["outcome"].apply(self._outcome_to_label)
        df = df[df["label"] != 1].copy()
        df.loc[df["label"] == 2, "label"] = 1
        df = self.cleaner.clean(df)

        X = df[available]
        y = df["label"]

        if y.nunique() < 2:
            return {"status": "SKIP", "reason": f"Hanya {y.nunique()} kelas, perlu 2."}

        sample_weight = self._compute_sample_weights(df)

        model = self.trainer.train(X, y, sample_weight=sample_weight)

        model_dir = Path("models")
        model_dir.mkdir(exist_ok=True)
        model_path = model_dir / self.model_name
        import joblib
        joblib.dump(model, model_path)

        wins = int((df["outcome"] > 0).sum())
        accuracy = round(wins / len(df) * 100, 1) if len(df) > 0 else 0

        mvm = ModelVersionManager()
        mvm.record_training(
            accuracy=accuracy,
            dataset_size=len(df),
            features_used=len(available)
        )

        return {
            "status": "RETRAINED",
            "reason": f"Retrain sukses ({len(df)} samples).",
            "samples": len(df),
            "features_used": len(available),
            "accuracy": accuracy
        }

    def get_learning_stats(self):
        path = self.learning_dir / "trade_features.csv"
        if not path.exists():
            return {"total": 0, "win": 0, "loss": 0, "win_rate": 0}
        df = pd.read_csv(path)
        if "outcome" not in df.columns:
            return {"total": 0, "win": 0, "loss": 0, "win_rate": 0}
        wins = (df["outcome"] > 0).sum()
        losses = (df["outcome"] <= 0).sum()
        total = len(df)
        return {
            "total": total,
            "win": int(wins),
            "loss": int(losses),
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0
        }

    def _outcome_to_label(self, outcome):
        if outcome > 0:
            return 2
        elif outcome < 0:
            return 0
        return 1
