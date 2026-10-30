def balance_layers():
    """Layer entry menurut saldo: > layers_balance_threshold (150) -> 2, selain itu 1.
    None bila saldo tidak terbaca (pemanggil memakai aturan lama)."""
    try:
        import MetaTrader5 as mt5
        from app.config.settings import get_trade_config
        acc = mt5.account_info()
        if acc is None:
            return None
        thr = float(get_trade_config("layers_balance_threshold", 150) or 150)
        return 2 if acc.balance > thr else 1
    except Exception:
        return None


def _min_entry_layers():
    """Jumlah layer minimum per entry: ikut saldo (balance_layers), fallback
    config entry_min_layers (default 2)."""
    _bl = balance_layers()
    if _bl:
        return _bl
    try:
        from app.config.settings import get_trade_config
        return max(1, int(get_trade_config("entry_min_layers", 2) or 2))
    except Exception:
        return 2


class DecisionEngine:

    def __init__(self, min_scalp_score=55):
        self.min_scalp_score = min_scalp_score
        try:
            from app.config.settings import get_trade_config
            self.sideways_penalty = float(get_trade_config("sideways_penalty", 10) or 10)
        except Exception:
            self.sideways_penalty = 10
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
            return {"action": "NO_TRADE", "reason": "Data tidak tersedia", "confidence": 0, "checks": []}
        bbma = scalp_result.get("bbma")
        if not isinstance(bbma, dict):
            return {
                "action": "NO_TRADE",
                "reason": "BBMA: data tidak tersedia (analyze belum jalan)",
                "confidence": 0,
                "score": 0,
                "grade": "-",
                "checks": []
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
            "confirm_hold_s": bbma.get("confirm_hold_s"),
            "confirm_hold_cycles": bbma.get("confirm_hold_cycles"),
        }

        checks = []

        def _bbma_fail(label, reason, detail=None):
            checks.append({"label": label, "ok": False,
                           "detail": detail if detail is not None else reason})
            return {
                "action": "NO_TRADE",
                "reason": reason,
                **base,
                "checks": checks,
            }

        def _bbma_ok(label, detail=None):
            checks.append({"label": label, "ok": True, "detail": detail})

        if direction not in ("BUY", "SELL"):
            return _bbma_fail(
                "BBMA arah",
                bbma.get("reason") or "BBMA: arah netral",
                f"direction={direction}"
            )
        _bbma_ok("BBMA arah", direction)

        # Defense-in-depth: anti-chase (analyze sudah cek, cek ulang di sini)
        try:
            from app.config.settings import get_trade_config
            _anti = float(get_trade_config("bbma_anti_chase_atr", 2.0) or 2.0)
        except Exception:
            _anti = 2.0
        if dist is not None and float(dist) > _anti:
            return _bbma_fail(
                "BBMA anti-chase",
                f"BBMA anti-chase: harga {float(dist):.1f}xATR dari mid BB (>{_anti:.1f})",
                f"{float(dist):.1f} > {_anti:.1f} ATR"
            )
        _bbma_ok("BBMA anti-chase", f"{dist} ATR dari mid BB (max {_anti:.1f})")

        if not bbma.get("trigger"):
            return _bbma_fail(
                "BBMA reentry trigger",
                bbma.get("reason") or "BBMA: reentry belum valid",
                "trigger belum valid"
            )
        _bbma_ok("BBMA reentry trigger", bbma.get("reason") or "trigger valid")

        return {
            "action": direction,
            "reason": bbma.get("reason") or f"BBMA reentry {direction}",
            **base,
            "entry_layers": _min_entry_layers(),
            "tier_reason": f"BBMA fixed ({slope}, dist {dist} ATR)",
            "checks": checks,
        }

    def _decide_zone(self, scalp_result):
        """Mode zone/reversal: keputusan murni dari state zona
        (scalp_result['zone'] oleh zone_strategy.analyze).
        Gate arah M5&M15, skor scalp, momentum, wick, rebound
        TIDAK dipakai (rang market - itulah titik masuknya).
        Proteksi keras tetap: RSI ekstrem, zona tembus, chase,
        posisi ekstrem, dan seluruh gate live_engine (daily risk,
        floor, session, margin, max positions, cooldown).
        Layer selalu dual 2.
        """
        if scalp_result is None:
            return {"action": "NO_TRADE", "reason": "Data tidak tersedia", "confidence": 0, "checks": []}
        zone = scalp_result.get("zone")
        if not isinstance(zone, dict):
            return {
                "action": "NO_TRADE",
                "reason": "Zone: data tidak tersedia (analyze belum jalan)",
                "confidence": 0, "score": 0, "grade": "-", "checks": []
            }

        direction = zone.get("direction", "NEUTRAL")
        rsi = zone.get("rsi")
        dist = zone.get("dist_atr")
        bounce = zone.get("bounce_atr")
        pos_pct = zone.get("pos_pct")
        base = {
            "confidence": 0,
            "score": 0,
            "grade": "-",
            "pos_pct": pos_pct,
            "entry_strategy": "zone",
            "zone_kind": (zone.get("zone") or {}).get("kind"),
            "zone_lo": (zone.get("zone") or {}).get("lo"),
            "zone_hi": (zone.get("zone") or {}).get("hi"),
            "zone_dist_atr": dist,
            "range_mid": zone.get("range_mid"),
            "zone_atr": zone.get("atr"),
            "close": zone.get("close"),
        }
        checks = []

        def _zfail(label, reason, detail=None):
            checks.append({"label": label, "ok": False,
                           "detail": detail if detail is not None else reason})
            return {"action": "NO_TRADE", "reason": reason, **base, "checks": checks}

        def _zok(label, detail=None):
            checks.append({"label": label, "ok": True, "detail": detail})

        try:
            from app.config.settings import get_trade_config
            _hard = float(get_trade_config("zone_rsi_hard", 80) or 80)
            _touch = float(get_trade_config("zone_touch_atr", 0.35) or 0.35)
            _pierce = float(get_trade_config("zone_pierce_atr", 0.5) or 0.5)
            _chase = float(get_trade_config("zone_chase_atr", 1.5) or 1.5)
            _pmax = float(get_trade_config("zone_pos_max", 0.80) or 0.80)
            _pmin = float(get_trade_config("zone_pos_min", 0.20) or 0.20)
        except Exception:
            _hard, _touch, _pierce, _chase, _pmax, _pmin = 80.0, 0.35, 0.5, 1.5, 0.80, 0.20

        if direction not in ("BUY", "SELL"):
            return _zfail(
                "Zone arah",
                zone.get("reason") or "Zone: tidak ada setup (netral)",
                f"direction={direction}"
            )
        _zok("Zone arah", direction)

        # RSI keras (Pengaman 2): BUY di puncak / SELL di lembah tetap diblokir
        if rsi is not None:
            if direction == "BUY" and rsi > _hard:
                return _zfail("Zone RSI keras",
                              f"RSI overbought ({rsi:.1f} > {_hard:.0f}) - jangan beli di puncak",
                              f"RSI {rsi:.1f}")
            if direction == "SELL" and rsi < (100.0 - _hard):
                return _zfail("Zone RSI keras",
                              f"RSI oversold ({rsi:.1f} < {100.0 - _hard:.0f}) - jangan jual di lembah",
                              f"RSI {rsi:.1f}")
            _zok("Zone RSI keras", f"RSI {rsi:.1f}")

        # TP mid-range: wajib ada ruang profit ke tengah range.
        # Exit khusus zone menaruh TP di mid-range; kalau jarak
        # entry->mid < zone_tp_min_atr maka risk/reward terlalu tipis.
        _rmid = zone.get("range_mid")
        _zclose = zone.get("close")
        _zatr = zone.get("atr")
        try:
            _tpmin = float(get_trade_config("zone_tp_min_atr", 0.5) or 0.5)
        except Exception:
            _tpmin = 0.5
        if _rmid and _zclose and _zatr and float(_zatr) > 0:
            if direction == "BUY":
                _room = (float(_rmid) - float(_zclose)) / float(_zatr)
            else:
                _room = (float(_zclose) - float(_rmid)) / float(_zatr)
            if _room < _tpmin:
                return _zfail("Zone TP mid-range",
                              f"Ruang ke mid-range {_room:.2f}xATR (< {_tpmin:.2f}) - TP terlalu dekat",
                              f"{_room:.2f} < {_tpmin:.2f} xATR")
            _zok("Zone TP mid-range", f"{_room:.2f}xATR ke mid {float(_rmid):.2f}")

        # Validasi ulang jarak zona (defense-in-depth terhadap analyze)
        if dist is not None:
            if dist > _touch:
                return _zfail("Zone jarak",
                              f"Harga belum sampai zona (dist {dist:.2f}xATR > {_touch:.2f})",
                              f"{dist:.2f} > {_touch:.2f}")
            if dist < -_pierce:
                return _zfail("Zone tembus",
                              f"Zona sudah tembus (dist {dist:.2f}xATR < -{_pierce:.2f})",
                              f"{dist:.2f} < -{_pierce:.2f}")
            _zok("Zone jarak", f"{dist:.2f}xATR dari tepi zona")

        # Chase: bounce sudah terlalu jauh
        if bounce is not None and bounce > _chase:
            return _zfail("Zone chase",
                          f"Sudah bounce {bounce:.2f}xATR dari zona (max {_chase:.2f}) - telat",
                          f"{bounce:.2f} > {_chase:.2f}")
        _zok("Zone chase", f"bounce {bounce if bounce is not None else '-'}xATR")

        # Posisi range ekstrem
        if pos_pct is not None:
            if direction == "BUY" and pos_pct > _pmax:
                return _zfail("Zone posisi",
                              f"Harga di {pos_pct:.0%} range (> {_pmax:.0%}) - jangan buy di atas",
                              f"{pos_pct:.0%} > {_pmax:.0%}")
            if direction == "SELL" and pos_pct < _pmin:
                return _zfail("Zone posisi",
                              f"Harga di {pos_pct:.0%} range (< {_pmin:.0%}) - jangan sell di bawah",
                              f"{pos_pct:.0%} < {_pmin:.0%}")
            _zok("Zone posisi", f"{pos_pct:.0%} range")

        if not zone.get("trigger"):
            return _zfail("Zone trigger", zone.get("reason") or "Zone: trigger belum valid",
                          "trigger belum valid")
        _zok("Zone trigger", zone.get("reason") or "trigger valid")

        return {
            "action": direction,
            "reason": zone.get("reason") or f"Zone reentry {direction}",
            **base,
            "entry_layers": _min_entry_layers(),
            "tier_reason": f"Zone fixed {_min_entry_layers()}",
            "checks": checks,
        }

    def decide(self, prediction=None, scalp_result=None, regime=None, higher_trend=None, higher_adx=0, strategy=None) -> dict:
        strat = str(strategy or self._entry_strategy() or "scalp").lower()
        if strat == "bbma":
            return self._decide_bbma(scalp_result)
        if strat == "zone":
            return self._decide_zone(scalp_result)

        if scalp_result is None or regime is None:
            return {"action": "NO_TRADE", "reason": "Data tidak tersedia", "confidence": 0,
                    "entry_strategy": "scalp", "checks": []}

        score_data = scalp_result.get("scalp_score", {})
        score = score_data.get("score", 0)
        direction = score_data.get("direction", "NEUTRAL")
        grade = score_data.get("grade", "D")

        # =====================================
        # Trace tiap guard: setiap guard yang
        # dievaluasi dicatat (lolos/gagal) agar
        # entry checklist di dashboard bisa
        # menampilkan status per guard.
        # =====================================
        checks = []

        def _ck(label, ok, detail=None):
            checks.append({"label": label, "ok": bool(ok), "detail": detail})

        def _reject(label, reason, detail=None):
            _ck(label, False, detail if detail is not None else reason)
            return {
                "action": "NO_TRADE",
                "reason": reason,
                "confidence": score / 100,
                "score": score,
                "grade": grade,
                "entry_strategy": "scalp",
                "checks": checks
            }

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
        trend = regime.get("trend", "SIDEWAYS") if regime else "SIDEWAYS"
        mode = regime.get("mode", "RANGING") if regime else "RANGING"
        adx = regime.get("adx", 0) if regime else 0
        expected_dir = self.trend_map.get(trend)
        # Graduated strong_trend: threshold turun seiring ADX naik
        # ADX 30-39: threshold 70%, ADX 40+: threshold 50%
        # Guard TIDAK PERNAH dimatikan total
        strong_trend = (expected_dir == direction
                        and (adx >= 30 or higher_adx >= 30))
        _guard_mult = 1.0
        if strong_trend:
            _effective_adx = max(adx, higher_adx)
            if _effective_adx >= 40:
                _guard_mult = 0.5
            else:
                _guard_mult = 0.7

        # =====================================
        # Momentum entry mode (config-driven):
        # saat trend kuat terkonfirmasi (ADX
        # >= momentum_min_adx searah sinyal),
        # guard keluarga "extended/kejar harga"
        # dilonggarkan supaya entry bisa masuk
        # di tengah gerakan (continuation).
        # Proteksi keras TIDAK dilonggar:
        # min score, gate M5&M15, trend_override,
        # wick rejection, M1 momentum, semua
        # exit (SL+, emergency, floor, loss cap).
        # =====================================
        _mom = False
        _mom_cfg = {}
        try:
            from app.config.settings import get_trade_config as _gtc_mom
            if int(_gtc_mom("momentum_entry", 0) or 0) == 1:
                _mom_adx = float(_gtc_mom("momentum_min_adx", 40) or 40)
                if strong_trend and max(adx, higher_adx) >= _mom_adx:
                    _mom = True
                    _mom_cfg = {
                        "rsi": float(_gtc_mom("momentum_rsi_max", 80) or 80),
                        "move": float(_gtc_mom("momentum_move_atr", 4.0) or 4.0),
                        "exh": float(_gtc_mom("momentum_exhaustion_atr", 4.5) or 4.5),
                        "re": float(_gtc_mom("momentum_reentry_atr", 3.0) or 3.0),
                        "pos": float(_gtc_mom("momentum_pos_max", 0.92) or 0.92),
                        "rng": float(_gtc_mom("momentum_rng_block", 0.95) or 0.95),
                    }
        except Exception:
            _mom = False

        # =====================================
        # RSI Overbought/Oversold filter:
        # Blokir BUY jika RSI > ambang
        # Blokir SELL jika RSI < 100 - ambang
        # Normal: rsi_max_normal (75); momentum: momentum_rsi_max (80)
        # Prevent entry di puncak/lembah. Filter WAJIB
        # (Pengaman 2) - tidak bisa dibypass skor tinggi.
        # =====================================
        _rsi_norm = 75.0
        try:
            from app.config.settings import get_trade_config as _gtc_rsi
            _rsi_norm = float(_gtc_rsi("rsi_max_normal", 75.0) or 75.0)
        except Exception:
            _rsi_norm = 75.0
        _rsi_max = _mom_cfg.get("rsi", 80.0) if _mom else _rsi_norm
        rsi_val = None
        try:
            _ind = scalp_result.get("indicators") or scalp_result
            rsi_val = float(_ind.get("RSI") or _ind.get("rsi") or 0)
        except Exception:
            pass
        if rsi_val is not None and rsi_val > 0:
            if direction == "BUY" and rsi_val > _rsi_max:
                return _reject(
                    "RSI",
                    f"RSI overbought ({rsi_val:.1f} > {_rsi_max:.0f}) - jangan beli di puncak",
                    f"RSI {rsi_val:.1f}"
                )
            if direction == "SELL" and rsi_val < (100.0 - _rsi_max):
                return _reject(
                    "RSI",
                    f"RSI oversold ({rsi_val:.1f} < {100.0 - _rsi_max:.0f}) - jangan jual di lembah",
                    f"RSI {rsi_val:.1f}"
                )
            _ck("RSI", True, f"RSI {rsi_val:.1f}")

        # =====================================
        # N-bar return cap: blokir entry jika
        # harga sudah bergerak terlalu jauh
        # dalam 10 bar terakhir (> 2.5x ATR;
        # 4.0 saat momentum mode).
        # Prevent chasing after extended move.
        # =====================================
        _move_max = _mom_cfg.get("move", 2.5) if _mom else 2.5
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
                if _move_atr > _move_max:
                    return _reject(
                        "10-bar move",
                        f"Harga sudah bergerak {_move_atr:.1f}xATR dalam 10 bar - terlalu jauh untuk entry",
                        f"{_move_atr:.1f}xATR > {_move_max:.1f}"
                    )
                _ck("10-bar move", True, f"{_move_atr:.1f}xATR dari 10 bar")
        except Exception:
            pass


        if score < self.min_scalp_score:
            return _reject(
                "Skor scalp",
                f"Scalp score terlalu rendah ({score}/100, {grade})",
                f"{score}/100 {grade} < {self.min_scalp_score}"
            )
        _ck("Skor scalp", True, f"{score}/100 {grade}")

        if direction in ("NEUTRAL", "WAIT"):
            return _reject(
                "Arah scalp",
                f"Scalp arah netral ({score}/100, {grade})",
                f"direction={direction}"
            )
        _ck("Arah scalp", True, direction)

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
            return _reject(
                "Momentum candle",
                f"Momentum candle terakhir melawan ({last_body}, akselerasi {accel:.2f}) - rawan gerakan tajam",
                f"{last_body} accel {accel:.2f}"
            )
        _ck("Momentum candle", True, f"{last_body} accel {accel:.2f}")

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
            return _reject(
                "Momentum HTF",
                f"Momentum {momentum.get('tf', 'M5')} {mom_dir} melawan sinyal {direction} "
                f"({momentum.get('bull_bodies', 0)}U/{momentum.get('bear_bodies', 0)}D) - tunggu searah",
                f"{momentum.get('tf', 'M5')} {mom_dir} vs {direction}"
            )
        _ck("Momentum HTF", True, f"{momentum.get('tf', 'M5')} {mom_dir}")

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
                return _reject(
                    "Wick rejection",
                    f"Wick atas {upper_wick:.2f} >= {wick_mult:.0f}x body {body:.2f} - candle rejection atas, rawan kejar puncak",
                    f"wick atas {upper_wick:.2f} vs {wick_mult:.0f}x{body:.2f}"
                )
            if direction == "SELL" and lower_wick >= wick_mult * body:
                return _reject(
                    "Wick rejection",
                    f"Wick bawah {lower_wick:.2f} >= {wick_mult:.0f}x body {body:.2f} - candle rejection bawah, rawan kejar lembah",
                    f"wick bawah {lower_wick:.2f} vs {wick_mult:.0f}x{body:.2f}"
                )
            _ck("Wick rejection", True, f"body {body:.2f} (mult {wick_mult:.1f})")

        # =====================================
        # Extension guard: harga sudah jauh/extended dari range terbaru
        # -> jangan entry mengejar gerakan yang sudah terlalu jauh.
        # ADAPTIF: hanya aktif saat trend LEMAH (strong_trend False).
        # Saat trend kuat, breakout dari range adalah continuation valid.
        # Momentum mode: skip total (breakout = continuation).
        # =====================================
        if not _mom:
            if direction == "BUY" and liquidity.get("extended_up"):
                _ext_thresh = 1.0 * _guard_mult
                if _ext_thresh < 1.0:
                    if _ext_thresh > 0:
                        return _reject(
                            "Extension range",
                            f"Harga extended di atas range + strong trend (ADX {adx:.0f}) - threshold diturunkan {int(_guard_mult*100)}%",
                            f"extended_up, thresh {_ext_thresh:.2f}"
                        )
            if direction == "SELL" and liquidity.get("extended_down"):
                _ext_thresh = 1.0 * _guard_mult
                if _ext_thresh < 1.0:
                    if _ext_thresh > 0:
                        return _reject(
                            "Extension range",
                            f"Harga extended di bawah range + strong trend (ADX {adx:.0f}) - threshold diturunkan {int(_guard_mult*100)}%",
                            f"extended_down, thresh {_ext_thresh:.2f}"
                        )
        _ck("Extension range", True,
            f"extended_up={bool(liquidity.get('extended_up'))} extended_down={bool(liquidity.get('extended_down'))}{' [momentum]' if _mom else ''}")

        # =====================================
        # Exhaustion guard: kalau harga sudah
        # jauh/extended dari EMA50 di arah yang
        # sama dengan sinyal -> jangan kejar.
        # Normal: exhaustion_atr_normal (3.0) x guard_mult
        # Momentum: momentum_exhaustion_atr (4.5).
        # Early: early_exhaustion_atr (4.5).
        # Filter WAJIB (Pengaman 2).
        # =====================================
        _exh_norm = 3.0
        try:
            from app.config.settings import get_trade_config as _gtc_exh
            _exh_norm = float(_gtc_exh("exhaustion_atr_normal", 3.0) or 3.0)
        except Exception:
            _exh_norm = 3.0
        _exh_base = _mom_cfg.get("exh", 4.5) if _mom else None
        if _exh_base is None and (scalp_result or {}).get("_early_entry"):
            try:
                from app.config.settings import get_trade_config as _gtc_eea
                _exh_base = float(_gtc_eea("early_exhaustion_atr", 4.5) or 4.5)
            except Exception:
                _exh_base = 4.5
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
                _exh_thresh = _exh_base if _exh_base is not None else _exh_norm * _guard_mult
                if direction == "BUY" and dist_atr >= _exh_thresh:
                    return _reject(
                        "Exhaustion EMA50",
                        f"Buy extended {dist_atr:.1f}xATR dari EMA50 (threshold {_exh_thresh:.1f}) - rawan kejar puncak",
                        f"{dist_atr:.1f}xATR >= {_exh_thresh:.1f}"
                    )
                if direction == "SELL" and dist_atr >= _exh_thresh:
                    return _reject(
                        "Exhaustion EMA50",
                        f"Sell extended {dist_atr:.1f}xATR dari EMA50 (threshold {_exh_thresh:.1f}) - rawan kejar lembah",
                        f"{dist_atr:.1f}xATR >= {_exh_thresh:.1f}"
                    )
                _ck("Exhaustion EMA50", True, f"{dist_atr:.1f}xATR (max {_exh_thresh:.1f}{' [momentum]' if _mom else ''})")
        except Exception:
            pass

        # =====================================
        # BBMA Reentry Filter (Oma Ally style):
        # Hanya entry saat harga pullback DEKAT
        # EMA20 (analogi MA5/10 di BBMA).
        # Threshold: 1.5 ATR
        # (momentum mode: momentum_reentry_atr).
        # =====================================
        try:
            _re_close = float(scalp_result.get("close", 0) or 0)
            _re_ema20 = float(scalp_result.get("ema20", 0) or 0)
            _re_atr = float(scalp_result.get("atr", 0) or 0)
            if _re_close > 0 and _re_ema20 > 0 and _re_atr > 0:
                _re_max = _mom_cfg.get("re", 3.0) if _mom else 1.5
                _re_dist = abs(_re_close - _re_ema20) / max(_re_atr, 0.01)
                if _re_dist > _re_max:
                    _side = "atas" if _re_close > _re_ema20 else "bawah"
                    return _reject(
                        "BBMA reentry",
                        f"BBMA reentry: harga {_re_dist:.1f}xATR dari EMA20 ({_side}) - tunggu pullback ke MA",
                        f"{_re_dist:.1f}xATR > {_re_max:.1f} ({_side})"
                    )
                _ck("BBMA reentry", True, f"{_re_dist:.1f}xATR dari EMA20 (max {_re_max:.1f}{' [momentum]' if _mom else ''})")
        except Exception:
            pass

        # =====================================
        # Rebound guard: tolak entry dekat tepi
        # range 20 candle M5.
        # Momentum mode: pengecekan ATR dilewati
        # (breakout continuation), TAPI tetap tolak
        # entry di ujung ekstrem range berdasarkan
        # posisi harga (rebound_pos_min, default 15%).
        # =====================================
        if not _mom:
            try:
                _r_close = float(scalp_result.get("close", 0) or 0)
                _r_high = float(scalp_result.get("range_high", 0) or 0)
                _r_low = float(scalp_result.get("range_low", 0) or 0)
                _r_atr = float(scalp_result.get("atr", 0) or 0)
                if _r_close > 0 and _r_low > 0 and _r_atr > 0:
                    _reb_thresh = _r_atr * 0.25 * _guard_mult
                    if direction == "SELL" and _r_close <= _r_low + _reb_thresh:
                        return _reject(
                            "Rebound edge",
                            f"Sell di dekat low range ({_r_close:.2f} <= low {_r_low:.2f} + {_reb_thresh:.2f} ATR) - rawan rebound naik",
                            f"{_r_close:.2f} <= {_r_low:.2f}+{_reb_thresh:.2f}"
                        )
                if _r_close > 0 and _r_high > 0 and _r_atr > 0:
                    _reb_thresh = _r_atr * 0.25 * _guard_mult
                    if direction == "BUY" and _r_close >= _r_high - _reb_thresh:
                        return _reject(
                            "Rebound edge",
                            f"Buy di dekat high range ({_r_close:.2f} >= high {_r_high:.2f} - {_reb_thresh:.2f} ATR) - rawan koreksi turun",
                            f"{_r_close:.2f} >= {_r_high:.2f}-{_reb_thresh:.2f}"
                        )
            except Exception:
                pass
        else:
            try:
                from app.config.settings import get_trade_config
                _reb_pos_min = float(
                    get_trade_config("rebound_pos_min", 0.15) or 0.15
                )
                _r_close = float(scalp_result.get("close", 0) or 0)
                _r_high = float(scalp_result.get("range_high", 0) or 0)
                _r_low = float(scalp_result.get("range_low", 0) or 0)
                if _r_close > 0 and _r_high > _r_low and _reb_pos_min > 0:
                    _pos = (_r_close - _r_low) / (_r_high - _r_low)
                    if direction == "SELL" and _pos < _reb_pos_min:
                        return _reject(
                            "Rebound edge",
                            f"Sell di {_pos:.0%} range (< {_reb_pos_min:.0%}) - rawan rebound naik",
                            f"pos {_pos:.0%} < {_reb_pos_min:.0%} [momentum]"
                        )
                    if direction == "BUY" and _pos > (1.0 - _reb_pos_min):
                        return _reject(
                            "Rebound edge",
                            f"Buy di {_pos:.0%} range (> {1.0 - _reb_pos_min:.0%}) - rawan koreksi turun",
                            f"pos {_pos:.0%} > {1.0 - _reb_pos_min:.0%} [momentum]"
                        )
            except Exception:
                pass
        try:
            from app.config.settings import get_trade_config as _gtc_reb
            _reb_min_log = float(_gtc_reb("rebound_pos_min", 0.15) or 0.15)
        except Exception:
            _reb_min_log = 0.15
        _ck("Rebound edge", True,
            "tidak di tepi range" if not _mom
            else f"momentum: pos >= {_reb_min_log:.0%}")

        # =====================================
        # Price position filter (absolute):
        # SELL diblokir jika harga < 100-pos_max
        # BUY diblokir jika harga > pos_max
        # Normal: 0.20/0.80 (momentum: 0.08/0.92)
        # Ini SELALU aktif (tidak tergantung trend).
        # =====================================
        _pos_max = _mom_cfg.get("pos", 0.92) if _mom else 0.80
        try:
            _rp_close = float(scalp_result.get("close", 0) or 0)
            _rp_high = float(scalp_result.get("range_high", 0) or 0)
            _rp_low = float(scalp_result.get("range_low", 0) or 0)
            if _rp_close > 0 and _rp_high > _rp_low:
                _pos_pct = (_rp_close - _rp_low) / (_rp_high - _rp_low)
                if direction == "SELL" and _pos_pct < (1.0 - _pos_max):
                    return _reject(
                        "Posisi harga di range",
                        f"Harga di posisi rendah ({_pos_pct:.0%} dari range) - jangan SELL di dekat low",
                        f"{_pos_pct:.0%} < {100.0 - _pos_max:.0f}%"
                    )
                if direction == "BUY" and _pos_pct > _pos_max:
                    return _reject(
                        "Posisi harga di range",
                        f"Harga di posisi tinggi ({_pos_pct:.0%} dari range) - jangan BUY di dekat high",
                        f"{_pos_pct:.0%} > {_pos_max:.0%}"
                    )
                _ck("Posisi harga di range", True, f"{_pos_pct:.0%} dari range")
        except Exception:
            pass

        # =====================================
        # M1 momentum wajib searah sinyal:
        # jika candle M1 terakhir masih melawan
        # arah, jangan entry (hindari melawan
        # gerakan intraday yang baru terbentuk)
        # Early-sideways: M1 harus searah EKSPLISIT
        # (konfirmasi momentum jelas - M15 SIDEWAYS,
        # jadi M1 jadi satu-satunya penegas arah).
        # =====================================
        try:
            m1 = (scalp_result or {}).get("m1_momentum") or {}
            m1_dir = m1.get("direction")
            if (scalp_result or {}).get("_early_sideways") and m1_dir != direction:
                return _reject(
                    "M1 momentum (early-sideways)",
                    f"EarlySideways butuh M1 momentum searah eksplisit (M1={m1_dir}, sinyal={direction})",
                    f"M1 {m1_dir} != {direction}"
                )
            if m1_dir in ("BUY", "SELL") and m1_dir != direction:
                return _reject(
                    "M1 momentum",
                    f"M1 momentum {m1_dir} melawan sinyal {direction} - tunggu konfirmasi searah",
                    f"M1 {m1_dir} vs {direction}"
                )
            _ck("M1 momentum", True, f"M1 {m1_dir}")
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
                return _reject(
                    "2 candle terakhir",
                    f"2 candle terakhir bullish ({momentum.get('bull_bodies',0)}U/{momentum.get('bear_bodies',0)}D) - jangan SELL saat harga naik",
                    f"{momentum.get('bull_bodies',0)}U/{momentum.get('bear_bodies',0)}D"
                )
            if direction == "BUY" and _candles_bear:
                return _reject(
                    "2 candle terakhir",
                    f"2 candle terakhir bearish ({momentum.get('bull_bodies',0)}U/{momentum.get('bear_bodies',0)}D) - jangan BUY saat harga turun",
                    f"{momentum.get('bull_bodies',0)}U/{momentum.get('bear_bodies',0)}D"
                )
            _ck("2 candle terakhir", True,
                f"{momentum.get('bull_bodies',0)}U/{momentum.get('bear_bodies',0)}D body {momentum.get('last_body', 'NEUT')}")
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
                return _reject(
                    "AI vs trend M5/M15",
                    f"Scalp {direction} vs AI {ai_signal} ({ai_conf:.0%}) - berlawanan arah",
                    f"scalp {direction} vs AI {ai_signal} {ai_conf:.0%}"
                )
            _ck("AI vs trend M5/M15", True,
                f"AI {ai_signal} {ai_conf:.0%} vs scalp {direction}")

        if expected_dir is None:
            if score < self.min_scalp_score + self.sideways_penalty:
                return _reject(
                    "Skor saat SIDEWAYS",
                    f"Trend SIDEWAYS, butuh skor >= {self.min_scalp_score + self.sideways_penalty} (dapat {score}/100 {grade})",
                    f"{score}/100 < {self.min_scalp_score + self.sideways_penalty}"
                )
            _ck("Skor saat SIDEWAYS", True, f"{score}/100 >= {self.min_scalp_score + self.sideways_penalty}")

        if expected_dir and direction != expected_dir:
            return _reject(
                "Searah trend",
                f"Scalp {direction} tidak searah trend {trend} - tunggu sinyal stabil",
                f"{direction} vs trend {trend}"
            )
        _ck("Searah trend", True, f"{direction} searah {trend}")

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
        _entry_layers = _min_entry_layers()
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
                    _entry_layers = max(_min_entry_layers(), min(_layer_cfg, _copies))
                    _tier_reason = f"score {score}, tests60 {int(_tests60)}, pos {int(_audit_pos * 100)}%"
                else:
                    _tier_reason = "; ".join(_fail)
        except Exception:
            _entry_layers = _min_entry_layers()

        _guard = momentum.get("trend_override")
        if _guard:
            return _reject(
                "Guard trend_override",
                f"Guard trend aktif ({_guard}) - entry diblokir.",
                f"trend_override {_guard}"
            ) | {
                "pos_pct": _audit_pos,
                "entry_layers": _min_entry_layers(),
                "tier_reason": f"guard aktif: {_guard}"
            }

        # =====================================
        # Hard block rng_pos (semua tier).
        # rng_pos_m1 sudah direction-aware:
        # BUY tinggi = dekat puncak range,
        # SELL tinggi = dekat dasar range.
        # > 0.85 = ekstrem mikro-range, jangan
        # entry terlepas score (13 Okt 12:58:
        # rng_pos 93%, score 73.9, langsung
        # jatuh -> equity floor).
        # Momentum mode: threshold momentum_rng_block (0.95).
        # =====================================
        if _mom:
            _rng_block = _mom_cfg.get("rng", 0.95)
        else:
            try:
                from app.config.settings import get_trade_config as _gtc
                _rng_block = float(_gtc("rng_pos_hard_block", 0.85) or 0)
            except Exception:
                _rng_block = 0.85
        if _rng_block > 0:
            _rng_now = momentum.get("rng_pos_m1")
            if _rng_now is not None and float(_rng_now) > _rng_block:
                return _reject(
                    "Guard rng_pos hard block",
                    f"Harga di {int(float(_rng_now) * 100)}% ekstrem range mikro (> {int(_rng_block * 100)}%) - entry diblokir semua tier.",
                    f"rng_pos {int(float(_rng_now) * 100)}% > {int(_rng_block * 100)}%"
                ) | {
                    "pos_pct": _audit_pos,
                    "entry_layers": _min_entry_layers(),
                    "tier_reason": f"rng_pos hard block {int(float(_rng_now) * 100)}%"
                }

        return {
            "action": direction,
            "reason": f"Scalp {grade} ({score}/100) searah trend {trend}" + (" [momentum]" if _mom else ""),
            "confidence": score / 100,
            "score": score,
            "grade": grade,
            "pos_pct": _audit_pos,
            "entry_layers": _entry_layers,
            "tier_reason": _tier_reason,
            "momentum_mode": _mom,
            "entry_strategy": "scalp",
            "checks": checks
        }
