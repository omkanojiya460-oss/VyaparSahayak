import os
from flask import Flask, request, jsonify
from groq import Groq
import requests

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

WATI_API_KEY = os.environ.get("WATI_API_KEY", "")
WATI_API_URL = os.environ.get("WATI_API_URL", "")

SYSTEM_PROMPT = """Tu ek smart business assistant hai jiska naam Vyapar Sahayak hai.
Tu Indian small business owners ki madad karta hai Hindi aur Hinglish mein.
Short aur clear jawab do. Emojis use karo."""

def send_wati_message(phone, message):
    url = f"{WATI_API_URL}/api/v1/sendSessionMessage/{phone}"
    headers = {"Authorization": f"Bearer {WATI_API_KEY}"}
    data = {"messageText": message}
    requests.post(url, headers=headers, json=data)

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Vyapar Sahayak chal raha hai!"})

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    # Wati se message aaya
    if data and "text" in data and "waId" in data:
        user_message = data["text"].get("body", "")
        phone = data["waId"]
        
        if user_message:
            # AI se jawab lo
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ]
            )
            ai_reply = response.choices[0].message.content
            
            # WhatsApp pe bhejo
            send_wati_message(phone, ai_reply)
    
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