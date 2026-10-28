import pandas as pd


class Backtester:
    """
    Simulasi trade berbasis harga: tiap sinyal BUY/SELL dieksekusi di close bar,
    lalu bar berikutnya dicek mana yang kena duluan: SL, TP, atau batas waktu.
    SL & TP = sl_atr/tp_atr x ATR (harus sama dengan LabelGenerator triple-barrier).
    Satu posisi sekali waktu, sinyal HOLD dilewati, spread dikurangkan.
    Profit = R-multiple x (risk_percent x balance).
    """

    def __init__(
        self,
        initial_balance=1000,
        risk_percent=1.0,
        tp_atr=2.0,
        sl_atr=1.0,
        max_bars=30,
        min_confidence=0.5,
        point=0.001,  # XAUUSDc Exness: symbol_info().point = 0.001
        symbol="XAUUSD",
        timeframe="M1"
    ):
        self.initial_balance = initial_balance
        self.risk_percent = risk_percent
        self.tp_atr = tp_atr
        self.sl_atr = sl_atr
        self.max_bars = max_bars
        self.min_confidence = min_confidence
        self.point = point
        self.symbol = symbol
        self.timeframe = timeframe

    def run(
        self,
        model,
        X_test,
        y_test,
        df_test
    ):

        predictions = model.predict(X_test)
        probabilities = model.predict_proba(X_test)

        signal_map = {0: "SELL", 1: "HOLD", 2: "BUY"}

        df_test = df_test.reset_index(drop=True)
        n = len(df_test)

        balance = self.initial_balance
        history = [balance]
        trades = []
        gross_profit = 0.0
        gross_loss = 0.0

        i = 0

        # sinyal tanpa max_bars bar sesudahnya tidak bisa diselesaikan
        while i < n - self.max_bars:

            pred = int(predictions[i])
            confidence = float(probabilities[i].max())

            if pred == 1 or confidence < self.min_confidence:
                i += 1
                continue

            signal = signal_map[pred]
            row = df_test.iloc[i]
            entry = float(row["close"])
            atr = float(row["ATR"])

            if not atr > 0:
                i += 1
                continue

            sl_dist = self.sl_atr * atr
            tp_dist = self.tp_atr * atr
            direction = 1 if signal == "BUY" else -1
            stop_loss = entry - direction * sl_dist
            take_profit = entry + direction * tp_dist

            exit_idx = i + self.max_bars
            exit_price = float(df_test.iloc[exit_idx]["close"])
            reason = "TIME"

            for j in range(i + 1, i + self.max_bars + 1):
                hi = float(df_test.iloc[j]["high"])
                lo = float(df_test.iloc[j]["low"])

                hit_sl = lo <= stop_loss if direction == 1 else hi >= stop_loss
                hit_tp = hi >= take_profit if direction == 1 else lo <= take_profit

                # SL dan TP di bar yang sama: SL dianggap duluan (konservatif)
                if hit_sl:
                    exit_price, exit_idx, reason = stop_loss, j, "SL"
                    break
                if hit_tp:
                    exit_price, exit_idx, reason = take_profit, j, "TP"
                    break

            spread_cost = float(row["spread"]) * self.point
            pnl_price = direction * (exit_price - entry) - spread_cost
            profit = (pnl_price / sl_dist) * balance * self.risk_percent / 100

            balance += profit
            history.append(balance)

            if profit > 0:
                gross_profit += profit
            else:
                gross_loss += -profit

            trades.append({
                "trade": len(trades) + 1,
                "time": str(row["time"]),
                "exit_time": str(df_test.iloc[exit_idx]["time"]),
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "signal": signal,
                "prediction": pred,
                "actual": int(y_test.iloc[i]),
                "confidence": round(confidence, 4),
                "sell_probability": round(float(probabilities[i][0]), 4),
                "hold_probability": round(float(probabilities[i][1]), 4),
                "buy_probability": round(float(probabilities[i][2]), 4),
                "entry_price": round(entry, 2),
                "stop_loss": round(stop_loss, 2),
                "take_profit": round(take_profit, 2),
                "exit_price": round(exit_price, 2),
                "exit_reason": reason,
                "bars_held": exit_idx - i,
                "spread_cost": round(spread_cost, 4),
                "profit": round(profit, 2),
                "balance": round(balance, 2),
                "result": "WIN" if profit > 0 else "LOSS",
                "ema20": round(float(row["EMA20"]), 2),
                "ema50": round(float(row["EMA50"]), 2),
                "ema200": round(float(row["EMA200"]), 2),
                "rsi": round(float(row["RSI"]), 2),
                "macd": round(float(row["MACD"]), 4),
                "adx": round(float(row["ADX"]), 2),
                "atr": round(atr, 2),
                "spread": int(row["spread"]),
                "volume": int(row["tick_volume"])
            })

            i = exit_idx + 1  # satu posisi sekali waktu

        win = sum(t["result"] == "WIN" for t in trades)

        return {
            "initial_balance": self.initial_balance,
            "ending_balance": balance,
            "net_profit": round(balance - self.initial_balance, 2),
            "total_trade": len(trades),
            "win": win,
            "loss": len(trades) - win,
            "win_rate": round(win / len(trades) * 100, 2) if trades else 0.0,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "history": history,
            "trades": pd.DataFrame(trades)
        }
