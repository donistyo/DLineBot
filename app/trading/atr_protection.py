import time

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
        be_buffer_atr=0.0,
        fast_tp_usd=2.5,
        stall_start_usd=1.0,
        stall_seconds=60,
        loser_seconds=600,
        loser_min_profit=0.0,
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
        self.be_buffer_atr = be_buffer_atr
        self.fast_tp_usd = fast_tp_usd
        self.stall_start_usd = stall_start_usd
        self.stall_seconds = stall_seconds
        self.loser_seconds = loser_seconds
        self.loser_min_profit = loser_min_profit

        self.controller = PositionController()
        self._partial_done = set()
        self._peak_price = {}
        self._stall_start = {}
        self._ever_profit = set()

    def cleanup(self, active_tickets):
        self._partial_done = {t for t in self._partial_done if t in active_tickets}
        self._peak_price = {t: p for t, p in self._peak_price.items() if t in active_tickets}
        self._stall_start = {t: s for t, s in self._stall_start.items() if t in active_tickets}
        self._ever_profit = {t for t in self._ever_profit if t in active_tickets}

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
        # MINIMUM SL GUARD: pastikan SL tidak
        # terlalu dekat ke entry. Jika SL sudah
        # ada tapi kurang dari sl_atr_mult * atr
        # dari entry, update ke jarak minimum.
        # ======================================
        min_dist = self.sl_atr_mult * atr
        if position.sl != 0 and min_dist > 0:
            if is_buy:
                min_sl = round(position.price_open - min_dist, 5)
                if position.sl > min_sl:
                    result = self.controller.modify_sl(position, min_sl)
                    return {"status": "UPDATED", "action": "MIN_SL_GUARD",
                            "reason": f"SL terlalu dekat ({position.sl:.2f}), diupdate ke minimum {min_dist:.1f}xATR ({min_sl:.2f}).",
                            "new_stop_loss": min_sl, "result": result}
            else:
                min_sl = round(position.price_open + min_dist, 5)
                if position.sl < min_sl:
                    result = self.controller.modify_sl(position, min_sl)
                    return {"status": "UPDATED", "action": "MIN_SL_GUARD",
                            "reason": f"SL terlalu dekat ({position.sl:.2f}), diupdate ke minimum {min_dist:.1f}xATR ({min_sl:.2f}).",
                            "new_stop_loss": min_sl, "result": result}

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

        now = time.time()

        # ======================================
        # LOSER EXIT: posisi tidak pernah profit
        # dalam loser_seconds -> close loss kecil.
        # ======================================
        if position.profit >= self.loser_min_profit:
            self._ever_profit.add(position.ticket)
        elif position.ticket not in self._ever_profit:
            open_age = now - float(position.time)
            if open_age >= self.loser_seconds:
                _log_close("LOSER_EXIT", position.ticket, position.symbol, position.profit)
                result = self.controller.close(position, caller="LOSER_EXIT")
                return {"status": "CLOSED", "action": "LOSER_EXIT",
                        "reason": f"Posisi belum pernah profit ({self.loser_min_profit:.2f}) "
                                  f"setelah {open_age / 60:.1f} menit -> close loss kecil.",
                        "ticket": position.ticket, "result": result}

        # ======================================
        # FAST TP: profit sudah >= target USD -> langsung close.
        # ======================================
        if position.profit >= self.fast_tp_usd:
            _log_close("FAST_TP", position.ticket, position.symbol, position.profit)
            result = self.controller.close(position, caller="FAST_TP")
            return {"status": "CLOSED", "action": "FAST_TP",
                    "reason": f"Profit {position.profit:.2f} sudah >= target {self.fast_tp_usd:.2f} USD.",
                    "ticket": position.ticket, "result": result}

        # ======================================
        # STALL EXIT: profit stabil di sekitar stall_start_usd
        # tanpa naik ke FAST_TP selama stall_seconds -> close.
        # ======================================
        if position.profit >= self.stall_start_usd:
            if position.ticket not in self._stall_start:
                self._stall_start[position.ticket] = now
            elif now - self._stall_start[position.ticket] >= self.stall_seconds:
                _log_close("STALL_EXIT", position.ticket, position.symbol, position.profit)
                result = self.controller.close(position, caller="STALL_EXIT")
                return {"status": "CLOSED", "action": "STALL_EXIT",
                        "reason": f"Profit {position.profit:.2f} mandek >= {self.stall_start_usd:.2f} "
                                  f"selama {self.stall_seconds}s tanpa naik ke {self.fast_tp_usd:.2f} USD.",
                        "ticket": position.ticket, "result": result}
        else:
            self._stall_start.pop(position.ticket, None)

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
                spread_buffer = atr * self.be_buffer_atr
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
