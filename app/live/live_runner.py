import json
import os
import time

from app.live.live_engine import LiveEngine
from app.live.scheduler import Scheduler
from app.notification.telegram_notifier import TelegramNotifier
from app.config.settings import DASHBOARD_URL


class LiveRunner:

    def __init__(self, interval=10, symbol="XAUUSDc", timeframe="M1", bars=2000, dry_run=True, mode="scalp"):

        self.interval = interval
        self.running = False
        self.dry_run = dry_run
        self.mode = mode
        self.timeframe = timeframe
        self.bars = bars

        self.symbol = symbol
        self.engine = self._build_engine()
        self.telegram = TelegramNotifier()

    def _build_engine(self):
        return LiveEngine(
            symbol=self.symbol,
            timeframe=self.timeframe,
            bars=self.bars,
            dry_run=self.dry_run,
            mode=self.mode
        )

    def _check_symbol_change(self):
        """Deteksi pergantian simbol/akun agar engine direbuild otomatis."""
        try:
            from app.mt5.account_store import get_active_symbol
            active_symbol = get_active_symbol()
        except Exception:
            return False

        changed = active_symbol != self.symbol

        restart_requested = False
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "runtime", "engine_restart.json")
            if os.path.exists(path):
                with open(path) as f:
                    flag = json.load(f)
                restart_requested = bool(flag.get("requested"))
                try:
                    os.remove(path)
                except Exception:
                    pass
        except Exception:
            pass

        return changed or restart_requested

    def rebuild_engine(self):
        if hasattr(self, "engine") and self.engine is not None:
            try:
                self.engine.stop()
            except Exception:
                pass
        self.engine = self._build_engine()
        print()
        print("=" * 60)
        print("ENGINE REBUILD")
        print("=" * 60)
        print(f"Symbol : {self.symbol}")
        print("=" * 60)

    def start(self):

        if self.running:
            return

        self.running = True

        print()
        print("=" * 60)
        print("DLineBot STARTED")
        print("=" * 60)
        print(f"Dashboard : {DASHBOARD_URL}")
        print(f"Symbol    : {self.symbol}")
        print("Run: python dashboard.py")
        print("=" * 60)

        self.telegram.send(f"DLineBot STARTED\nDashboard : {DASHBOARD_URL}")

        try:

            while self.running:

                if self._check_symbol_change():
                    self.symbol = self._current_symbol()
                    self.rebuild_engine()
                    self.telegram.send(f"Engine restart -> {self.symbol}")

                self.engine.run_once()

                if not self.running:
                    break

                print()
                print("=" * 60)
                print("SCHEDULER")
                print("=" * 60)
                print(f"Waiting {self.interval} seconds...")

                time.sleep(self.interval)

        except KeyboardInterrupt:

            self.stop()

        finally:

            self.engine.stop()

    def _current_symbol(self):
        try:
            from app.mt5.account_store import get_active_symbol
            return get_active_symbol()
        except Exception:
            return self.symbol

    def stop(self):

        self.running = False

        print()
        print("=" * 60)
        print("DLineBot STOPPED")
        print("=" * 60)
