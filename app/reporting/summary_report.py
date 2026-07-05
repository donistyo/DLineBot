class SummaryReport:

    def create(self, report):

        return {

            "initial_balance": report["initial_balance"],
            "ending_balance": report["ending_balance"],
            "net_profit": report["net_profit"],
            "total_trade": report["total_trade"],
            "winning_trade": report["win"],
            "losing_trade": report["loss"],
            "win_rate": round(report["win_rate"], 2)

        }