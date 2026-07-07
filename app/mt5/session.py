import MetaTrader5 as mt5
from app.config.settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER


class MT5Session:

    _connected = False

    # =====================================
    # Connect
    # =====================================

    @classmethod
    def connect(cls):

        if cls._connected:
            return True

        # Strategy 1: connect to already-running terminal
        if mt5.terminal_info() is not None:
            cls._connected = True
            acc = mt5.account_info()
            if acc:
                print()
                print("=" * 60)
                print("MT5 SESSION")
                print("=" * 60)
                print(f"Terminal running : {acc.login} @ {acc.server}")
                print(f"Balance    : {acc.balance:.2f} {acc.currency}")
            return True

        # Strategy 2: try initialize with credentials (fresh terminal)
        if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
            login = int(MT5_LOGIN) if MT5_LOGIN.isdigit() else MT5_LOGIN
            ok = mt5.initialize(login=login, password=MT5_PASSWORD,
                                server=MT5_SERVER, timeout=60000)
            if ok:
                acc = mt5.account_info()
                print()
                print("=" * 60)
                print("MT5 SESSION")
                print("=" * 60)
                print(f"Logged in  : {acc.login} @ {acc.server}")
                print(f"Balance    : {acc.balance:.2f} {acc.currency}")
                print(f"Leverage   : 1:{acc.leverage}")
                cls._connected = True
                return True

            err = mt5.last_error()
            print()
            print("=" * 60)
            print("MT5 SESSION")
            print("=" * 60)
            print(f"Auto-login gagal : {err}")
            print()
            print("PENYEBAB:")
            print("- Password MT5 ≠ Password Personal Area (harus diset terpisah)")
            print("- Server salah (cek di MT5 > File > Login to Trade Account)")
            print("- Akun Cent belum dibuat untuk MT5")
            print()
            print("SOLUSI:")
            print("1. Buka https://exness.com → Login Personal Area")
            print("   Email: dimas.fahmi09@icloud.com")
            print("2. Buka tab Trading → Accounts")
            print("3. Cari akun Cent (Standard Cent)")
            print("4. Klik ... (Settings) → Change MT5 Password")
            print("5. Set password baru untuk MT5")
            print("6. Update .env: MT5_PASSWORD=password_baru_tersebut")
            print(f"7. Login manual di MT5: File → Login to Trade Account")
            print(f"   Login: {MT5_LOGIN}")
            print(f"   Server: {MT5_SERVER}")
            cls._connected = False
            return False

        # Strategy 3: plain initialize (rely on terminal being pre-logged-in)
        if mt5.initialize():
            cls._connected = True
            acc = mt5.account_info()
            if acc:
                print()
                print("=" * 60)
                print("MT5 SESSION")
                print("=" * 60)
                print(f"Connected : {acc.login} @ {acc.server}")
                print(f"Balance   : {acc.balance:.2f} {acc.currency}")
            return True

        print()
        print("=" * 60)
        print("MT5 SESSION")
        print("=" * 60)
        print(f"Initialize failed : {mt5.last_error()}")
        return False

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