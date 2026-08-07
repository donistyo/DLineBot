class PositionSizingAI:

    def __init__(
        self,
        risk_percent=2.0,
        atr_sl_multiplier=2.5,
        min_confidence=0.50,
        max_spread_ratio=0.5,
        rr_ratio=2.0,
        lot_step=0.01
    ):
        self.risk_percent = risk_percent
        self.atr_sl_multiplier = atr_sl_multiplier
        self.min_confidence = min_confidence
        self.max_spread_ratio = max_spread_ratio
        self.rr_ratio = rr_ratio
        self.lot_step = lot_step

    def calculate(
        self,
        prediction,
        market,
        balance,
        regime=None
    ):
        signal = prediction["signal"]
        confidence = prediction["confidence"]
        current_price = market["close"]
        atr = market.get("ATR", 0)
        spread = market.get("spread", 0)

        # =====================================
        # 1. Base Risk Amount
        # =====================================
        risk_amount = balance * self.risk_percent / 100

        # =====================================
        # 2. Stop Loss — ATR-based
        # =====================================
        sl_points = max(atr * self.atr_sl_multiplier, spread * 2)
        if self.rr_ratio <= 2.0 and sl_points > 20:
            sl_points = max(5, atr * self.atr_sl_multiplier)
        sl_points = round(sl_points, 1)

        if signal == "BUY":
            stop_loss = current_price - sl_points
            take_profit = current_price + (sl_points * self.rr_ratio)
        else:
            stop_loss = current_price + sl_points
            take_profit = current_price - (sl_points * self.rr_ratio)

        # =====================================
        # 3. Confidence Multiplier (0.5 ~ 1.5)
        # =====================================
        conf_mult = 0.5 + (confidence - self.min_confidence) / (1 - self.min_confidence) * 1.0
        conf_mult = max(0.5, min(1.5, conf_mult))

        # =====================================
        # 4. Market Regime Multiplier
        # =====================================
        if regime:
            mode = regime.get("mode", "RANGING")
            strength = regime.get("strength", "Neutral")
            if mode == "TREND" and strength == "Strong":
                regime_mult = 1.2
            elif mode == "TREND":
                regime_mult = 1.0
            else:
                regime_mult = 0.6
        else:
            regime_mult = 1.0

        # =====================================
        # 5. Volatility Multiplier
        # =====================================
        if atr > 0 and current_price > 0:
            atr_pct = atr / current_price * 100
            if atr_pct > 1.0:
                vol_mult = 0.5
            elif atr_pct > 0.5:
                vol_mult = 0.75
            elif atr_pct > 0.2:
                vol_mult = 1.0
            else:
                vol_mult = 1.2
        else:
            vol_mult = 1.0

        # =====================================
        # 6. Spread Penalty
        # =====================================
        if atr > 0 and spread > 0:
            spread_ratio = spread / atr
            if spread_ratio > self.max_spread_ratio:
                return {
                    "entry_price": current_price,
                    "lot_size": 0,
                    "risk_amount": 0,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "sl_points": sl_points,
                    "reason": f"Spread terlalu tinggi ({spread_ratio:.1f}x ATR)",
                    "position_size": 0
                }
            spread_penalty = max(0.5, 1 - (spread_ratio / self.max_spread_ratio) * 0.5)
        else:
            spread_penalty = 1.0

        # =====================================
        # 7. Final Lot Size
        # =====================================
        adjusted_risk = (
            risk_amount
            * conf_mult
            * regime_mult
            * vol_mult
            * spread_penalty
        )

        if sl_points <= 0:
            lot_size = 0
        else:
            raw_lot = adjusted_risk / (sl_points * 10)
            lot_size = round(raw_lot / self.lot_step) * self.lot_step
            lot_size = max(self.lot_step, lot_size)

        return {
            "entry_price": current_price,
            "lot_size": lot_size,
            "risk_amount": round(adjusted_risk, 2),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "sl_points": sl_points,
            "confidence_mult": round(conf_mult, 2),
            "regime_mult": round(regime_mult, 2),
            "volatility_mult": round(vol_mult, 2),
            "spread_penalty": round(spread_penalty, 2),
            "position_size": lot_size,
            "reason": "AI Position Sizing"
        }
