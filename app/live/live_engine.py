import traceback
from app.data.collector import Collector
from app.indicators.engine import IndicatorEngine
from app.preprocessing.cleaner import DataCleaner

from app.ai.model_loader import ModelLoader
from app.ai.predictor import Predictor

from app.trading.decision_engine import DecisionEngine
from app.trading.risk_manager import RiskManager
from app.trading.auto_trader import AutoTrader

from app.mt5.account_manager import AccountManager

from app.config.features import FEATURE_COLUMNS

from app.logger.trade_logger import TradeLogger

from app.live.account_view import AccountView
from app.live.prediction_view import PredictionView
from app.live.decision_view import DecisionView
from app.live.risk_view import RiskView
from app.live.market_info import MarketInfo
from app.live.auto_trader_view import AutoTraderView

from app.mt5.session import MT5Session

from app.trading.position_monitor import PositionMonitor

from app.live.position_view import PositionView
from app.live.history_view import HistoryView
from app.trading.trade_filter import TradeFilter
from app.live.trade_filter_view import TradeFilterView

from app.trading.daily_risk_manager import DailyRiskManager
from app.live.daily_risk_view import DailyRiskView
from app.trading.position_filter import PositionFilter
from app.live.position_filter_view import PositionFilterView

from app.mt5.position_manager import PositionManager

from app.trading.exit_manager import ExitManager
from app.trading.break_even import BreakEvenManager
from app.trading.trailing_stop_manager import TrailingStopManager

from app.live.exit_view import ExitView
from app.trading.performance_manager import PerformanceManager
from app.live.performance_view import PerformanceView
from app.mt5.history_manager import HistoryManager
from app.trading.equity_manager import EquityManager
from app.live.equity_view import EquityView
from app.trading.drawdown_manager import DrawdownManager
from app.live.drawdown_view import DrawdownView
from app.trading.news_filter import NewsFilter
from app.live.news_filter_view import NewsFilterView
from app.trading.market_regime import MarketRegimeDetector
from app.live.market_regime_view import MarketRegimeView
from app.trading.confidence_manager import ConfidenceManager
from app.live.confidence_view import ConfidenceView
from app.live.dashboard_view import DashboardView
from app.notification.telegram_notifier import TelegramNotifier
from app.database.db_logger import DatabaseLogger
from app.database.session import init_db


