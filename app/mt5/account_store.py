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
    return _load_json(ACTIVE_FILE, {})


def set_active_account(login, password, server):
    data = {
        "login": str(login),
        "password": str(password),
        "server": str(server),
    }
    _save_json(ACTIVE_FILE, data)
    return data


def clear_active_account():
    if os.path.exists(ACTIVE_FILE):
        os.remove(ACTIVE_FILE)


def get_saved_accounts():
    return _load_json(SAVED_FILE, [])


def add_saved_account(name, login, password, server):
    accounts = get_saved_accounts()
    accounts = [a for a in accounts if a.get("name", "").lower() != name.lower()]
    accounts.append({
        "name": name,
        "login": str(login),
        "password": str(password),
        "server": str(server),
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
