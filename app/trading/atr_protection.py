from app.mt5.position_controller import PositionController, _log_close


class ATRProtectionManager:

    def __init__(
        self,
        sl_atr_mult=1.5,
        be_trigger_atr=0.5,
        partial_trigger_atr=1.0,
        partial_pct=0.5,
        trail_activation_atr=1.5,
        trail_distance_atr=1.0,
        lock_profit_atr=2.0,
        lock_amount_atr=0.5,
        tp_atr=4.0,
        emergency_atr=2.5,
        partial_close=False,
        early_tp_atr=0.65,
        early_pullback_atr=0.25,
    ):
        self.sl_atr_mult = sl_atr_mult
        self.be_trigger_atr = be_trigger_atr
        self.partial_trigger_atr = partial_trigger_atr
        self.partial_pct = partial_pct
        self.trail_activation_atr = trail_activation_atr
        self.trail_distance_atr = trail_distance_atr
        self.lock_profit_atr = lock_profit_atr
        self.lock_amount_atr = lock_amount_atr
        self.tp_atr = tp_atr
        self.emergency_atr = emergency_atr
        self.partial_close = partial_close
        self.early_tp_atr = early_tp_atr
        self.early_pullback_atr = early_pullback_atr

        self.controller = PositionController()
        self._partial_done = set()
        self._peak_price = {}

    def cleanup(self, active_tickets):
        self._partial_done = {t for t in self._partial_done if t in active_tickets}
        self._peak_price = {t: p for t, p in self._peak_price.items() if t in active_tickets}

    def attach_initial_sl(self, position, atr):
        dist = self.sl_atr_mult * atr
        if dist <= 0:
            return None
        if position.type == 0:
            new_sl = round(position.price_open - dist, 5)
        else:
            new_sl = round(position.price_open + dist, 5)

        if position.sl == 0 or (position.type == 0 and new_sl > position.sl) or (position.type == 1 and new_sl < position.sl):
            result = self.controller.modify_sl(position, new_sl)
            return {"status": "UPDATED", "action": "INITIAL_SL",
                    "reason": f"SL awal {self.sl_atr_mult:.1f}xATR terpasang.",
                    "new_stop_loss": new_sl, "result": result}
        return None

    def process(self, position, atr, current_price):
        if atr <= 0:
            return {"status": "SKIP", "action": "NONE", "reason": "ATR tidak tersedia."}

        is_buy = position.type == 0

        # ======================================
        # Emergency: loss > 2.5x ATR -> close
        # ======================================
        emergency_loss = self.emergency_atr * atr
        if position.profit <= -emergency_loss:
            _log_close("ATR_EMERGENCY", position.ticket, position.symbol, position.profit)
            result = self.controller.close(position, caller="ATR_EMERGENCY")
            return {"status": "CLOSED", "action": "EMERGENCY",
                    "reason": f"Loss {position.profit:.2f} >= {self.emergency_atr:.1f}xATR ({emergency_loss:.2f}).",
                    "ticket": position.ticket, "result": result}

        # ======================================
        # Partial close 50% at 1.0x ATR
        # ======================================
        if self.partial_close and position.ticket not in self._partial_done:
            partial_trigger = self.partial_trigger_atr * atr
            if position.profit >= partial_trigger:
                vol = round(position.volume * self.partial_pct, 2)
                if vol > 0:
                    result = self.controller.close_partial(position, vol)
                    self._partial_done.add(position.ticket)
                    return {"status": "PARTIAL", "action": "PARTIAL_CLOSE",
                            "reason": f"Tutup {self.partial_pct:.0%} di {self.partial_trigger_atr:.1f}xATR ({partial_trigger:.2f}).",
                            "ticket": position.ticket, "result": result}

        # ======================================
        # Early TP: lock profit kecil ~2.5x kalau harga mandek/balik,
        # tapi biarkan berjalan sampai TP besar (tp_atr) jika terus naik.
        # ======================================
        early_trigger = self.early_tp_atr * atr
        early_pullback = self.early_pullback_atr * atr
        if position.profit >= early_trigger:
            if is_buy:
                self._peak_price[position.ticket] = max(
                    self._peak_price.get(position.ticket, position.price_open),
                    current_price
                )
            else:
                self._peak_price[position.ticket] = min(
                    self._peak_price.get(position.ticket, position.price_open),
                    current_price
                )

        peak = self._peak_price.get(position.ticket)
        if peak is not None:
            if is_buy and (peak - current_price) >= early_pullback:
                _log_close("EARLY_TP", position.ticket, position.symbol, position.profit)
                result = self.controller.close(position, caller="EARLY_TP")
                return {"status": "CLOSED", "action": "EARLY_TP",
                        "reason": f"Profit {position.profit:.2f} balik {peak - current_price:.2f} dari puncak {peak:.2f}.",
                        "ticket": position.ticket, "result": result}
            if not is_buy and (current_price - peak) >= early_pullback:
                _log_close("EARLY_TP", position.ticket, position.symbol, position.profit)
                result = self.controller.close(position, caller="EARLY_TP")
                return {"status": "CLOSED", "action": "EARLY_TP",
                        "reason": f"Profit {position.profit:.2f} balik {current_price - peak:.2f} dari puncak {peak:.2f}.",
                        "ticket": position.ticket, "result": result}

        # ======================================
        # Take Profit final at 4.0x ATR
        # ======================================
        tp_trigger = self.tp_atr * atr
        if position.profit >= tp_trigger:
            _log_close("ATR_TP", position.ticket, position.symbol, position.profit)
            result = self.controller.close(position, caller="ATR_TP")
            return {"status": "CLOSED", "action": "TP",
                    "reason": f"Profit {position.profit:.2f} >= {self.tp_atr:.1f}xATR ({tp_trigger:.2f}).",
                    "ticket": position.ticket, "result": result}

        # ======================================
        # Profit lock at 2.0x ATR -> SL ke +0.5x ATR
        # ======================================
        lock_trigger = self.lock_profit_atr * atr
        lock_sl = self.lock_amount_atr * atr
        if position.profit >= lock_trigger:
            if is_buy:
                new_sl = round(position.price_open + lock_sl, 5)
            else:
                new_sl = round(position.price_open - lock_sl, 5)
            if position.sl == 0 or (is_buy and new_sl > position.sl) or (not is_buy and new_sl < position.sl):
                result = self.controller.modify_sl(position, new_sl)
                return {"status": "UPDATED", "action": "LOCK_PROFIT",
                        "reason": f"Lock profit +{self.lock_amount_atr:.1f}xATR ({new_sl:.2f}).",
                        "new_stop_loss": new_sl, "result": result}
            return {"status": "OK", "action": "LOCK_PROFIT", "reason": "SL sudah optimal."}

        # ======================================
        # Trailing at 1.5x ATR, jarak 1.0x ATR
        # ======================================
        trail_trigger = self.trail_activation_atr * atr
        if position.profit >= trail_trigger:
            dist = self.trail_distance_atr * atr
            if is_buy:
                new_sl = round(current_price - dist, 5)
                better = position.sl == 0 or new_sl > position.sl
            else:
                new_sl = round(current_price + dist, 5)
                better = position.sl == 0 or new_sl < position.sl
            if better:
                result = self.controller.modify_sl(position, new_sl)
                return {"status": "UPDATED", "action": "TRAILING",
                        "reason": f"Trailing jarak {self.trail_distance_atr:.1f}xATR ({new_sl:.2f}).",
                        "new_stop_loss": new_sl, "result": result}
            return {"status": "OK", "action": "TRAILING", "reason": "SL trailing sudah optimal."}

        # ======================================
        # Break even at 0.5x ATR + spread buffer
        # ======================================
        be_trigger = self.be_trigger_atr * atr
        if position.profit >= be_trigger:
            if position.sl == 0 or (is_buy and position.sl < position.price_open) or (not is_buy and position.sl > position.price_open):
                spread_buffer = atr * 0.05
                if is_buy:
                    be_sl = round(position.price_open - spread_buffer, 5)
                else:
                    be_sl = round(position.price_open + spread_buffer, 5)
                result = self.controller.modify_sl(position, be_sl)
                return {"status": "UPDATED", "action": "BREAK_EVEN",
                        "reason": f"Break even di {self.be_trigger_atr:.1f}xATR ({be_trigger:.2f}) + spread buffer.",
                        "new_stop_loss": be_sl, "result": result}
            return {"status": "OK", "action": "BREAK_EVEN", "reason": "Break even sudah aktif."}

        return {"status": "WAITING", "action": "NONE",
                "reason": f"Profit {position.profit:.2f} < BE {self.be_trigger_atr:.1f}xATR ({be_trigger:.2f})."}
