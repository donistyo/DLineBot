import MetaTrader5 as mt5
from app.mt5.session import MT5Session
from app.mt5.order_builder import OrderBuilder
from app.mt5.order_sender import OrderSender
from app.mt5.response_parser import ResponseParser
from app.database.db_logger import DatabaseLogger


class PartedOrderError(Exception):
    pass


class PartedOrder:

    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.sender = OrderSender(dry_run=False)
        self.logger = DatabaseLogger()

    def _tick(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise PartedOrderError(f"Gagal mengambil tick untuk {symbol}")
        return tick

    def _info(self, symbol):
        info = mt5.symbol_info(symbol)
        if info is None:
            raise PartedOrderError(f"Symbol {symbol} tidak ditemukan")
        return info

    def _split_volume(self, volume):
        min_lot = 0.01
        half = round(volume / 2, 2)
        vol1 = half
        vol2 = round(volume - half, 2)
        if vol1 < min_lot or vol2 < min_lot:
            return round(volume, 2), 0.0
        return vol1, vol2

    def execute(
        self,
        symbol,
        signal,
        volume,
        entry_price=None,
        stop_loss=None,
        take_profit1=None,
        take_profit2=None,
        magic=10001,
        comment="DLineBot-Manual"
    ):
        MT5Session.ensure_connection()

        info = self._info(symbol)
        tick = self._tick(symbol)

        signal = signal.upper()
        if signal not in ("BUY", "SELL"):
            raise PartedOrderError("Signal harus BUY atau SELL")

        point = info.point
        requested_entry = entry_price

        market_price = tick.ask if signal == "BUY" else tick.bid
        market_price = round(market_price / point) * point

        if entry_price is None:
            entry_price = market_price
        else:
            entry_price = round(entry_price / point) * point
            diff = abs(entry_price - market_price)
            if diff > point * 10:
                print()
                print("WARNING: Entry manual berbeda dari harga market!")
                print(f"  Entry manual : {entry_price}")
                print(f"  Harga market : {market_price}")
                print(f"  Selisih      : {diff / point:.0f} pts")
                print("  Market order akan pakai harga market (ask/bid saat ini)")
                print()

        from app.config.settings import get_symbol_params
        _sp = get_symbol_params(symbol)
        _sl_pts = _sp.get("sl_points", 500)
        _tp1_pts = _sp.get("tp1_points", 500)
        _tp2_pts = _sp.get("tp2_points", 1000)

        if stop_loss is None:
            sl_distance = _sl_pts * point
            stop_loss = entry_price - sl_distance if signal == "BUY" else entry_price + sl_distance
            stop_loss = round(stop_loss / point) * point

        if take_profit1 is None:
            tp1_distance = _tp1_pts * point
            take_profit1 = entry_price + tp1_distance if signal == "BUY" else entry_price - tp1_distance
            take_profit1 = round(take_profit1 / point) * point

        if take_profit2 is None:
            tp2_distance = _tp2_pts * point
            take_profit2 = entry_price + tp2_distance if signal == "BUY" else entry_price - tp2_distance
            take_profit2 = round(take_profit2 / point) * point

        exec_price = market_price

        vol1, vol2 = self._split_volume(volume)

        print()
        print("=" * 60)
        print(f"{signal} {symbol}")
        print("=" * 60)
        print(f"Total Lot  : {volume}")
        print(f"  Lot 1    : {vol1}  -> TP1 {take_profit1}")
        print(f"  Lot 2    : {vol2}  -> TP2 {take_profit2}")
        print(f"Entry rekam: {requested_entry or exec_price}")
        print(f"Exec price : {exec_price}")
        print(f"SL         : {stop_loss}")
        print()

        if self.dry_run:
            result1 = {"success": True, "dry_run": True, "ticket": 0}
            result2 = {"success": True, "dry_run": True, "ticket": 0}
            print("[DRY RUN] Order 1 & 2 tidak dikirim ke MT5")
        else:
            if signal == "BUY":
                req1 = OrderBuilder.buy(symbol, vol1, exec_price, stop_loss, take_profit1, magic, comment)
            else:
                req1 = OrderBuilder.sell(symbol, vol1, exec_price, stop_loss, take_profit1, magic, comment)
            result1 = self.sender.send(req1)

            if vol2 > 0:
                if signal == "BUY":
                    req2 = OrderBuilder.buy(symbol, vol2, exec_price, stop_loss, take_profit2, magic, comment)
                else:
                    req2 = OrderBuilder.sell(symbol, vol2, exec_price, stop_loss, take_profit2, magic, comment)
                result2 = self.sender.send(req2)
            else:
                result2 = {"success": True, "skipped": True, "reason": "Volume terlalu kecil untuk di-split"}

        self._log_result(symbol, signal, volume, entry_price, stop_loss,
                         take_profit1, take_profit2, vol1, vol2, result1, result2)

        return {
            "symbol": symbol,
            "signal": signal,
            "volume": volume,
            "volume_1": vol1,
            "volume_2": vol2,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit1": take_profit1,
            "take_profit2": take_profit2,
            "result_1": result1,
            "result_2": result2,
        }

    def _log_result(self, symbol, signal, volume, entry, sl, tp1, tp2,
                    vol1, vol2, result1, result2):
        ticket1 = None
        ticket2 = None
        status1 = "SUCCESS"
        status2 = "SUCCESS"
        reason1 = ""
        reason2 = ""

        if not result1.get("success"):
            status1 = "FAILED"
            reason1 = str(result1.get("errors", result1.get("error", "")))
        if result2.get("skipped"):
            status2 = "SKIPPED"
            reason2 = result2.get("reason", "")
        elif not result2.get("success"):
            status2 = "FAILED"
            reason2 = str(result2.get("errors", result2.get("error", "")))

        if not self.dry_run:
            ticket1 = result1.get("order") or 0
            ticket2 = result2.get("order") or 0

        self.logger.log_trade({
            "symbol": symbol,
            "signal": signal,
            "confidence": 1.0,
            "action": f"{signal} TP1",
            "status": status1,
            "reason": reason1 or f"Parted TP1 vol={vol1}",
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp1,
            "lot_size": vol1,
            "ticket": ticket1,
        })
        self.logger.log_trade({
            "symbol": symbol,
            "signal": signal,
            "confidence": 1.0,
            "action": f"{signal} TP2",
            "status": status2,
            "reason": reason2 or f"Parted TP2 vol={vol2}",
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp2,
            "lot_size": vol2,
            "ticket": ticket2,
        })

    def notify_telegram(self, result):
        try:
            from app.notification.telegram_notifier import TelegramNotifier
            tg = TelegramNotifier()
            if not tg.enabled:
                return

            p = result
            s = p["signal"]
            emoji = "\U0001f7e2" if s == "BUY" else "\U0001f534"
            text = (
                f"{emoji} <b>MANUAL {s}</b>\n"
                f"\n"
                f"Symbol   {p['symbol']}\n"
                f"Lot      {p['volume']}  ({p['volume_1']}x{p['take_profit1']} / {p['volume_2']}x{p['take_profit2']})\n"
                f"Entry    {p['entry_price']}\n"
                f"SL       {p['stop_loss']}\n"
                f"TP1      {p['take_profit1']}\n"
                f"TP2      {p['take_profit2']}\n"
            )

            ticket1 = p.get("result_1", {}).get("order", 0)
            ticket2 = p.get("result_2", {}).get("order", 0)
            if ticket1 or ticket2:
                text += f"\nTicket   {ticket1} / {ticket2}\n"

            ok1 = p.get("result_1", {}).get("success", False)
            ok2 = p.get("result_2", {}).get("success", False)
            skip2 = p.get("result_2", {}).get("skipped", False)
            if ok1 and ok2:
                text += "\nStatus   OK"
            elif skip2:
                text += f"\nStatus   TP1={'OK' if ok1 else 'FAIL'} TP2=SKIP (lot terlalu kecil)"
            else:
                text += f"\nStatus   TP1={'OK' if ok1 else 'FAIL'} TP2={'OK' if ok2 else 'FAIL'}"

            text += "\n\n\U0001f916 DLineBot"
            tg.send(text)
        except Exception as e:
            print(f"Telegram notify gagal: {e}")
