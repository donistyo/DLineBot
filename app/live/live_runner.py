import time

from app.live.live_engine import LiveEngine
from app.live.scheduler import Scheduler
from app.notification.telegram_notifier import TelegramNotifier
from app.config.settings import DASHBOARD_URL


class LiveRunner:

    def __init__(self, interval=10, symbol="XAUUSDc", timeframe="M1", bars=2000, dry_run=True, mode="scalp"):

        self.interval = interval
        self.running = False

        self.engine = LiveEngine(
            symbol=symbol,
            timeframe=timeframe,
            bars=bars,
            dry_run=dry_run,
            mode=mode
        )
        self.telegram = TelegramNotifier()

    def start(self):

        if self.running:
            return

        self.running = True

        print()
        print("=" * 60)
        print("DLineBot STARTED")
        print("=" * 60)
        print(f"Dashboard : {DASHBOARD_URL}")
        print("Run: python dashboard.py")
        print("=" * 60)

        self.telegram.send(f"DLineBot STARTED\nDashboard : {DASHBOARD_URL}")

        try:

            while self.running:

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

    def stop(self):

        self.running = False

        print()
        print("=" * 60)
        print("DLineBot STOPPED")
        print("=" * 60)