import requests
from datetime import datetime

from app.config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


class TelegramNotifier:

    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    @property
    def enabled(self):
        return bool(self.token and self.chat_id)

    def send(self, text):
        if not self.enabled:
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                },
                timeout=10
            )
            return resp.ok
        except Exception as e:
            print(f"Telegram: Gagal mengirim - {e}")
            return False

    # =====================================
    # OPEN notification
    # =====================================

    def notify_open(self, prediction, risk, symbol, score=None, filters=None):
        signal = prediction["signal"]
        confidence = prediction["confidence"]
        lot = risk.get("lot_size", 0)
        entry = risk.get("entry_price", 0)
        sl = risk.get("stop_loss", 0)
        tp = risk.get("take_profit", 0)

        emoji = "\U0001f7e2" if signal == "BUY" else "\U0001f534"
        text = (
            f"{emoji} <b>{signal} OPEN</b>\n"
            f"\n"
            f"Symbol     {symbol}\n"
            f"Entry      {entry}\n"
            f"SL         {sl}\n"
            f"TP         {tp}\n"
            f"Lot        {lot}\n"
            f"Confidence {confidence:.0%}\n"
        )

        if score:
            text += f"Score      {score.get('grade', '-')} ({score.get('score', 0)})\n"

        reason_lines = []
        if filters:
            checks = {
                "Trend": filters.get("trend_ok"),
                "AI": filters.get("ai_ok"),
                "MultiTF": filters.get("multitf_ok"),
                "ATR": filters.get("atr_ok"),
                "Spread": filters.get("spread_ok"),
                "News": filters.get("news_ok"),
            }
            for label, ok in checks.items():
                icon = "\u2705" if ok else "\u274c"
                reason_lines.append(f"  {icon} {label}")

        if reason_lines:
            text += "\nReason\n" + "\n".join(reason_lines)

        text += "\n\n\U0001f916 DLineBot"
        return self.send(text)

    # =====================================
    # CLOSE notification
    # =====================================

    def notify_close(self, ticket, symbol, profit, entry_price, exit_price,
                     reason, duration_minutes, signal=None):
        emoji = "\u2705" if profit > 0 else "\u274c"
        label = "PROFIT" if profit > 0 else "LOSS"
        sign = "+" if profit > 0 else ""

        text = (
            f"{emoji} <b>{label}</b>\n"
            f"\n"
            f"Symbol   {symbol}\n"
            f"Profit   {sign}${profit:.2f}\n"
            f"Duration {duration_minutes:.0f} menit\n"
            f"Reason   {reason}\n"
            f"Entry    {entry_price}\n"
            f"Exit     {exit_price}\n"
        )

        if signal:
            text += f"Signal   {signal}\n"

        text += "\n\U0001f916 DLineBot"
        return self.send(text)

    # =====================================
    # Old notify_order (keep for backward compat)
    # =====================================

    def notify_order(self, prediction, risk, symbol):
        return self.notify_open(prediction, risk, symbol)

    def notify_dashboard(self, dash_data, account, dashboard_url=None):
        balance = account.get("balance", 0) if account else 0
        equity = account.get("equity", 0) if account else 0

        text = (
            f"\U0001f4ca DLineBot Dashboard\n"
            f"\n"
            f"\U0001f3e6 Balance   ${balance:.2f}\n"
            f"\U0001f4b0 Equity    ${equity:.2f}\n"
            f"\n"
            f"\U0001f3af Signal    {dash_data['signal']}\n"
            f"\U0001f4ad Conf      {dash_data['confidence']:.0%}\n"
            f"\U0001f4b2 Score     {dash_data.get('score', '-')}\n"
            f"\U0001f6eb Trade     {dash_data['trade']}\n"
            f"\U0001f4cf Spread    {dash_data['spread']}\n"
            f"\U0001f300 ATR       {dash_data['atr']}\n"
            f"\U0001f6e1 Risk      {dash_data['risk']}\n"
            f"\U0001f4cc Position  {dash_data['position']}\n"
            f"\U0001f4c5 DailyRisk {dash_data['daily_risk']}\n"
            f"\U0001f4c9 Drawdown  {dash_data['drawdown']}\n"
            f"\U0001f916 AutoTrade {dash_data['auto_trader']}\n"
            f"\U0001f4d6 Learning  {dash_data.get('learning', '-')}\n"
            f"\n"
        )

        if dashboard_url:
            text += f"\U0001f310 Dashboard : {dashboard_url}\n"

        text += f"\n\U0001f916 DLineBot"

        return self.send(text)
