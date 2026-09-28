import uvicorn
import socket
import atexit
import threading
from pathlib import Path
from dotenv import load_dotenv, set_key

load_dotenv()

ENV_PATH = Path(".env")

_runner = None
_runner_thread = None


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


if __name__ == "__main__":
    port = 8000
    local_ip = get_local_ip()

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

    uvicorn.run(
        "app.web_dashboard.main:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )
