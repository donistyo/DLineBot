from app.mt5.position_controller import PositionController, _log_close
from app.mt5.history_manager import HistoryManager


class SmartPositionManager:

    def __init__(self, symbol="XAUUSD", levels=None):
        self.symbol = symbol
        self.controller = PositionController()
        self.history_mgr = HistoryManager()

        # Track executed levels per ticket: {ticket: {action: True}}
        self._executed = {}

        # Track recently closed positions for re-entry
        self._recent_closes = []

        self.levels = levels if levels is not None else [
            {"profit": 4.5, "action": "SCALE_OUT",       "label": "Close 70%",       "close_pct": 70},
            {"profit": 9,   "action": "BREAK_EVEN",      "label": "Break Even"},
            {"profit": 13.5,"action": "CLOSE",            "label": "Close Sisa"},
            {"profit": 18,  "action": "TRAIL_LOOSE",      "label": "Trailing Start",   "distance": 9},
            {"profit": 30,  "action": "TRAIL_TIGHT",      "label": "Trailing Rapat",   "distance": 6},
            {"profit": 60,  "action": "LOCK_PROFIT",      "label": "Lock Profit +30",  "lock_at": 30},
            {"profit": 120, "action": "SCALE_OUT",        "label": "Scale Out 50%",    "close_pct": 50},
            {"profit": 180, "action": "TRAIL_FINAL",      "label": "Trailing Final",   "distance": 3},
        ]

    def process(self, position, prediction=None, regime=None, last=None):

        ticket = position.ticket
        profit = position.profit
        pos_type = "BUY" if position.type == 0 else "SELL"
        entry = position.price_open

        if ticket not in self._executed:
            self._executed[ticket] = set()

        done = self._executed[ticket]
        results = []

        for level in self.levels:
            if profit >= level["profit"]:
                action = level["action"]

                if action in done:
                    continue

                label = level["label"]

                if action == "BREAK_EVEN":
                    if position.sl == 0 or abs(position.sl - entry) >= 0.01:
                        resp = self.controller.modify_sl(position, entry)
                        done.add(action)
                        results.append({
                            "status": "UPDATED", "action": "BREAK_EVEN",
                            "reason": f"SL pindah ke entry ({label})",
                            "ticket": ticket, "result": resp
                        })
                    else:
                        results.append({
                            "status": "SKIPPED", "action": "BREAK_EVEN",
                            "reason": f"Break Even sudah aktif ({label})",
                            "ticket": ticket
                        })

                elif action == "TRAIL_LOOSE":
                    new_sl = self._trail_sl(position, level["distance"])
                    if new_sl and (position.sl == 0 or abs(new_sl - position.sl) > 0):
                        resp = self.controller.modify_sl(position, new_sl)
                        done.add(action)
                        results.append({
                            "status": "UPDATED", "action": "TRAIL_LOOSE",
                            "reason": f"Trailing start ({label})", "ticket": ticket, "result": resp
                        })
                    else:
                        results.append({
                            "status": "SKIPPED", "action": "TRAIL_LOOSE",
                            "reason": f"Trailing sudah aktif ({label})", "ticket": ticket
                        })

                elif action == "TRAIL_TIGHT":
                    new_sl = self._trail_sl(position, level["distance"])
                    if new_sl and (position.sl == 0 or abs(new_sl - position.sl) > 0):
                        resp = self.controller.modify_sl(position, new_sl)
                        done.add(action)
                        results.append({
                            "status": "UPDATED", "action": "TRAIL_TIGHT",
                            "reason": f"Trailing dirapatkan ({label})", "ticket": ticket, "result": resp
                        })
                    else:
                        results.append({
                            "status": "SKIPPED", "action": "TRAIL_TIGHT",
                            "reason": f"Trailing sudah rapat ({label})", "ticket": ticket
                        })

                elif action == "LOCK_PROFIT":
                    lock_price = entry + level["lock_at"] if pos_type == "BUY" else entry - level["lock_at"]
                    if position.sl == 0 or (pos_type == "BUY" and position.sl < lock_price) or (pos_type == "SELL" and position.sl > lock_price):
                        resp = self.controller.modify_sl(position, lock_price)
                        done.add(action)
                        results.append({
                            "status": "UPDATED", "action": "LOCK_PROFIT",
                            "reason": f"Profit diamankan +{level['lock_at']} ({label})",
                            "ticket": ticket, "result": resp
                        })
                    else:
                        results.append({
                            "status": "SKIPPED", "action": "LOCK_PROFIT",
                            "reason": f"Lock Profit sudah aktif ({label})", "ticket": ticket
                        })

                elif action == "SCALE_OUT":
                    close_volume = round(position.volume * level["close_pct"] / 100, 2)
                    if close_volume > 0 and close_volume < position.volume:
                        resp = self.controller.close_partial(position, close_volume)
                        done.add(action)
                        results.append({
                            "status": "SCALED", "action": "SCALE_OUT",
                            "reason": f"Scale out {level['close_pct']:.0f}% ({label})",
                            "ticket": ticket, "result": resp,
                            "closed_volume": close_volume
                        })

                elif action == "CLOSE":
                    _log_close("SMART_POSITION(TP)", position.ticket, position.symbol, position.profit)
                    resp = self.controller.close(position)
                    done.add(action)
                    results.append({
                        "status": "CLOSED", "action": "CLOSE",
                        "reason": f"Take Profit {label} (${profit:.2f})",
                        "ticket": ticket, "result": resp
                    })

                elif action == "TRAIL_FINAL":
                    new_sl = self._trail_sl(position, level["distance"])
                    if new_sl and (position.sl == 0 or abs(new_sl - position.sl) > 0):
                        resp = self.controller.modify_sl(position, new_sl)
                        done.add(action)
                        results.append({
                            "status": "UPDATED", "action": "TRAIL_FINAL",
                            "reason": f"Trailing final ({label})", "ticket": ticket, "result": resp
                        })
                    else:
                        results.append({
                            "status": "SKIPPED", "action": "TRAIL_FINAL",
                            "reason": f"Trailing final sudah aktif ({label})", "ticket": ticket
                        })

        # Cleanup stale tracking
        active_tickets = {p.ticket for p in self._get_active_positions()}
        for tid in list(self._executed.keys()):
            if tid not in active_tickets:
                del self._executed[tid]

        if not results:
            return {
                "status": "HOLD", "action": "NONE",
                "reason": f"Profit ${profit:.2f} — belum mencapai level berikutnya.",
                "ticket": ticket, "profit": profit
            }

        return {
            "status": "MANAGED", "action": "MULTI",
            "reason": f"{len(results)} level terpenuhi.",
            "ticket": ticket, "profit": profit,
            "details": results
        }

    def check_re_entry(self, prediction=None, regime=None, last=None):

        signal = prediction.get("signal") if prediction else None
        if not signal or signal == "HOLD":
            return {"re_entry": False, "reason": "Tidak ada sinyal."}

        if self._has_open_position():
            return {"re_entry": False, "reason": "Masih ada posisi terbuka."}

        trend_ok = False
        if regime:
            mode = regime.get("mode")
            trend = regime.get("trend")
            strength = regime.get("strength")
            if mode == "TREND" and strength == "Strong":
                trend_ok = True
            elif mode == "TREND":
                trend_ok = True

        if not trend_ok:
            return {"re_entry": False, "reason": "Trend tidak cukup kuat untuk re-entry."}

        if self._was_recently_closed_on_tp():
            return {
                "re_entry": True,
                "reason": f"Trend masih {trend}, sinyal {signal} — siap re-entry.",
                "signal": signal
            }

        return {"re_entry": False, "reason": "Tidak ada posisi yg ditutup dgn TP."}

    def track_close(self, ticket, reason="unknown"):
        self._recent_closes.append({
            "ticket": ticket,
            "reason": reason,
            "time": __import__("time").time()
        })
        if len(self._recent_closes) > 10:
            self._recent_closes.pop(0)

    def _was_recently_closed_on_tp(self):
        now = __import__("time").time()
        self._recent_closes = [
            c for c in self._recent_closes
            if now - c["time"] < 300
        ]
        return any(
            "TP" in c["reason"] or "take_profit" in c["reason"].lower()
            for c in self._recent_closes
        )

    def _get_active_positions(self):
        from app.mt5.position_manager import PositionManager
        pm = PositionManager()
        return pm.get_positions(self.symbol) or []

    def _has_open_position(self):
        return len(self._get_active_positions()) > 0

    def _trail_sl(self, position, distance):
        if position.type == 0:
            new_sl = position.price_current - distance
            if position.sl != 0 and new_sl <= position.sl:
                return None
        else:
            new_sl = position.price_current + distance
            if position.sl != 0 and new_sl >= position.sl:
                return None
        return new_sl
