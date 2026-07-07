class TimeExitView:

    @staticmethod
    def show(data):
        if data["action"] == "TIME_EXIT":
            print()
            print("=" * 60)
            print("TIME EXIT")
            print("=" * 60)
            print(f"Status : {data['status']}")
            print(f"Reason : {data['reason']}")
        elif data["action"] == "NONE" and data.get("elapsed", 0) > 0:
            print()
            print("=" * 60)
            print("TIME EXIT")
            print("=" * 60)
            print(f"Status : {data['status']}")
            print(f"Elapsed : {data['elapsed']:.0f}m")
            print(f"Reason : {data['reason']}")
