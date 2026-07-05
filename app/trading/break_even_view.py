class BreakEvenView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("BREAK EVEN")
        print("=" * 60)

        print(f"Status : {result['status']}")

        if "reason" in result:
            print(f"Reason : {result['reason']}")

        if "result" in result:
            print(result["result"])