class LiveEngine:

    def __init__(
        self,
        symbol="XAUUSD",
        timeframe="H1",
        bars=500,
        dry_run=True
    ):

        # =====================================
        # Configuration
        # =====================================

        self.symbol = symbol
        self.timeframe = timeframe
        self.bars = bars

        # =====================================
        # Core
        # =====================================

        self.collector = Collector()
        self.indicator = IndicatorEngine()
        self.cleaner = DataCleaner()

        # =====================================
        # AI
        # =====================================

        self.loader = ModelLoader()

        self.model = self.loader.load(
            "xgboost_xauusd_h1.joblib"
        )

        self.predictor = Predictor(
            self.model
        )

        # =====================================
        # Trading
        # =====================================

        self.decision_engine = DecisionEngine()

        self.risk_manager = RiskManager()

        self.auto_trader = AutoTrader(
            dry_run=dry_run
        )

        self.account_manager = AccountManager()

        self.trade_filter = TradeFilter()

        self.position_filter = PositionFilter()

        # =====================================
        # Logger
        # =====================================

        self.trade_logger = TradeLogger()

        # =====================================
        # Runtime
        # =====================================

        self.position_manager = PositionManager()

        self.position_monitor = PositionMonitor()

        self.break_even = BreakEvenManager()

        self.trailing = TrailingStopManager()

        self.exit_manager = ExitManager()

        self.daily_risk = DailyRiskManager()

        self.performance = PerformanceManager()

        self.history_manager = HistoryManager()

        self.equity_manager = EquityManager()

        self.drawdown_manager = DrawdownManager()

        news_country = [self.symbol[-3:]]
        self.news_filter = NewsFilter(countries=news_country)

        self.regime = MarketRegimeDetector()

        self.confidence = ConfidenceManager()

        self.telegram = TelegramNotifier()

        init_db()
        self.db_logger = DatabaseLogger()

        self.last_candle_time = None

        MT5Session.connect()

    # =====================================
    # Load Market
    # =====================================

    def load_market(self):

        df = self.collector.load(
            symbol=self.symbol,
            timeframe=self.timeframe,
            bars=self.bars
        )

        df = self.indicator.calculate(df)

        df = self.cleaner.clean(df)

        return df

    # =====================================
    # Prediction
    # =====================================

    def predict(self, df):
        missing = [
            col for col in FEATURE_COLUMNS
            if col not in df.columns
        ]

        if missing:
            raise RuntimeError(
                f"Feature tidak ditemukan: {missing}"
            )

        X_live = df[FEATURE_COLUMNS].tail(1)

        return self.predictor.predict(
            X_live
        )

    # =====================================
    # Decision
    # =====================================

    def decide(self, prediction):

        return self.decision_engine.decide(
            prediction
        )

    # =====================================
    # Risk
    # =====================================

    def calculate_risk(
        self,
        prediction,
        current_price
    ):

        account = self.account_manager.get_info()

        if account is None:

            raise RuntimeError(
                "Account MT5 belum tersedia."
            )

        balance = account.get("balance", 0)

        return self.risk_manager.calculate(

            prediction=prediction,

            current_price=current_price,

            balance=balance

        )

    # =====================================
    # Run One Cycle
    # =====================================

    def run_once(self):

        try:

            # ===============================
            # Load Market
            # ===============================

            df = self.load_market()
            
            if df.empty:
                raise RuntimeError("Data market kosong.")

            last = df.iloc[-1]


            # ===============================
            # New Candle Check
            # ===============================

            current_candle = last["time"]

            if current_candle == self.last_candle_time:

                print()
                print("=" * 60)
                print("SCHEDULER")
                print("=" * 60)
                print("Belum ada candle baru.")

                return None

            self.last_candle_time = current_candle

            # ===============================
            # Account
            # ===============================

            account = self.account_manager.get_info()

            if account is not None:

                AccountView.show(account)

            else:

                print()
                print("=" * 60)
                print("ACCOUNT INFORMATION")
                print("=" * 60)
                print("MT5 Account belum tersedia.")

            # ===============================
            # Equity
            # ===============================

            equity = self.equity_manager.get_info()

            EquityView.show(equity)

            # ===============================
            # Market Regime
            # ===============================

            regime = self.regime.detect(last)

            MarketRegimeView.show(regime)

            # ===============================
            # Prediction
            # ===============================

            prediction = self.predict(df)

            PredictionView.show(
                prediction,
                last
            )

            # ===============================
            # AI Confidence
            # ===============================

            confidence_result = self.confidence.allow(prediction)

            ConfidenceView.show(confidence_result)

            # ===============================
            # Decision
            # ===============================

            decision = self.decide(
                prediction
            )

            DecisionView.show(
                decision
            )

            # ===============================
            # Trade Filter
            # ===============================

            filter_result = self.trade_filter.allow(last)
            TradeFilterView.show(filter_result)

            # ===============================
            # Daily Risk
            # ===============================

            daily_result = self.daily_risk.allow()
            DailyRiskView.show(daily_result)

            # ===============================
            # Position Filter
            # ===============================

            position_result = self.position_filter.allow(
                self.symbol
            )

            PositionFilterView.show(position_result)

            # ===============================
            # Drawdown
            # ===============================

            drawdown_result = self.drawdown_manager.allow()

            DrawdownView.show(drawdown_result)

            # ===============================
            # News Filter
            # ===============================

            news_result = self.news_filter.allow()

            NewsFilterView.show(news_result)

            # ===============================
            # Exit Manager
            # ===============================

            positions = self.position_manager.get_positions(
                self.symbol
            )

            if positions:

                for position in positions:

                    be_result = self.break_even.process(position)
                    ExitView.show(be_result)

                    ts_result = self.trailing.process(position)
                    ExitView.show(ts_result)

                    exit_result = self.exit_manager.process(
                        position,
                        prediction
                    )

                    ExitView.show(exit_result)

            else:

                print()
                print("=" * 60)
                print("EXIT MANAGER")
                print("=" * 60)
                print("Tidak ada posisi yang perlu dikelola.")

            # ===============================
            # Risk
            # ===============================

            risk = None

            can_trade = (

                decision["action"] != "NO_TRADE"

                and filter_result["allowed"]

                and daily_result["allowed"]

                and position_result["allowed"]

            )

            if can_trade:

                risk = self.calculate_risk(

                    prediction,

                    last["close"]

                )

            RiskView.show(risk)

            # ===============================
            # Auto Trader
            # ===============================

            if not filter_result["allowed"]:

                result = {

                    "status": "BLOCKED",

                    "reason": filter_result["reason"]

                }

            elif not daily_result["allowed"]:

                result = {

                    "status": "BLOCKED",

                    "reason": daily_result["reason"]

                }

            elif not position_result["allowed"]:

                result = {

                    "status": "BLOCKED",

                    "reason": position_result["reason"]

                }

            else:

                result = self.auto_trader.execute(

                    decision=decision,

                    risk=risk,

                    symbol=self.symbol

                )

            AutoTraderView.show(result)

            if result["status"] in ("DRY_RUN", "SUCCESS"):
                self.telegram.notify_order(
                    prediction, risk, self.symbol
                )

            performance = self.performance.summary()

            PerformanceView.show(performance)

            history = self.history_manager.summary()

            HistoryView.show(history)

            # ===============================
            # Logger
            # ===============================

            log_file = self.trade_logger.log(

                prediction=prediction,

                decision=decision,

                result=result,

                market=last,

                risk=risk

            )

            print()
            print("=" * 60)
            print("TRADE LOGGER")
            print("=" * 60)
            print(f"Saved : {log_file}")

            trade_data = {
                "time": last["time"],
                "symbol": self.symbol,
                "signal": prediction["signal"],
                "confidence": prediction["confidence"],
                "action": decision["action"],
                "status": result.get("status"),
                "reason": result.get("reason"),
                "entry_price": risk["entry_price"] if risk else None,
                "stop_loss": risk["stop_loss"] if risk else None,
                "take_profit": risk["take_profit"] if risk else None,
                "lot_size": risk["lot_size"] if risk else None
            }
            self.db_logger.log_trade(trade_data)

            if equity:
                self.db_logger.log_equity(equity)

            # ===============================
            # Market Info
            # ===============================

            MarketInfo.show(last)

            position = self.position_monitor.monitor(
                self.symbol
            )

            PositionView.show(position)

            # ===============================
            # Dashboard Summary
            # ===============================

            spread_ok = self.trade_filter.spread_filter.allow(last)["allowed"]
            atr_ok = self.trade_filter.volatility_filter.allow(last)["allowed"]

            dash_data = {
                "signal": prediction["signal"],
                "confidence": prediction["confidence"],
                "trade": "YES" if decision["action"] != "NO_TRADE" else "NO",
                "spread": "OK" if spread_ok else "NG",
                "atr": "OK" if atr_ok else "NG",
                "risk": "OK" if risk is not None else "WAIT",
                "position": str(len(positions)) if positions else "NONE",
                "daily_risk": "OK" if daily_result["allowed"] else "NG",
                "drawdown": "OK" if drawdown_result["allowed"] else "NG",
                "auto_trader": result.get("status", "READY")
            }

            DashboardView.show(dash_data)

            # ===============================
            # Return
            # ===============================

            return {

                "account": account,

                "prediction": prediction,

                "decision": decision,

                "risk": risk,

                "market": last,

                "trading": result

            }

        except Exception as e:

            print()
            print("=" * 60)
            print("LIVE ENGINE ERROR")
            print("=" * 60)
            print(str(e))

            traceback.print_exc()

            return None

    # =====================================
    # Stop Engine
    # =====================================

    def stop(self):

        MT5Session.disconnect()

        print()
        print("=" * 60)
        print("LIVE ENGINE")
        print("=" * 60)
        print("Stopped.")