from app.mt5.connection import MT5Connection
from app.mt5.account_manager import AccountManager

conn = MT5Connection()

conn.connect()

account = AccountManager()

info = account.get_info()

print()

print("=" * 60)
print("ACCOUNT INFORMATION")
print("=" * 60)

for k, v in info.items():
    print(f"{k:<15}: {v}")

conn.disconnect()