class RiskManager:

    def __init__(
        self,
        risk_percent=2,
        stop_loss_points=10,
        risk_reward_ratio=2
    ):
        self.risk_percent = risk_percent
        self.stop_loss_points = stop_loss_points
        self.risk_reward_ratio = risk_reward_ratio

    def calculate(
        self,
        prediction,
        current_price,
        balance
    ):
        risk_amount = balance * self.risk_percent / 100

        signal = prediction["signal"]

        if signal == "BUY":
            stop_loss = current_price - self.stop_loss_points
            take_profit = current_price + (
                self.stop_loss_points * self.risk_reward_ratio
            )
        else:
            stop_loss = current_price + self.stop_loss_points
            take_profit = current_price - (
                self.stop_loss_points * self.risk_reward_ratio
            )

        return {
            "entry_price": current_price,
            "lot_size": round(risk_amount / 10, 2),
            "risk_amount": risk_amount,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }