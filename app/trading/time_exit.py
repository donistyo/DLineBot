from datetime import datetime, timedelta
from app.mt5.position_controller import PositionController


class TimeExit:

    def __init__(self, max_minutes=120):
        self.max_minutes = max_minutes
        self.controller = PositionController()
        self._entry_times = {}

    def track(self, position):
        ticket = position.ticket
        if ticket not in self._entry_times:
            self._entry_times[ticket] = datetime.now()

    def process(self, position):
        ticket = position.ticket
        self.track(position)

        entry_time = self._entry_times.get(ticket)
        if not entry_time:
            return {"status": "SKIP", "action": "NONE",
                    "reason": "Entry time tidak diketahui.", "ticket": ticket}

        elapsed = (datetime.now() - entry_time).total_seconds() / 60

        if elapsed >= self.max_minutes:
            result = self.controller.close(position)
            self._entry_times.pop(ticket, None)
            return {"status": "CLOSED", "action": "TIME_EXIT",
                    "reason": f"Time exit ({elapsed:.0f}/{self.max_minutes} menit).",
                    "ticket": ticket, "result": result}

        remaining = self.max_minutes - elapsed
        return {"status": "HOLD", "action": "NONE",
                "reason": f"Sisa {remaining:.0f} menit.", "ticket": ticket,
                "elapsed": elapsed}

    def cleanup(self, active_tickets):
        for tid in list(self._entry_times.keys()):
            if tid not in active_tickets:
                del self._entry_times[tid]
