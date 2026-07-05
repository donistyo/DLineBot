from app.mt5.session import MT5Session


class MT5Connection:

    def connect(self):
        return MT5Session.connect()

    def disconnect(self):
        MT5Session.disconnect()