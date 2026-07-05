from app.mt5.connection import MT5Connection


def main():

    mt5_conn = MT5Connection()

    mt5_conn.connect()

    mt5_conn.disconnect()


if __name__ == "__main__":
    main()