"""Find the chat id of whoever sent /start to the bot and save it to .env."""
import os

import requests
from dotenv import load_dotenv, set_key

load_dotenv()
token = os.getenv("TELEGRAM_TOKEN")
updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json().get("result", [])
chats = {u["message"]["chat"]["id"]: u["message"]["chat"] for u in updates if "message" in u}
if not chats:
    raise SystemExit("No messages yet: open the bot in Telegram, press Start, then run this again.")
chat_id, chat = list(chats.items())[-1]
set_key(".env", "TELEGRAM_CHAT_ID", str(chat_id))
print(f"Saved TELEGRAM_CHAT_ID={chat_id} ({chat.get('title') or chat.get('first_name')})")
requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
              data={"chat_id": chat_id, "text": "✅ Wildfire alert channel connected."})
