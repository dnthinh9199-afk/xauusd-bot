"""
telegram_bot.py - Gửi tín hiệu giao dịch về Telegram
Hỗ trợ retry, format đẹp, emoji rõ ràng
"""

import logging
import time
import requests
from datetime import datetime

import config
from strategy import TradeSignal

logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Bot Telegram gửi tín hiệu giao dịch.
    Dùng Telegram Bot API v6+ (sendMessage với parse_mode=HTML).
    """

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self):

        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID

        # FIX LỖI Ở ĐÂY
        self._enabled = bool(
            self.token and
            self.chat_id
        )

        if not self._enabled:

            logger.warning(
                "[Telegram] ⚠️ Token/Chat ID chưa cấu hình."
            )

        else:

            logger.info(
                f"[Telegram] ✅ Bot đã kết nối. Chat ID: {self.chat_id}"
            )

    # ----------------------------------------------------------
    # PUBLIC API
    # ----------------------------------------------------------

    def send_signal(self, signal: TradeSignal, retries: int = 3) -> bool:

        if not self._enabled:
            return False

        message = self._format_signal(signal)

        return self._send_message(
            message,
            retries=retries
        )

    def send_startup(self) -> bool:

        if not self._enabled:
            return False

        msg = (
            "🤖 <b>XAUUSD Trading Bot đã khởi động</b>\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🔄 Cập nhật mỗi <b>{config.UPDATE_INTERVAL_MINUTES} phút</b>\n"
            "📊 Phân tích: H1 | M15 | M5\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Đang theo dõi <b>XAUUSD</b>..."
        )

        return self._send_message(msg)

    def send_error(self, error_msg: str) -> bool:

        if not self._enabled:
            return False

        msg = (
            f"⚠️ <b>BOT ERROR</b>\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"📛 {error_msg}"
        )

        return self._send_message(msg)

    def send_strong_alert(self, signal: TradeSignal) -> bool:

        if not self._enabled:
            return False

        emoji = "🚨🟢" if signal.direction == "BUY" else "🚨🔴"

        msg = (
            f"{emoji} <b>CẢNH BÁO: TÍN HIỆU MẠNH {signal.direction}!</b>\n"
            f"💪 Độ mạnh: <b>{signal.strength:.0f}%</b>\n"
            f"💰 Entry: <b>{signal.entry:.2f}</b>\n"
            f"🛑 SL: {signal.stop_loss:.2f} | "
            f"🎯 TP: {signal.take_profit:.2f}"
        )

        return self._send_message(msg)

    # ----------------------------------------------------------
    # FORMATTING
    # ----------------------------------------------------------

    def _format_signal(self, signal: TradeSignal) -> str:

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        if signal.direction == "BUY":

            dir_icon = "🟢"
            dir_label = "📈 <b>BUY (Mua)</b>"

        elif signal.direction == "SELL":

            dir_icon = "🔴"
            dir_label = "📉 <b>SELL (Bán)</b>"

        else:

            dir_icon = "⏸"
            dir_label = "⏸ <b>CHỜ (Wait)</b>"

        strength_pct = signal.strength

        if strength_pct >= 80:
            str_icon = "🔥"

        elif strength_pct >= 65:
            str_icon = "💪"

        else:
            str_icon = "✅"

        # MTF Bias
        bias_lines = []

        for tf, bias in signal.timeframe_bias.items():

            b_icon = (
                "🟢" if bias == "BUY"
                else "🔴" if bias == "SELL"
                else "⚪"
            )

            bias_lines.append(
                f"  {b_icon} {tf}: {bias}"
            )

        bias_text = "\n".join(bias_lines)

        # Reasons
        if signal.reasons:

            reasons_text = "\n".join(
                f"  • {r}" for r in signal.reasons
            )

        else:

            reasons_text = "  • Tín hiệu Price Action cơ bản"

        # Warnings
        warnings_text = ""

        if signal.warnings:

            warnings_text = (
                "\n⚠️ <b>Lưu ý:</b>\n" +
                "\n".join(
                    f"  • {w}" for w in signal.warnings
                )
            )

        msg = (
            f"{'━'*26}\n"
            f"📊 <b>XAUUSD Signal</b> | {now}\n"
            f"{'━'*26}\n"
            f"{dir_icon} {dir_label}\n\n"
            f"{str_icon} Độ mạnh tín hiệu: "
            f"<b>{strength_pct:.0f}%</b>\n\n"
            f"💰 <b>Entry:</b> {signal.entry:.2f}\n"
            f"🛑 <b>Stop Loss:</b> {signal.stop_loss:.2f}\n"
            f"🎯 <b>Take Profit:</b> {signal.take_profit:.2f}\n"
            f"📐 <b>Risk/Reward:</b> "
            f"1:{signal.risk_reward:.1f}\n\n"
            f"📈 <b>Phân tích MTF:</b>\n"
            f"{bias_text}\n\n"
            f"🔍 <b>Lý do:</b>\n"
            f"{reasons_text}\n"
            f"{warnings_text}\n"
            f"{'━'*26}\n"
            f"⚙️ Pattern: "
            f"{signal.nearest_pattern or 'N/A'} | "
            f"Event: "
            f"{signal.structure_event or 'N/A'}"
        )

        return msg

    # ----------------------------------------------------------
    # HTTP HELPER
    # ----------------------------------------------------------

    def _send_message(self, text: str, retries: int = 3) -> bool:

        url = self.BASE_URL.format(
            token=self.token,
            method="sendMessage"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        for attempt in range(1, retries + 1):

            try:

                resp = requests.post(
                    url,
                    json=payload,
                    timeout=15
                )

                if (
                    resp.status_code == 200 and
                    resp.json().get("ok")
                ):

                    logger.info(
                        "[Telegram] ✅ Gửi tin thành công"
                    )

                    return True

                else:

                    logger.warning(
                        f"[Telegram] API Error "
                        f"{resp.status_code}: "
                        f"{resp.text[:200]}"
                    )

            except requests.exceptions.Timeout:

                logger.warning(
                    f"[Telegram] Timeout attempt {attempt}"
                )

            except requests.exceptions.ConnectionError:

                logger.warning(
                    f"[Telegram] Connection Error {attempt}"
                )

            except Exception as e:

                logger.error(
                    f"[Telegram] Error: {e}"
                )

            if attempt < retries:
                time.sleep(2)

        logger.error(
            "[Telegram] ❌ Gửi thất bại"
        )

        return False

    # ----------------------------------------------------------
    # TEST CONNECTION
    # ----------------------------------------------------------

    def test_connection(self) -> bool:

        if not self._enabled:

            print("[Telegram] Bot chưa được cấu hình.")

            return False

        url = self.BASE_URL.format(
            token=self.token,
            method="getMe"
        )

        try:

            resp = requests.get(
                url,
                timeout=10
            )

            data = resp.json()

            if data.get("ok"):

                bot_name = data["result"].get(
                    "username",
                    "unknown"
                )

                logger.info(
                    f"[Telegram] ✅ Kết nối thành công "
                    f"với @{bot_name}"
                )

                return True

        except Exception as e:

            logger.error(
                f"[Telegram] Lỗi test kết nối: {e}"
            )

        return False


# Singleton instance
telegram_bot = TelegramBot()


# ----------------------------------------------------------
# RUN TEST
# ----------------------------------------------------------

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

    bot = TelegramBot()

    print("Testing Telegram Connection...")

    if bot.test_connection():

        print("Telegram OK")

        bot.send_startup()

    else:

        print("Telegram FAILED")