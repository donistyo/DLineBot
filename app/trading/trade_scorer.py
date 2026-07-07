class TradeScorer:

    def __init__(self):
        self.weights = {
            "confidence": 0.25,
            "multi_tf": 0.20,
            "regime": 0.15,
            "volatility": 0.10,
            "spread": 0.10,
            "risk_reward": 0.10,
            "position_sizing": 0.10
        }

    def score(
        self,
        prediction=None,
        tf_confirmation=None,
        regime=None,
        market=None,
        risk=None,
        sizing_details=None,
        news=None,
        scalping=None
    ):
        details = {}
        total = 0.0
        bonuses = 0.0

        # =====================================
        # 1. AI Confidence Score (0-100)
        # =====================================
        if prediction:
            conf = prediction.get("confidence", 0)
            conf_score = min(100, conf * 100)
            details["confidence"] = conf_score
            total += conf_score * self.weights["confidence"]

        # =====================================
        # 2. Multi Timeframe Score (0-100)
        # =====================================
        if tf_confirmation:
            alignment = tf_confirmation.get("alignment", 0)
            tf_score = alignment * 100
            details["multi_tf"] = tf_score
            total += tf_score * self.weights["multi_tf"]

        # =====================================
        # 3. Market Regime Score (0-100)
        # =====================================
        if regime:
            mode = regime.get("mode", "RANGING")
            strength = regime.get("strength", "Neutral")
            adx = regime.get("adx", 0)
            if mode == "TREND" and strength == "Strong":
                regime_score = 90
            elif mode == "TREND":
                regime_score = 70
            elif adx >= 20:
                regime_score = 50
            else:
                regime_score = 30
            details["regime"] = regime_score
            total += regime_score * self.weights["regime"]

        # =====================================
        # 4. Volatility Score (0-100)
        # =====================================
        if market is not None:
            try:
                atr = float(market.get("ATR", 0) if hasattr(market, "get") else market["ATR"])
            except Exception:
                atr = 0
            try:
                close = float(market.get("close", 0) if hasattr(market, "get") else market["close"])
            except Exception:
                close = 0
            if close > 0 and atr > 0:
                atr_pct = atr / close * 100
                if 0.2 <= atr_pct <= 0.5:
                    vol_score = 80
                elif 0.1 <= atr_pct <= 0.8:
                    vol_score = 60
                else:
                    vol_score = 40
            else:
                vol_score = 50
            details["volatility"] = vol_score
            total += vol_score * self.weights["volatility"]

        # =====================================
        # 5. Spread Score (0-100)
        # =====================================
        if market is not None:
            try:
                spread = float(market.get("spread", 0) if hasattr(market, "get") else market["spread"])
            except Exception:
                spread = 0
            try:
                atr = float(market.get("ATR", 0) if hasattr(market, "get") else market["ATR"])
            except Exception:
                atr = 0
            if atr > 0 and spread > 0:
                ratio = spread / atr
                if ratio < 0.1:
                    spread_score = 90
                elif ratio < 0.2:
                    spread_score = 75
                elif ratio < 0.3:
                    spread_score = 60
                elif ratio < 0.5:
                    spread_score = 40
                else:
                    spread_score = 20
            else:
                spread_score = 50
            details["spread"] = spread_score
            total += spread_score * self.weights["spread"]

        # =====================================
        # 6. Risk/Reward Score (0-100)
        # =====================================
        rr_bonus = 0
        if risk:
            entry = risk.get("entry_price", 0)
            sl = risk.get("stop_loss", 0)
            tp = risk.get("take_profit", 0)
            if entry > 0 and sl != entry:
                rr = abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0
                if rr >= 3.0:
                    rr_score = 90
                    rr_bonus = 10
                elif rr >= 2.0:
                    rr_score = 75
                    rr_bonus = 7
                elif rr >= 1.5:
                    rr_score = 60
                    rr_bonus = 4
                elif rr >= 1.0:
                    rr_score = 40
                    rr_bonus = 0
                else:
                    rr_score = 20
                    rr_bonus = -5
            else:
                rr_score = 0
            details["risk_reward"] = rr_score
            total += rr_score * self.weights["risk_reward"]

        # =====================================
        # 7. Position Sizing Score (0-100)
        # =====================================
        if sizing_details:
            mults = [
                sizing_details.get("confidence_mult", 1),
                sizing_details.get("regime_mult", 1),
                sizing_details.get("volatility_mult", 1),
                sizing_details.get("spread_penalty", 1)
            ]
            avg_mult = sum(mults) / len(mults)
            size_score = avg_mult / 1.5 * 100
            size_score = min(100, size_score)
            details["position_sizing"] = size_score
            total += size_score * self.weights["position_sizing"]

        # =====================================
        # 8. News Bonus / Penalty
        # =====================================
        news_bonus = 0
        if news is not None:
            impact = news.get("impact", "") if isinstance(news, dict) else ""
            if impact == "High":
                news_bonus = -30
            elif impact == "Medium":
                news_bonus = -15
            elif impact == "Low":
                news_bonus = -5
            else:
                news_bonus = 10
        else:
            news_bonus = 10
        details["news"] = news_bonus
        bonuses += news_bonus

        bonuses += rr_bonus
        details["rr_bonus"] = rr_bonus

        # =====================================
        # 9. Smart Scalping Bonus / Penalty
        # =====================================
        scalp_bonus = 0
        if scalping:
            scalp = scalping.get("scalp_score", {})
            scalp_score = scalp.get("score", 0)
            if scalp_score >= 85:
                scalp_bonus = 10
            elif scalp_score >= 75:
                scalp_bonus = 6
            elif scalp_score >= 65:
                scalp_bonus = 3
            elif scalp_score < 50:
                scalp_bonus = -10

            details["scalping"] = scalp_score
            details["scalp_bonus"] = scalp_bonus
            bonuses += scalp_bonus

        # =====================================
        # Final Score
        # =====================================
        final_score = round(total, 1)
        max_possible = sum(self.weights[k] * 100 for k in self.weights)
        normalized = round(final_score / max_possible * 100, 1) if max_possible > 0 else 0
        normalized = max(0, min(100, normalized + bonuses))

        # =====================================
        # Grade
        # =====================================
        if normalized >= 80:
            grade = "A"
        elif normalized >= 65:
            grade = "B"
        elif normalized >= 50:
            grade = "C"
        elif normalized >= 35:
            grade = "D"
        else:
            grade = "F"

        return {
            "score": normalized,
            "grade": grade,
            "raw": round(total, 1),
            "details": details,
            "bonuses": {
                "rr_bonus": rr_bonus,
                "news": news_bonus,
                "scalping": scalp_bonus
            },
            "action": "TRADE" if normalized >= 50 else "SKIP"
        }
