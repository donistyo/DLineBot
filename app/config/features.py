# Feature yang digunakan model AI
FEATURE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",

    "tick_volume",
    "spread",
    "real_volume",

    "EMA20",
    "EMA50",
    "EMA200",

    "RSI",

    "MACD",
    "MACD_SIGNAL",
    "MACD_HIST",

    "ATR",

    "BB_UPPER",
    "BB_MIDDLE",
    "BB_LOWER",

    "ADX",

    "STO_K",
    "STO_D"
]

# Kolom yang tidak digunakan sebagai feature
DROP_COLUMNS = [
    "time",
    "future_close",
    "price_diff",
    "label"
]