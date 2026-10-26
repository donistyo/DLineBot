import uvicorn
import socket
import atexit
import threading
import time
from pathlib import Path
from dotenv import load_dotenv, set_key

load_dotenv()

ENV_PATH = Path(".env")

_runner = None
_runner_thread = None


class _QuietStdout:
    """Filter stdout engine: buang baris kosong/separator berulang.

    View console dicetak tiap siklus (~26 baris/detik), mayoritas
    kosong dan '====='. Tanpa filter log membengkak >100 MB/hari.
    Baris unik (harga, sinyal, error) tetap ditulis apa adanya;
    baris identik dalam window detik yang sama hanya ditulis sekali.
    """

    def __init__(self, stream, window=60.0):
        self._stream = stream
        self._window = window
        self._last = {}
        self._last_blank = False
        self._lock = threading.Lock()
        self._buf = ""

    def _emit(self, line):
        s = line.strip()
        if not s:
            if self._last_blank:
                return False
            self._last_blank = True
            return True
        now = time.monotonic()
        key = "SEP" if (len(s) >= 3 and set(s) == {"="}) else s
        prev = self._last.get(key)
        self._last[key] = now
        if len(self._last) > 5000:
            cutoff = now - self._window
            self._last = {k: v for k, v in self._last.items() if v >= cutoff}
            if len(self._last) > 5000:
                self._last.clear()
        if prev is not None and (now - prev) < self._window:
            return False
        self._last_blank = False
        return True

    def write(self, data):
        if not isinstance(data, str):
            return self._stream.write(data)
        with self._lock:
            self._buf += data
            if "\n" not in self._buf:
                return len(data)
            out = []
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                if self._emit(line):
                    out.append(line + "\n")
            if out:
                try:
                    self._stream.write("".join(out))
                    self._stream.flush()
                except Exception:
                    pass
            return len(data)

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_quiet_stdout():
    import sys
    if isinstance(sys.stdout, _QuietStdout):
        return
    try:
        sys.stdout = _QuietStdout(sys.stdout)
        print("[LOG] Filter log aktif (baris berulang/blank dibatasi)")
    except Exception:
        pass


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_engine():
    global _runner, _runner_thread
    if _runner and _runner.running:
        return
    from app.live.live_runner import LiveRunner
    try:
        from app.mt5.account_store import get_active_symbol
        symbol = get_active_symbol()
    except Exception:
        symbol = "XAUUSDc"
    print(f"Engine symbol: {symbol}")
    _runner = LiveRunner(interval=10, symbol=symbol, timeframe="M1", bars=2000, dry_run=False, mode="scalp")
    _runner_thread = threading.Thread(target=_runner.start, daemon=True)
    _runner_thread.start()
    print("Live engine started.")


def start_engine_watchdog():
    """Restart engine otomatis jika thread-nya mati (exception tak tertangani)."""
    def _watch():
        global _runner, _runner_thread
        while True:
            import time
            time.sleep(30)
            try:
                if _runner is None or _runner_thread is None:
                    # engine belum pernah start / start gagal -> coba lagi
                    try:
                        start_engine()
                    except Exception as e:
                        print(f"[WATCHDOG] engine start gagal: {e}")
                    continue
                if not _runner_thread.is_alive():
                    print(f"[WATCHDOG] Engine thread mati - restart {time.strftime('%H:%M:%S')}")
                    with open("logs/runner_error.log", "a") as f:
                        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WATCHDOG: engine thread mati, restart otomatis\n")
                    try:
                        _runner.running = False
                    except Exception:
                        pass
                    _runner = None
                    start_engine()
            except Exception as e:
                print(f"[WATCHDOG] error: {e}")
    threading.Thread(target=_watch, daemon=True).start()


def stop_engine():
    global _runner
    if _runner and _runner.running:
        _runner.stop()
        print("Live engine stopped.")
        return True
    return False


def patch_websockets_limits():
    """Handshake WebSocket dibatasi websockets-lib 8 KiB per baris header.

    Header besar (mis. Cookie raksasa dari browser) bikin server balas 431
    yang bahkan tidak sampai ke klien -> chart WS RECONNECT terus.
    Longgarkan limit + catat header besar untuk diagnosis.
    """
    try:
        import datetime
        from websockets import http11

        http11.MAX_LINE_LENGTH = 65536
        http11.MAX_NUM_HEADERS = 512
        _orig_parse = http11.Request.parse.__func__

        def _parse(cls, read_line):
            request = yield from _orig_parse(cls, read_line)
            try:
                big = [(k, len(v)) for k, v in request.headers.raw_items()
                       if len(v) >= 8000]
                if big:
                    detail = ", ".join(f"{k}={n}B" for k, n in big)
                    with open("logs/ws_big_headers.log", "a", encoding="utf-8") as f:
                        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} "
                                f"handshake header besar: {detail} "
                                f"(total_headers={len(request.headers)})\n")
            except Exception:
                pass
            return request

        http11.Request.parse = classmethod(_parse)
        print("[WS-PATCH] batas header handshake WS dinaikkan ke 64 KiB")
    except Exception as e:
        print(f"[WS-PATCH] gagal patch websockets: {e}")


if __name__ == "__main__":
    port = 8000
    local_ip = get_local_ip()

    install_quiet_stdout()

    local_url = f"http://{local_ip}:{port}"

    print("=" * 60)
    print("DASHBOARD + LIVE ENGINE")
    print("=" * 60)
    print(f"Local : {local_url}")
    print(f"Akses dari HP dalam jaringan: {local_url}")
    print()

    set_key(ENV_PATH, "DASHBOARD_URL", local_url)

    try:
        start_engine()
    except Exception:
        import traceback
        traceback.print_exc()
        print("[DASHBOARD] Engine gagal start - dashboard tetap jalan, watchdog akan coba lagi")
    start_engine_watchdog()
    atexit.register(stop_engine)

    print("=" * 60)

    patch_websockets_limits()

    uvicorn.run(
        "app.web_dashboard.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        h11_max_incomplete_event_size=1048576,
    )
