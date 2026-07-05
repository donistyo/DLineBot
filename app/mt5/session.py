import MetaTrader5 as mt5


class MT5Session:

    _connected = False

    # =====================================
    # Connect
    # =====================================

    @classmethod
    def connect(cls):

        # Sudah connect
        if cls._connected:
            return True

        if mt5.terminal_info() is not None:
            cls._connected = True
            return True

        if not mt5.initialize():

            print()
            print("=" * 60)
            print("MT5 SESSION")
            print("=" * 60)
            print(f"Failed : {mt5.last_error()}")

            cls._connected = False

            return False

        cls._connected = True

        print()
        print("=" * 60)
        print("MT5 SESSION")
        print("=" * 60)
        print("Connected")

        return True

    # =====================================
    # Disconnect
    # =====================================

    @classmethod
    def disconnect(cls):

        if not cls._connected:
            return

        mt5.shutdown()

        cls._connected = False

        print()
        print("=" * 60)
        print("MT5 SESSION")
        print("=" * 60)
        print("Disconnected")

    # =====================================
    # Ensure Connection
    # =====================================

    @classmethod
    def ensure_connection(cls):

        if cls._connected:

            if mt5.terminal_info() is not None:
                return True

            cls._connected = False

        return cls.connect()

    # =====================================
    # Status
    # =====================================

    @classmethod
    def is_connected(cls):

        return cls._connected