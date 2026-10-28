"""Eksperimen: apakah fitur relatif menaikkan akurasi/profit di atas tebakan acak?
Tidak menyentuh model live, dataset, atau history. Jalankan: venv\\Scripts\\python.exe experiment_features.py
"""
import numpy as np
from sklearn.metrics import accuracy_score, log_loss

from app.ai.trainer import XGBoostTrainer
from app.backtest.backtester import Backtester
from app.config.features import FEATURE_COLUMNS
from app.data.collector import Collector
from app.indicators.engine import IndicatorEngine
from app.preprocessing.cleaner import DataCleaner
from app.preprocessing.feature_builder import EXTRA_FEATURES, build_features
from app.preprocessing.labeler import LabelGenerator

TP, SL, BARS = 2.0, 1.0, 30

df = Collector().load(symbol="XAUUSDc", timeframe="M1", bars=99999)
df = DataCleaner().clean(IndicatorEngine().calculate(df))
df = build_features(df)
df = LabelGenerator(tp_atr=TP, sl_atr=SL, max_bars=BARS).generate(df)

n = len(df)
i1 = int(n * 0.70)
i2 = i1 + BARS + int((n - i1 - BARS) * 0.5)
parts = {
    "train": slice(0, i1),
    "valid": slice(i1 + BARS, i2),
    "test": slice(i2 + BARS, n),
}
print(f"\nBar: {n} | label: {df['label'].value_counts(normalize=True).sort_index().round(3).to_dict()}")

for name, feats in (("LAMA (21 fitur mentah)", FEATURE_COLUMNS), ("BARU (fitur relatif)", EXTRA_FEATURES)):

    X = df[feats]
    y = df["label"]
    model = XGBoostTrainer().train(X.iloc[parts["train"]], y.iloc[parts["train"]])

    print("\n" + "=" * 60)
    print(name)
    print("=" * 60)

    for part in ("valid", "test"):
        Xp, yp = X.iloc[parts[part]], y.iloc[parts[part]]
        proba = model.predict_proba(Xp)
        prior = np.bincount(y.iloc[parts["train"]], minlength=3) / i1
        base = log_loss(yp, np.tile(prior, (len(yp), 1)), labels=[0, 1, 2])
        print(f"{part:<5} acc={accuracy_score(yp, proba.argmax(1)):.4f} "
              f"logloss={log_loss(yp, proba, labels=[0, 1, 2]):.4f} (baseline prior {base:.4f})")

    Xt, yt = X.iloc[parts["test"]], y.iloc[parts["test"]]
    dft = df.iloc[parts["test"]]
    proba = model.predict_proba(Xt)
    print(f"\nTest backtest (TP {TP}xATR / SL {SL}xATR, spread dikurangkan, break-even win rate ~33%)")
    print(f"{'min_conf':>8} {'trade':>6} {'win%':>6} {'PF':>5} {'net$':>9} {'maxDD%':>7}")
    for mc in (0.40, 0.45, 0.50, 0.55, 0.60):
        r = Backtester(tp_atr=TP, sl_atr=SL, max_bars=BARS, min_confidence=mc).run(model, Xt, yt, dft)
        h = np.array(r["history"])
        dd = ((np.maximum.accumulate(h) - h) / np.maximum.accumulate(h)).max() * 100
        pf = r["gross_profit"] / r["gross_loss"] if r["gross_loss"] else float("inf")
        print(f"{mc:>8.2f} {r['total_trade']:>6} {r['win_rate']:>6.1f} {pf:>5.2f} {r['net_profit']:>9.2f} {dd:>7.1f}")

    if name.startswith("BARU"):
        imp = sorted(zip(model.feature_importances_, feats), reverse=True)[:8]
        print("\nTop fitur:", ", ".join(f"{f}={v:.3f}" for v, f in imp))
