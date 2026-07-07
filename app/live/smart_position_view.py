class SmartPositionView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("SMART POSITION MANAGER")
        print("=" * 60)

        if not result:
            print("Tidak ada posisi.")
            return

        ticket = result.get("ticket", "?")
        profit = result.get("profit", 0)
        status = result.get("status", "HOLD")
        action = result.get("action", "NONE")
        reason = result.get("reason", "")

        print(f"Ticket : {ticket}")
        print(f"Profit : ${profit:.2f}")
        print(f"Status : {status}")
        print(f"Action : {action}")
        print(f"Reason : {reason}")

        details = result.get("details")
        if details:
            print()
            for d in details:
                print(f"  [{d['status']}] {d['action']:15s} {d['reason']}")
