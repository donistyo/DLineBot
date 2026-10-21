"""Candle stream MT5 -> WebSocket chart (display-only).

- History awal: copy_rates_from_pos M1/M5/M15 (500 bar)
- Update bar berjalan dari tick polling (0.5s)
- Fail-safe: semua error ditangkap, stream tidak boleh mengganggu engine
"""
import threading
import time

import MetaTrader5 as mt5

TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800,
              "H1": 3600, "H4": 14400, "D1": 86400}
MT5_TF = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}
DEFAULT_BARS = 2000
VALID_TFS = tuple(TF_SECONDS.keys())


def rate_to_bar(r):
    return {
        "time": int(r[0]),
        "open": round(float(r[1]), 3),
        "high": round(float(r[2]), 3),
        "low": round(float(r[3]), 3),
        "close": round(float(r[4]), 3),
    }


def next_bar_time(last_bar_time, tick_time, tf_seconds):
    """Bucket bar berikutnya. None last_bar_time -> bucket dari tick."""
    if last_bar_time is None:
        return tick_time - (tick_time % tf_seconds)
    t = last_bar_time
    while t + tf_seconds <= tick_time:
        t += tf_seconds
    return t


def apply_tick(bars, bid, tick_time, tf_seconds):
    """Update list bars (in-place) dari satu tick.

    Return list pesan: {"event": "new"|"update", "bar": {...}}
    MT5 epoch = epoch UTC asli; alignment bar server (offset tz
    kelipatan 60/300/900) sama dengan epoch % tf.
    """
    msgs = []
    last = bars[-1] if bars else None
    if last is None:
        nb = {
            "time": tick_time - (tick_time % tf_seconds),
            "open": bid, "high": bid, "low": bid, "close": bid,
        }
        bars.append(nb)
        msgs.append({"event": "new", "bar": dict(nb)})
        return msgs
    nxt = next_bar_time(last["time"], tick_time, tf_seconds)
    if nxt == last["time"]:
        changed = False
        if bid > last["high"]:
            last["high"] = bid
            changed = True
        if bid < last["low"]:
            last["low"] = bid
            changed = True
        if bid != last["close"]:
            last["close"] = bid
            changed = True
        if changed:
            msgs.append({"event": "update", "bar": dict(last)})
    else:
        nb = {"time": nxt, "open": bid, "high": bid, "low": bid, "close": bid}
        bars.append(nb)
        if len(bars) > DEFAULT_BARS:
            del bars[: len(bars) - DEFAULT_BARS]
        msgs.append({"event": "new", "bar": dict(nb)})
    return msgs


def positions_hash(positions):
    return str([
        (p.get("ticket"), p.get("type"), p.get("open_price"),
         p.get("sl"), p.get("tp"), p.get("profit"))
        for p in (positions or [])
    ])


