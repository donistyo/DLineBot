class RecoveryExitView:
    @staticmethod
    def show(result):
        if result is None:
            return
        print()
        print("=" * 60)
        print("RECOVERY EXIT")
        print("=" * 60)
        for k, v in result.items():
            print(f"{k:<15}: {v}")
