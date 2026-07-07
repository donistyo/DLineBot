from datetime import datetime
from pathlib import Path
import pandas as pd

from app.config.features import FEATURE_COLUMNS
from app.database.session import db_session
from app.database.models import TradeLog


class LearningManager:

    def __init__(self, trade_learner, history_manager, notifier=None):
        self.learner = trade_learner
        self.history = history_manager
        self.notifier = notifier
        self.learning_dir = Path("learning_data")
        self.learning_dir.mkdir(exist_ok=True)
        self._processed_ids = set()

    def track_open(self, ticket, features, signal, confidence):
        entry_time = datetime.now()
        path = self.learning_dir / "trade_features.csv"
        record = features.copy()
        record["signal"] = signal
        record["confidence"] = confidence
        record["ticket"] = ticket
        record["entry_time"] = entry_time.isoformat()
        record["outcome"] = 0
        record["saved_at"] = entry_time.isoformat()
        df_new = pd.DataFrame([record])
        if path.exists():
            df_old = pd.read_csv(path)
            df_all = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_all = df_new
        df_all.to_csv(path, index=False)
        return len(df_all)

    def check_closed(self):
        result = {"updated": 0, "retrained": False}
        try:
            deals = self.history.today()
        except Exception:
            return result

        for deal in deals:
            if deal.ticket in self._processed_ids:
                continue
            if deal.profit == 0:
                continue
            self._processed_ids.add(deal.ticket)
            ok = self._process_closed(deal)
            if ok:
                result["updated"] += 1
                self._update_db_profit(deal)

        if result["updated"] > 0:
            retrain = self.learner.retrain()
            result["retrained"] = retrain.get("status") == "RETRAINED"

        return result

    def _update_db_profit(self, deal):
        try:
            with db_session() as db:
                trade = db.query(TradeLog).filter_by(ticket=deal.ticket).first()
                if trade:
                    trade.profit = deal.profit
                    db.commit()
        except Exception:
            pass

    def _process_closed(self, deal):
        path = self.learning_dir / "trade_features.csv"
        if not path.exists():
            return False

        df = pd.read_csv(path)
        close_time = datetime.now()
        ticket_col = "ticket"
        matched = None

        if ticket_col in df.columns:
            try:
                df[ticket_col] = pd.to_numeric(df[ticket_col], errors="coerce").fillna(-1).astype(int)
            except Exception:
                pass
            mask = df[ticket_col] == deal.ticket
            if mask.any():
                matched = mask.idxmax() if mask.any() else None
                df.loc[mask, "outcome"] = deal.profit
                df.loc[mask, "close_time"] = close_time.isoformat()

        if matched is None and "entry_time" in df.columns:
            df["entry_time_dt"] = pd.to_datetime(df["entry_time"], errors="coerce")
            df = df.sort_values("entry_time_dt")
            pending = df[df["outcome"] == 0]
            if not pending.empty:
                matched = pending.index[-1]
                df.loc[matched, "outcome"] = deal.profit
                df.loc[matched, "close_time"] = close_time.isoformat()
                df.loc[matched, "ticket"] = deal.ticket
                df = df.drop(columns=["entry_time_dt"], errors="ignore")

        if matched is not None:
            df.to_csv(path, index=False)
            self._update_ai_weights(df.loc[matched])
            self._notify_close(deal, df.loc[matched])
            return True

        return False

    def _notify_close(self, deal, row):
        if not self.notifier or not self.notifier.enabled:
            return
        try:
            entry_time = row.get("entry_time")
            duration = 0
            if entry_time:
                try:
                    et = datetime.fromisoformat(str(entry_time))
                    duration = (datetime.now() - et).total_seconds() / 60
                except Exception:
                    pass

            signal = str(row.get("signal", ""))
            entry_price = float(row.get("close", 0)) or float(row.get("entry_price", 0)) or 0
            exit_price = deal.price

            self.notifier.notify_close(
                ticket=deal.ticket,
                symbol=deal.symbol,
                profit=deal.profit,
                entry_price=entry_price,
                exit_price=exit_price,
                reason=self._close_reason(deal),
                duration_minutes=duration,
                signal=signal
            )
        except Exception:
            pass

    def _close_reason(self, deal):
        if deal.profit > 0 and deal.comment:
            c = deal.comment.upper()
            if "TP" in c:
                return "Take Profit"
            if "TRAIL" in c:
                return "Trailing Stop"
        if deal.profit <= 0:
            return "Stop Loss"
        return "Closed"

    def _update_ai_weights(self, row):
        try:
            features = {col: row[col] for col in FEATURE_COLUMNS if col in row.index}
            confidence = float(row.get("confidence", 0.5))
            profit = float(row.get("outcome", 0))
            self.learner.adjust_weights(features, confidence, profit)
        except Exception:
            pass

    def get_learning_stats(self):
        return self.learner.get_learning_stats()