class CandleStream:
    def __init__(self, symbol, on_message, positions_provider=None,
                 signals_path="runtime/signal_history.json",
                 tick_interval=0.5, bars=DEFAULT_BARS):
        self.symbol = symbol
        self._on_message = on_message
        self._positions_provider = positions_provider
        self._signals_path = signals_path
        self._tick_interval = tick_interval
        self._bars_limit = bars
        self.bars = {tf: [] for tf in VALID_TFS}
        self.tick = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._last_pos_hash = None
        self._last_signals_mtime = 0.0
        self._last_aux = 0.0
        self._last_resync = 0.0

    # ===============================
    # Lifecycle
    # ===============================
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="candle-stream")
        self._thread.start()

    def stop(self):
        self._running = False

    # ===============================
    # Data
    # ===============================
    def load_history(self, symbol=None):
        sym = symbol or self.symbol
        for tf, mt5_tf in MT5_TF.items():
            try:
                rates = mt5.copy_rates_from_pos(sym, mt5_tf, 0, self._bars_limit)
            except Exception:
                rates = None
            bars = []
            if rates is not None:
                for r in rates:
                    try:
                        bars.append(rate_to_bar(r))
                    except Exception:
                        continue
            with self._lock:
                self.bars[tf] = bars

    def set_symbol(self, symbol):
        if not symbol or symbol == self.symbol:
            return
        self.symbol = symbol
        self.load_history(symbol)

    def snapshot(self, symbol=None, tf="M5"):
        sym = symbol or self.symbol
        if tf not in VALID_TFS:
            tf = "M5"
        with self._lock:
            bars = [dict(b) for b in self.bars.get(tf, [])]
            tick = dict(self.tick) if self.tick else None
        positions = []
        if self._positions_provider:
            try:
                positions = [p for p in (self._positions_provider() or [])
                             if p.get("symbol") == sym]
            except Exception:
                positions = []
        signals = self._read_signals()
        return {
            "type": "snapshot",
            "symbol": sym,
            "tf": tf,
            "bars": bars,
            "tick": tick,
            "positions": positions,
            "signals": signals,
        }

    def _read_signals(self):
        try:
            import json
            with open(self._signals_path) as f:
                data = json.load(f)
            if isinstance(data, list):
                return data[-20:]
        except Exception:
            pass
        return []

    # ===============================
    # Loop (thread)
    # ===============================
    def _loop(self):
        try:
            self.load_history()
        except Exception:
            pass
        while self._running:
            try:
                self._poll_once()
            except Exception:
                pass
            time.sleep(self._tick_interval)

    def _poll_once(self):
        try:
            tick = mt5.symbol_info_tick(self.symbol)
        except Exception:
            tick = None
        if tick is None:
            time.sleep(1.0)
            return
        bid = round(float(tick.bid), 3)
        ask = round(float(tick.ask), 3)
        tick_time = int(tick.time)
        msgs = []
        with self._lock:
            self.tick = {"bid": bid, "ask": ask, "time": tick_time}
            for tf, sec in TF_SECONDS.items():
                for m in apply_tick(self.bars[tf], bid, tick_time, sec):
                    msgs.append({"type": "bar", "tf": tf, "event": m["event"],
                                 "bar": m["bar"]})
        self._emit({"type": "tick", "bid": bid, "ask": ask, "time": tick_time})
        for m in msgs:
            self._emit(m)
        now = time.time()
        if now - self._last_aux >= 2.0:
            self._last_aux = now
            self._check_positions()
            self._check_signals()
        if now - self._last_resync >= 60.0:
            self._last_resync = now
            self._resync_tail()

    def _resync_tail(self):
        """Koreksi drift bar berjalan: ambil 2 bar terakhir dari MT5."""
        for tf, mt5_tf in MT5_TF.items():
            try:
                rates = mt5.copy_rates_from_pos(self.symbol, mt5_tf, 0, 2)
            except Exception:
                continue
            if rates is None or len(rates) == 0:
                continue
            tail = [rate_to_bar(r) for r in rates]
            with self._lock:
                bars = self.bars[tf]
                if not bars:
                    self.bars[tf] = tail
                    continue
                last_hist = tail[-1]
                if bars[-1]["time"] == last_hist["time"]:
                    bars[-1] = last_hist
                    self._emit({"type": "bar", "tf": tf, "event": "update",
                                "bar": dict(last_hist)})
                elif last_hist["time"] > bars[-1]["time"]:
                    bars.append(last_hist)
                    self._emit({"type": "bar", "tf": tf, "event": "new",
                                "bar": dict(last_hist)})

    def _check_positions(self):
        if not self._positions_provider:
            return
        try:
            positions = [p for p in (self._positions_provider() or [])
                         if p.get("symbol") == self.symbol]
        except Exception:
            return
        h = positions_hash(positions)
        if h != self._last_pos_hash:
            self._last_pos_hash = h
            self._emit({"type": "positions", "positions": positions})

    def _check_signals(self):
        try:
            import os
            mtime = os.path.getmtime(self._signals_path)
        except Exception:
            return
        if mtime != self._last_signals_mtime:
            first = self._last_signals_mtime == 0.0
            self._last_signals_mtime = mtime
            if first:
                return
            self._emit({"type": "signals", "signals": self._read_signals()})

    def _emit(self, msg):
        try:
            self._on_message(msg)
        except Exception:
            pass
