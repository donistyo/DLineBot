from datetime import datetime, timedelta
import time


class Scheduler:

    def wait(self, seconds):

        print()
        print("=" * 60)
        print("SCHEDULER")
        print("=" * 60)

        print(f"Menunggu {seconds} detik...\n")

        time.sleep(seconds)

    def seconds_until_next_hour(self):

        now = datetime.now()

        next_hour = (
            now.replace(
                minute=0,
                second=0,
                microsecond=0
            )
            + timedelta(hours=1)
        )

        return int(
            (next_hour - now).total_seconds()
        )