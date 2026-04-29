import os
from flask import Flask, request, jsonify
from groq import Groq


client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

app = Flask(__name__)

SYSTEM_PROMPT = """
Tu ek smart business assistant hai jiska naam Vyapar Sahayak hai.
Tu Indian small business owners ki madad karta hai Hindi aur Hinglish mein.
Tu sale record karta hai, stock track karta hai, aur invoice banata hai.
Short aur clear jawab do WhatsApp style mein. Emojis use karo.
"""

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

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Vyapar Sahayak chal raha hai!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))