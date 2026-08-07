import json
import os
from pathlib import Path
import requests
from datetime import datetime

from app.config.settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from app.mt5.position_controller import PositionController


class TelegramNotifier:

    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self._update_offset = 0

    @property
    def enabled(self):
        return bool(self.token and self.chat_id)

    def send(self, text, chat_id=None):
        if not self.enabled:
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": chat_id or self.chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                },
                timeout=10
            )
            return resp.ok
        except Exception as e:
            print(f"Telegram: Gagal mengirim - {e}")
            return False

    def get_updates(self):
        if not self.enabled:
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/getUpdates",
                params={
                    "offset": self._update_offset + 1,
                    "timeout": 5
                },
                timeout=10
            )
            if resp.ok:
                data = resp.json()
                return data.get("result", [])
            return []
        except Exception as e:
            print(f"Telegram: Gagal getUpdates - {e}")
            return []

    def handle_updates(self):
        updates = self.get_updates()
        for upd in updates:
            self._update_offset = upd["update_id"]
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            text = msg.get("text", "").strip()
            chat_id = msg["chat"]["id"]
            if text == "/dashboard":
                self._send_dashboard(chat_id)
            elif text in ("/start", "/on"):
                self._cmd_start(chat_id)
            elif text == "/off":
                self._cmd_off(chat_id)
            elif text == "/closeall":
                self._cmd_closeall(chat_id)
            elif text == "/help":
                self._cmd_help(chat_id)

    def _cmd_help(self, chat_id):
        help_text = (
            "\U0001f916 DLine Commands\n\n"
            "/dashboard - Tampilkan dashboard\n"
            "/start atau /on - Hidupkan auto-trade\n"
            "/off - Matikan auto-trade\n"
            "/closeall - Tutup semua posisi\n"
            "/help - Bantuan ini"
        )
        self.send(help_text, chat_id)

    def _cmd_start(self, chat_id):
        try:
            with open("runtime/auto_trade_enabled.json", "w") as f:
                json.dump({"enabled": True}, f)
            self.send("\u2705 Auto-Trade diaktifkan", chat_id)
        except Exception as e:
            self.send(f"Gagal: {e}", chat_id)

    def _cmd_off(self, chat_id):
        try:
            with open("runtime/auto_trade_enabled.json", "w") as f:
                json.dump({"enabled": False}, f)
            self.send("\u274c Auto-Trade dimatikan", chat_id)
        except Exception as e:
            self.send(f"Gagal: {e}", chat_id)

    def _cmd_closeall(self, chat_id):
        try:
            import MetaTrader5 as mt5
            mt5.initialize()
            positions = mt5.positions_get()
            count = len(positions) if positions else 0
            if count == 0:
                self.send("Tidak ada posisi terbuka", chat_id)
                return
            controller = PositionController()
            closed = 0
            for p in positions:
                r = controller.close(p, caller="TELEGRAM_CLOSEALL")
                if r.get("success"):
                    closed += 1
            mt5.shutdown()
            self.send(f"\u2705 Ditutup {closed}/{count} posisi", chat_id)
        except Exception as e:
            self.send(f"Gagal close all: {e}", chat_id)

    def _send_dashboard(self, chat_id):
        overview_path = Path("runtime/overview.json")
        if not overview_path.exists():
            self.send("Belum ada data dashboard. Tunggu siklus berikutnya.", chat_id)
            return

        try:
            with open(overview_path) as f:
                d = json.load(f)

            signal = d.get("signal", "-")
            balance = d.get("balance", 0)
            equity = d.get("equity", 0)
            trades_today = d.get("trades_today", 0)
            profit_today = d.get("profit_today", 0)
            open_count = d.get("open_count", 0)
            spread = d.get("spread", 0)

            text = (
                "\U0001f4ca DLine Dashboard\n"
                "\n"
                f"\U0001f3e6 Balance   ${balance:.2f}\n"
                f"\U0001f4b0 Equity    ${equity:.2f}\n"
                f"\U0001f3af Signal    {signal}\n"
                f"\U0001f4cc Open      {open_count} posisi\n"
                f"\U0001f4c5 Today     {trades_today} trade | "
                f"{'+' if profit_today >= 0 else ''}${profit_today:.2f}\n"
                f"\U0001f4cf Spread    {spread}\n"
                "\n"
                "\U0001f916 DLine"
            )
            self.send(text, chat_id)

        except Exception as e:
            self.send(f"Gagal baca dashboard: {e}", chat_id)

    # =====================================
    # OPEN notification
    # =====================================

    def notify_open(self, prediction, risk, symbol, score=None, filters=None, signal=None):
        if not signal:
            signal = prediction.get("signal", "HOLD")
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

        text += "\n\n\U0001f916 DLine"
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

        text += "\n\U0001f916 DLine"
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
            f"\U0001f4ca DLine Dashboard\n"
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
        )

        at_reason = dash_data.get("auto_trader_reason", "")
        if dash_data["auto_trader"] == "BLOCKED" and at_reason:
            text += f"\n\u26a0\ufe0f Alasan BLOCK: {at_reason}\n"

        if dashboard_url:
            text += f"\U0001f310 Dashboard : {dashboard_url}\n"

        text += f"\n\U0001f916 DLine"

        return self.send(text)
