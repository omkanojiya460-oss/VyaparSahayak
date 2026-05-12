import os
from flask import Flask, request, jsonify
from groq import Groq
import requests

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

WATI_API_KEY = os.environ.get("WATI_API_KEY", "")
WATI_API_URL = os.environ.get("WATI_API_URL", "")

SYSTEM_PROMPT = """Tu Vyapar Sahayak hai — Indian dukandars ka smart AI assistant.

Rules:
- Hamesha Hindi/Hinglish mein baat kar
- Short aur simple jawab do — max 3-4 lines
- Sale record karo jab koi bole "X kg Y becha Z rupaye"
- Stock batao jab koi pooche
- Invoice banao jab maango
- Koi bhi sawaal poochho mat — seedha helpful jawab do
- Emojis use karo par kam

Example replies:
User: "50 kg aata becha 35 rs" → "✅ Record ho gaya! Aata: 50kg @ ₹35 = ₹1750"
User: "aata kitna bacha" → "📦 Aata stock: Abhi record nahi hai. Pehle batao kitna tha!"
User: "invoice chahiye" → "📄 Invoice ke liye customer ka naam aur items batao!"
"""

def send_wati_message(phone, message):
    url = f"{WATI_API_URL}/api/v1/sendSessionMessage/{phone}"
    headers = {
        "Authorization": WATI_API_KEY,
        "Content-Type": "application/json"
    }
    message = (message or "").replace("**", "").replace("*", "").replace("#", "").strip()
    if not message:
        print(f"Skipping Wati send to {phone}: message text is empty")
        return

    print(f"Sending to {phone}: [{message}]")
    print(f"URL: {url}")
    try:
        r = requests.post(url, headers=headers, params={"messageText": message})
        print("Wati response:", r.text)
        print("Status code:", r.status_code)
    except Exception as e:
        print("Send error:", e)

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Vyapar Sahayak chal raha hai!"})

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    try:
        if data:
            # Wati text field extract karo
            text_field = data.get("text", "")
            if isinstance(text_field, dict):
                user_message = text_field.get("body", "")
            else:
                user_message = str(text_field) if text_field else ""
            
            phone = data.get("waId", "")
            print(f"Message: {user_message}, Phone: {phone}")
            
            if user_message and phone:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ]
                )
                ai_reply = response.choices[0].message.content
                print(f"AI Reply: {ai_reply}")
                send_wati_message(phone, ai_reply)
    except Exception as e:
        print("Error:", e)
    return jsonify({"status": "ok"})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
    )
    return jsonify({"reply": response.choices[0].message.content})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
