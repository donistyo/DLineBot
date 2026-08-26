class MultiTFView:

    @staticmethod
    def show(result):

        print()
        print("=" * 60)
        print("MULTI TIMEFRAME CONFIRMATION")
        print("=" * 60)

        if not result:
            print("Tidak ada data.")
            return

        print(f"Status    : {'OK' if result['allowed'] else 'REJECTED'}")
        print(f"Alignment : {result['alignment']:.0%}")
        print(f"Reason    : {result['reason']}")

        details = result.get("details", {})
        if details:
            print()
            for tf, info in details.items():
                mode = info.get("mode", "?")
                trend = info.get("ema_trend", info.get("trend", "?"))
                adx = info.get("adx", 0)
                print(f"  {tf:>4} : {mode:<8} {trend:<6} ADX {adx:.1f}")
