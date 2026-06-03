import os
import requests
from flask import Flask, request
from google import genai

app = Flask(__name__)

# ====== ENV / SECRETS ======

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not TELEGRAM_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN env variable missing.")
if not GOOGLE_API_KEY:
    print("ERROR: GOOGLE_API_KEY env variable missing.")

# Gemini client
client = genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None

TELEGRAM_SEND_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# ====== AKANE PERSONA ======

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

# ====== MULTI-USER MEMORY ======

# { chat_id: [ {role: "user"/"model", parts: [{"text": "..."}]}, ... ] }
conversations = {}

# Har user ke liye kitne last turns (user+bot) yaad rakhne:
MAX_TURNS = 6


def build_contents_for_user(chat_id: int, user_text: str):
    """
    Is user ke liye history + naya message mila kar
    Gemini ko dene layak contents return karta hai.
    """
    history = conversations.get(chat_id, [])

    new_history = history + [
        {"role": "user", "parts": [{"text": user_text}]}
    ]

    return new_history


def save_reply_to_history(chat_id: int, contents, bot_reply_text: str):
    """
    Model ke reply ko history me add karta hai aur
    history ka size limit ke andar rakhta hai.
    """
    new_history = contents + [
        {"role": "model", "parts": [{"text": bot_reply_text}]}
    ]

    max_messages = MAX_TURNS * 2  # 1 turn = user + model
    if len(new_history) > max_messages:
        new_history = new_history[-max_messages:]

    conversations[chat_id] = new_history


def ask_akane(chat_id: int, user_text: str) -> str:
    """
    User ke message ka reply Gemini 3.5 Flash se laata hai,
    per-user history ke saath.
    """
    if not GOOGLE_API_KEY or client is None:
        return "Meri settings me thoda issue hai (API key missing). Owner ko check karne bolo."

    contents = build_contents_for_user(chat_id, user_text)

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=contents,
            config={
                "temperature": 0.9,
                "max_output_tokens": 256,
                "system_instruction": AKANE_SYSTEM_PROMPT,
            },
        )

        reply = (response.text or "").strip()
        if not reply:
            reply = "Mujhe thoda confusion ho gaya, fir se likhoge kya?"

        save_reply_to_history(chat_id, contents, reply)

        return reply

    except Exception as e:
        # Debug ke liye console me print karo
        print("Error from Google AI API:", repr(e))
        return "Abhi thoda technical issue aa raha hai, thodi der baad phir try karna."


# ====== FLASK ROUTES ======

@app.route("/", methods=["GET"])
def home():
    return "Akane multi-user bot (Gemini 3.5 Flash) is running on Replit."


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
        # Non-text messages ignore
        return "ok"

    cleaned = text.strip()

    # /reset command: is user ki history clear
    if cleaned.lower() in ("/reset", "/startreset", "reset"):
        if chat_id in conversations:
            conversations.pop(chat_id, None)
        reset_msg = "Maine hamari chat memory reset kar di. Ab hum fresh se baat kar sakte hain. 🙂"
        try:
            requests.post(
                TELEGRAM_SEND_URL,
                json={"chat_id": chat_id, "text": reset_msg},
                timeout=10,
            )
        except Exception as e:
            print("Error sending reset msg to Telegram:", e)
        return "ok"

    # /start pe ek cute welcome
    if cleaned.lower() == "/start":
        welcome = (
            "Hey, main Akane Sharma hoon, tumhari virtual AI chat companion. 💕\n"
            "Bas yaad rakhna, main ek AI hoon, real insaan nahi.\n\n"
            "Jo mann me ho, mujhe likh sakte ho. Agar kabhi memory clear karni ho to /reset type karna. 🙂"
        )
        try:
            requests.post(
                TELEGRAM_SEND_URL,
                json={"chat_id": chat_id, "text": welcome},
                timeout=10,
            )
        except Exception as e:
            print("Error sending /start msg to Telegram:", e)
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
