class ConfidenceView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("AI CONFIDENCE MANAGER")
        print("=" * 60)

        print()
        print(f"Signal      : {result['signal']}")
        print()
        print(f"Confidence  : {result['confidence']:.0%}")

        print()
        if result["allowed"]:
            print(f"Status      : ALLOW")
        else:
            print(f"Status      : BLOCK")
