class PerformanceAnalyzer:

    def analyze(self, report: dict) -> dict:
        """
        Analisis hasil trading simulation.
        """

        initial_balance = report["initial_balance"]
        ending_balance = report["ending_balance"]

        net_profit = report["net_profit"]

        total_trade = report["total_trade"]
        winning_trade = report["win"]
        losing_trade = report["loss"]

        win_rate = report["win_rate"]

        history = report["history"]

        # =====================================
        # Return on Investment (ROI)
        # =====================================

        roi = (
            net_profit /
            initial_balance
        ) * 100

        # =====================================
        # Average Profit per Trade
        # =====================================

        average_profit = (
            net_profit / total_trade
            if total_trade > 0 else 0
        )

        # =====================================
        # Profit Factor (versi sederhana)
        # =====================================

        gross_profit = max(net_profit, 0)

        gross_loss = abs(min(net_profit, 0))

        if gross_loss == 0:
            profit_factor = float("inf")
        else:
            profit_factor = gross_profit / gross_loss

        # =====================================
        # Maximum Drawdown
        # =====================================

        peak = history[0]
        max_drawdown = 0

        for balance in history:

            if balance > peak:
                peak = balance

            drawdown = (
                peak - balance
            ) / peak * 100

            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return {

            "initial_balance": initial_balance,

            "ending_balance": ending_balance,

            "net_profit": net_profit,

            "roi": roi,

            "total_trade": total_trade,

            "winning_trade": winning_trade,

            "losing_trade": losing_trade,

            "win_rate": win_rate,

            "average_profit": average_profit,

            "profit_factor": profit_factor,

            "max_drawdown": max_drawdown

        }