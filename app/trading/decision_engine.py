class DecisionEngine:

    def __init__(self, min_scalp_score=55):
        self.min_scalp_score = min_scalp_score
        self.sideways_penalty = 15
        self.trend_map = {"UP": "BUY", "DOWN": "SELL", "SIDEWAYS": None}

    def decide(self, prediction=None, scalp_result=None, regime=None, higher_trend=None) -> dict:
        if scalp_result is None or regime is None:
            return {"action": "NO_TRADE", "reason": "Data tidak tersedia", "confidence": 0}

        score_data = scalp_result.get("scalp_score", {})
        score = score_data.get("score", 0)
        direction = score_data.get("direction", "NEUTRAL")
        grade = score_data.get("grade", "D")

        # =====================================
        # Satu sumber kebenaran kekuatan trend.
        # Dipakai bersama oleh Liquidity guard,
        # EMA50 guard, dan Rebound guard di
        # bawah (bukan re-implementasi terpisah).
        # Definisi: mode TREND + ADX M5 >= 30 +
        # trend searah sinyal.
        # =====================================
        trend = regime.get("trend", "SIDEWAYS") if regime else "SIDEWAYS"
        mode = regime.get("mode", "RANGING") if regime else "RANGING"
        adx = regime.get("adx", 0) if regime else 0
        expected_dir = self.trend_map.get(trend)
        strong_trend = (mode == "TREND" and adx >= 30
                        and expected_dir == direction)

        if score < self.min_scalp_score:
            return {
                "action": "NO_TRADE",
                "reason": f"Scalp score terlalu rendah ({score}/100, {grade})",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        if direction in ("NEUTRAL", "WAIT"):
            return {
                "action": "NO_TRADE",
                "reason": f"Scalp arah netral ({score}/100, {grade})",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        momentum = {}
        if scalp_result:
            momentum = scalp_result.get("momentum", {}) or {}
            if not momentum and isinstance(scalp_result.get("scalp_score"), dict):
                momentum = scalp_result["scalp_score"].get("details", {}) or {}

        last_body = momentum.get("last_body", "NEUT")
        accel = momentum.get("acceleration", 0)
        accel_opposing = (
            (direction == "BUY" and last_body == "SELL" and accel < 0
             and abs(accel) >= 0.5) or
            (direction == "SELL" and last_body == "BUY" and accel > 0
             and accel >= 0.5)
        )
        if accel_opposing:
            return {
                "action": "NO_TRADE",
                "reason": f"Momentum candle terakhir melawan ({last_body}, akselerasi {accel:.2f}) - rawan gerakan tajam",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        # =====================================
        # Wick rejection: blokir entry saat candle terakhir
        # rejection (wick panjang di sisi arah entry = kejar puncak/lembah)
        # =====================================
        liquidity = {}
        if scalp_result:
            liquidity = scalp_result.get("liquidity", {}) or {}
        body = float(liquidity.get("body", 0) or 0)
        upper_wick = float(liquidity.get("upper_wick", 0) or 0)
        lower_wick = float(liquidity.get("lower_wick", 0) or 0)

        wick_mult = 2.0
        try:
            from app.config.settings import load_trade_config, get_trade_config
            wick_mult = float(get_trade_config("wick_reject_mult", 2.0))
        except Exception:
            pass

        if body > 0:
            if direction == "BUY" and upper_wick >= wick_mult * body:
                return {
                    "action": "NO_TRADE",
                    "reason": f"Wick atas {upper_wick:.2f} >= {wick_mult:.0f}x body {body:.2f} - candle rejection atas, rawan kejar puncak",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }
            if direction == "SELL" and lower_wick >= wick_mult * body:
                return {
                    "action": "NO_TRADE",
                    "reason": f"Wick bawah {lower_wick:.2f} >= {wick_mult:.0f}x body {body:.2f} - candle rejection bawah, rawan kejar lembah",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }

        # =====================================
        # Extension guard: harga sudah jauh/extended dari range terbaru
        # -> jangan entry mengejar gerakan yang sudah terlalu jauh.
        # ADAPTIF: hanya aktif saat trend LEMAH (strong_trend False).
        # Saat trend kuat, breakout dari range adalah continuation valid.
        # =====================================
        if direction == "BUY" and liquidity.get("extended_up") and not strong_trend:
            return {
                "action": "NO_TRADE",
                "reason": "Harga extended di atas range M5 terbaru - jangan kejar puncak",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }
        if direction == "SELL" and liquidity.get("extended_down") and not strong_trend:
            return {
                "action": "NO_TRADE",
                "reason": "Harga extended di bawah range M5 terbaru - jangan kejar lembah",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        # =====================================
        # Exhaustion guard: kalau harga sudah
        # jauh/extended dari EMA50 di arah yang
        # sama dengan sinyal -> jangan kejar.
        # Mencegah entry tepat di dasar/puncak.
        # ADAPTIF: hanya aktif saat trend LEMAH.
        # Saat trend kuat harga wajar extended ->
        # izinkan (continuation, bukan kejar).
        # Memakai flag strong_trend tunggal di atas.
        # =====================================
        try:
            _ema_ref = float(scalp_result.get("close", 0) or 0)
            ema50 = None
            if scalp_result and scalp_result.get("ema50"):
                ema50 = float(scalp_result["ema50"])
            else:
                ema50 = None
            if ema50 and ema50 > 0 and _ema_ref > 0:
                _last_atr = 0
                try:
                    if scalp_result and scalp_result.get("atr"):
                        _last_atr = float(scalp_result["atr"])
                    elif scalp_result and scalp_result.get("liquidity"):
                        _last_atr = float(scalp_result["liquidity"].get("atr", 0) or 0)
                except Exception:
                    _last_atr = 0
                if _last_atr <= 0:
                    _last_atr = 2.5
                dist_atr = abs(_ema_ref - ema50) / max(_last_atr, 0.01)
                if not strong_trend:
                    if direction == "BUY" and dist_atr >= 1.2:
                        return {
                            "action": "NO_TRADE",
                            "reason": f"Buy extended {dist_atr:.1f}xATR dari EMA50 - rawan kejar puncak",
                            "confidence": score / 100, "score": score, "grade": grade
                        }
                    if direction == "SELL" and dist_atr >= 1.2:
                        return {
                            "action": "NO_TRADE",
                            "reason": f"Sell extended {dist_atr:.1f}xATR dari EMA50 - rawan kejar lembah",
                            "confidence": score / 100, "score": score, "grade": grade
                        }
        except Exception:
            pass

        # =====================================
        # Rebound guard: tolak entry dekat tepi
        # range 20 candle M5 (SELL di dekat low =
        # jual di dasar jelang rebound, BUY di
        # dekat high = beli di puncak jelang koreksi).
        # ADAPTIF: hanya aktif saat trend LEMAH.
        # Saat trend kuat, dekat tepi range adalah
        # breakout valid (pakai flag strong_trend
        # tunggal yang sama dengan guard lain).
        # =====================================
        try:
            _r_close = float(scalp_result.get("close", 0) or 0)
            _r_high = float(scalp_result.get("range_high", 0) or 0)
            _r_low = float(scalp_result.get("range_low", 0) or 0)
            _r_atr = float(scalp_result.get("atr", 0) or 0)
            if _r_close > 0 and _r_low > 0 and _r_atr > 0:
                if direction == "SELL" and _r_close <= _r_low + _r_atr and not strong_trend:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Sell di dekat low range ({_r_close:.2f} <= low {_r_low:.2f} + {_r_atr:.2f} ATR) - rawan rebound naik",
                        "confidence": score / 100, "score": score, "grade": grade
                    }
            if _r_close > 0 and _r_high > 0 and _r_atr > 0:
                if direction == "BUY" and _r_close >= _r_high - _r_atr and not strong_trend:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Buy di dekat high range ({_r_close:.2f} >= high {_r_high:.2f} - {_r_atr:.2f} ATR) - rawan koreksi turun",
                        "confidence": score / 100, "score": score, "grade": grade
                    }
        except Exception:
            pass

        # =====================================
        # M1 momentum wajib searah sinyal:
        # jika candle M1 terakhir masih melawan
        # arah, jangan entry (hindari melawan
        # gerakan intraday yang baru terbentuk)
        # =====================================
        try:
            m1 = (scalp_result or {}).get("m1_momentum") or {}
            m1_dir = m1.get("direction")
            if m1_dir in ("BUY", "SELL") and m1_dir != direction:
                return {
                    "action": "NO_TRADE",
                    "reason": f"M1 momentum {m1_dir} melawan sinyal {direction} - tunggu konfirmasi searah",
                    "confidence": score / 100, "score": score, "grade": grade
                }
        except Exception:
            pass

        if prediction:
            ai_signal = prediction.get("signal", "WAIT")
            ai_conf = prediction.get("confidence", 0)
            if ai_conf > 1:
                ai_conf = ai_conf / 100.0
            # AI hanya konfirmasi trend: blokir hanya jika AI SEARAH
            # dengan arah trend M5/M15 (higher_trend). Jika AI melawan
            # trend M5/M15 (mis. AI BUY saat M5/M15 DOWN), AI dianggap
            # salah/tidak valid -> jangan blokir entry yang searah trend.
            ai_aligned_trend = (higher_trend in ("BUY", "SELL")) and (ai_signal == higher_trend)
            if ai_aligned_trend and ai_conf >= 0.55 and direction != ai_signal:
                return {
                    "action": "NO_TRADE",
                    "reason": f"Scalp {direction} vs AI {ai_signal} ({ai_conf:.0%}) - berlawanan arah",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }

        if expected_dir is None:
            if score < self.min_scalp_score + self.sideways_penalty:
                return {
                    "action": "NO_TRADE",
                    "reason": f"Trend SIDEWAYS, butuh skor >= {self.min_scalp_score + self.sideways_penalty} (dapat {score}/100 {grade})",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }

        if expected_dir and direction != expected_dir:
            return {
                "action": "NO_TRADE",
                "reason": f"Scalp {direction} tidak searah trend {trend} - tunggu sinyal stabil",
                "confidence": score / 100,
                "score": score,
                "grade": grade
            }

        return {
            "action": direction,
            "reason": f"Scalp {grade} ({score}/100) searah trend {trend}",
            "confidence": score / 100,
            "score": score,
            "grade": grade
        }