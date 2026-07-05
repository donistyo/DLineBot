import requests

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

    def notify_order(self, prediction, risk, symbol):

        signal = prediction["signal"]
        confidence = prediction["confidence"]
        lot = risk["lot_size"]
        entry = risk["entry_price"]
        sl = risk["stop_loss"]
        tp = risk["take_profit"]

        text = (
            f"\U0001f4e2 {signal} {symbol}\n"
            f"Lot    {lot}\n"
            f"Entry  {entry}\n"
            f"SL     {sl}\n"
            f"TP     {tp}\n"
            f"Confidence  {confidence:.0%}\n"
            f"\n"
            f"\U0001f916 DLineBot"
        )

        return self.send(text)
