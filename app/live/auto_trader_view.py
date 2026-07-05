class AutoTraderView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("AUTO TRADER")
        print("=" * 60)

        if result is None:

            print("Tidak ada hasil.")

            return

        for key, value in result.items():

            print(f"{key:<15}: {value}")