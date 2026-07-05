class MarketInfo:

    @staticmethod
    def show(last):

        print()
        print("=" * 60)
        print("MARKET INFORMATION")
        print("=" * 60)

        print(f"Symbol      : XAUUSD")
        print(f"Timeframe   : H1")
        print(f"Time        : {last['time']}")

        print(f"Open        : {last['open']:.2f}")
        print(f"High        : {last['high']:.2f}")
        print(f"Low         : {last['low']:.2f}")
        print(f"Close       : {last['close']:.2f}")

        print(f"Volume      : {last['tick_volume']}")
        print(f"Spread      : {last['spread']}")

        print()

        print(f"EMA20       : {last['EMA20']:.2f}")
        print(f"EMA50       : {last['EMA50']:.2f}")
        print(f"EMA200      : {last['EMA200']:.2f}")

        print(f"RSI         : {last['RSI']:.2f}")
        print(f"MACD        : {last['MACD']:.4f}")
        print(f"ADX         : {last['ADX']:.2f}")
        print(f"ATR         : {last['ATR']:.2f}")