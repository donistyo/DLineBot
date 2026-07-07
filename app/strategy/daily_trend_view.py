class DailyTrendView:

    @staticmethod
    def show(data):

        print()
        print("=" * 60)
        print("FUNDAMENTAL DAILY")
        print("=" * 60)
        print()
        print(f"Bias       : {data['bias']}")
        print(f"Confidence : {data['confidence']}%")
        print(f"Score      : {data['score']}/10")
        print()
        if data["reasons"]:
            print("Reasons:")
            for r in data["reasons"]:
                print(f"  - {r}")
