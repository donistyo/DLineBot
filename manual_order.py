import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.mt5.session import MT5Session
from app.mt5.parted_order import PartedOrder


def main():
    print()
    print("=" * 60)
    print("MANUAL ORDER - SL, TP1, TP2")
    print("=" * 60)
    print()

    MT5Session.connect()

    try:
        symbol = input("Symbol (default XAUUSDc): ").strip() or "XAUUSDc"
        signal = input("Signal (BUY/SELL): ").strip().upper()
        while signal not in ("BUY", "SELL"):
            signal = input("Signal harus BUY atau SELL: ").strip().upper()

        lot_str = input("Lot size: ").strip()
        volume = float(lot_str) if lot_str else 0.01

        entry_str = input("Entry price (enter=auto): ").strip()
        entry = float(entry_str) if entry_str else None

        sl_str = input("Stop Loss: ").strip()
        sl = float(sl_str) if sl_str else None

        tp1_str = input("Take Profit 1: ").strip()
        tp1 = float(tp1_str) if tp1_str else None

        tp2_str = input("Take Profit 2: ").strip()
        tp2 = float(tp2_str) if tp2_str else None

        dry_run_str = input("Dry run? (y/N): ").strip().lower()
        dry_run = dry_run_str == "y"

        print()
        print("-" * 60)
        print("RINGKASAN ORDER")
        print("-" * 60)
        print(f"Symbol   : {symbol}")
        print(f"Signal   : {signal}")
        print(f"Lot      : {volume}")
        print(f"Entry    : {entry or 'AUTO'}")
        print(f"SL       : {sl}")
        print(f"TP1      : {tp1}")
        print(f"TP2      : {tp2}")
        print(f"Dry run  : {'Ya' if dry_run else 'Tidak'}")
        print()

        confirm = input("Konfirmasi kirim? (y/N): ").strip().lower()
        if confirm != "y":
            print("Dibatalkan.")
            return

        order = PartedOrder(dry_run=dry_run)
        result = order.execute(
            symbol=symbol,
            signal=signal,
            volume=volume,
            entry_price=entry,
            stop_loss=sl,
            take_profit1=tp1,
            take_profit2=tp2,
        )

        print()
        print("=" * 60)
        print("HASIL ORDER")
        print("=" * 60)
        r1 = result["result_1"]
        r2 = result["result_2"]

        if dry_run:
            print("TP1: [DRY RUN]")
            print("TP2: [DRY RUN]")
        else:
            ticket1 = r1.get("ticket") or r1.get("result", {}).get("order", 0)
            ticket2 = r2.get("ticket") or r2.get("result", {}).get("order", 0)
            print(f"TP1: {'OK' if r1.get('success') else 'GAGAL'}  Ticket={ticket1}")
            print(f"TP2: {'OK' if r2.get('success') else 'GAGAL'}  Ticket={ticket2}")
            if not r1.get("success"):
                print(f"  Error TP1: {r1.get('errors', r1.get('error', '-'))}")
            if not r2.get("success"):
                print(f"  Error TP2: {r2.get('errors', r2.get('error', '-'))}")

        if not dry_run:
            order.notify_telegram(result)
            print("\nTelegram notification sent.")

    except KeyboardInterrupt:
        print("\nDibatalkan.")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        MT5Session.disconnect()


if __name__ == "__main__":
    main()
