import webbrowser
from pathlib import Path
from app.data.collector import Collector
from app.indicators.engine import IndicatorEngine
from app.data.dataset_manager import DatasetManager
from app.preprocessing.cleaner import DataCleaner
from app.preprocessing.labeler import LabelGenerator
from app.preprocessing.splitter import DataSplitter

from app.ai.trainer import XGBoostTrainer
from app.ai.evaluator import Evaluator
from app.ai.predictor import Predictor

from app.models.model_manager import ModelManager
from app.trading.decision_engine import DecisionEngine
from app.risk.risk_manager import RiskManager
from app.backtest.backtester import Backtester

from app.analytics.performance_analyzer import PerformanceAnalyzer
from app.backtest.trade_history import TradeHistory
from app.reporting.report_exporter import ReportExporter
from app.reporting.summary_report import SummaryReport

from app.reporting.report_manager import ReportManager
from app.visualization.equity_curve import EquityCurve
from app.visualization.drawdown_chart import DrawdownChart
from app.visualization.signal_distribution import SignalDistribution
from app.visualization.feature_importance import FeatureImportance

from app.reporting.dashboard_report import DashboardReport


def main():

    DEBUG = True

    # ==================================================
    # Inisialisasi Module
    # ==================================================

    collector = Collector()
    engine = IndicatorEngine()
    dataset = DatasetManager()

    cleaner = DataCleaner()
    labeler = LabelGenerator()
    splitter = DataSplitter()

    trainer = XGBoostTrainer()
    evaluator = Evaluator()
    model_manager = ModelManager()

    decision_engine = DecisionEngine()
    risk_manager = RiskManager()
    report_exporter = ReportExporter()
    summary_report = SummaryReport()
    backtester = Backtester()

    performance_analyzer = PerformanceAnalyzer()
    trade_history = TradeHistory()
    report_manager = ReportManager()

    equity_curve = EquityCurve()
    drawdown_chart = DrawdownChart()
    signal_distribution = SignalDistribution()
    feature_importance = FeatureImportance()

    dashboard = DashboardReport()

    print("=" * 60)
    print("          DLineBot Enterprise")
    print("=" * 60)

    # ==================================================
    # 1. Load Data
    # ==================================================

    df = collector.load(
        symbol="XAUUSDc",
        timeframe="M1",
        bars=2000
    )

    print("[OK] Data berhasil diambil")

    # ==================================================
    # 2. Hitung Indicator
    # ==================================================

    df = engine.calculate(df)

    print("[OK] Indicator berhasil dihitung")

    # ==================================================
    # 3. Cleaning Dataset
    # ==================================================

    df = cleaner.clean(df)

    print("[OK] Dataset berhasil dibersihkan")

    # ==================================================
    # 4. Generate Label
    # ==================================================

    df = labeler.generate(df)

    print("[OK] Label AI berhasil dibuat")

    print("\nPreview Label AI")
    print("-" * 60)

    print(
        df[
            [
                "time",
                "close",
                "future_close",
                "price_diff",
                "label"
            ]
        ].tail(15)
    )

    # ==================================================
    # 5. Simpan Dataset
    # ==================================================

    dataset_path = dataset.save(
        df,
        "XAUUSD",
        "M1"
    )

    print(f"\n[OK] Dataset disimpan : {dataset_path}")

    # ==================================================
    # 6. Informasi Dataset
    # ==================================================

    print("\nInformasi Dataset")
    print("-" * 60)

    dataset.info(df)

    if DEBUG:
        print("\nPreview Dataset")
        print("-" * 60)
        print(df.tail(10))

    # ==================================================
    # 7. Split Dataset
    # ==================================================

    (
        X_train,
        X_valid,
        X_test,
        y_train,
        y_valid,
        y_test
    ) = splitter.split(df)

    print("\nDataset Split")
    print("-" * 60)

    print(f"Training   : {len(X_train)}")
    print(f"Validation : {len(X_valid)}")
    print(f"Testing    : {len(X_test)}")

    print("\nShape Dataset")
    print("-" * 60)

    print(f"X_train : {X_train.shape}")
    print(f"X_valid : {X_valid.shape}")
    print(f"X_test  : {X_test.shape}")

    print()

    print(f"y_train : {y_train.shape}")
    print(f"y_valid : {y_valid.shape}")
    print(f"y_test  : {y_test.shape}")

    print(f"\nJumlah Feature : {X_train.shape[1]}")

    # ==================================================
    # Feature List
    # ==================================================

    print("\nDaftar Feature")
    print("-" * 60)

    for feature in X_train.columns:
        print(f"• {feature}")

    if DEBUG:

        print("\nFeature Training")
        print("-" * 60)
        print(X_train.head())

        print("\nTarget Training")
        print("-" * 60)
        print(
            y_train.to_frame(name="label").head()
        )

    # ==================================================
    # Statistik Label
    # ==================================================

    label_count = (
        df["label"]
        .value_counts()
        .sort_index()
    )

    print("\nDistribusi Label")
    print("-" * 60)

    print(f"SELL (0) : {label_count.get(0, 0)}")
    print(f"HOLD (1) : {label_count.get(1, 0)}")
    print(f"BUY  (2) : {label_count.get(2, 0)}")

    print("\nPersentase Label")
    print("-" * 60)

    print(
        (
            label_count / len(df) * 100
        ).round(2)
    )

    # ==================================================
    # 8. Training Model
    # ==================================================

    print("\n" + "=" * 60)
    print("Training AI XGBoost")
    print("=" * 60)

    model = trainer.train(
        X_train,
        y_train
    )

    print("[OK] Model berhasil dilatih")

    # ==================================================
    # 9. Evaluasi Model
    # ==================================================

    print("\nEvaluasi Model")
    print("-" * 60)

    train_accuracy = evaluator.evaluate(
        model,
        X_train,
        y_train,
        title="Training"
    )

    valid_accuracy = evaluator.evaluate(
        model,
        X_valid,
        y_valid,
        title="Validation"
    )

    test_accuracy = evaluator.evaluate(
        model,
        X_test,
        y_test,
        title="Testing"
    )

    # ==================================================
    # 10. Prediction
    # ==================================================

    predictor = Predictor(model)

    prediction = predictor.predict(X_test)

    print("\nPrediction Result")
    print("-" * 60)

    print(f"Signal      : {prediction['signal']}")
    print(f"Confidence  : {prediction['confidence']:.2%}")

    print("\nProbability")
    print("-" * 60)

    print(f"SELL : {prediction['probability']['SELL']:.2%}")
    print(f"HOLD : {prediction['probability']['HOLD']:.2%}")
    print(f"BUY  : {prediction['probability']['BUY']:.2%}")

    # ==================================================
    # 11. Trade Decision
    # ==================================================

    decision = decision_engine.decide(prediction)

    print("\nTrade Decision")
    print("-" * 60)

    print(f"Action      : {decision['action']}")
    print(f"Reason      : {decision['reason']}")
    print(f"Signal      : {prediction['signal']}")
    print(f"Confidence  : {prediction['confidence']:.2%}")

    # ==================================================
    # Risk Management
    # ==================================================

    risk = risk_manager.calculate(
        prediction=prediction,
        current_price=df.iloc[-1]["close"],
        balance=1000
    )

    print()
    print("=" * 60)
    print("Risk Management")
    print("=" * 60)

    print(f"Current Price : {risk['entry_price']:.2f}")
    print(f"Lot Size      : {risk['lot_size']}")
    print(f"Risk Amount   : ${risk['risk_amount']:.2f}")
    print(f"Stop Loss     : {risk['stop_loss']:.2f}")
    print(f"Take Profit   : {risk['take_profit']:.2f}")

    # ==================================================
    # Backtesting
    # ==================================================
    df_test = df.loc[X_test.index].copy()

    report = backtester.run(
        model,
        X_test,
        y_test,
        df.loc[X_test.index]
    )

    print()
    print("=" * 60)
    print("Trading Simulation")
    print("=" * 60)

    print(f"Initial Balance : ${report['initial_balance']:.2f}")
    print(f"Ending Balance  : ${report['ending_balance']:.2f}")
    print(f"Net Profit      : ${report['net_profit']:.2f}")

    print()

    print(f"Total Trade     : {report['total_trade']}")
    print(f"Winning Trade   : {report['win']}")
    print(f"Losing Trade    : {report['loss']}")
    print(f"Win Rate        : {report['win_rate']:.2f}%")

    # ==================================================
    # Reporting
    # ==================================================

    files = report_manager.export_all(
        report=report,
        symbol="XAUUSDc",
        timeframe="M1"
    )

    print()
    print("=" * 60)
    print("Export Report")
    print("=" * 60)

    print(f"Trade History : {files['csv']}")
    print(f"Summary       : {files['summary']}")
    print(f"Metadata      : {files['metadata']}")

    # ==================================================
    # Trade History
    # ==================================================

    history_path = trade_history.save(
        report["trades"]
    )

    print()
    print("=" * 60)
    print("Trade History")
    print("=" * 60)

    print(report["trades"].head())

    print(f"\nHistory disimpan : {history_path}")

    # ==================================================
    # Backtest Summary
    # ==================================================

    summary = summary_report.create(report)

    print()
    print("=" * 60)
    print("Backtest Summary")
    print("=" * 60)

    for key, value in summary.items():

        if isinstance(value, float):
            print(f"{key:<20}: {value:.2f}")
        else:
            print(f"{key:<20}: {value}")

    # ==================================================
    # Performance
    # ==================================================
    performance = performance_analyzer.analyze(report)

    print()
    print("=" * 60)
    print("Performance Analysis")
    print("=" * 60)

    print(f"Initial Balance : ${performance['initial_balance']:.2f}")
    print(f"Ending Balance  : ${performance['ending_balance']:.2f}")
    print(f"Net Profit      : ${performance['net_profit']:.2f}")
    print(f"ROI             : {performance['roi']:.2f}%")
    print(f"Average Profit  : ${performance['average_profit']:.2f}")
    print(f"Profit Factor   : {performance['profit_factor']:.2f}")
    print(f"Max Drawdown    : {performance['max_drawdown']:.2f}%")

    dashboard_file = dashboard.export(
        report,
        performance,
        symbol="XAUUSDc",
        timeframe="M1"
    )

    webbrowser.open(
        Path(dashboard_file).resolve().as_uri()
    )

    # ==================================================
    # Visualization
    # ==================================================

    equity_path = equity_curve.export(report)
    drawdown_path = drawdown_chart.export(report)
    signal_path = signal_distribution.export(report)
    feature_path = feature_importance.export(
        model,
        X_train.columns
    )

    print()
    print("=" * 60)
    print("Visualization")
    print("=" * 60)

    print(f"Equity Curve        : {equity_path}")
    print(f"Drawdown Curve      : {drawdown_path}")
    print(f"Signal Distribution : {signal_path}")
    print(f"Feature Importance  : {feature_path}")
    print(f"Dashboard Report    : {dashboard_file}")

    # ==================================================
    # 12. Simpan Model
    # ==================================================

    model_path = model_manager.save(
        model,
        "xgboost_xauusd_m1.joblib"
    )

    print(f"\n[OK] Model disimpan : {model_path}")

    # ==================================================
    # Ringkasan
    # ==================================================

    print("\n" + "=" * 60)
    print("Sprint 18 Selesai")
    print("=" * 60)

    print(f"Training Accuracy   : {train_accuracy:.4f}")
    print(f"Validation Accuracy : {valid_accuracy:.4f}")
    print(f"Testing Accuracy    : {test_accuracy:.4f}")

    print()

    print("[OK] MT5 Collector")
    print("[OK] Indicator Engine")
    print("[OK] Data Cleaner")
    print("[OK] Label Generator")
    print("[OK] Dataset Manager")
    print("[OK] Data Splitter")
    print("[OK] XGBoost Trainer")
    print("[OK] Model Evaluator")
    print("[OK] Predictor")
    print("[OK] Decision Engine")
    print("[OK] Risk Manager")
    print("[OK] Model Manager")

    print("\nSiap memasuki Sprint 20 (Backtesting Engine)")


if __name__ == "__main__":
    main()