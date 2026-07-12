import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))

from app.notification.telegram_notifier import TelegramNotifier
from push_to_vercel import push_overview


VERCEL_URL = "https://dlinebot-dashboard.vercel.app"
PUSH_INTERVAL = 15
POLL_ORDER_INTERVAL = 5


def execute_pending_orders():
    try:
        resp = requests.get(
            f"{VERCEL_URL.rstrip('/')}/api/order/pending",
            timeout=10
        )
        if not resp.ok:
            return

        data = resp.json()
        orders = data.get("orders", [])
        if not orders:
            return

        for order in orders:
            dry_run = order.get("dry_run", False)
            print(f"\nMenjalankan order dari Vercel: {order}")
            try:
                from app.mt5.parted_order import PartedOrder
                po = PartedOrder(dry_run=dry_run)
                result = po.execute(
                    symbol=order.get("symbol", "XAUUSDc"),
                    signal=order.get("signal", "BUY"),
                    volume=order.get("volume", 0.01),
                    entry_price=order.get("entry"),
                    stop_loss=order.get("sl"),
                    take_profit1=order.get("tp1"),
                    take_profit2=order.get("tp2"),
                )
                po.notify_telegram(result)
                print(f"Order selesai: {result}")
            except Exception as e:
                print(f"Gagal eksekusi order: {e}")

    except Exception as e:
        print(f"Gagal polling pending orders: {e}")


def main():
    bot = TelegramNotifier()
    print("=" * 60)
    print("DLineBot Telegram Bot - polling commands...")
    print("Kirim /dashboard ke @DLineTradeBot")
    print(f"Push ke Vercel setiap {PUSH_INTERVAL}s")
    print(f"Poll order dari Vercel setiap {POLL_ORDER_INTERVAL}s")
    print("=" * 60)

    last_push = 0
    last_order_poll = 0

    while True:
        now = time.time()
        try:
            bot.handle_updates()

            if now - last_push >= PUSH_INTERVAL:
                ok = push_overview(VERCEL_URL)
                if ok:
                    print("Push ke Vercel OK")
                last_push = now

            if now - last_order_poll >= POLL_ORDER_INTERVAL:
                execute_pending_orders()
                last_order_poll = now

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(3)


if __name__ == "__main__":
    main()
