class DecisionView:

    @staticmethod
    def show(decision):

        print()
        print("=" * 60)
        print("LIVE DECISION")
        print("=" * 60)

        print(f"Action      : {decision['action']}")
        print(f"Reason      : {decision['reason']}")