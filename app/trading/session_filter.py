from datetime import datetime


class SessionFilter:

    def __init__(self, windows=None, start_hour=7, end_hour=21):
        """
        windows: list of window, masing-masing salah satu bentuk:
          - (start_hour, end_hour)          -> resolusi jam (INKLUSIF), UTC
          - (start_h, start_m, end_h, end_m) -> resolusi menit (INKLUSIF), UTC
        Mendukung interval yang melewati tengah malam
        (mis. (23, 12) = 23:00-00:00 lalu 00:00-12:00 UTC).

        Catatan: waktu yang dipakai adalah UTC.
        WIB = UTC+7, jadi 05:50 WIB = 22:50 UTC (hari sebelumnya).
        """
        if windows is None:
            windows = [(23, 12)]
        self.windows = windows
        self.start_hour = start_hour
        self.end_hour = end_hour

    def _parse_window(self, w):
        """Return (start_minutes, end_minutes) dari tuple window."""
        if len(w) >= 4:
            start = int(w[0]) * 60 + int(w[1])
            end = int(w[2]) * 60 + int(w[3])
        else:
            start = int(w[0]) * 60
            end = int(w[1]) * 60 + 59  # presisi jam: sampai menit terakhir
        return start, end

    def _in_window(self, minutes, start, end):
        if start <= end:
            return start <= minutes <= end
        # interval melewati tengah malam
        return minutes >= start or minutes <= end

    def allow(self):
        now = datetime.utcnow()
        minutes = now.hour * 60 + now.minute

        for w in self.windows:
            start, end = self._parse_window(w)
            if self._in_window(minutes, start, end):
                s_h, s_m = divmod(start, 60)
                e_h, e_m = divmod(end, 60)
                return {
                    "allowed": True,
                    "reason": f"Trading session aktif ({s_h:02d}:{s_m:02d}-{e_h:02d}:{e_m:02d} UTC)."
                }

        return {
            "allowed": False,
            "reason": "Di luar jam trading (NY aktif / jetak)."
        }
