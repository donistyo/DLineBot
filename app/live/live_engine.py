import json
import traceback
from datetime import datetime
from pathlib import Path
from app.data.collector import Collector
from app.indicators.engine import IndicatorEngine
from app.preprocessing.cleaner import DataCleaner

from app.ai.model_loader import ModelLoader
from app.ai.predictor import Predictor

from app.trading.decision_engine import DecisionEngine
from app.trading.risk_manager import RiskManager
from app.trading.position_sizing import PositionSizingAI
from app.trading.multi_tf_confirmation import MultiTimeframeConfirmation
from app.trading.trade_scorer import TradeScorer
from app.trading.trade_learner import TradeLearner
from app.trading.auto_trader import AutoTrader

from app.mt5.account_manager import AccountManager

from app.config.features import FEATURE_COLUMNS
from app.config.settings import DASHBOARD_URL, BROKER

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
from app.trading.smart_position_manager import SmartPositionManager

from app.live.exit_view import ExitView
from app.live.smart_position_view import SmartPositionView
from app.trading.time_exit import TimeExit
from app.live.time_exit_view import TimeExitView
from app.trading.ai_exit import AIExit
from app.live.ai_exit_view import AIExitView
from app.trading.emergency_exit import EmergencyExit
from app.live.emergency_exit_view import EmergencyExitView
from app.trading.smart_scalping import SmartScalpingEngine
from app.live.smart_scalping_view import SmartScalpingView
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
from app.strategy.daily_trend_engine import DailyTrendEngine
from app.strategy.real_fundamental_engine import RealFundamentalEngine
from app.strategy.daily_trend_view import DailyTrendView
from app.live.multi_tf_view import MultiTFView
from app.live.score_view import ScoreView
from app.trading.learning_manager import LearningManager
from app.trading.fundamental_trader import FundamentalTrader
from app.trading.grid_manager import GridManager


class LiveEngine:

    def __init__(
        self,
        symbol="XAUUSDc",
        timeframe="M1",
        bars=2000,
        dry_run=True,
        mode="scalp",
        grid_mode=False,
        grid_layers=3,
        grid_atr_multiplier=0.5,
    ):

        # =====================================
        # Configuration
        # =====================================

        self.symbol = symbol
        self.timeframe = timeframe
        self.bars = bars
        self.mode = mode

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

        model_name = "xgboost_xauusd_m1.joblib" if mode == "scalp" else "xgboost_xauusd_h1.joblib"
        self.model = self.loader.load(model_name)

        self.predictor = Predictor(
            self.model
        )

        # =====================================
        # Trading
        # =====================================

        if mode == "scalp":
            confidence_th = 0.60
            sl_points = 4
            rr_ratio = 1.5
            max_spread = 40
            min_atr_val = 0.5
        else:
            confidence_th = 0.70
            sl_points = 10
            rr_ratio = 2
            max_spread = 80
            min_atr_val = 5

        # =====================================
        # Broker Profile Overrides
        # =====================================

        if BROKER == "exness":
            print()
            print("=" * 60)
            print("BROKER PROFILE : Exness")
            print("=" * 60)
            print("Spread   : max_spread 40 -> 200")
            print("SL       : sl_points  4  -> 5")
            print("TimeExit : 120 menit  -> 60 menit")
            print("Risk     : 2%         -> 1.5%")
            print("DailyMax : 15         -> 50")

            if mode == "scalp":
                max_spread = 500
                sl_points = 6
                min_atr_val = 0.5

        self.decision_engine = DecisionEngine(
            min_scalp_score=30
        )

        self.risk_manager = RiskManager(
            stop_loss_points=sl_points,
            risk_reward_ratio=rr_ratio
        )

        risk_percent = 1.5 if BROKER == "exness" else 2.0
        self.position_sizing = PositionSizingAI(
            risk_percent=risk_percent,
            atr_sl_multiplier=1.5 if mode == "scalp" else 2.0,
            rr_ratio=rr_ratio,
            max_spread_ratio=100,
            min_confidence=0.10,
            lot_step=0.01
        )

        self.auto_trader = AutoTrader(
            dry_run=dry_run
        )

        self.account_manager = AccountManager()

        self.trade_filter = TradeFilter(
            max_spread=max_spread,
            min_atr=min_atr_val,
            start_hour=0,
            end_hour=23
        )

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

        if mode == "scalp":
            be_trigger = 999.0
            trail_activation = 1.5
            trail_distance = 0.5
            exit_min_conf = 1.0
            daily_max_trade = 15
            daily_max_loss = -100
            daily_max_profit = 200
        else:
            be_trigger = 999.0
            trail_activation = 999.0
            trail_distance = 1.0
            exit_min_conf = 0.75
            daily_max_trade = 5
            daily_max_loss = -150
            daily_max_profit = 300

        if BROKER == "exness" and mode == "scalp":
            daily_max_trade = 100
            daily_max_loss = -500

        self.break_even = BreakEvenManager(
            trigger_profit=be_trigger
        )

        self.trailing = TrailingStopManager(
            activation_profit=trail_activation,
            distance=trail_distance
        )

        self.exit_manager = ExitManager(
            min_confidence=exit_min_conf
        )

        if mode == "scalp":
            sp_levels = [
                {"profit": 1,   "action": "BREAK_EVEN",      "label": "Break Even"},
                {"profit": 3,   "action": "CLOSE",           "label": "Ambil Profit 3+"},
            ]
        else:
            sp_levels = None

        self.smart_position = SmartPositionManager(
            symbol=symbol,
            levels=sp_levels
        )

        self._auto_trade_enabled = True

        self.daily_risk = DailyRiskManager(
            max_trade=daily_max_trade,
            max_daily_loss=daily_max_loss,
            max_daily_profit=daily_max_profit
        )

        self.performance = PerformanceManager()

        self.history_manager = HistoryManager()

        if mode == "scalp":
            dd_warning = 3.0
            dd_danger = 7.0
            max_dd = 7.0
        else:
            dd_warning = 5.0
            dd_danger = 10.0
            max_dd = 10.0

        self.equity_manager = EquityManager(
            drawdown_warning=dd_warning,
            drawdown_danger=dd_danger
        )

        self.drawdown_manager = DrawdownManager(
            max_drawdown=max_dd
        )

        news_country = [self.symbol[-3:]]
        self.news_filter = NewsFilter(countries=news_country)

        self.regime = MarketRegimeDetector()

        self.trade_scorer = TradeScorer()

        self.smart_scalping = SmartScalpingEngine()

        time_exit_minutes = 9999
        self.time_exit = TimeExit(
            max_minutes=time_exit_minutes
        )

        self.ai_exit = AIExit(
            min_exit_confidence=1.0,
            lookback=999
        )

        self.emergency_exit = EmergencyExit(
            max_loss_per_trade=20,
            max_daily_loss=9999,
            max_drawdown_pct=100,
            max_spread_mult=999
        )

        self.trade_learner = TradeLearner(
            model_name=model_name
        )

        self.multi_tf = MultiTimeframeConfirmation(
            symbol=symbol,
            primary_tf=timeframe,
            higher_tfs=["M5", "M15"] if mode == "scalp" else ["H4", "D1"],
            bars=bars
        )

        self.confidence = ConfidenceManager(
            min_confidence=confidence_th
        )

        self.telegram = TelegramNotifier()

        init_db()
        self.db_logger = DatabaseLogger()

        self.learning_manager = LearningManager(
            trade_learner=self.trade_learner,
            history_manager=self.history_manager,
            notifier=self.telegram
        )

        self.fundamental_trader = FundamentalTrader(
            symbol=symbol,
            dry_run=dry_run,
            cooldown_minutes=60
        )

        self.grid_mode = grid_mode
        grid_lot = 0.01 if mode == "scalp" else 0.02
        self.grid_manager = GridManager(
            symbol=symbol,
            dry_run=dry_run,
            grid_layers=grid_layers,
            grid_atr_multiplier=grid_atr_multiplier,
            lot_size=grid_lot,
            magic=10002,
        )
        self.grid_placed = False

        self.last_candle_time = None
        self.last_signal_time = None
        self.last_fundamental_trade_time = None
        self.daily_fundamental = RealFundamentalEngine(cache_minutes=15)

        self.fundamental_trader.engine = self.daily_fundamental

        print()
        print("=" * 60)
        print(f"MODE : {mode.upper()}")
        print(f"SYMBOL : {symbol}")
        print(f"TIMEFRAME : {timeframe}")
        print(f"BARS : {bars}")
        print(f"DRY RUN : {dry_run}")
        print(f"GRID MODE : {'ON' if grid_mode else 'OFF'}")
        print(f"BROKER : {BROKER.upper() if BROKER else 'DEFAULT'}")
        if mode == "scalp":
            print(f"ENTRY : SCALP ENGINE")
            print(f"SL POINTS : {sl_points}")
            print(f"RR RATIO : {rr_ratio}")
            print(f"MAX SPREAD : {max_spread}")
            print(f"MIN ATR : {min_atr_val}")
            print(f"BE TRIGGER : {be_trigger}")
            print(f"TRAIL ACTIVATION : {trail_activation}")
            print(f"TRAIL DISTANCE : {trail_distance}")
            print(f"EXIT MIN CONF : {exit_min_conf}")
            print(f"DAILY MAX TRADE : {daily_max_trade}")
            print(f"DD WARNING : {dd_warning}%")
            print(f"DD DANGER : {dd_danger}%")
            print(f"MAX DRAWDOWN : {max_dd}%")
            print(f"RISK PERCENT : {risk_percent}%")
            print(f"TIME EXIT : {time_exit_minutes} menit")
        print("=" * 60)

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

    def decide(self, prediction, scalp_result=None, regime=None):

        return self.decision_engine.decide(
            prediction, scalp_result, regime
        )

    # =====================================
    # Risk
    # =====================================

    def calculate_risk(
        self,
        prediction,
        current_price,
        market_last=None,
        regime=None
    ):

        account = self.account_manager.get_info()

        if account is None:

            raise RuntimeError(
                "Account MT5 belum tersedia."
            )

        balance = account.get("balance", 0)

        if market_last is not None:
            market = market_last
        else:
            market = {"close": current_price, "ATR": 0, "spread": 0}

        sizing = self.position_sizing.calculate(
            prediction=prediction,
            market=market,
            balance=balance,
            regime=regime
        )

        if sizing["lot_size"] == 0:
            return sizing

        return sizing

    # =====================================
    # Run One Cycle
    # =====================================

    def run_once(self):

        try:

            self.telegram.handle_updates()

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

            if current_candle != self.last_candle_time:
                self.last_candle_time = current_candle

            # ===============================
            # Grid Management
            # ===============================

            if self.grid_mode and not self.grid_placed:
                atr = last.get("ATR", 1.0)
                grid_result = self.grid_manager.place_grid(
                    current_price=last["close"],
                    atr=atr
                )
                self.grid_placed = True
                print()
                print("=" * 60)
                print("GRID PLACED")
                print("=" * 60)
                for r in grid_result:
                    status = "OK" if r["result"].get("success") or r["result"].get("dry_run") else "FAIL"
                    print(f"  Layer {r['layer']} {r['side']} @ {r['stop_price']} [{status}]")

            elif self.grid_mode and self.grid_placed:
                grid_status = self.grid_manager.manage()
                if grid_status["triggered"] > 0:
                    print()
                    print("=" * 60)
                    print("GRID TRIGGERED")
                    print("=" * 60)
                    print(f"Triggered: {grid_status['triggered']} layer(s)")
                    print(f"Active    : {grid_status['active']} pending order(s)")

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
            # Learning Manager
            # ===============================

            learn_result = self.learning_manager.check_closed()
            if learn_result["updated"] > 0:
                print()
                print("=" * 60)
                print("LEARNING MANAGER")
                print("=" * 60)
                print(f"Updated : {learn_result['updated']} trades")
                if learn_result["retrained"]:
                    print("Model retrained with real outcomes!")

            # ===============================
            # Market Regime
            # ===============================

            regime = self.regime.detect(last)

            MarketRegimeView.show(regime)

            # ===============================
            # Fundamental Daily
            # ===============================

            fundamental = self.daily_fundamental.analyze()

            DailyTrendView.show(fundamental)

            # ===============================
            # 15-Minute Signal
            # ===============================

            now = last["time"]
            if (self.last_signal_time is None or
                (now - self.last_signal_time).total_seconds() >= 900):

                self.last_signal_time = now

                signal_text = (
                    f"[SIGNAL] {fundamental['bias']}\n"
                    f"Confidence: {fundamental['confidence']}%\n"
                    f"Score: {fundamental['score']}/10\n"
                )
                if fundamental["reasons"]:
                    signal_text += "\nReasons:\n" + "\n".join(
                        f"- {r}" for r in fundamental["reasons"]
                    )
                self.telegram.send(signal_text)

                # -------------------------------------------------
                # 15-Minute Fundamental Trade Execution
                # -------------------------------------------------
                ft_result = self.fundamental_trader.execute()
                if ft_result and ft_result["status"] not in ("SKIPPED", "ERROR"):
                    print()
                    print("=" * 60)
                    print("FUNDAMENTAL TRADE EXECUTED")
                    print("=" * 60)
                    print(f"Signal : {ft_result['signal']}")
                    print(f"Lot    : {ft_result['volume']}")
                    print(f"Entry  : {ft_result['entry_price']}")
                    print(f"SL     : {ft_result['stop_loss']}")
                    print(f"TP1    : {ft_result['take_profit1']}")
                    print(f"TP2    : {ft_result['take_profit2']}")

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
            # Multi Timeframe Confirmation
            # ===============================

            tf_confirmation = self.multi_tf.confirm(
                prediction, last
            )

            MultiTFView.show(tf_confirmation)

            # ===============================
            # Smart Scalping Engine
            # ===============================

            scalp_result = self.smart_scalping.analyze(df, last)
            SmartScalpingView.show(scalp_result)
            Path("runtime").mkdir(exist_ok=True)
            with open("runtime/scalping.json", "w") as f:
                json.dump(scalp_result, f, default=str, indent=2)
            self._scalp_result = scalp_result

            # ===============================
            # Decision
            # ===============================

            decision = self.decide(
                prediction,
                scalp_result,
                regime
            )

            DecisionView.show(
                decision
            )

            # ===============================
            # Proposed Trade
            # ===============================

            try:
                proposed = self.calculate_risk(
                    prediction, last["close"], last, regime
                )
            except Exception:
                proposed = None

            if proposed and proposed.get("lot_size", 0) > 0:
                print()
                print("=" * 60)
                print("PROPOSED TRADE")
                print("=" * 60)
                print(f"Signal      : {prediction['signal']}")
                print(f"Entry       : {proposed['entry_price']:.2f}")
                print(f"Stop Loss   : {proposed['stop_loss']:.2f}")
                print(f"Take Profit : {proposed['take_profit']:.2f}")
                print(f"Lot Size    : {proposed['lot_size']}")
                print(f"Risk Amount : ${proposed['risk_amount']:.2f}")

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
            # Smart Position Manager
            # ===============================

            positions = self.position_manager.get_positions(
                self.symbol
            )

            if positions:
                active_tickets = {p.ticket for p in positions}

                self.time_exit.cleanup(active_tickets)
                self.ai_exit.cleanup(active_tickets)

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

                    sp_result = self.smart_position.process(
                        position, prediction, regime, last
                    )
                    SmartPositionView.show(sp_result)

                    time_exit_result = self.time_exit.process(position)
                    TimeExitView.show(time_exit_result)

                    ai_exit_result = self.ai_exit.process(
                        position, prediction, last
                    )
                    AIExitView.show(ai_exit_result)

                    emergency_result = self.emergency_exit.process(
                        position, account, last
                    )
                    EmergencyExitView.show(emergency_result)

            else:

                if self.grid_mode and self.grid_placed:
                    gs = self.grid_manager.get_status()
                    if gs["active_count"] > 0 or gs["triggered_count"] > 0:
                        print()
                        print("=" * 60)
                        print("GRID STATUS")
                        print("=" * 60)
                        print(f"Active Pending   : {gs['active_count']}")
                        print(f"Triggered Layers : {gs['triggered_count']}")
                        for tl in gs["triggered_levels"]:
                            print(f"  Layer {tl['layer']} {tl['side']} @ {tl['stop_price']} [FILLED]")
                        for ap in gs["active_pending"]:
                            print(f"  {ap['type']} {ap['volume']} @ {ap['price']} [ACTIVE]")

                re = self.smart_position.check_re_entry(
                    prediction, regime, last
                )
                if re["re_entry"]:
                    print()
                    print("=" * 60)
                    print("SMART RE-ENTRY")
                    print("=" * 60)
                    print(re["reason"])
                else:
                    print()
                    print("=" * 60)
                    print("SMART POSITION MANAGER")
                    print("=" * 60)
                    print("Tidak ada posisi yang perlu dikelola.")

            # ===============================
            # Risk
            # ===============================

            risk = None

            try:
                with open("runtime/auto_trade_enabled.json") as f:
                    self._auto_trade_enabled = json.load(f).get("enabled", True)
            except:
                pass

            can_trade = (

                self._auto_trade_enabled

                and decision["action"] != "NO_TRADE"

                and not decision.get("manual", False)

                and filter_result["allowed"]

                and daily_result["allowed"]

                and position_result["allowed"]

            )

            if can_trade:

                risk = self.calculate_risk(
                    prediction,
                    last["close"],
                    market_last=last,
                    regime=regime
                )

            RiskView.show(risk)

            if risk:
                risk["lot_size"] = 0.01
                risk["sl_points"] = 6.0
                spread_price = float(last.get("spread", 0)) * 0.01
                if decision["action"] == "BUY":
                    ask_price = risk["entry_price"] + spread_price / 2
                    risk["stop_loss"] = 0.0
                    risk["take_profit"] = 0.0
                elif decision["action"] == "SELL":
                    bid_price = risk["entry_price"] - spread_price / 2
                    risk["stop_loss"] = 0.0
                    risk["take_profit"] = 0.0

            # ===============================
            # AI Trade Score
            # ===============================

            news_data = news_result.get("news") if hasattr(self, 'news_filter') else None

            trade_score = self.trade_scorer.score(
                prediction=prediction,
                tf_confirmation=tf_confirmation,
                regime=regime,
                market=last,
                risk=risk,
                sizing_details=risk,
                news=news_data,
                scalping=scalp_result
            )

            ScoreView.show(trade_score)

            # ===============================
            # Auto Trader
            # ===============================

            if not self._auto_trade_enabled:

                result = {

                    "status": "BLOCKED",

                    "reason": "Auto-trade dimatikan dari dashboard."

                }

            elif decision.get("manual", False):

                result = {

                    "status": "BLOCKED",

                    "reason": f"Manual: {decision.get('reason', 'berlawanan trend')}"

                }

            elif not filter_result["allowed"]:

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
                self.telegram.notify_open(
                    prediction=prediction,
                    risk=risk,
                    symbol=self.symbol,
                    score=trade_score,
                    filters={
                        "trend_ok": regime.get("mode") == "TREND" if regime else False,
                        "ai_ok": confidence_result.get("allowed", False),
                        "multitf_ok": tf_confirmation.get("aligned", False) if tf_confirmation else False,
                        "atr_ok": filter_result.get("allowed", False),
                        "spread_ok": filter_result.get("allowed", False),
                        "news_ok": not news_result.get("news") if hasattr(self, 'news_filter') else True,
                    }
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

            ticket = None
            if result.get("result") and hasattr(result["result"], "order"):
                ticket = result["result"].order

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
                "lot_size": risk["lot_size"] if risk else None,
                "profit": None,
                "ticket": ticket
            }
            self.db_logger.log_trade(trade_data)

            if equity:
                self.db_logger.log_equity(equity)

            if result["status"] in ("DRY_RUN", "SUCCESS"):
                features = {col: last[col] for col in FEATURE_COLUMNS if col in last.index}
                total_samples = self.learning_manager.track_open(
                    ticket=ticket or 0,
                    features=features,
                    signal=prediction["signal"],
                    confidence=prediction["confidence"]
                )
                print()
                print("=" * 60)
                print("LEARNING MANAGER")
                print("=" * 60)
                print(f"Trade tracked : {total_samples} samples")

            try:
                retrain_result = self.trade_learner.retrain()
            except Exception as e:
                print(f"[RETRAIN ERROR] {e}")
                retrain_result = {"status": "SKIP", "reason": str(e)}
            if retrain_result["status"] == "RETRAINED":
                print()
                print("=" * 60)
                print("AI LEARNING")
                print("=" * 60)
                print(f"Model retrained: {retrain_result['reason']}")
                print(f"Samples: {retrain_result['samples']}")

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

            lr_stats = self.trade_learner.get_learning_stats()
            scalp_signal = "WAIT"
            if scalp_result and "scalp_score" in scalp_result:
                ss = scalp_result["scalp_score"]
                scalp_signal = ss.get("direction", "NEUTRAL")

            dash_data = {
                "signal": decision.get("action", "WAIT") if decision.get("action") != "NO_TRADE" else "WAIT",
                "confidence": round(decision.get("confidence", 0) * 100, 1),
                "trade": "YES" if decision["action"] != "NO_TRADE" else "NO",
                "score": trade_score.get("grade", "-"),
                "spread": "OK" if spread_ok else "NG",
                "atr": "OK" if atr_ok else "NG",
                "risk": "OK" if risk is not None else "WAIT",
                "position": str(len(positions)) if positions else "NONE",
                "daily_risk": "OK" if daily_result["allowed"] else "NG",
                "drawdown": "OK" if drawdown_result["allowed"] else "NG",
                "auto_trader": result.get("status", "READY"),
                "learning": f"{lr_stats['total']} ({lr_stats['win_rate']}%)",
                "reason": decision.get("reason", ""),
                "scalp_grade": decision.get("grade", "-")
            }

            # ---- Write comprehensive dashboard data ----
            open_positions = []
            if positions:
                for p in positions:
                    open_positions.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "type": "BUY" if p.type == 0 else "SELL",
                        "volume": p.volume,
                        "price_open": p.price_open,
                        "price_current": p.price_current,
                        "profit": round(p.profit, 2),
                        "sl": p.sl,
                        "tp": p.tp,
                    })

            from app.database.session import db_session
            from app.database.models import TradeLog, EquitySnapshot
            _trades_list = []
            _equity_list = []
            with db_session() as _db:
                for t in _db.query(TradeLog).order_by(TradeLog.id.desc()).limit(20).all():
                    _trades_list.append({
                        "id": t.id, "time": str(t.time), "symbol": t.symbol,
                        "signal": t.signal, "confidence": round(t.confidence * 100, 1) if t.confidence else 0,
                        "action": t.action, "status": t.status, "reason": t.reason,
                        "entry_price": t.entry_price, "stop_loss": t.stop_loss,
                        "take_profit": t.take_profit, "lot_size": t.lot_size,
                        "profit": t.profit,
                    })
                for s in _db.query(EquitySnapshot).order_by(EquitySnapshot.id.desc()).limit(50).all():
                    _equity_list.append({
                        "time": str(s.time), "balance": s.balance, "equity": s.equity,
                        "floating_pl": s.floating_pl, "drawdown": s.drawdown,
                    })
                _equity_list.reverse()

            _win = sum(1 for t in _trades_list if t.get("profit") and t["profit"] > 0)
            _loss = sum(1 for t in _trades_list if t.get("profit") and t["profit"] < 0)
            _total_trades_db = len(_trades_list)

            _today_deals = []
            try:
                for d in self.history_manager.today():
                    _today_deals.append({
                        "ticket": d.ticket,
                        "symbol": d.symbol,
                        "profit": round(d.profit, 2),
                        "time": str(datetime.fromtimestamp(d.time).strftime("%H:%M")),
                        "type": "BUY" if d.type == 0 else "SELL",
                        "volume": d.volume,
                        "price": d.price,
                        "comment": d.comment or "",
                    })
            except:
                pass

            overview = {
                "balance": account.get("balance", 0) if account else 0,
                "equity": account.get("equity", 0) if account else 0,
                "floating_pl": equity["floating_pl"] if equity else 0,
                "drawdown": equity["drawdown"] if equity else 0,
                "margin": account.get("margin", 0) if account else 0,
                "margin_free": account.get("free_margin", 0) if account else 0,
                "margin_level": account.get("margin_level", 0) if account else 0,
                "server_time": str(datetime.now()),
                "signal": dash_data["signal"],
                "confidence": dash_data["confidence"],
                "trade": dash_data["trade"],
                "score": dash_data["score"],
                "reason": dash_data.get("reason", ""),
                "scalp_grade": dash_data.get("scalp_grade", "-"),
                "open_positions": open_positions,
                "open_count": len(open_positions),
                "trades_today": performance.get("total_trade", 0),
                "profit_today": round(performance.get("net_profit", 0), 2),
                "trades": _trades_list,
                "today_deals": _today_deals,
                "equity_snapshots": _equity_list,
                "learning": {"total": lr_stats['total'], "win": lr_stats.get('win', _win),
                            "loss": lr_stats.get('loss', _loss), "win_rate": lr_stats['win_rate']},
                "scalping": getattr(self, '_scalp_result', None),
            }
            Path("runtime").mkdir(exist_ok=True)
            with open("runtime/overview.json", "w") as f:
                json.dump(overview, f, indent=2, default=str)

            DashboardView.show(dash_data)

            self.telegram.notify_dashboard(dash_data, account, DASHBOARD_URL)

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
