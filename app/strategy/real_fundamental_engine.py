import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf
import urllib.request

logger = logging.getLogger(__name__)


class RealFundamentalEngine:

    def __init__(self, cache_minutes=15):
        self.cache_minutes = cache_minutes
        self._cache = None
        self._cache_time = None

    # =====================================
    # Public API (sama seperti DailyTrendEngine)
    # =====================================

    def analyze(self):
        now = datetime.now()
        if self._cache and self._cache_time:
            if (now - self._cache_time) < timedelta(minutes=self.cache_minutes):
                return self._cache

        result = self._fetch_and_analyze()
        self._cache = result
        self._cache_time = now
        return result

    def get(self):
        return self.analyze()

    def update(self, bias=None, confidence=None, score=None, reasons=None):
        pass

    @property
    def bias_multiplier(self):
        data = self.analyze()
        bias = data.get("bias", "NEUTRAL")
        if bias in ("STRONG BULLISH", "BULLISH"):
            return 1.3
        elif bias in ("STRONG BEARISH", "BEARISH"):
            return 1.3
        return 1.0

    @property
    def trend_bias(self):
        return self.analyze().get("bias", "NEUTRAL")

    # =====================================
    # Fetch & Analyze
    # =====================================

    def _fetch_and_analyze(self):
        reasons = []
        score = 0
        confidence = 0
        bullish_signals = 0
        bearish_signals = 0
        total_signals = 0

        # --- DXY ---
        dxy = self._fetch_dxy()
        if dxy is not None:
            total_signals += 1
            change_pct = dxy.get("change_pct", 0)
            direction = dxy.get("direction", "neutral")
            price = dxy.get("price", 0)
            prev_close = dxy.get("prev_close", price)
            points = price - prev_close

            if direction == "down":
                bullish_signals += 1
                reasons.append(f"DXY turun {abs(points):.2f} pts ({abs(change_pct):.2f}%) -> Bullish XAU")
            elif direction == "up":
                bearish_signals += 1
                reasons.append(f"DXY naik {points:.2f} pts ({change_pct:.2f}%) -> Bearish XAU")
            else:
                reasons.append(f"DXY stabil ({price:.2f})")

        # --- US10Y Yield ---
        yield_data = self._fetch_us10y()
        if yield_data is not None:
            total_signals += 1
            price = yield_data.get("price", 0)
            change_pct = yield_data.get("change_pct", 0)
            direction = yield_data.get("direction", "neutral")
            prev_close = yield_data.get("prev_close", price)
            points = price - prev_close

            if direction == "down":
                bullish_signals += 1
                reasons.append(f"US10Y Yield turun {abs(points):.2f}% ({abs(change_pct):.2f}%) -> Bullish XAU")
            elif direction == "up":
                bearish_signals += 1
                reasons.append(f"US10Y Yield naik {points:.2f}% ({change_pct:.2f}%) -> Bearish XAU")
            else:
                reasons.append(f"US10Y Yield stabil ({price:.3f}%)")

        # --- Economic Calendar (High Impact) ---
        news_events = self._fetch_forex_factory()
        high_impact_today = [e for e in news_events if e.get("impact") == "High"]
        for event in high_impact_today:
            total_signals += 1
            sentiment = self._interpret_news(event)
            if sentiment == "bullish":
                bullish_signals += 1
                reasons.append(f"{event.get('currency','USD')} {event.get('event','')}: Bullish")
            elif sentiment == "bearish":
                bearish_signals += 1
                reasons.append(f"{event.get('currency','USD')} {event.get('event','')}: Bearish")
            else:
                reasons.append(f"{event.get('currency','USD')} {event.get('event','')}: Netral")

        # --- Determine Bias ---
        if total_signals == 0:
            bias = "NEUTRAL"
            confidence = 0
            score = 0
        else:
            bullish_pct = bullish_signals / total_signals * 100
            bearish_pct = bearish_signals / total_signals * 100

            if bullish_pct >= 70:
                bias = "STRONG BULLISH"
                confidence = min(100, int(bullish_pct))
                score = min(10, max(1, round(bullish_signals * 2.5)))
            elif bullish_pct >= 50:
                bias = "BULLISH"
                confidence = min(90, int(bullish_pct))
                score = min(8, max(1, round(bullish_signals * 2)))
            elif bearish_pct >= 70:
                bias = "STRONG BEARISH"
                confidence = min(100, int(bearish_pct))
                score = min(10, max(1, round(bearish_signals * 2.5)))
            elif bearish_pct >= 50:
                bias = "BEARISH"
                confidence = min(90, int(bearish_pct))
                score = min(8, max(1, round(bearish_signals * 2)))
            else:
                bias = "NEUTRAL"
                confidence = 50
                score = max(1, round(total_signals))

        return {
            "bias": bias,
            "confidence": confidence,
            "score": score,
            "reasons": reasons,
        }

    # =====================================
    # DXY via Yahoo Finance
    # =====================================

    def _fetch_dxy(self):
        try:
            ticker = yf.Ticker("DX-Y.NYB")
            hist = ticker.history(period="5d")
            if hist.empty:
                return None
            last = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else last
            price = round(float(last["Close"]), 3)
            prev_close = round(float(prev["Close"]), 3)
            change = price - prev_close
            change_pct = round(change / prev_close * 100, 2)
            direction = "up" if change > 0 else ("down" if change < 0 else "neutral")
            return {
                "price": price,
                "prev_close": prev_close,
                "change": round(change, 3),
                "change_pct": change_pct,
                "direction": direction,
            }
        except Exception as e:
            logger.warning(f"DXY fetch error: {e}")
            return None

    # =====================================
    # US10Y Yield via Yahoo Finance
    # =====================================

    def _fetch_us10y(self):
        try:
            ticker = yf.Ticker("^TNX")
            hist = ticker.history(period="5d")
            if hist.empty:
                return None
            last = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else last
            price = round(float(last["Close"]), 3)
            prev_close = round(float(prev["Close"]), 3)
            change = price - prev_close
            change_pct = round(change / prev_close * 100, 2)
            direction = "up" if change > 0 else ("down" if change < 0 else "neutral")
            return {
                "price": price,
                "prev_close": prev_close,
                "change": round(change, 3),
                "change_pct": change_pct,
                "direction": direction,
            }
        except Exception as e:
            logger.warning(f"US10Y fetch error: {e}")
            return None

    # =====================================
    # ForexFactory Economic Calendar
    # =====================================

    def _fetch_forex_factory(self):
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            events = []
            today = datetime.now().strftime("%Y-%m-%d")
            for item in data:
                if item.get("date") == today:
                    impact = (item.get("impact") or "").strip()
                    country = (item.get("country") or "").strip()
                    event_name = (item.get("title") or item.get("event") or "").strip()
                    actual = item.get("actual")
                    forecast = item.get("forecast")
                    previous = item.get("previous")

                    impact_map = {
                        "High": "High",
                        "Medium": "Medium",
                        "Low": "Low",
                        "Non": "Low",
                        "Holiday": "Low",
                    }
                    mapped_impact = impact_map.get(impact, "Low")

                    events.append({
                        "currency": country,
                        "event": event_name,
                        "impact": mapped_impact,
                        "time": item.get("time", ""),
                        "actual": actual,
                        "forecast": forecast,
                        "previous": previous,
                    })
            return events
        except Exception as e:
            logger.warning(f"ForexFactory fetch error: {e}")
            return []

    # =====================================
    # News Interpretation
    # =====================================

    def _interpret_news(self, event):
        try:
            actual = event.get("actual")
            forecast = event.get("forecast")
            previous = event.get("previous")
            currency = event.get("currency", "USD")
            evt = (event.get("event") or "").lower()

            if actual is None and forecast is None:
                return "neutral"

            actual_f = float(actual) if actual not in (None, "") else None
            forecast_f = float(forecast) if forecast not in (None, "") else None
            previous_f = float(previous) if previous not in (None, "") else None

            if actual_f is None:
                return "neutral"

            # CPI / Inflation related
            if any(w in evt for w in ["cpi", "inflation", "ppi", "m2"]):
                if actual_f > (forecast_f or actual_f):
                    return "bearish" if currency == "USD" else "bullish"
                elif actual_f < (forecast_f or actual_f):
                    return "bullish" if currency == "USD" else "bearish"

            # Employment (NFP, unemployment)
            if any(w in evt for w in ["nonfarm", "employment", "unemployment", "jobless", "payrolls"]):
                if actual_f > (forecast_f or actual_f):
                    return "bearish" if currency == "USD" else "bullish"
                elif actual_f < (forecast_f or actual_f):
                    return "bullish" if currency == "USD" else "bearish"

            # GDP
            if "gdp" in evt:
                if actual_f > (forecast_f or actual_f):
                    return "bearish" if currency == "USD" else "bullish"
                elif actual_f < (forecast_f or actual_f):
                    return "bullish" if currency == "USD" else "bearish"

            # Retail Sales / Consumer
            if any(w in evt for w in ["retail", "consumer", "spending"]):
                if actual_f > (forecast_f or actual_f):
                    return "bearish" if currency == "USD" else "bullish"
                elif actual_f < (forecast_f or actual_f):
                    return "bullish" if currency == "USD" else "bearish"

            # Interest Rate Decision
            if any(w in evt for w in ["interest rate", "rate decision", "fed", "monetary"]):
                if actual_f > (forecast_f or actual_f):
                    return "bearish" if currency == "USD" else "bullish"
                elif actual_f < (forecast_f or actual_f):
                    return "bullish" if currency == "USD" else "bearish"

            # Manufacturing / Industrial
            if any(w in evt for w in ["manufacturing", "industrial", "durable", "factory"]):
                if actual_f > (forecast_f or actual_f):
                    return "neutral"

            # Trade Balance
            if any(w in evt for w in ["trade", "import", "export"]):
                if actual_f > (forecast_f or actual_f):
                    return "bearish" if currency == "USD" else "bullish"
                elif actual_f < (forecast_f or actual_f):
                    return "bullish" if currency == "USD" else "bearish"

            # Housing
            if any(w in evt for w in ["housing", "home", "building", "mortgage"]):
                if actual_f > (forecast_f or actual_f):
                    return "bearish" if currency == "USD" else "bullish"
                elif actual_f < (forecast_f or actual_f):
                    return "bullish" if currency == "USD" else "bearish"

            # Default: stronger data = bearish for XAU (hawkish USD)
            if actual_f > (forecast_f or previous_f or actual_f):
                return "bearish" if currency == "USD" else "bullish"
            elif actual_f < (forecast_f or previous_f or actual_f):
                return "bullish" if currency == "USD" else "bearish"

        except (ValueError, TypeError) as e:
            logger.debug(f"News interpret error: {e}")

        return "neutral"
