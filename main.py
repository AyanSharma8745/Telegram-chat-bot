import os
import threading

import telebot
import google.generativeai as genai
from flask import Flask

# ====== ENV VARIABLES (Secrets) ======
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
    raise RuntimeError("TELEGRAM_BOT_TOKEN ya GEMINI_API_KEY missing hai (Replit secrets check karo).")

BOT_DISPLAY_NAME = "Akane"

# ====== GEMINI SETUP ======
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",  # chaaho to pro use kar sakte ho agar access hai
    system_instruction=(
        "Tum ek virtual girlfriend-style chatbot ho jiska naam Akane hai. "
        "Tum Hindi ya Hinglish mein baat karti ho. "
        "Tum pyaari, supportive aur thodi flirty ho, lekin hamesha respectful aur safe. "
        "User ka mood theek karne ki koshish karti ho, unko judge nahi karti. "
        "Agar user pooche ki tum insaan ho ya AI, to clearly batao ki tum AI chatbot ho jiska naam Akane hai. "
        "Naam pooche to hamesha bolo ki tumhara naam Akane hai."
    )
)

# ====== TELEGRAM BOT SETUP ======
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode=None)

# Per-user conversation history
# key = user_id, value = list of {role, parts}
conversation_history = {}


def get_user_key(message):
    """Har user ke liye alag context (chahe group me ho ya private)."""
    return message.from_user.id


def call_gemini(user_key, user_text):
    """Gemini ko call karke reply lana, aur history maintain karna."""
    history = conversation_history.get(user_key, [])

    # Naya user message add karo
    history.append({"role": "user", "parts": [user_text]})

    # Gemini se response
    response = model.generate_content(history)
    bot_reply = response.text

    # Bot ka reply bhi history me daal do
    history.append({"role": "model", "parts": [bot_reply]})

    # Sirf last 10 messages rakhte hain (memory bachane ke liye)
    conversation_history[user_key] = history[-10:]

    return bot_reply


# ====== TELEGRAM HANDLERS ======
@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    text = (
        f"Hey, main {BOT_DISPLAY_NAME} hoon.\n"
        "(Note: main ek AI chatbot hoon, tumhare saath friendly/girlfriend-style chat ke liye.)\n\n"
        "Mujhe bas message bhejo, main tumse baat karungi.\n"
        "Agar group me ho, to mera naam likhkar ('Akane') message bhejo tab main reply karungi."
    )
    bot.reply_to(message, text)


@bot.message_handler(content_types=["text"])
def handle_text(message):
    text = message.text.strip()

    # Group/supergroup handling: sirf jab naam liya ho
    if message.chat.type in ["group", "supergroup"]:
        lower = text.lower()
        if "akane" not in lower:
            # Agar naam nahi liya, to ignore (warna bot har message pe reply karega)
            return

    user_key = get_user_key(message)

    try:
        reply = call_gemini(user_key, text)
    except Exception as e:
        print("Gemini error:", e)
        reply = "Kuch technical problem aa gaya hai, thodi der baad phir try karna."

    bot.reply_to(message, reply)


# ====== FLASK APP (uptime ke liye) ======
app = Flask(__name__)


@app.route("/")
def home():
    return "Akane bot running"


def run_flask():
    # Replit ke liye commonly 0.0.0.0 aur port 8080
    app.run(host="0.0.0.0", port=8080)


def run_bot():
    # Telegram long polling
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    # Flask ko background thread me chalao taaki uptime service ping kar sake
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    # Bot chalao
    run_bot()
