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

    def _direction_from_bias(self, bias):
        bias = bias.upper()
        if bias in ("STRONG BULLISH", "BULLISH"):
            return "BUY"
        elif bias in ("STRONG BEARISH", "BEARISH"):
            return "SELL"
        return None

    def _calculate_sl_tp(self, direction, current_price):
        info = self.trader.symbol_info(self.symbol)
        tick = self.trader.tick(self.symbol)
        point = info.point

        atr = self._estimate_atr()
        sl_distance = max(atr * 1.5, 500 * point)
        sl_distance = round(sl_distance / point) * point

        if direction == "BUY":
            sl = round((current_price - sl_distance) / point) * point
            tp1 = round((current_price + sl_distance * 1.0) / point) * point
            tp2 = round((current_price + sl_distance * 2.0) / point) * point
        else:
            sl = round((current_price + sl_distance) / point) * point
            tp1 = round((current_price - sl_distance * 1.0) / point) * point
            tp2 = round((current_price - sl_distance * 2.0) / point) * point

        return sl, tp1, tp2

    def _estimate_atr(self):
        import MetaTrader5 as mt5
        rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M5, 0, 14)
        if rates is None or len(rates) < 14:
            return 0
        tr_sum = 0
        for i in range(1, len(rates)):
            high = rates[i]["high"]
            low = rates[i]["low"]
            prev_close = rates[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_sum += tr
        return tr_sum / (len(rates) - 1)

    def _cooldown_ok(self):
        if self.last_trade_time is None:
            return True
        return datetime.now() - self.last_trade_time >= self.cooldown

    def should_trade(self):
        fundamental = self.engine.analyze()
        bias = fundamental.get("bias", "NEUTRAL")
        conf = fundamental.get("confidence", 0)

        direction = self._direction_from_bias(bias)
        if direction is None:
            return False, "Fundamental NEUTRAL"

        if conf < 50:
            return False, f"Fundamental confidence too low ({conf}%)"

        if self.position_manager.has_position(self.symbol):
            return False, "Already has position"

        if not self._cooldown_ok():
            remaining = self.cooldown - (datetime.now() - self.last_trade_time)
            mins = int(remaining.total_seconds() // 60)
            return False, f"Cooldown {mins}m remaining"

        return True, f"Fundamental {bias} -> {direction}"

    def execute(self):
        MT5Session.ensure_connection()

        ok, reason = self.should_trade()
        if not ok:
            print()
            print("=" * 60)
            print("FUNDAMENTAL TRADER")
            print("=" * 60)
            print(f"Skip: {reason}")
            return {"status": "SKIPPED", "reason": reason}

        fundamental = self.engine.analyze()
        bias = fundamental.get("bias", "NEUTRAL")
        direction = self._direction_from_bias(bias)

        tick = self.trader.tick(self.symbol)
        entry = tick.ask if direction == "BUY" else tick.bid
        sl, tp1, tp2 = self._calculate_sl_tp(direction, entry)

        info = self.trader.symbol_info(self.symbol)

        try:
            result = self.order.execute(
                symbol=self.symbol,
                signal=direction,
                volume=info.volume_min * 2,
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
