import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.data.collector import Collector
from app.indicators.engine import IndicatorEngine
from app.preprocessing.cleaner import DataCleaner
from app.preprocessing.labeler import LabelGenerator
from app.preprocessing.splitter import DataSplitter
from app.ai.trainer import XGBoostTrainer
from app.ai.evaluator import Evaluator
from app.models.model_manager import ModelManager
from app.config.settings import get_model_prefix, is_crypto_symbol, LABEL_ATR_MULTIPLIER


def train(symbol, timeframe, bars, atr_threshold, future_bars):
    print("=" * 60)
    print(f"TRAIN MODEL : {symbol} | {timeframe} | {bars} bars")
    print("=" * 60)

    collector = Collector()
    engine = IndicatorEngine()
    cleaner = DataCleaner()
    splitter = DataSplitter()

    labeler = LabelGenerator(
        future_bars=future_bars,
        atr_multiplier=atr_threshold,
    )

    trainer = XGBoostTrainer()
    evaluator = Evaluator()
    model_manager = ModelManager()

    df = collector.load(symbol=symbol, timeframe=timeframe, bars=bars)
    df = engine.calculate(df)
    df = cleaner.clean(df)

    if atr_threshold is not None:
        print(f"[LABEL] Threshold berbasis ATR: {atr_threshold} x ATR")
    df = labeler.generate(df)

    label_count = df["label"].value_counts().sort_index()
    print("\nDistribusi Label")
    print("-" * 60)
    print(f"SELL (0) : {label_count.get(0, 0)}")
    print(f"HOLD (1) : {label_count.get(1, 0)}")
    print(f"BUY  (2) : {label_count.get(2, 0)}")
    if len(df) > 0:
        print((label_count / len(df) * 100).round(2))

    X_train, X_valid, X_test, y_train, y_valid, y_test = splitter.split(df)

    print(f"\nTrain: {len(X_train)} | Valid: {len(X_valid)} | Test: {len(X_test)}")

    model = trainer.train(X_train, y_train)

    train_acc = evaluator.evaluate(model, X_train, y_train)
    valid_acc = evaluator.evaluate(model, X_valid, y_valid)
    test_acc = evaluator.evaluate(model, X_test, y_test)

    print(f"\nTraining Accuracy   : {train_acc:.4f}")
    print(f"Validation Accuracy : {valid_acc:.4f}")
    print(f"Testing Accuracy    : {test_acc:.4f}")

    prefix = get_model_prefix(symbol)
    suffix = "h1" if timeframe.upper() in ("H1", "H4", "D1") else "m1"
    filename = f"xgboost_{prefix}_{suffix}.joblib"
    model_path = model_manager.save(model, filename)

    print(f"\n[OK] Model disimpan : {model_path}")
    return model_path


def main():
    parser = argparse.ArgumentParser(description="Train XGBoost model per symbol")
    parser.add_argument("--symbol", default="XAUUSDc", help="MT5 symbol (default XAUUSDc)")
    parser.add_argument("--tf", default="M1", help="Timeframe (default M1)")
    parser.add_argument("--bars", type=int, default=2000, help="Jumlah bar (default 2000)")
    parser.add_argument("--atr", type=float, default=None,
                        help="Threshold label berbasis ATR (default: otomatis untuk kripto)")
    parser.add_argument("--future-bars", type=int, default=5,
                        help="Jumlah bar lookahead untuk label (default 5)")
    args = parser.parse_args()

    if args.atr is None and is_crypto_symbol(args.symbol):
        args.atr = LABEL_ATR_MULTIPLIER
        print(f"[INFO] Simbol kripto -> label ATR-based ({args.atr} x ATR)")

    train(args.symbol, args.tf, args.bars, args.atr, args.future_bars)


if __name__ == "__main__":
    main()
