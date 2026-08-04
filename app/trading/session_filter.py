from datetime import datetime


class SessionFilter:

    def __init__(self, windows=None, start_hour=7, end_hour=21):
        """
        windows: list of (start_hour, end_hour) INCLUSIVE, dalam UTC.
        Mendukung interval yang melewati tengah malam (mis. (23, 12) = 23:00-00:00 lalu 00:00-12:00 UTC).

        Default (Asia + awal London) sesuai rekomendasi:
          - Asia  : 23:00 UTC - 07:00 UTC  (06:00-14:00 WIB)
          - London: 07:00 UTC - 12:30 UTC  (14:00-19:30 WIB)
        => aktif rentang 23:00 - 12:30 UTC (NY aktif 12:30-23:00 UTC dimatikan).
        """
        if windows is None:
            windows = [(23, 12)]
        self.windows = windows
        self.start_hour = start_hour
        self.end_hour = end_hour

    def _in_window(self, hour, start, end):
        if start <= end:
            return start <= hour <= end
        # interval melewati tengah malam, mis (23,12)
        return hour >= start or hour <= end

    def allow(self):
        hour = datetime.utcnow().hour

        for start, end in self.windows:
            if self._in_window(hour, start, end):
                return {
                    "allowed": True,
                    "reason": f"Trading session aktif ({start:02d}:00-{end:02d}:00 UTC)."
                }

        return {
            "allowed": False,
            "reason": "Di luar jam trading (NY aktif / jetak)."
        }