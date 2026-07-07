class ScoreView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print(f"AI TRADE SCORE : {result['grade']}")
        print("=" * 60)
        print(f"Score  : {result['score']}/100")
        print(f"Action : {result['action']}")

        details = result.get("details", {})
        if details:
            print()
            for key, val in details.items():
                label = key.replace("_", " ").title()
                print(f"  {label:<20} {val:.0f}")
