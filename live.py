import subprocess
import sys
import atexit
import signal
import os
from pathlib import Path

from app.live.live_runner import LiveRunner

_dashboard_proc = None


def start_dashboard():
    global _dashboard_proc
    script = str(Path(__file__).parent / "dashboard.py")
    _dashboard_proc = subprocess.Popen(
        [sys.executable, script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    )
    print(f"Dashboard started (PID: {_dashboard_proc.pid})")
    return _dashboard_proc


def stop_dashboard():
    global _dashboard_proc
    if _dashboard_proc and _dashboard_proc.poll() is None:
        _dashboard_proc.terminate()
        try:
            _dashboard_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _dashboard_proc.kill()
        print("Dashboard stopped.")
        _dashboard_proc = None


def main():

    print("=" * 60)
    print("DLineBot - Starting Bot + Dashboard")
    print("=" * 60)

    atexit.register(stop_dashboard)
    signal.signal(signal.SIGINT, lambda s, f: (stop_dashboard(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (stop_dashboard(), sys.exit(0)))

    start_dashboard()

    try:
        from app.mt5.account_store import get_active_symbol
        symbol = get_active_symbol()
    except Exception:
        symbol = "XAUUSDc"
    print(f"Engine symbol: {symbol}")

    runner = LiveRunner(
        interval=10,
        symbol=symbol,
        timeframe="M1",
        bars=2000,
        dry_run=False,
        mode="scalp"
    )

    runner.start()


if __name__ == "__main__":
    main()