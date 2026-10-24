import urllib.request
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
ENABLED_FILE = Path(r"C:\Project\Bot\DLineBot\runtime\auto_trade_enabled.json")
NEWS_FLAG = Path(r"C:\Project\Bot\DLineBot\runtime\news_off_active.json")
OFF_MINUTES = 20
REENABLE_AFTER_MIN = 10
WINDOW_START = (5, 50)   # 05:50 WIB
WINDOW_END = (23, 0)     # 23:00 WIB


def set_enabled(flag):
    ENABLED_FILE.write_text(json.dumps({"enabled": flag}))
    print(f"[news-off] auto_trade_enabled -> {flag} ({datetime.now():%H:%M})")


def in_window(now):
    m = now.hour * 60 + now.minute
    return WINDOW_START[0] * 60 + WINDOW_START[1] <= m <= WINDOW_END[0] * 60 + WINDOW_END[1]


def try_reenable(now):
    """Nyalakan kembali otomatis kalau news sudah lewat + buffer 10 menit."""
    if not NEWS_FLAG.exists():
        return
    try:
        data = json.loads(NEWS_FLAG.read_text() or "{}")
    except Exception:
        data = {}
    et = None
    if data.get("event_time"):
        try:
            et = datetime.fromisoformat(data["event_time"])
        except Exception:
            et = None
    if et is None or now < et + timedelta(minutes=REENABLE_AFTER_MIN):
        return
    if not in_window(now):
        return  # di luar jadwal: biarkan; task pagi 05:50 yang menyalakan
    set_enabled(True)
    NEWS_FLAG.unlink(missing_ok=True)
    print(f"[news-off] ON kembali setelah news \"{data.get('title', '')}\" selesai ({now:%H:%M})")


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main():
    backoff = 10
    already_off_for = set()
    while True:
        try:
            now = datetime.now()
            try_reenable(now)
            data = fetch()
            backoff = 10
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
                        NEWS_FLAG.write_text(json.dumps({
                            "event_time": t.isoformat(),
                            "title": title,
                        }))
                        print(f"[news-off] OFF: {title} {t:%H:%M} ({mins:.0f} menit lagi)")
                else:
                    print(f"[news-off] {title} {t:%H:%M} -> {mins:.0f} menit lagi, menunggu...")
            else:
                print(f"[news-off] tidak ada High USD news dalam 6 jam ({now:%H:%M})")
        except Exception as e:
            print(f"[news-off] fetch gagal ({e}), retry dalam {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 600)
            continue
        time.sleep(300)


if __name__ == "__main__":
    main()
