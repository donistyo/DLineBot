import time

from app.live.live_engine import LiveEngine
from app.live.scheduler import Scheduler
from app.notification.telegram_notifier import TelegramNotifier


class LiveRunner:

    def __init__(self, interval=10):

        self.interval = interval
        self.running = False

        self.engine = LiveEngine()
        self.telegram = TelegramNotifier()

    def start(self):

        if self.running:
            return

        self.running = True

        print()
        print("=" * 60)
        print("DLineBot STARTED")
        print("=" * 60)

        self.telegram.send("DLineBot STARTED")

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