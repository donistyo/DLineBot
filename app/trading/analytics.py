from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from app.database.session import db_session
from app.database.models import TradeLog, EquitySnapshot


class Analytics:

    def __init__(self):
        self.learning_dir = Path("learning_data")

    def _query_all(self, model, *filters):
        with db_session() as db:
            q = db.query(model)
            for f in filters:
                q = q.filter(f)
            return q.all()

    def _query_count(self, model, *filters):
        with db_session() as db:
            q = db.query(model)
            for f in filters:
                q = q.filter(f)
            return q.count()

    # =====================================
    # Win Rate
    # =====================================

    def win_rate(self):
        total = self._query_count(TradeLog)
        wins = self._query_count(TradeLog, TradeLog.profit > 0)
        losses = self._query_count(TradeLog, TradeLog.profit < 0)
        return {
            "total": total,
            "win": wins,
            "loss": losses,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0
        }

    # =====================================
    # Monthly Profit
    # =====================================

    def monthly_profit(self, months=6):
        trades = self._query_all(TradeLog, TradeLog.profit.isnot(None))
        df = pd.DataFrame([{
            "month": t.time.strftime("%Y-%m"),
            "profit": t.profit or 0
        } for t in trades if t.time])

        if df.empty:
            return []

        grouped = df.groupby("month")["profit"].sum().reset_index()
        grouped = grouped.sort_values("month").tail(months)
        return grouped.to_dict("records")

    # =====================================
    # Drawdown Curve
    # =====================================

    def drawdown_curve(self, limit=100):
        with db_session() as db:
            snapshots = db.query(EquitySnapshot).order_by(EquitySnapshot.id.desc()).limit(limit).all()
        return [
            {"time": str(s.time), "drawdown": s.drawdown}
            for s in reversed(snapshots)
        ]

    # =====================================
    # Trade Distribution (Buy vs Sell)
    # =====================================

    def trade_distribution(self):
        buys = self._query_count(TradeLog, TradeLog.action == "BUY")
        sells = self._query_count(TradeLog, TradeLog.action == "SELL")
        holds = self._query_count(TradeLog, TradeLog.action == "HOLD")
        return {"buy": buys, "sell": sells, "hold": holds}

    # =====================================
    # Signal Distribution
    # =====================================

    def signal_distribution(self):
        buy_sig = self._query_count(TradeLog, TradeLog.signal == "BUY")
        sell_sig = self._query_count(TradeLog, TradeLog.signal == "SELL")
        return {"buy": buy_sig, "sell": sell_sig}

    # =====================================
    # Confidence Histogram
    # =====================================

    def confidence_histogram(self):
        trades = self._query_all(TradeLog, TradeLog.confidence.isnot(None))
        buckets = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
        for t in trades:
            c = t.confidence * 100
            if c < 20:
                buckets["0-20"] += 1
            elif c < 40:
                buckets["20-40"] += 1
            elif c < 60:
                buckets["40-60"] += 1
            elif c < 80:
                buckets["60-80"] += 1
            else:
                buckets["80-100"] += 1
        return buckets

    # =====================================
    # Hour Performance
    # =====================================

    def hour_performance(self):
        trades = self._query_all(TradeLog, TradeLog.profit.isnot(None), TradeLog.time.isnot(None))
        hours = {str(h).zfill(2): {"count": 0, "profit": 0.0} for h in range(24)}
        for t in trades:
            h = str(t.time.hour).zfill(2)
            hours[h]["count"] += 1
            hours[h]["profit"] += t.profit or 0
        return [{"hour": h, "count": v["count"], "profit": round(v["profit"], 2)}
                for h, v in sorted(hours.items())]

    # =====================================
    # Session Performance
    # =====================================

    def session_performance(self):
        trades = self._query_all(TradeLog, TradeLog.profit.isnot(None), TradeLog.time.isnot(None))
        sessions = {"Asia": {"count": 0, "profit": 0.0},
                    "London": {"count": 0, "profit": 0.0},
                    "New York": {"count": 0, "profit": 0.0}}
        for t in trades:
            h = t.time.hour
            if 0 <= h < 8:
                sess = "Asia"
            elif 8 <= h < 16:
                sess = "London"
            else:
                sess = "New York"
            sessions[sess]["count"] += 1
            sessions[sess]["profit"] += t.profit or 0
        return {s: {"count": v["count"], "profit": round(v["profit"], 2)}
                for s, v in sessions.items()}

    # =====================================
    # Heatmap (Day x Hour)
    # =====================================

    def heatmap(self):
        trades = self._query_all(TradeLog, TradeLog.profit.isnot(None), TradeLog.time.isnot(None))
        days = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
        data = {d: {str(h).zfill(2): 0.0 for h in range(24)} for d in days}
        for t in trades:
            d = days[t.time.weekday()]
            h = str(t.time.hour).zfill(2)
            data[d][h] += t.profit or 0

        result = []
        for d in days:
            for h in range(24):
                result.append({
                    "day": d,
                    "hour": str(h).zfill(2),
                    "profit": round(data[d][str(h).zfill(2)], 2)
                })
        return result

    # =====================================
    # AI Accuracy
    # =====================================

    def ai_accuracy(self):
        path = self.learning_dir / "trade_features.csv"
        if not path.exists():
            return {"accuracy": 0, "total": 0, "correct": 0, "confusion_matrix": {}}

        df = pd.read_csv(path)
        if "outcome" not in df.columns or "confidence" not in df.columns:
            return {"accuracy": 0, "total": 0, "correct": 0, "confusion_matrix": {}}

        df = df[df["outcome"] != 0].copy()
        if df.empty:
            return {"accuracy": 0, "total": 0, "correct": 0, "confusion_matrix": {}}

        df["predicted"] = df["confidence"].apply(lambda c: "BUY" if c > 0.5 else "SELL")
        df["actual"] = df["outcome"].apply(lambda p: "WIN" if p > 0 else "LOSS")

        tp = ((df["predicted"] == "BUY") & (df["actual"] == "WIN")).sum()
        fp = ((df["predicted"] == "BUY") & (df["actual"] == "LOSS")).sum()
        tn = ((df["predicted"] == "SELL") & (df["actual"] == "WIN")).sum()
        fn = ((df["predicted"] == "SELL") & (df["actual"] == "LOSS")).sum()

        correct = tp + tn
        total = len(df)

        return {
            "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
            "total": total,
            "correct": correct,
            "confusion_matrix": {
                "tp": int(tp), "fp": int(fp),
                "tn": int(tn), "fn": int(fn)
            }
        }

    # =====================================
    # Learning Progress
    # =====================================

    def learning_progress(self):
        path = self.learning_dir / "trade_features.csv"
        if not path.exists():
            return []

        df = pd.read_csv(path)
        if "saved_at" not in df.columns or "outcome" not in df.columns:
            return []

        df = df[df["outcome"] != 0].copy()
        if df.empty:
            return []

        df["saved_at"] = pd.to_datetime(df["saved_at"], errors="coerce")
        df = df.sort_values("saved_at")
        df["cum_win"] = (df["outcome"] > 0).cumsum()
        df["cum_total"] = range(1, len(df) + 1)
        df["cum_win_rate"] = (df["cum_win"] / df["cum_total"] * 100).round(1)

        result = []
        for _, row in df.iterrows():
            result.append({
                "time": str(row["saved_at"]),
                "win_rate": row["cum_win_rate"],
                "total": row["cum_total"]
            })

        return result[::max(1, len(result)//20)]
