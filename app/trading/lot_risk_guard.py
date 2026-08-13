import json


MAX_RISK_PERCENT = 10.0
DEFAULT_SL_ATR_MULT = 2.5
DEFAULT_ATR = 5.0
XAUUSD_POINT_VALUE = 1.0


def get_safe_lot(balance, atr, sl_atr_mult=None, selected_lot=None):
    if selected_lot is None:
        try:
            with open("runtime/trade_config.json") as f:
                selected_lot = json.load(f).get("lot_size", 0.01)
        except Exception:
            selected_lot = 0.01

    if sl_atr_mult is None:
        try:
            with open("runtime/trade_config.json") as f:
                sl_atr_mult = float(json.load(f).get("sl_atr_mult", DEFAULT_SL_ATR_MULT))
        except Exception:
            sl_atr_mult = DEFAULT_SL_ATR_MULT

    if atr <= 0:
        atr = DEFAULT_ATR

    sl_distance = sl_atr_mult * atr
    max_risk_amount = balance * MAX_RISK_PERCENT / 100.0
    max_lot = max_risk_amount / (sl_distance * XAUUSD_POINT_VALUE)
    max_lot = round(max_lot, 2)
    max_lot = max(0.01, max_lot)

    if selected_lot > max_lot:
        return {
            "lot_size": max_lot,
            "original_lot": selected_lot,
            "reduced": True,
            "reason": f"Lot {selected_lot} melebihi max risk {MAX_RISK_PERCENT}% (${max_risk_amount:.2f}). Auto-reduce ke {max_lot}.",
            "max_risk_amount": round(max_risk_amount, 2),
            "sl_distance": round(sl_distance, 2),
        }

    return {
        "lot_size": selected_lot,
        "original_lot": selected_lot,
        "reduced": False,
        "reason": f"Lot {selected_lot} aman (risk ${selected_lot * sl_distance * XAUUSD_POINT_VALUE:.2f} < {MAX_RISK_PERCENT}% = ${max_risk_amount:.2f}).",
        "max_risk_amount": round(max_risk_amount, 2),
        "sl_distance": round(sl_distance, 2),
    }


def get_max_positions_for_lot(lot):
    if lot <= 0.01:
        return 5
    elif lot <= 0.05:
        return 3
    elif lot <= 0.10:
        return 2
    else:
        return 1
