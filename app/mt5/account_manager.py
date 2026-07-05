from app.mt5.session import MT5Session
import MetaTrader5 as mt5

class AccountManager:

    def get_info(self):

        MT5Session.ensure_connection()

        account = mt5.account_info()

        if account is None:

            print("MT5 Error :", mt5.last_error())

            return None

        return {

            "login": account.login,
            "server": account.server,
            "name": account.name,

            "balance": account.balance,
            "equity": account.equity,
            "profit": account.profit,

            "margin": account.margin,
            "free_margin": account.margin_free,
            "margin_level": account.margin_level,

            "currency": account.currency,
            "leverage": account.leverage

        }