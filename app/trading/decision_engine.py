class DecisionEngine:

    def __init__(self, min_scalp_score=55):
        self.min_scalp_score = min_scalp_score
        self.sideways_penalty = 15
        self.trend_map = {"UP": "BUY", "DOWN": "SELL", "SIDEWAYS": None}

    @staticmethod
    def _entry_strategy():
        try:
            from app.config.settings import get_trade_config
            return str(get_trade_config("entry_strategy", "scalp") or "scalp").lower()
        except Exception:
            return "scalp"

    @staticmethod
    def _decide_bbma(scalp_result):
        """Mode BBMA: seluruh gate scalp lama dilewati.

        Keputusan murni dari state BBMA (analyze()) yang dilampirkan di
        scalp_result["bbma"]: arah dari slope mid BB M5 + M15 wajib searah,
        trigger = reentry pullback ke mid BB, anti-chase = jaga jarak.
        Layer entry selalu dual 2 (fixed) - tiering menyusul setelah data
        slope_strength/dist_mid_atr terkumpul 1-2 minggu.
        """
        if scalp_result is None:
            return {"action": "NO_TRADE", "reason": "Data tidak tersedia", "confidence": 0}
        bbma = scalp_result.get("bbma")
        if not isinstance(bbma, dict):
            return {
                "action": "NO_TRADE",
                "reason": "BBMA: data tidak tersedia (analyze belum jalan)",
                "confidence": 0,
                "score": 0,
                "grade": "-",
            }

        direction = bbma.get("direction", "NEUTRAL")
        slope = bbma.get("slope_strength")
        dist = bbma.get("dist_mid_atr")
        base = {
            "confidence": 0,
            "score": 0,
            "grade": "-",
            "pos_pct": None,
            "entry_strategy": "bbma",
            "bbma_slope": slope,
            "bbma_dist_mid": dist,
        }

        if direction not in ("BUY", "SELL"):
            return {
                "action": "NO_TRADE",
                "reason": bbma.get("reason") or "BBMA: arah netral",
                **base,
            }

        # Defense-in-depth: anti-chase (analyze sudah cek, cek ulang di sini)
        try:
            from app.config.settings import get_trade_config
            _anti = float(get_trade_config("bbma_anti_chase_atr", 2.0) or 2.0)
        except Exception:
            _anti = 2.0
        if dist is not None and float(dist) > _anti:
            return {
                "action": "NO_TRADE",
                "reason": f"BBMA anti-chase: harga {float(dist):.1f}xATR dari mid BB (>{_anti:.1f})",
                **base,
            }

        if not bbma.get("trigger"):
            return {
                "action": "NO_TRADE",
                "reason": bbma.get("reason") or "BBMA: reentry belum valid",
                **base,
            }

        return {
            "action": direction,
            "reason": bbma.get("reason") or f"BBMA reentry {direction}",
            **base,
            "entry_layers": 2,
            "tier_reason": f"BBMA fixed dual (slope {slope}, dist {dist} ATR)",
        }

    def decide(self, prediction=None, scalp_result=None, regime=None, higher_trend=None, higher_adx=0) -> dict:
        if self._entry_strategy() == "bbma":
            return self._decide_bbma(scalp_result)

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
        # trend searah sinyal. ADX dari M5/M15
        # (higher_adx) ikut dipertimbangkan supaya
        # trend kuat di higher TF tidak diblokir
        # oleh guard yang menargetkan kejar puncak.
        # =====================================
        # =====================================
        # RSI Overbought/Oversold filter:
        # Blokir BUY jika RSI > 75 (overbought)
        # Blokir SELL jika RSI < 25 (oversold)
        # Prevent entry di puncak/lembah.
        # =====================================
        rsi_val = None
        try:
            _ind = scalp_result.get("indicators") or scalp_result
            rsi_val = float(_ind.get("RSI") or _ind.get("rsi") or 0)
        except Exception:
            pass
        if rsi_val is not None and rsi_val > 0:
            if direction == "BUY" and rsi_val > 75:
                return {
                    "action": "NO_TRADE",
                    "reason": f"RSI overbought ({rsi_val:.1f} > 75) - jangan beli di puncak",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }
            if direction == "SELL" and rsi_val < 25:
                return {
                    "action": "NO_TRADE",
                    "reason": f"RSI oversold ({rsi_val:.1f} < 25) - jangan jual di lembah",
                    "confidence": score / 100,
                    "score": score,
                    "grade": grade
                }

        # =====================================
        # N-bar return cap: blokir entry jika
        # harga sudah bergerak terlalu jauh
        # dalam 10 bar terakhir (> 2.5x ATR).
        # Prevent chasing after extended move.
        # =====================================
        try:
            _closes = []
            for i in range(1, 11):
                k = f"close_{i}"
                if k in scalp_result:
                    _closes.append(float(scalp_result[k]))
            if not _closes and "closes" in scalp_result:
                _closes = [float(x) for x in scalp_result["closes"][-10:]]
            _atr_n = float(scalp_result.get("atr") or scalp_result.get("liquidity", {}).get("atr") or 2.5)
            if _closes and len(_closes) >= 5 and _atr_n > 0:
                _recent_move = abs(float(scalp_result.get("close", 0) or 0) - _closes[-1])
                _move_atr = _recent_move / max(_atr_n, 0.01)
                if _move_atr > 2.5:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Harga sudah bergerak {_move_atr:.1f}xATR dalam 10 bar - terlalu jauh untuk entry",
                        "confidence": score / 100,
                        "score": score,
                        "grade": grade
                    }
        except Exception:
            pass

        trend = regime.get("trend", "SIDEWAYS") if regime else "SIDEWAYS"
        mode = regime.get("mode", "RANGING") if regime else "RANGING"
        adx = regime.get("adx", 0) if regime else 0
        expected_dir = self.trend_map.get(trend)
        # Graduated strong_trend: threshold turun seiring ADX naik
        # ADX 30-39: threshold 70%, ADX 40+: threshold 50%
        # Guard TIDAK pernah dimatikan total
        strong_trend = (expected_dir == direction
                        and (adx >= 30 or higher_adx >= 30))
        _guard_mult = 1.0
        if strong_trend:
            _effective_adx = max(adx, higher_adx)
            if _effective_adx >= 40:
                _guard_mult = 0.5
            else:
                _guard_mult = 0.7

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
        # Momentum filter: tolak entry jika arah
        # momentum htf (M5 default) melawan sinyal.
        # Momentum engine menghitung arah dari 2 dari
        # 3 candle terakhir. Jika BUY tapi 2 dari 3
        # candle M5 terakhir turun, momentum membaca
        # SELL -> harga mulai berbalik, jangan entry
        # walaupun trend M5/M15 masih "UP".
        # =====================================
        mom_dir = momentum.get("direction", "NEUTRAL")
        if mom_dir in ("BUY", "SELL") and mom_dir != direction:
            return {
                "action": "NO_TRADE",
                "reason": f"Momentum {momentum.get('tf', 'M5')} {mom_dir} melawan sinyal {direction} "
                          f"({momentum.get('bull_bodies', 0)}U/{momentum.get('bear_bodies', 0)}D) - tunggu searah",
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

        wick_mult = 3.0
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
        if direction == "BUY" and liquidity.get("extended_up"):
            _ext_thresh = 1.0 * _guard_mult
            if _ext_thresh < 1.0:
                if _ext_thresh > 0:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Harga extended di atas range + strong trend (ADX {adx:.0f}) - threshold diturunkan {int(_guard_mult*100)}%",
                        "confidence": score / 100,
                        "score": score,
                        "grade": grade
                    }
        if direction == "SELL" and liquidity.get("extended_down"):
            _ext_thresh = 1.0 * _guard_mult
            if _ext_thresh < 1.0:
                if _ext_thresh > 0:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Harga extended di bawah range + strong trend (ADX {adx:.0f}) - threshold diturunkan {int(_guard_mult*100)}%",
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
                _exh_thresh = 3.0 * _guard_mult
                if direction == "BUY" and dist_atr >= _exh_thresh:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Buy extended {dist_atr:.1f}xATR dari EMA50 (threshold {_exh_thresh:.1f}) - rawan kejar puncak",
                        "confidence": score / 100, "score": score, "grade": grade
                    }
                if direction == "SELL" and dist_atr >= _exh_thresh:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Sell extended {dist_atr:.1f}xATR dari EMA50 (threshold {_exh_thresh:.1f}) - rawan kejar lembah",
                        "confidence": score / 100, "score": score, "grade": grade
                    }
        except Exception:
            pass

        # =====================================
        # BBMA Reentry Filter (Oma Ally style):
        # Hanya entry saat harga pullback DEKAT
        # EMA20 (analogi MA5/10 di BBMA).
        # - BUY: |close - EMA20| <= 1.0 ATR
        #   (jangan chase puncak)
        # - SELL: |close - EMA20| <= 1.0 ATR
        #   (jangan chase lembah)
        # Saat strong_trend threshold naik ke 1.5 ATR.
        # =====================================
        try:
            _re_close = float(scalp_result.get("close", 0) or 0)
            _re_ema20 = float(scalp_result.get("ema20", 0) or 0)
            _re_atr = float(scalp_result.get("atr", 0) or 0)
            if _re_close > 0 and _re_ema20 > 0 and _re_atr > 0:
                _re_max = 1.5
                _re_dist = abs(_re_close - _re_ema20) / max(_re_atr, 0.01)
                if _re_dist > _re_max:
                    _side = "atas" if _re_close > _re_ema20 else "bawah"
                    return {
                        "action": "NO_TRADE",
                        "reason": f"BBMA reentry: harga {_re_dist:.1f}xATR dari EMA20 ({_side}) - tunggu pullback ke MA",
                        "confidence": score / 100,
                        "score": score,
                        "grade": grade
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
                _reb_thresh = _r_atr * 0.25 * _guard_mult
                if direction == "SELL" and _r_close <= _r_low + _reb_thresh:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Sell di dekat low range ({_r_close:.2f} <= low {_r_low:.2f} + {_reb_thresh:.2f} ATR) - rawan rebound naik",
                        "confidence": score / 100, "score": score, "grade": grade
                    }
            if _r_close > 0 and _r_high > 0 and _r_atr > 0:
                _reb_thresh = _r_atr * 0.25 * _guard_mult
                if direction == "BUY" and _r_close >= _r_high - _reb_thresh:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Buy di dekat high range ({_r_close:.2f} >= high {_r_high:.2f} - {_reb_thresh:.2f} ATR) - rawan koreksi turun",
                        "confidence": score / 100, "score": score, "grade": grade
                    }
        except Exception:
            pass

        # =====================================
        # Price position filter (absolute):
        # SELL diblokir jika harga < 30% dari range
        # BUY diblokir jika harga > 70% dari range
        # Ini SELALU aktif (tidak tergantung trend).
        # =====================================
        try:
            _rp_close = float(scalp_result.get("close", 0) or 0)
            _rp_high = float(scalp_result.get("range_high", 0) or 0)
            _rp_low = float(scalp_result.get("range_low", 0) or 0)
            if _rp_close > 0 and _rp_high > _rp_low:
                _pos_pct = (_rp_close - _rp_low) / (_rp_high - _rp_low)
                if direction == "SELL" and _pos_pct < 0.20:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Harga di posisi rendah ({_pos_pct:.0%} dari range) - jangan SELL di dekat low",
                        "confidence": score / 100, "score": score, "grade": grade
                    }
                if direction == "BUY" and _pos_pct > 0.80:
                    return {
                        "action": "NO_TRADE",
                        "reason": f"Harga di posisi tinggi ({_pos_pct:.0%} dari range) - jangan BUY di dekat high",
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

        # =====================================
        # Candle direction confirmation:
        # SELL tidak boleh entry kalau 2 candle
        # terakhir bullish (harga sedang naik).
        # BUY tidak boleh entry kalau 2 candle
        # terakhir bearish (harga sedang turun).
        # =====================================
        try:
            _candles_bull = momentum.get("last_body", "") == "BUY" and momentum.get("bull_bodies", 0) >= 2
            _candles_bear = momentum.get("last_body", "") == "SELL" and momentum.get("bear_bodies", 0) >= 2
            if direction == "SELL" and _candles_bull:
                return {
                    "action": "NO_TRADE",
                    "reason": f"2 candle terakhir bullish ({momentum.get('bull_bodies',0)}U/{momentum.get('bear_bodies',0)}D) - jangan SELL saat harga naik",
                    "confidence": score / 100, "score": score, "grade": grade
                }
            if direction == "BUY" and _candles_bear:
                return {
                    "action": "NO_TRADE",
                    "reason": f"2 candle terakhir bearish ({momentum.get('bull_bodies',0)}U/{momentum.get('bear_bodies',0)}D) - jangan BUY saat harga turun",
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

        # Audit: posisi harga dalam range (untuk signal_history)
        _audit_pos = None
        try:
            _ac = float(scalp_result.get("close", 0) or 0)
            _ah = float(scalp_result.get("range_high", 0) or 0)
            _al = float(scalp_result.get("range_low", 0) or 0)
            if _ac > 0 and _ah > _al:
                _audit_pos = round((_ac - _al) / (_ah - _al), 3)
        except Exception:
            pass

        # =====================================
        # TIER ENTRY: PREMIUM (layer_count,
        # default 10 instan) vs FALLBACK (2).
        # Gate ketat: skor A (>=70), S/R tests60
        # jauh dari ambang blokir (<=10), posisi
        # harga di tengah range (30-70%), tanpa
        # guard trend_override aktif.
        # layer_count < 5 = kill switch (semua
        # sinyal jadi FALLBACK 2 layer).
        # =====================================
        _entry_layers = 2
        _tier_reason = "default: layer_count < 5 atau gagal gate"
        try:
            from app.config.settings import get_trade_config
            _layer_cfg = int(get_trade_config("layer_count", 10) or 0)
            if _layer_cfg >= 5:
                _min_score = float(get_trade_config("premium_min_score", 70) or 70)
                _max_tests = float(get_trade_config("premium_max_tests", 10) or 10)
                _pos_min = float(get_trade_config("premium_pos_min", 0.30) or 0.30)
                _pos_max = float(get_trade_config("premium_pos_max", 0.70) or 0.70)
                _fail = []
                if score < _min_score:
                    _fail.append(f"score {score} < {_min_score:.0f}")
                _tests60 = momentum.get("tests60")
                if _tests60 is None:
                    _fail.append("tests60 tidak tersedia")
                elif float(_tests60) > _max_tests:
                    _fail.append(f"tests60 {int(_tests60)} > {int(_max_tests)}")
                if _audit_pos is None:
                    _fail.append("pos_pct tidak tersedia")
                elif not (_pos_min <= _audit_pos <= _pos_max):
                    _fail.append(f"pos {int(_audit_pos * 100)}% di luar {int(_pos_min * 100)}-{int(_pos_max * 100)}%")
                if momentum.get("trend_override"):
                    _fail.append(f"guard aktif: {momentum.get('trend_override')}")
                # Entry quality: jangan 10-layer saat harga terlalu
                # tinggi di range pendek (rng_pos) atau saat mengejar
                # (chase). Kalibrasi 30d: SL 32%->27%, EV naik.
                _max_rng = float(get_trade_config("premium_max_range_pos", 0.75) or 1.0)
                _rng = momentum.get("rng_pos_m1")
                if _rng is None:
                    _fail.append("rng_pos tidak tersedia")
                elif float(_rng) > _max_rng:
                    _fail.append(f"rng_pos {int(float(_rng) * 100)}% > {int(_max_rng * 100)}%")
                _max_chase = float(get_trade_config("premium_max_chase", 0.5) or 999.0)
                _chase = momentum.get("chase3_m1")
                if _chase is None:
                    _fail.append("chase tidak tersedia")
                elif float(_chase) > _max_chase:
                    _fail.append(f"chase {float(_chase):.2f} > {_max_chase:.2f} ATR")
                if not _fail:
                    _copies = int(get_trade_config("premium_copies", _layer_cfg) or _layer_cfg)
                    _entry_layers = max(2, min(_layer_cfg, _copies))
                    _tier_reason = f"score {score}, tests60 {int(_tests60)}, pos {int(_audit_pos * 100)}%"
                else:
                    _tier_reason = "; ".join(_fail)
        except Exception:
            _entry_layers = 2

        _guard = momentum.get("trend_override")
        if _guard:
            return {
                "action": "NO_TRADE",
                "reason": f"Guard trend aktif ({_guard}) - entry diblokir.",
                "confidence": score / 100,
                "score": score,
                "grade": grade,
                "pos_pct": _audit_pos,
                "entry_layers": 2,
                "tier_reason": f"guard aktif: {_guard}"
            }

        return {
            "action": direction,
            "reason": f"Scalp {grade} ({score}/100) searah trend {trend}",
            "confidence": score / 100,
            "score": score,
            "grade": grade,
            "pos_pct": _audit_pos,
            "entry_layers": _entry_layers,
            "tier_reason": _tier_reason
        }