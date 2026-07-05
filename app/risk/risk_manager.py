class RiskManager:

    def __init__(
        self,
        risk_percent: float = 2.0,
        reward_ratio: float = 2.0,
        stop_loss_points: float = 10.0
    ):
        self.risk_percent = risk_percent
        self.reward_ratio = reward_ratio
        self.stop_loss_points = stop_loss_points

    def calculate(
        self,
        prediction: dict,
        current_price: float,
        balance: float
    ) -> dict:

        risk_amount = balance * (self.risk_percent / 100)

        lot_size = round(
            risk_amount / self.stop_loss_points,
            2
        )

        signal = prediction["signal"]

        if signal == "BUY":

            stop_loss = current_price - self.stop_loss_points

            take_profit = (
                current_price +
                (self.stop_loss_points * self.reward_ratio)
            )

        elif signal == "SELL":

            stop_loss = current_price + self.stop_loss_points

            take_profit = (
                current_price -
                (self.stop_loss_points * self.reward_ratio)
            )

        else:

            stop_loss = current_price
            take_profit = current_price

        return {
            "entry_price": current_price,
            "lot_size": lot_size,
            "risk_amount": risk_amount,
            "stop_loss": stop_loss,
            "take_profit": take_profit
        }