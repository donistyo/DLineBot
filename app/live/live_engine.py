import json
import time
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
from app.config.settings import DASHBOARD_URL
from app.config.settings import TRADE_LOT_SIZE, BROKER
from app.config.settings import get_symbol_params, is_crypto_symbol, get_model_prefix
from app.config.settings import get_trade_config

from app.logger.trade_logger import TradeLogger

from app.live.account_view import AccountView
from app.live.prediction_view import PredictionView
from app.live.decision_view import DecisionView
from app.live.risk_view import RiskView
from app.live.market_info import MarketInfo
from app.live.auto_trader_view import AutoTraderView

from app.mt5.session import MT5Session

import MetaTrader5 as mt5

from app.trading.position_monitor import PositionMonitor

from app.live.position_view import PositionView
from app.live.history_view import HistoryView
from app.trading.trade_filter import TradeFilter
from app.live.trade_filter_view import TradeFilterView

from app.trading.daily_risk_manager import DailyRiskManager
from app.live.daily_risk_view import DailyRiskView
from app.trading.position_filter import PositionFilter
from app.live.position_filter_view import PositionFilterView
from app.trading.session_manager import SessionManager

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
from app.live.recovery_exit_view import RecoveryExitView
from app.mt5.position_controller import PositionController, _log_close
from app.trading.smart_scalping import SmartScalpingEngine
from app.trading.atr_helper import ATRHelper
from app.trading.atr_protection import ATRProtectionManager
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

        model_prefix = get_model_prefix(self.symbol)
        model_name = f"xgboost_{model_prefix}_m1.joblib" if mode == "scalp" else f"xgboost_{model_prefix}_h1.joblib"
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

        # =====================================
        # Per-Symbol Overrides
        # =====================================

        _sym_params = get_symbol_params(self.symbol)
        if _sym_params:
            max_spread = _sym_params.get("max_spread", max_spread)
            min_atr_val = _sym_params.get("min_atr", min_atr_val)
            _s_start, _s_end = _sym_params.get("session", (0, 23))

        self.decision_engine = DecisionEngine(
            min_scalp_score=55
        )

        self.risk_manager = RiskManager(
            stop_loss_points=sl_points,
            risk_reward_ratio=rr_ratio
        )

        risk_percent = 1.5 if BROKER == "exness" else 2.0
        self.position_sizing = PositionSizingAI(
            risk_percent=risk_percent,
            atr_sl_multiplier=2.5,
            rr_ratio=rr_ratio,
            max_spread_ratio=100,
            min_confidence=0.10,
            lot_step=0.01
        )

        self.auto_trader = AutoTrader(
            dry_run=dry_run
        )

        self.account_manager = AccountManager()

        from app.config.settings import load_trade_config, get_trade_config
        load_trade_config()
        _cfg_windows = get_trade_config("session_windows")
        if isinstance(_cfg_windows, list) and _cfg_windows:
            _s_start, _s_end = tuple(_cfg_windows[0])[:2]
            _session_windows = _cfg_windows
        else:
            _session_windows = [(23, 12)]  # Asia + awal London, NY off

        self.trade_filter = TradeFilter(
            max_spread=max_spread,
            min_atr=min_atr_val,
            start_hour=_s_start,
            end_hour=_s_end,
            windows=_session_windows
        )

        max_pos = 10 if TRADE_LOT_SIZE <= 0.01 else 3
        from app.config.settings import load_trade_config, get_trade_config
        load_trade_config()
        _cfg_positions = get_trade_config("max_positions")
        if _cfg_positions:
            max_pos = int(_cfg_positions)
        _cfg_same_dir = get_trade_config("max_same_direction")
        _same_dir = int(_cfg_same_dir) if _cfg_same_dir else 3
        self.position_filter = PositionFilter(max_positions=max_pos, max_same_direction=_same_dir)

        self.session_manager = SessionManager(max_sessions=10, max_per_session=10)

        # =====================================
        # Logger
        # =====================================

        self.trade_logger = TradeLogger()

        # =====================================
        # Runtime
        # =====================================

        self.position_manager = PositionManager()

        self.position_monitor = PositionMonitor()

        self.controller = PositionController()

        # Pre-populate recovery tracker for existing deep loss positions
        existing = self.position_manager.get_positions(self.symbol)
        self._recovery_seen = {}
        self._last_same_dir_entry = {}
        if existing:
            for p in existing:
                if p.profit < -15.0:
                    self._recovery_seen[p.ticket] = True
                try:
                    direction = "BUY" if p.type == 0 else "SELL"
                    entry_time = datetime.fromtimestamp(p.time)
                    prev = self._last_same_dir_entry.get(direction)
                    if prev is None or entry_time > prev:
                        self._last_same_dir_entry[direction] = entry_time
                except Exception:
                    pass

        if mode == "scalp":
            be_trigger = 2.0
            trail_activation = 1.5
            trail_distance = 1.0
            exit_min_conf = 1.0
            daily_max_trade = 100
            daily_max_loss = -100
            daily_max_profit = 9999
        else:
            be_trigger = 999.0
            trail_activation = 999.0
            trail_distance = 1.0
            exit_min_conf = 0.75
            daily_max_trade = 5
            daily_max_loss = -150
            daily_max_profit = 300

        if BROKER == "exness" and mode == "scalp":
            daily_max_trade = 20
            daily_max_loss = -500

        # Override dari runtime/trade_config.json (mis. uji coba)
        from app.config.settings import load_trade_config, get_trade_config
        load_trade_config()
        _cfg_max_trade = get_trade_config("max_trade")
        if _cfg_max_trade:
            daily_max_trade = int(_cfg_max_trade)

        _cfg_max_loss = get_trade_config("daily_max_loss")
        if _cfg_max_loss is not None:
            daily_max_loss = float(_cfg_max_loss)

        _cfg_max_profit = get_trade_config("daily_max_profit")
        if _cfg_max_profit is not None:
            daily_max_profit = float(_cfg_max_profit)

        self.atr_protection = ATRProtectionManager(
            sl_atr_mult=float(get_trade_config("sl_atr_mult", 1.5)),
            be_trigger_atr=float(get_trade_config("be_trigger_atr", 0.5)),
            partial_trigger_atr=float(get_trade_config("partial_trigger_atr", 1.0)),
            partial_pct=float(get_trade_config("partial_pct", 0.5)),
            trail_activation_atr=float(get_trade_config("trail_activation_atr", 1.5)),
            trail_distance_atr=float(get_trade_config("trail_distance_atr", 1.0)),
            lock_profit_atr=float(get_trade_config("lock_profit_atr", 2.0)),
            lock_amount_atr=float(get_trade_config("lock_amount_atr", 0.5)),
            tp_atr=float(get_trade_config("tp_atr", 4.0)),
            emergency_atr=float(get_trade_config("emergency_atr", 2.5)),
            partial_close=bool(get_trade_config("partial_close", False)),
            early_tp_atr=float(get_trade_config("early_tp_atr", 0.65)),
            early_pullback_atr=float(get_trade_config("early_pullback_atr", 0.25)),
            be_buffer_atr=float(get_trade_config("be_buffer_atr", 0.0)),
            fast_tp_usd=float(get_trade_config("fast_tp_usd", 2.5)),
            stall_start_usd=float(get_trade_config("stall_start_usd", 1.0)),
            stall_seconds=float(get_trade_config("stall_seconds", 60.0)),
            loser_seconds=float(get_trade_config("loser_seconds", 600.0)),
            loser_min_profit=float(get_trade_config("loser_min_profit", 0.0)),
        )

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
            sp_levels = []
        else:
            sp_levels = None

        self.smart_position = SmartPositionManager(
            symbol=symbol,
            levels=sp_levels
        )

        self._auto_trade_enabled = True
        self._equity_floor_hit = False

        self.daily_risk = DailyRiskManager(
            max_trade=daily_max_trade,
            max_daily_loss=daily_max_loss,
            max_daily_profit=daily_max_profit
        )

        self.performance = PerformanceManager()

        self.history_manager = HistoryManager()

        if mode == "scalp":
            dd_warning = 10.0
            dd_danger = 25.0
            max_dd = 30.0
        else:
            dd_warning = 10.0
            dd_danger = 25.0
            max_dd = 30.0

        self.equity_manager = EquityManager(
            drawdown_warning=dd_warning,
            drawdown_danger=dd_danger
        )

        self.drawdown_manager = DrawdownManager(
            max_drawdown=max_dd
        )

        if is_crypto_symbol(self.symbol):
            news_country = []
            self.news_filter = None
            print(f"[SYMBOL] {self.symbol} adalah kripto - News Filter dinonaktifkan (24/7 market).")
        else:
            news_country = [self.symbol[-3:]]
            self.news_filter = NewsFilter(countries=news_country)

        self.regime = MarketRegimeDetector()

        self.trade_scorer = TradeScorer()

        self.smart_scalping = SmartScalpingEngine(symbol=symbol)

        self.atr_helper = ATRHelper(symbol=symbol, timeframe=mt5.TIMEFRAME_M5)

        time_exit_minutes = 9999
        self.time_exit = TimeExit(
            max_minutes=time_exit_minutes
        )

        self.ai_exit = AIExit(
            min_exit_confidence=1.0,
            lookback=999
        )

        self.emergency_exit = EmergencyExit(
            max_loss_per_trade=30,
            max_daily_loss=9999,
            max_drawdown_pct=100,
            max_spread_mult=999
        )
        self.emergency_exit.controller = self.controller

        self.trade_learner = TradeLearner(
            model_name=model_name
        )

        self.multi_tf = MultiTimeframeConfirmation(
            symbol=symbol,
            primary_tf=timeframe,
            higher_tfs=["M5", "M15"] if mode == "scalp" else ["H4", "D1"],
            bars=bars,
            min_adx=float(get_trade_config("min_adx", 30)),
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

        self._last_closed_direction = None
        self._last_closed_time = None
        self._last_closed_was_win = True
        self._last_same_dir_entry = {}
        self._same_dir_spacing = 60.0
        try:
            _spacing_cfg = float(get_trade_config("same_dir_spacing", 60.0))
            if _spacing_cfg > 0:
                self._same_dir_spacing = _spacing_cfg
        except Exception:
            pass
        self._seen_tickets = set()
        self._consecutive_losses = 0
        self._score_penalty = 0

        self.fundamental_trader.engine = self.daily_fundamental
        self.fundamental_trader.multi_tf = self.multi_tf

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

    def decide(self, prediction, scalp_result=None, regime=None, higher_trend=None, higher_adx=0):

        return self.decision_engine.decide(
            prediction, scalp_result, regime, higher_trend, higher_adx
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
            # Equity Floor: close all jika equity terlalu rendah
            # ===============================

            if equity and not self._equity_floor_hit:
                floor = 1200.0
                try:
                    with open("runtime/trade_config.json") as _f:
                        floor = float(json.load(_f).get("equity_floor", 1200.0))
                except:
                    pass

                if equity["equity"] <= floor:
                    self._equity_floor_hit = True
                    floor_positions = self.position_manager.get_positions(self.symbol) or []
                    closed = 0
                    for fp in floor_positions:
                        try:
                            fr = self.controller.close(fp, caller="EQUITY_FLOOR")
                            if fr.get("success"):
                                closed += 1
                        except Exception:
                            pass
                    self._auto_trade_enabled = False
                    Path("runtime").mkdir(exist_ok=True)
                    with open("runtime/auto_trade_enabled.json", "w") as f:
                        json.dump({"enabled": False}, f)
                    print()
                    print("=" * 60)
                    print("EQUITY FLOOR TRIGGERED")
                    print("=" * 60)
                    print(f"Equity      : {equity['equity']:.2f}")
                    print(f"Floor       : {floor:.2f}")
                    print(f"Closed      : {closed}/{len(floor_positions)} posisi")
                    print("Auto-trade  : OFF (perlu re-enable manual)")
                    try:
                        self.telegram.send(
                            f"⚠️ EQUITY FLOOR ({floor:.0f})\n"
                            f"Equity {equity['equity']:.2f}\n"
                            f"Ditutup {closed}/{len(floor_positions)} posisi\n"
                            f"Auto-trade dimatikan."
                        )
                    except Exception:
                        pass

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
            # Prediction
            # ===============================

            prediction = self.predict(df)

            PredictionView.show(
                prediction,
                last
            )

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
                # 15-Minute Fundamental Trade Execution  [DISABLED]
                # Jalur Fundamental dinonaktifkan karena sering entry
                # di timing buruk dan bypass checklist scalp engine.
                # -------------------------------------------------
                print()
                print("=" * 60)
                print("FUNDAMENTAL TRADER")
                print("=" * 60)
                print("Jalur Fundamental DISABLED - hanya scalp engine yang aktif")

            # ===============================
            # AI Confidence
            # ===============================

            confidence_result = self.confidence.allow(prediction)

            ConfidenceView.show(confidence_result)

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
            # Multi Timeframe Confirmation
            # (setelah scalp engine agar bisa pakai scalp direction)
            # ===============================

            scalp_dir = (scalp_result or {}).get("scalp_score", {}).get("direction", "NEUTRAL")
            tf_signal = scalp_dir if scalp_dir in ("BUY", "SELL") else None
            tf_confirmation = self.multi_tf.confirm(
                prediction, last, signal=tf_signal
            )
            MultiTFView.show(tf_confirmation)

            # ===============================
            # Decision
            # ===============================

            self.decision_engine.min_scalp_score = self._current_min_score()

            higher_trend = None
            higher_adx = 0
            try:
                tf_details = (tf_confirmation or {}).get("details", {}) or {}
                _dirs = []
                _adxs = []
                for _tf, _info in tf_details.items():
                    if isinstance(_info, dict) and _info.get("ema_trend") in ("UP", "DOWN"):
                        _dirs.append(self.decision_engine.trend_map.get(_info["ema_trend"]))
                        _adxs.append(float(_info.get("adx", 0) or 0))
                if _dirs and all(d == _dirs[0] for d in _dirs):
                    higher_trend = _dirs[0]
                    higher_adx = max(_adxs) if _adxs else 0
            except Exception:
                higher_trend = None
                higher_adx = 0

            # =====================================
            # Decision
            # =====================================

            decision = self.decide(
                prediction,
                scalp_result,
                regime,
                higher_trend,
                higher_adx,
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

            daily_result = self.daily_risk.allow(symbol=self.symbol)
            DailyRiskView.show(daily_result)

            if not daily_result["allowed"] and "Batas trade harian" in daily_result.get("reason", ""):
                if self._auto_trade_enabled:
                    self._auto_trade_enabled = False
                    with open("runtime/auto_trade_enabled.json", "w") as f:
                        json.dump({"enabled": False}, f)
                    print()
                    print("=" * 60)
                    print("AUTO TRADE OFF")
                    print("=" * 60)
                    print(f"Alasan: {daily_result['reason']}")
                    print(f"Trade hari ini: {daily_result.get('trade_today', '?')}")
                    try:
                        self.telegram.send(f"AutoTrade OFF — {daily_result['reason']} ({daily_result.get('trade_today', '?')} trade)")
                    except:
                        pass

            # ===============================
            # Position Filter
            # ===============================

            try:
                with open("runtime/trade_config.json") as _f:
                    _lot = json.load(_f).get("lot_size", TRADE_LOT_SIZE)
            except:
                _lot = TRADE_LOT_SIZE

            from app.config.settings import load_trade_config, get_trade_config
            load_trade_config()
            _cfg_positions = get_trade_config("max_positions")
            if _cfg_positions:
                self.position_filter.max_positions = int(_cfg_positions)
            else:
                self.position_filter.max_positions = 5 if _lot <= 0.01 else 3

            position_result = self.position_filter.allow(
                self.symbol,
                direction=decision["action"]
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

            news_result = None
            if self.news_filter is not None:
                news_result = self.news_filter.allow()
                NewsFilterView.show(news_result)
            else:
                news_result = {"allowed": True, "reason": "Kripto: news filter off.", "news": None}

            # ===============================
            # Smart Position Manager
            # ===============================

            positions = self.position_manager.get_positions(
                self.symbol
            )

            active_tickets = {p.ticket for p in positions} if positions else set()
            closed_tickets = self._seen_tickets - active_tickets
            if closed_tickets:
                self._last_closed_direction = self._ticket_direction(closed_tickets)
                self._last_closed_time = datetime.now()
                self._last_closed_was_win = self._ticket_profit(closed_tickets) >= 0
                self._track_consecutive_losses(closed_tickets)
            self._seen_tickets = active_tickets

            if positions:
                self.time_exit.cleanup(active_tickets)
                self.ai_exit.cleanup(active_tickets)
                self.atr_protection.cleanup(active_tickets)

                for position in positions:

                    _use_atr_mode = True
                    try:
                        with open("runtime/trade_config.json") as _f:
                            _use_atr_mode = bool(json.load(_f).get("use_atr_protection", True))
                    except Exception:
                        pass

                    if _use_atr_mode:
                        _atr_now = float(last.get("ATR", 0) or 0)
                        _atr_m5 = float(self.atr_helper.current_atr())
                        if _atr_m5 > 0:
                            _atr_now = _atr_m5
                        ap_result = self.atr_protection.process(
                            position, _atr_now, float(last["close"])
                        )
                        ExitView.show(ap_result)
                        if ap_result["status"] in ("CLOSED", "PARTIAL"):
                            continue
                    else:
                        attach_sltp_result = self._attach_sl_tp_on_profit(position)
                        if attach_sltp_result:
                            ExitView.show(attach_sltp_result)

                        be_result = self.break_even.process(position)
                        ExitView.show(be_result)

                        ts_result = self.trailing.process(position)
                        ExitView.show(ts_result)

                    exit_result = self.exit_manager.process(
                        position,
                        prediction
                    )
                    ExitView.show(exit_result)

                    recovery_result = self._check_recovery_close(position)
                    if recovery_result:
                        RecoveryExitView.show(recovery_result)
                        continue

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

                    if position.ticket in self._recovery_seen:
                        # Safety limit: kalau loss > -60, baru emergency close
                        if position.profit <= -60:
                            emergency_result = self.emergency_exit.process(
                                position, account, last
                            )
                        else:
                            emergency_result = {"status": "SKIP", "action": "NONE",
                                                "reason": "Menunggu recovery.", "ticket": position.ticket}
                    else:
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
                    _enabled_now = json.load(f).get("enabled", True)
                    if _enabled_now and not self._auto_trade_enabled:
                        self._equity_floor_hit = False
                    self._auto_trade_enabled = _enabled_now
            except:
                pass

            reentry_reason = self._reentry_blocked(
                decision["action"],
                cooldown_minutes=15,
                cooldown_win_minutes=float(get_trade_config("reentry_cooldown_win_min", 15.0)),
            )
            same_dir_reason = self._same_dir_spacing_blocked(decision["action"])

            if not reentry_reason and same_dir_reason:
                reentry_reason = same_dir_reason

            _atr_filter_ok = True
            _atr_filter_reason = None
            try:
                with open("runtime/trade_config.json") as _f:
                    _vol_filter_on = bool(json.load(_f).get("atr_volatility_filter", True))
                if _vol_filter_on:
                    _atr_filter_ok, _atr_filter_reason = self.atr_helper.volatility_ok()
            except Exception:
                pass

            can_trade = (

                self._auto_trade_enabled

                and decision["action"] != "NO_TRADE"

                and not decision.get("manual", False)

                and filter_result["allowed"]

                and daily_result["allowed"]

                and position_result["allowed"]

                and (tf_confirmation.get("allowed", False) if tf_confirmation else True)

                and not reentry_reason

                and not same_dir_reason

                and _atr_filter_ok

            )

            if can_trade:
                session_result = None
                open_tickets = {p.ticket for p in positions} if positions else set()
                session_result = self.session_manager.allow(open_tickets)
                if not session_result["allowed"]:
                    can_trade = False
            else:
                session_result = None

            self._write_entry_checklist(
                can_trade=can_trade,
                decision=decision,
                filter_result=filter_result,
                daily_result=daily_result,
                position_result=position_result,
                tf_confirmation=tf_confirmation,
                reentry_reason=reentry_reason,
                same_dir_reason=same_dir_reason,
                atr_filter_ok=_atr_filter_ok,
                atr_filter_reason=_atr_filter_reason,
                session_result=session_result,
                scalp_result=scalp_result,
                regime=regime,
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
                try:
                    with open("runtime/trade_config.json") as _f:
                        _cfg = json.load(_f)
                        risk["lot_size"] = _cfg.get("lot_size", TRADE_LOT_SIZE)
                        _use_atr = bool(_cfg.get("use_atr_protection", True))
                        _sl_atr_mult = float(_cfg.get("sl_atr_mult", 2.5))
                except:
                    risk["lot_size"] = TRADE_LOT_SIZE
                    _use_atr = True
                    _sl_atr_mult = 2.5
                _sp = get_symbol_params(self.symbol)
                _sl_pts = float(_sp.get("sl_points", 6.0))
                _tp1_pts = float(_sp.get("tp1_points", _sl_pts * 1.5))
                _sl_dist = _sl_pts * float(_sp.get("point", 0.01))
                _tp_dist = _tp1_pts * float(_sp.get("point", 0.01))
                _atr_now = float(last.get("ATR", 0) or 0)
                _atr_m5 = float(self.atr_helper.current_atr())
                if _atr_m5 > 0:
                    _atr_now = _atr_m5
                if _use_atr and _atr_now > 0:
                    _sl_dist = _atr_now * _sl_atr_mult
                    _tp_dist = 0.0
                    risk["atr"] = _atr_now
                    risk["sl_atr"] = _sl_atr_mult

                from app.trading.lot_risk_guard import get_safe_lot, get_max_positions_for_lot
                _account = self.account_manager.get_info()
                _balance = _account.get("balance", 0) if isinstance(_account, dict) else 1000
                _lot_check = get_safe_lot(_balance, _atr_now, _sl_atr_mult, risk["lot_size"])
                if _lot_check["reduced"]:
                    print()
                    print("=" * 60)
                    print("LOT RISK GUARD")
                    print("=" * 60)
                    print(f"  {_lot_check['reason']}")
                risk["lot_size"] = _lot_check["lot_size"]

                _safe_max_pos = get_max_positions_for_lot(risk["lot_size"])
                if _safe_max_pos < self.position_filter.max_positions:
                    self.position_filter.max_positions = _safe_max_pos
                    print(f"  Max positions disesuaikan ke {_safe_max_pos} (lot {risk['lot_size']})")
                if decision["action"] == "BUY":
                    risk["stop_loss"] = round(risk["entry_price"] - _sl_dist, 5)
                    risk["take_profit"] = round(risk["entry_price"] + _tp_dist, 5) if _tp_dist > 0 else 0.0
                elif decision["action"] == "SELL":
                    risk["stop_loss"] = round(risk["entry_price"] + _sl_dist, 5)
                    risk["take_profit"] = round(risk["entry_price"] - _tp_dist, 5) if _tp_dist > 0 else 0.0

            # ===============================
            # AI Trade Score
            # ===============================

            news_data = news_result.get("news") if self.news_filter is not None else None

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

                if not getattr(self, '_daily_limit_notified', False):
                    reason = daily_result["reason"]
                    self.telegram.send(f"⚠️ AUTO-TRADE STOP: {reason}")
                    self._daily_limit_notified = True

                result = {

                    "status": "BLOCKED",

                    "reason": daily_result["reason"]

                }

            elif not position_result["allowed"]:

                result = {

                    "status": "BLOCKED",

                    "reason": position_result["reason"]

                }

            elif decision["action"] == "NO_TRADE":

                result = {

                    "status": "BLOCKED",

                    "reason": "Sinyal WAIT / NO_TRADE."

                }

            elif session_result and not session_result["allowed"]:

                result = {

                    "status": "BLOCKED",

                    "reason": session_result["reason"]

                }

            elif tf_confirmation and not tf_confirmation.get("allowed", False):

                result = {

                    "status": "BLOCKED",

                    "reason": tf_confirmation.get("reason", "Higher TF menolak.")

                }

            elif reentry_reason:

                result = {

                    "status": "BLOCKED",

                    "reason": reentry_reason

                }

            elif same_dir_reason:

                result = {

                    "status": "BLOCKED",

                    "reason": same_dir_reason

                }

            elif not _atr_filter_ok:

                result = {

                    "status": "BLOCKED",

                    "reason": _atr_filter_reason or "Filter volatilitas ATR menolak."

                }

            else:

                result = self.auto_trader.execute(

                    decision=decision,

                    risk=risk,

                    symbol=self.symbol

                )

            AutoTraderView.show(result)

            if result["status"] in ("DRY_RUN", "SUCCESS"):
                self._update_same_dir_entry(decision["action"])
                self.telegram.notify_open(
                    prediction=prediction,
                    risk=risk,
                    symbol=self.symbol,
                    score=trade_score,
                    signal=decision["action"],
                    filters={
                        "trend_ok": regime.get("mode") == "TREND" if regime else False,
                        "ai_ok": confidence_result.get("allowed", False),
                        "multitf_ok": tf_confirmation.get("aligned", False) if tf_confirmation else False,
                        "atr_ok": filter_result.get("allowed", False),
                        "spread_ok": filter_result.get("allowed", False),
                        "news_ok": not news_result.get("news") if self.news_filter is not None else True,
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
            if result.get("results"):
                for _r in result["results"]:
                    if _r.get("success") and hasattr(_r["result"], "order"):
                        ticket = _r["result"].order
                        break
            elif result.get("result") and hasattr(result["result"], "order"):
                ticket = result["result"].order

            if ticket:
                self.session_manager.register_entry(ticket)

            trade_data = {
                "time": last["time"],
                "symbol": self.symbol,
                "signal": decision["action"] if decision["action"] != "NO_TRADE" else prediction["signal"],
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
                    signal=decision["action"] if decision["action"] != "NO_TRADE" else prediction["signal"],
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
                "auto_trader_reason": result.get("reason", ""),
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
                for d in self.history_manager.today_exits():
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
                "auto_trader_reason": dash_data.get("auto_trader_reason", ""),
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
    # Recovery Close
    # =====================================

    def _check_recovery_close(self, position):
        ticket = position.ticket
        profit = position.profit

        if position.sl == 0 and position.tp == 0:
            if profit <= -15.0:
                _log_close("PROTECTIVE", ticket, position.symbol, profit)
                result = self.controller.close(position, caller="PROTECTIVE")
                return {"status": "CLOSED", "action": "PROTECTIVE",
                        "reason": f"Posisi tanpa SL/TP turun ke {profit:.2f} (proteksi).",
                        "ticket": ticket, "result": result}
            return None

        if profit < -15.0:
            self._recovery_seen[ticket] = True
            return None

        if self._recovery_seen.get(ticket) and 1.5 <= profit <= 4.5:
            _log_close("RECOVERY", ticket, position.symbol, profit)
            result = self.controller.close(position, caller="RECOVERY")
            self._recovery_seen.pop(ticket, None)
            return {"status": "CLOSED", "action": "RECOVERY",
                    "reason": f"Recovery close at {profit:.2f}",
                    "ticket": ticket, "result": result}

        return None

    # =====================================
    # Attach SL/TP on Profit
    # =====================================

    def _attach_sl_tp_on_profit(self, position):
        try:
            with open("runtime/trade_config.json") as _f:
                _cfg = json.load(_f)
                if not bool(_cfg.get("entry_without_sl_tp", False)):
                    return None
                _trigger = float(_cfg.get("attach_profit_trigger", 0.5))
        except Exception:
            return None

        if position.sl != 0 or position.tp != 0:
            return None

        if position.profit < _trigger:
            return {"status": "WAITING", "action": "NONE",
                    "reason": f"Profit belum {_trigger:.1f} ({position.profit:.2f})."}

        _sp = get_symbol_params(self.symbol)
        _sl_pts = float(_sp.get("sl_points", 6.0))
        _tp1_pts = float(_sp.get("tp1_points", _sl_pts * 1.5))
        _point = float(_sp.get("point", 0.01))
        _tp_dist = _tp1_pts * _point

        if position.type == 0:
            _sl = round(position.price_open, 5)
            _tp = round(position.price_open + _tp_dist, 5)
        else:
            _sl = round(position.price_open, 5)
            _tp = round(position.price_open - _tp_dist, 5)

        result = self.controller.modify_sl_tp(position, _sl, _tp)
        return {"status": "UPDATED" if result.get("success") else "FAILED",
                "action": "ATTACH_SLTP",
                "reason": f"Pasang SL/TP saat profit +{position.profit:.2f}.",
                "new_stop_loss": _sl, "new_take_profit": _tp, "result": result}

    # =====================================
    # Re-entry Protection
    # =====================================

    def _ticket_direction(self, tickets):
        try:
            if not tickets:
                return None
            ticket = sorted(tickets)[-1]
            deals = mt5.history_deals_get(position=ticket) if hasattr(mt5, "history_deals_get") else None
            if deals:
                for d in deals:
                    if d.entry == mt5.DEAL_ENTRY_IN:
                        return "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL"
        except Exception:
            pass
        return None

    def _ticket_profit(self, tickets):
        try:
            total = 0.0
            for ticket in sorted(tickets):
                deals = mt5.history_deals_get(position=ticket) if hasattr(mt5, "history_deals_get") else None
                if not deals:
                    continue
                for d in deals:
                    if d.entry == mt5.DEAL_ENTRY_OUT:
                        total += d.profit
            return total
        except Exception:
            return 0.0

    def _reentry_blocked(self, decision_action, cooldown_minutes=15, cooldown_win_minutes=5):
        if not self._last_closed_direction or not self._last_closed_time:
            return None
        if decision_action != self._last_closed_direction:
            return None
        minutes = cooldown_minutes if not self._last_closed_was_win else cooldown_win_minutes
        if (datetime.now() - self._last_closed_time).total_seconds() / 60 > minutes:
            return None
        return f"Hindari re-entry arah sama: posisi {self._last_closed_direction} baru ditutup (tunggu {minutes:.0f}m, mode {'win' if self._last_closed_was_win else 'loss'})."

    def _same_dir_spacing_blocked(self, decision_action):
        if decision_action not in ("BUY", "SELL"):
            return None
        last_time = self._last_same_dir_entry.get(decision_action)
        if last_time is None:
            return None
        elapsed = (datetime.now() - last_time).total_seconds()
        if elapsed >= self._same_dir_spacing:
            return None
        return (f"Jarak antar entry {decision_action} {elapsed:.0f}s < "
                f"{self._same_dir_spacing:.0f}s - tunggu spacing searah.")

    def _update_same_dir_entry(self, decision_action):
        if decision_action in ("BUY", "SELL"):
            self._last_same_dir_entry[decision_action] = datetime.now()

    # =====================================
    # Circuit Breaker Skor
    # =====================================

    def _track_consecutive_losses(self, closed_tickets):
        try:
            total_profit = 0.0
            for ticket in sorted(closed_tickets):
                deals = mt5.history_deals_get(position=ticket) if hasattr(mt5, "history_deals_get") else None
                if not deals:
                    continue
                for d in deals:
                    if d.entry == mt5.DEAL_ENTRY_OUT:
                        total_profit += d.profit
            if total_profit < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0
        except Exception:
            pass

        if self._consecutive_losses >= 3:
            self._score_penalty = 10
        elif self._consecutive_losses == 0:
            self._score_penalty = 0

    def _current_min_score(self):
        return 67 + self._score_penalty

    # =====================================
    # Entry Checklist (live menuju dashboard)
    # =====================================

    def _write_entry_checklist(self, can_trade, decision, filter_result, daily_result,
                               position_result, tf_confirmation, reentry_reason,
                               same_dir_reason, atr_filter_ok, atr_filter_reason,
                               session_result, scalp_result, regime):
        try:
            score_data = (scalp_result or {}).get("scalp_score", {}) or {}
            score = score_data.get("score", 0)
            direction = score_data.get("direction", "NEUTRAL")
            action = decision.get("action", "NO_TRADE")
            min_score = self._current_min_score()
            penalty = self._score_penalty

            items = []
            items.append(self._ck("Autotrade ON", self._auto_trade_enabled, None))

            equity_floor_ok = True
            try:
                _account = self.account_manager.get_info()
                _equity = float(_account.get("equity", 0))
                with open("runtime/trade_config.json") as _f:
                    floor = float(json.load(_f).get("equity_floor", 100.0))
                equity_floor_ok = _equity > floor
            except Exception:
                floor = 100.0
            items.append(self._ck("Equity > floor", equity_floor_ok, f"Equity vs floor {floor:.0f}"))

            sig_enough = score >= min_score
            items.append(self._ck(
                f"Scalp score >= {min_score}",
                sig_enough,
                f"{score:.1f}/100 {score_data.get('grade', '-')}" + (f" (penalti loss x{penalty})" if penalty else "")
            ))

            items.append(self._ck("Arah sinyal jelas", action in ("BUY", "SELL"), f"Direction {direction}"))

            action_ok = action in ("BUY", "SELL")
            items.append(self._ck("Keputusan siap trade", action_ok, decision.get("reason", "")))

            not_manual = not decision.get("manual", False)
            items.append(self._ck("Bukan sinyal manual", not_manual, None))

            items.append(self._ck(
                "Regime trend searah",
                action_ok and direction == self.decision_engine.trend_map.get(str(regime.get("trend", "SIDEWAYS")).upper()),
                f"Trend {regime.get('trend', 'SIDEWAYS')} vs {direction}"
            ))

            items.append(self._ck("Trade filter (session/spread/vol)", filter_result.get("allowed", False), filter_result.get("reason", "")))
            items.append(self._ck("Daily risk OK", daily_result.get("allowed", False), daily_result.get("reason", "")))
            items.append(self._ck("Posisi aman (max/arah/loss)", position_result.get("allowed", False), position_result.get("reason", "")))

            tf_allowed = bool(tf_confirmation.get("allowed", False)) if tf_confirmation else True
            items.append(self._ck("M5 & M15 searah sinyal", tf_allowed, (tf_confirmation or {}).get("reason", "")))

            items.append(self._ck("Cooldown re-entry 15 menit", not reentry_reason, reentry_reason or None))
            items.append(self._ck("Spacing entry searah 60s", not same_dir_reason, same_dir_reason or None))
            items.append(self._ck("ATR volatility filter OK", atr_filter_ok, atr_filter_reason or None))

            session_ok = True
            session_reason = None
            if session_result is not None:
                session_ok = session_result.get("allowed", True)
                session_reason = session_result.get("reason") or (None if session_ok else "Session tidak diizinkan")
            items.append(self._ck("Session aktif diizinkan", session_ok, session_reason))

            blocked_reason = None
            if not can_trade:
                for it in items:
                    if not it["ok"]:
                        blocked_reason = it["label"] + ": " + (it["detail"] or "")
                        break
                if blocked_reason is None:
                    blocked_reason = decision.get("reason", "Diblok oleh engine lain")

            payload = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "can_trade": can_trade,
                "decision_action": action,
                "decision_reason": decision.get("reason", ""),
                "blocked_reason": blocked_reason,
                "min_score": min_score,
                "score": score,
                "direction": direction,
                "items": items
            }
            with open("runtime/entry_checklist.json", "w") as _f:
                json.dump(payload, _f, indent=2, ensure_ascii=False)
        except Exception as e:
            import traceback
            with open("runtime/checklist_error.log", "a") as _elog:
                _elog.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ERROR: {e}\n")
                _elog.write(traceback.format_exc() + "\n")

    @staticmethod
    def _ck(label, ok, detail):
        return {"label": label, "ok": bool(ok), "detail": detail}

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
