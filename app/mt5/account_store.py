import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
ACTIVE_FILE = os.path.join(RUNTIME_DIR, "active_account.json")
SAVED_FILE = os.path.join(RUNTIME_DIR, "saved_accounts.json")


def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_active_account():
    data = _load_json(ACTIVE_FILE, {})
    if data and "symbol" not in data:
        data["symbol"] = first_symbol_for_login(data.get("login"))
    return data


def set_active_account(login, password, server, symbol=None):
    data = {
        "login": str(login),
        "password": str(password),
        "server": str(server),
        "symbol": symbol or first_symbol_for_login(login),
    }
    _save_json(ACTIVE_FILE, data)
    return data


def get_active_symbol():
    return get_active_account().get("symbol") or "XAUUSDc"


def set_active_symbol(symbol):
    data = get_active_account()
    data["symbol"] = symbol
    _save_json(ACTIVE_FILE, data)
    return data


def first_symbol_for_login(login):
    symbols = get_account_symbols(login)
    return symbols[0] if symbols else "XAUUSDc"


PRIORITY_SYMBOLS = ["XAUUSDc", "BTCUSDc", "ETHUSDc", "XAGUSDc"]


def get_account_symbols(login):
    login = str(login)
    saved = []
    for a in get_saved_accounts():
        if str(a.get("login")) == login:
            saved = a.get("symbols") or []
            break
    if saved:
        base = saved
    else:
        base = []
    for s in PRIORITY_SYMBOLS:
        if s not in base:
            base.append(s)
    return base or ["XAUUSDc"]


def clear_active_account():
    if os.path.exists(ACTIVE_FILE):
        os.remove(ACTIVE_FILE)


def get_saved_accounts():
    return _load_json(SAVED_FILE, [])


def add_saved_account(name, login, password, server, symbols=None):
    accounts = get_saved_accounts()
    accounts = [a for a in accounts if a.get("name", "").lower() != name.lower()]
    accounts.append({
        "name": name,
        "login": str(login),
        "password": str(password),
        "server": str(server),
        "symbols": symbols or ["XAUUSDc"],
    })
    _save_json(SAVED_FILE, accounts)
    return accounts


def remove_saved_account(name):
    accounts = get_saved_accounts()
    accounts = [a for a in accounts if a.get("name", "").lower() != name.lower()]
    _save_json(SAVED_FILE, accounts)
    return accounts


def find_saved_account(name):
    for a in get_saved_accounts():
        if a.get("name", "").lower() == name.lower():
            return a
    return None
