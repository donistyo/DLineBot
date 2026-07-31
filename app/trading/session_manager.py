from pathlib import Path
from datetime import datetime, date
import json


class SessionManager:

    def __init__(self, max_sessions=5, max_per_session=10):
        self.max_sessions = max_sessions
        self.max_per_session = max_per_session
        self._state_file = Path("runtime/session_state.json")
        self._state = self._load()

    # =====================================
    # State
    # =====================================

    def _load(self):
        try:
            with open(self._state_file) as f:
                d = json.load(f)
            if d.get("date") == str(date.today()):
                return d
        except:
            pass
        return {
            "date": str(date.today()),
            "current_session": 1,
            "entries_this_session": 0,
            "session_entry_tickets": [],
            "closed_today": 0,
        }

    def _save(self):
        self._state_file.parent.mkdir(exist_ok=True)
        with open(self._state_file, "w") as f:
            json.dump(self._state, f, indent=2)

    # =====================================
    # Allow check
    # =====================================

    def allow(self, open_tickets):
        s = self._state

        # Reset if new day
        if s.get("date") != str(date.today()):
            self.reset()
            s = self._state

        # Remove tickets that are no longer open
        s["session_entry_tickets"] = [
            t for t in s["session_entry_tickets"] if t in open_tickets
        ]

        # If current session done and all closed → next session
        if s["entries_this_session"] >= self.max_per_session:
            if len(s["session_entry_tickets"]) == 0:
                if s["current_session"] < self.max_sessions:
                    s["current_session"] += 1
                    s["entries_this_session"] = 0
                    self._save()
                else:
                    return {
                        "allowed": False,
                        "reason": f"Semua {self.max_sessions} sesi terpakai ({self.max_sessions}x{self.max_per_session}).",
                        "session": s["current_session"],
                        "entries_this_session": s["entries_this_session"],
                        "max_sessions": self.max_sessions,
                    }
            else:
                return {
                    "allowed": False,
                    "reason": f"Sesi {s['current_session']} penuh, tunggu {len(s['session_entry_tickets'])} posisi close.",
                    "session": s["current_session"],
                    "entries_this_session": s["entries_this_session"],
                    "open_in_session": len(s["session_entry_tickets"]),
                }

        # Can trade
        remaining = self.max_per_session - s["entries_this_session"]
        return {
            "allowed": True,
            "reason": f"Sesi {s['current_session']}: {s['entries_this_session']}/{self.max_per_session} entry ({remaining} slot).",
            "session": s["current_session"],
            "entries_this_session": s["entries_this_session"],
            "remaining": remaining,
            "max_sessions": self.max_sessions,
        }

    # =====================================
    # Register entry
    # =====================================

    def register_entry(self, ticket):
        s = self._state
        if s["entries_this_session"] < self.max_per_session:
            s["entries_this_session"] += 1
            s["session_entry_tickets"].append(ticket)
            s["closed_today"] += 1
            self._save()

    # =====================================
    # Reset for new day
    # =====================================

    def reset(self):
        self._state = {
            "date": str(date.today()),
            "current_session": 1,
            "entries_this_session": 0,
            "session_entry_tickets": [],
            "closed_today": 0,
        }
        self._save()
