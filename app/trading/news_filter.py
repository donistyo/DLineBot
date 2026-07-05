import urllib.request
import json
from datetime import datetime, timedelta, timezone


class NewsFilter:

    def __init__(
        self,
        countries=None,
        min_impact="High",
        window_minutes=30
    ):
        self.url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        self.countries = countries or ["USD"]
        self.min_impact = min_impact
        self.window_minutes = window_minutes
        self._cache = None
        self._cache_time = None

    def _fetch(self):

        now = datetime.now()

        if self._cache and self._cache_time:
            if (now - self._cache_time) < timedelta(minutes=5):
                return self._cache

        try:
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            print(f"NewsFilter: Gagal fetch calendar - {e}")
            return None

        self._cache = data
        self._cache_time = now
        return data

    def allow(self):

        events = self._fetch()

        if events is None:
            return {
                "allowed": True,
                "reason": "Gagal memuat data news.",
                "news": None
            }

        now = datetime.now().replace(tzinfo=None)

        upcoming = []

        for event in events:
            country = event.get("country", "")
            impact = event.get("impact", "")
            title = event.get("title", "")

            if country not in self.countries:
                continue

            if self.min_impact == "High" and impact != "High":
                continue

            try:
                dt_str = event["date"]
                if dt_str.endswith(":00") and len(dt_str) > 19:
                    dt_str = dt_str[:-6]
                event_time = datetime.fromisoformat(dt_str)
                if event_time.tzinfo is not None:
                    event_time = event_time.replace(tzinfo=None)
            except Exception:
                continue

            diff = (event_time - now).total_seconds()

            if diff < -300:
                continue

            upcoming.append({
                "title": title,
                "country": country,
                "impact": impact,
                "time": event_time,
                "minutes_away": max(0, int(diff / 60))
            })

        upcoming.sort(key=lambda x: x["time"])

        for news in upcoming:
            if news["minutes_away"] <= self.window_minutes:
                return {
                    "allowed": False,
                    "reason": (
                        f"{news['impact']} Impact {news['country']} - "
                        f"{news['title']} "
                        f"({news['minutes_away']} menit lagi)"
                    ),
                    "news": news
                }

        return {
            "allowed": True,
            "reason": "Tidak ada High Impact News.",
            "news": None
        }
