from datetime import datetime


class SessionFilter:

    def __init__(
        self,
        start_hour=7,
        end_hour=21
    ):

        self.start_hour = start_hour
        self.end_hour = end_hour

    def allow(self):

        hour = datetime.utcnow().hour

        if self.start_hour <= hour <= self.end_hour:

            return {
                "allowed": True,
                "reason": "Trading session aktif."
            }

        return {
            "allowed": False,
            "reason": "Di luar jam trading."
        }