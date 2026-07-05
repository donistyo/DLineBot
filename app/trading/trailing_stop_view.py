class TrailingStopView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("TRAILING STOP")
        print("=" * 60)

        print(f"Status : {result['status']}")

        if "reason" in result:
            print(f"Reason : {result['reason']}")

        if "new_stop_loss" in result:
            print(f"New SL : {result['new_stop_loss']:.2f}")