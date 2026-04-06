import os
from telegram import Bot
from telegram.error import TelegramError

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
bot = Bot(token=TELEGRAM_BOT_TOKEN)


async def send_telegram_message(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured")
        return

    max_len = 4096

    try:
        for i in range(0, len(text), max_len):
            chunk = text[i:i + max_len]
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=chunk)
    except TelegramError as e:
        print(f"Failed to send telegram message: {e}")