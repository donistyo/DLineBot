class ExitView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("EXIT MANAGER")
        print("=" * 60)

        print(f"Status : {result['status']}")
        print(f"Reason : {result['reason']}")

        if "action" in result:
            print(f"Action : {result['action']}")

        if "new_stop_loss" in result:
            print(f"New SL : {result['new_stop_loss']}")

        if "ticket" in result:
            print(f"Ticket : {result['ticket']}")