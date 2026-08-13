import urllib.request
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
ENABLED_FILE = Path(r"C:\Users\ADSS\AI-XAU-BOT\runtime\auto_trade_enabled.json")
OFF_MINUTES = 20


def set_enabled(flag):
    ENABLED_FILE.write_text(json.dumps({"enabled": flag}))
    print(f"[news-off] auto_trade_enabled -> {flag} ({datetime.now():%H:%M})")


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main():
    backoff = 10
    already_off_for = set()
    while True:
        try:
            data = fetch()
            backoff = 10
            now = datetime.now()
            upcoming = []
            for ev in data:
                if ev.get("country", "") != "USD" or ev.get("impact", "") != "High":
                    continue
                d = ev.get("date", "")
                if d.endswith(":00") and len(d) > 19:
                    d = d[:-6]
                try:
                    t = datetime.fromisoformat(d)
                    if t.tzinfo:
                        t = t.replace(tzinfo=None)
                except Exception:
                    continue
                diff = (t - now).total_seconds()
                if -300 < diff < 6 * 3600:
                    upcoming.append((t, ev.get("title", ""), diff))

            upcoming.sort(key=lambda x: x[2])
            if upcoming:
                t, title, diff = upcoming[0]
                mins = diff / 60
                if mins <= OFF_MINUTES:
                    if t not in already_off_for:
                        set_enabled(False)
                        already_off_for.add(t)
                        print(f"[news-off] OFF: {title} {t:%H:%M} ({mins:.0f} menit lagi)")
                else:
                    print(f"[news-off] {title} {t:%H:%M} -> {mins:.0f} menit lagi, menunggu...")
            else:
                print(f"[news-off] tidak ada High USD news dalam 6 jam ({now:%H:%M})")
        except Exception as e:
            print(f"[news-off] fetch gagal ({e}), retry dalam {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue
        time.sleep(30)


if __name__ == "__main__":
    main()
