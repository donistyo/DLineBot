class AIExitView:

    @staticmethod
    def show(data):
        if data["action"] in ("AI_EXIT", "WATCH"):
            print()
            print("=" * 60)
            print("AI EXIT")
            print("=" * 60)
            print(f"Status : {data['status']}")
            print(f"Reason : {data['reason']}")
            if data.get("reversal_count"):
                print(f"Reversal : {data['reversal_count']}x")
