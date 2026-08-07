from datetime import datetime, timedelta
from app.strategy.daily_trend_engine import DailyTrendEngine
from app.mt5.session import MT5Session
from app.mt5.parted_order import PartedOrder, PartedOrderError
from app.mt5.position_manager import PositionManager
from app.mt5.trader import MT5Trader
from app.notification.telegram_notifier import TelegramNotifier


class FundamentalTrader:

    def __init__(self, symbol="XAUUSDc", dry_run=False, cooldown_minutes=60):
        self.symbol = symbol
        self.dry_run = dry_run
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.last_trade_time = None
        self.engine = DailyTrendEngine()
        self.order = PartedOrder(dry_run=dry_run)
        self.position_manager = PositionManager()
        self.trader = MT5Trader()
        self.telegram = TelegramNotifier()
        self.multi_tf = None

    def _higher_tf_aligned(self, direction):
        """Filter ketat: M5 & M15 harus searah dengan arah fundamental."""
        if self.multi_tf is None:
            return True, "Multi-TF tidak tersedia."
        try:
            res = self.multi_tf.confirm({}, signal=direction)
        except Exception as e:
            return True, f"Multi-TF error: {e}"
        if not res.get("allowed", True):
            return False, f"Higher TF menolak ({res.get('reason', 'tidak searah')})"
        return True, res.get("reason", "Higher TF searah")

    def _direction_from_bias(self, bias):
        bias = bias.upper()
        if bias in ("STRONG BULLISH", "BULLISH"):
            return "BUY"
        elif bias in ("STRONG BEARISH", "BEARISH"):
            return "SELL"
        return None

    def _calculate_sl_tp(self, direction, current_price):
        info = self.trader.symbol_info(self.symbol)
        point = info.point

        from app.config.settings import get_symbol_params
        _sp = get_symbol_params(self.symbol)
        _sl_pts = float(_sp.get("sl_points", 800))
        _tp1_pts = float(_sp.get("tp1_points", _sl_pts * 1.5))
        _tp2_pts = float(_sp.get("tp2_points", _sl_pts * 3.0))

        sl_distance = _sl_pts * point
        tp1_distance = _tp1_pts * point
        tp2_distance = _tp2_pts * point

        if sl_distance <= 0:
            atr = self._estimate_atr()
            sl_distance = max(atr * 1.5, 500 * point)
            tp1_distance = sl_distance
            tp2_distance = sl_distance * 2.0

        sl_distance = round(sl_distance / point) * point
        tp1_distance = round(tp1_distance / point) * point
        tp2_distance = round(tp2_distance / point) * point

        if direction == "BUY":
            sl = round((current_price - sl_distance) / point) * point
            tp1 = round((current_price + tp1_distance) / point) * point
            tp2 = round((current_price + tp2_distance) / point) * point
        else:
            sl = round((current_price + sl_distance) / point) * point
            tp1 = round((current_price - tp1_distance) / point) * point
            tp2 = round((current_price - tp2_distance) / point) * point

        return sl, tp1, tp2

    def _estimate_atr(self):
        try:
            from app.trading.atr_helper import ATRHelper
            return float(ATRHelper(symbol=self.symbol, timeframe=mt5.TIMEFRAME_M5).current_atr())
        except Exception:
            return 0

    def _cooldown_ok(self):
        if self.last_trade_time is None:
            return True
        return datetime.now() - self.last_trade_time >= self.cooldown

    def should_trade(self, regime=None, prediction=None):
        import json, os
        try:
            with open("runtime/auto_trade_enabled.json") as f:
                if not json.load(f).get("enabled", True):
                    return False, "Auto-trade dimatikan dari dashboard."
        except Exception:
            pass

        fundamental = self.engine.analyze()
        bias = fundamental.get("bias", "NEUTRAL")
        conf = fundamental.get("confidence", 0)

        direction = self._direction_from_bias(bias)
        if direction is None:
            return False, "Fundamental NEUTRAL"

        if conf < 50:
            return False, f"Fundamental confidence too low ({conf}%)"

        if regime:
            mode = regime.get("mode", "RANGING")
            trend = regime.get("trend", "SIDEWAYS")
            if mode == "RANGING":
                return False, f"Regime RANGING (ADX {regime.get('adx', 0):.0f}), skip fundamental"
            expected = {"UP": "BUY", "DOWN": "SELL"}.get(trend)
            if expected and direction != expected:
                return False, f"Fundamental {direction} vs trend {trend} (lawan arah)"

        if prediction:
            ai_signal = prediction.get("signal", "WAIT")
            ai_conf = prediction.get("confidence", 0)
            if ai_signal in ("BUY", "SELL") and ai_conf >= 60 and direction != ai_signal:
                return False, f"Fundamental {direction} vs AI {ai_signal} ({ai_conf:.0f}%) (lawan arah)"

        tf_ok, tf_reason = self._higher_tf_aligned(direction)
        if not tf_ok:
            return False, tf_reason

        if self.position_manager.has_position(self.symbol):
            return False, "Already has position"

        if not self._cooldown_ok():
            remaining = self.cooldown - (datetime.now() - self.last_trade_time)
            mins = int(remaining.total_seconds() // 60)
            return False, f"Cooldown {mins}m remaining"

        return True, f"Fundamental {bias} -> {direction}"

    def execute(self, regime=None, prediction=None):
        MT5Session.ensure_connection()

        ok, reason = self.should_trade(regime, prediction)
        if not ok:
            print()
            print("=" * 60)
            print("FUNDAMENTAL TRADER")
            print("=" * 60)
            print(f"Skip: {reason}")
            return {"status": "SKIPPED", "reason": reason}

        import json as _json
        scalp_direction = None
        try:
            with open("runtime/scalping.json") as _sf:
                _sd = _json.load(_sf)
                scalp_direction = _sd.get("scalp_score", {}).get("direction", "NEUTRAL")
        except Exception:
            pass

        fundamental = self.engine.analyze()
        bias = fundamental.get("bias", "NEUTRAL")
        direction = self._direction_from_bias(bias)

        if scalp_direction and scalp_direction in ("BUY", "SELL") and direction != scalp_direction:
            print()
            print("=" * 60)
            print("FUNDAMENTAL TRADER")
            print("=" * 60)
            print(f"Skip: Fundamental {direction} vs scalp {scalp_direction} (tidak searah)")
            return {"status": "SKIPPED", "reason": f"Fundamental {direction} vs scalp {scalp_direction} (tidak searah)"}

        tick = self.trader.tick(self.symbol)
        entry = tick.ask if direction == "BUY" else tick.bid
        sl, tp1, tp2 = self._calculate_sl_tp(direction, entry)

        import json
        try:
            with open("runtime/trade_config.json") as _f:
                _cfg = json.load(_f)
                _use_atr = bool(_cfg.get("use_atr_protection", True))
                _sl_atr_mult = float(_cfg.get("sl_atr_mult", 1.5))
        except Exception:
            _use_atr = True
            _sl_atr_mult = 1.5

        if _use_atr:
            atr = self._estimate_atr()
            if atr > 0:
                sl_dist = atr * _sl_atr_mult
                sl_dist = round(sl_dist / 0.001) * 0.001
                if direction == "BUY":
                    sl = round((entry - sl_dist) / 0.001) * 0.001
                else:
                    sl = round((entry + sl_dist) / 0.001) * 0.001
            tp1, tp2 = 0.0, 0.0

        info = self.trader.symbol_info(self.symbol)

        from app.config.settings import load_trade_config, get_trade_config
        load_trade_config()
        _lot = get_trade_config("lot_size")
        volume = float(_lot) if _lot else info.volume_min

        from app.trading.lot_risk_guard import get_safe_lot
        try:
            from app.mt5.account_manager import AccountManager
            _acc = AccountManager().get_info()
            _bal = _acc.get("balance", 1000) if isinstance(_acc, dict) else 1000
        except Exception:
            _bal = 1000
        _atr_now = self._estimate_atr()
        _lot_check = get_safe_lot(_bal, _atr_now, None, volume)
        volume = _lot_check["lot_size"]
        if _lot_check["reduced"]:
            print(f"  LOT RISK GUARD: {_lot_check['reason']}")

        try:
            result = self.order.execute(
                symbol=self.symbol,
                signal=direction,
                volume=volume,
                entry_price=entry,
                stop_loss=sl,
                take_profit1=tp1,
                take_profit2=tp2,
                comment="DLineBot-Fundamental"
            )
            self.last_trade_time = datetime.now()

            print()
            print("=" * 60)
            print("FUNDAMENTAL TRADER")
            print("=" * 60)
            print(f"Bias   : {bias}")
            print(f"Action : {direction} @ {entry}")
            print(f"SL     : {sl}")
            print(f"TP1    : {tp1}")
            print(f"TP2    : {tp2}")
            print(f"Status : {'OK' if not self.dry_run else 'DRY RUN'}")

            result["status"] = "DRY_RUN" if self.dry_run else "SUCCESS"
            if not self.dry_run:
                self.order.notify_telegram(result)

            return result

        except PartedOrderError as e:
            print(f"Fundamental trade error: {e}")
            return {"status": "ERROR", "reason": str(e)}
