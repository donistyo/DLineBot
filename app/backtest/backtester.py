import pandas as pd


class Backtester:

    def __init__(
        self,
        initial_balance=1000,
        profit_per_win=10,
        loss_per_trade=5
    ):
        self.initial_balance = initial_balance
        self.profit_per_win = profit_per_win
        self.loss_per_trade = loss_per_trade

    def run(
        self,
        model,
        X_test,
        y_test,
        df_test
    ):

        # ==========================================
        # Prediction
        # ==========================================

        predictions = model.predict(X_test)
        probabilities = model.predict_proba(X_test)

        signal_map = {
            0: "SELL",
            1: "HOLD",
            2: "BUY"
        }

        # ==========================================
        # Backtesting Variable
        # ==========================================

        balance = self.initial_balance

        win = 0
        loss = 0

        history = []
        trades = []

        # ==========================================
        # Loop Semua Trade
        # ==========================================

        for i in range(len(predictions)):

            pred = int(predictions[i])
            actual = int(y_test.iloc[i])

            signal = signal_map[pred]

            confidence = float(probabilities[i].max())

            sell_prob = float(probabilities[i][0])
            hold_prob = float(probabilities[i][1])
            buy_prob = float(probabilities[i][2])

            entry_price = float(df_test.iloc[i]["close"])

            # Simulasi SL / TP
            if signal == "BUY":

                stop_loss = entry_price - 10
                take_profit = entry_price + 20

            elif signal == "SELL":

                stop_loss = entry_price + 10
                take_profit = entry_price - 20

            else:

                stop_loss = entry_price
                take_profit = entry_price

            # Simulasi hasil trade
            if pred == actual:

                profit = self.profit_per_win
                result = "WIN"
                exit_price = take_profit
                win += 1

            else:

                profit = -self.loss_per_trade
                result = "LOSS"
                exit_price = stop_loss
                loss += 1

            balance += profit
            history.append(balance)

            # ==========================================
            # Simpan History Trade
            # ==========================================

            trades.append({

                "trade": i + 1,
                "time": str(df_test.iloc[i]["time"]),
                "symbol": "XAUUSD",
                "timeframe": "H1",

                "signal": signal,

                "prediction": pred,
                "actual": actual,

                "confidence": round(confidence, 4),

                "sell_probability": round(sell_prob, 4),
                "hold_probability": round(hold_prob, 4),
                "buy_probability": round(buy_prob, 4),

                "entry_price": round(entry_price, 2),
                "stop_loss": round(stop_loss, 2),
                "take_profit": round(take_profit, 2),
                "exit_price": round(exit_price, 2),

                "profit": round(profit, 2),
                "balance": round(balance, 2),

                "result": result,

                "ema20": round(float(df_test.iloc[i]["EMA20"]), 2),
                "ema50": round(float(df_test.iloc[i]["EMA50"]), 2),
                "ema200": round(float(df_test.iloc[i]["EMA200"]), 2),

                "rsi": round(float(df_test.iloc[i]["RSI"]), 2),
                "macd": round(float(df_test.iloc[i]["MACD"]), 4),
                "adx": round(float(df_test.iloc[i]["ADX"]), 2),
                "atr": round(float(df_test.iloc[i]["ATR"]), 2),

                "spread": int(df_test.iloc[i]["spread"]),
                "volume": int(df_test.iloc[i]["tick_volume"])

            })

        # ==========================================
        # Convert ke DataFrame
        # ==========================================

        trade_df = pd.DataFrame(trades)

        # ==========================================
        # Return Report
        # ==========================================

        return {

            "initial_balance": self.initial_balance,

            "ending_balance": balance,

            "net_profit": round(
                balance - self.initial_balance,
                2
            ),

            "total_trade": len(predictions),

            "win": win,

            "loss": loss,

            "win_rate": round(
                (win / len(predictions)) * 100,
                2
            ),

            "history": history,

            "trades": trade_df

        }