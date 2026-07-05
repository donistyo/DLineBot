class NewsFilterView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("NEWS FILTER")
        print("=" * 60)

        if result["news"]:
            news = result["news"]
            print()
            print(f"Impact        : {news['impact']} Impact {news['country']}")
            print()
            print(f"{news['minutes_away']} menit lagi")
        else:
            print()
            print("No High Impact News")

        print()
        if result["allowed"]:
            print(f"Trading       : ALLOWED")
        else:
            print(f"Trading       : BLOCKED")
