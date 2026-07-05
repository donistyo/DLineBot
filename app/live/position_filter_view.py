class PositionFilterView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("POSITION FILTER")
        print("=" * 60)

        print(f"Allowed : {result['allowed']}")
        print(f"Reason  : {result['reason']}")

        if not result["allowed"]:

            if "ticket" in result:

                print(f"Ticket  : {result['ticket']}")

            if "position_type" in result:

                print(f"Type    : {result['position_type']}")

            if "volume" in result:

                print(f"Volume  : {result['volume']}")