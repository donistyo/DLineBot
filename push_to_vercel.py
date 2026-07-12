import json
import sys
import time
from pathlib import Path
from threading import Thread

import requests


VERCEL_URL = "https://dlinebot-dashboard.vercel.app"


def get_partec_orders():
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from app.database.session import db_session
        from app.database.models import TradeLog
        with db_session() as db:
            orders = []
            for t in db.query(TradeLog).filter(
                TradeLog.action.like("%TP1%")
            ).order_by(TradeLog.id.desc()).limit(50).all():
                orders.append({
                    "time": str(t.time), "symbol": t.symbol,
                    "signal": t.signal, "entry_price": t.entry_price,
                    "stop_loss": t.stop_loss, "take_profit": t.take_profit,
                    "lot_size": t.lot_size, "status": t.status,
                    "ticket": t.ticket,
                })
            return orders
    except Exception as e:
        print(f"Gagal baca parted orders: {e}")
        return []


def push_overview(vercel_url=None):
    url = vercel_url or VERCEL_URL
    overview_path = Path("runtime/overview.json")
    if not overview_path.exists():
        return False

    try:
        with open(overview_path) as f:
            data = json.load(f)

        data["parted_orders"] = get_partec_orders()

        resp = requests.post(
            f"{url.rstrip('/')}/api/push",
            json=data,
            timeout=10
        )
        return resp.ok
    except Exception as e:
        print(f"Push ke Vercel gagal: {e}")
        return False


def start_pusher(interval=10, vercel_url=None):
    def _loop():
        while True:
            push_overview(vercel_url)
            time.sleep(interval)

    t = Thread(target=_loop, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    url = sys.argv[2] if len(sys.argv) > 2 else None
    print(f"Push data ke Vercel setiap {interval} detik")
    while True:
        ok = push_overview(url)
        print(f"Push {'OK' if ok else 'GAGAL'}")
        time.sleep(interval)
