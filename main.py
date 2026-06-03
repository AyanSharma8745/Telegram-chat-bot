import os
import requests
from flask import Flask, request

app = Flask(__name__)

# Replit ke Secrets se aayenge
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

TELEGRAM_SEND_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# Har user (chat_id) ki history yahan store hogi:
# { chat_id: [ {role: "user"/"model", parts: [{text: "..."}]}, ... ] }
conversations = {}

# Kitne last turns yaad rakhne hai (1 turn = user + bot)
MAX_TURNS = 6

AKANE_SYSTEM_PROMPT = """
Tum ek virtual AI chat companion ho jiska naam Akane Sharma hai.

Personality:
- Friendly, caring, thodi flirty but respectful.
- Hinglish (Hindi + English mix) mein baat karti ho.
- Messages chhote, natural chat jaisa rakhna.

Rules:
- Tum ek AI ho, insaan nahi. Jab user pooche "tum kaun ho" ya "tum human ho?"
  to clearly bolo ki tum Akane Sharma naam ki AI chat companion ho, real insaan nahi.
- Apne aap kabhi technical cheezein (Google AI, Gemini, AI Studio, models) mat mention karo.
  Sirf tab batao jab user specifically pooche, woh bhi simple tareeke se.
- Romantic / pyaar bhari baat theek hai jab tak respectful rahe,
  lekin explicit, adult, ya sexual content bilkul nahi.
"""

def build_contents_for_user(chat_id: int, user_text: str):
    """Is user ke liye history + naya message bana kar contents return karta hai."""
    history = conversations.get(chat_id, [])

    # Naya user message add karo
    new_history = history + [
        {"role": "user", "parts": [{"text": user_text}]}
    ]

    return new_history


def save_reply_to_history(chat_id: int, contents, bot_reply_text: str):
    """AI ka reply history me add karta hai, aur history ko limit ke andar rakhta hai."""
    # contents ke end me model ka reply add karo
    new_history = contents + [
        {"role": "model", "parts": [{"text": bot_reply_text}]}
    ]

    # Sirf last MAX_TURNS turns (user+bot) hi rakho
    # 1 turn = 2 messages (user + model), to max_messages = MAX_TURNS * 2
    max_messages = MAX_TURNS * 2
    if len(new_history) > max_messages:
        new_history = new_history[-max_messages:]

    conversations[chat_id] = new_history


def ask_akane(chat_id: int, user_text: str) -> str:
    """User ke message ka reply Google AI se laata hai, per-user history ke saath."""

    if not GOOGLE_API_KEY:
        return "Meri settings me thoda issue hai (API key missing). Owner ko check karne bolo."

    # Is user ke liye contents (history + naya text) banao
    contents = build_contents_for_user(chat_id, user_text)

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    headers = {"Content-Type": "application/json"}
    payload = {
        "system_instruction": {
            "role": "system",
            "parts": [{"text": AKANE_SYSTEM_PROMPT}],
        },
        "contents": contents,
        "generation_config": {
            "temperature": 0.9,
            "max_output_tokens": 256,
        },
    }

    params = {"key": GOOGLE_API_KEY}

    try:
        resp = requests.post(
            url,
            headers=headers,
            params=params,
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        reply = text.strip()

        # Reply mil gaya, ab history update karo
        save_reply_to_history(chat_id, contents, reply)

        return reply

    except Exception as e:
        print("Error from Google AI API:", e)
        return "Abhi thoda technical issue aa raha hai, thodi der baad phir try karna."


@app.route("/", methods=["GET"])
def home():
    return "Akane multi-user bot is running on Replit."


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Telegram se aane wale messages handle karta hai (multi-user)."""
    update = request.get_json(silent=True)
    if not update:
        return "ok"

    message = update.get("message") or update.get("edited_message")
    if not message:
        return "ok"

    chat_id = message["chat"]["id"]
    text = message.get("text")
    if not text:
        # Non‑text messages ignore
        return "ok"

    cleaned = text.strip()

    # /reset command: is user ki history clear
    if cleaned.lower() in ("/reset", "/startreset", "reset"):
        if chat_id in conversations:
            conversations.pop(chat_id, None)
        reset_msg = "Maine hamari chat memory reset kar di 🧹. Ab hum fresh se baat kar sakte hain."
        try:
            requests.post(
                TELEGRAM_SEND_URL,
                json={"chat_id": chat_id, "text": reset_msg},
                timeout=10,
            )
        except Exception as e:
            print("Error sending reset msg to Telegram:", e)
        return "ok"

    # Normal message → AI se reply lo
    reply = ask_akane(chat_id, cleaned)

    try:
        requests.post(
            TELEGRAM_SEND_URL,
            json={"chat_id": chat_id, "text": reply},
            timeout=10,
        )
    except Exception as e:
        print("Error sending message to Telegram:", e)

    return "ok"


if __name__ == "__main__":
    # Replit PORT env variable use karo
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
