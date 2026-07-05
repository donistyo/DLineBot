import ta

def add_indicators(df):
    # EMA
    df["EMA20"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=20
    ).ema_indicator()

    df["EMA50"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=50
    ).ema_indicator()

    df["EMA200"] = ta.trend.EMAIndicator(
        close=df["close"],
        window=200
    ).ema_indicator()

    # RSI
    df["RSI"] = ta.momentum.RSIIndicator(
        close=df["close"],
        window=14
    ).rsi()

    # MACD
    macd = ta.trend.MACD(df["close"])

    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()
    df["MACD_HIST"] = macd.macd_diff()

    # ATR
    atr = ta.volatility.AverageTrueRange(
        high=df["high"],
        low=df["low"],
        close=df["close"]
    )

    df["ATR"] = atr.average_true_range()

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(df["close"])

    df["BB_UPPER"] = bb.bollinger_hband()
    df["BB_MIDDLE"] = bb.bollinger_mavg()
    df["BB_LOWER"] = bb.bollinger_lband()

    return df