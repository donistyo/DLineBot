from app.mt5.connection import MT5Connection
from app.mt5.history_manager import HistoryManager
from app.live.history_view import HistoryView


def main():

    conn = MT5Connection()

    conn.connect()

    history = HistoryManager()

    HistoryView.show(history)

    conn.disconnect()


if __name__ == "__main__":

    main()