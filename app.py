import os
from flask import Flask, request, jsonify
from groq import Groq
import requests
from supabase import create_client

app = Flask(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

WATI_API_KEY = os.environ.get("WATI_API_KEY", "")
WATI_API_URL = os.environ.get("WATI_API_URL", "")

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

SYSTEM_PROMPT = """Tu Vyapar Sahayak hai — Indian dukandars ka WhatsApp AI assistant.

Rules:
- Hindi/Hinglish mein baat kar
- Short jawab do — max 3 lines
- Emojis use karo

Jab sale ho: "X kg Y becha Z rupaye" → calculate karo aur confirm karo
Jab stock poochen: "Y kitna bacha" → database se batao
Jab purchase ho: "X kg Y aayi Z rupaye" → stock update karo
Sirf usi cheez ka jawab do jo poocha gaya"""

def save_transaction(phone, item, qty, price, type_, customer=""):
    total = float(qty) * float(price)
    supabase.table("transactions").insert({
        "phone": phone,
        "item": item,
        "quantity": float(qty),
        "price": float(price),
        "total": total,
        "type": type_,
        "customer": customer
    }).execute()
    
    # Stock update karo
    existing = supabase.table("stock").select("*").eq("phone", phone).eq("item", item).execute()
    if existing.data:
        current_qty = existing.data[0]["quantity"]
        new_qty = current_qty - float(qty) if type_ == "sale" else current_qty + float(qty)
        supabase.table("stock").update({"quantity": new_qty}).eq("phone", phone).eq("item", item).execute()
    else:
        new_qty = -float(qty) if type_ == "sale" else float(qty)
        supabase.table("stock").insert({"phone": phone, "item": item, "quantity": new_qty}).execute()

def get_stock(phone, item):
    result = supabase.table("stock").select("*").eq("phone", phone).eq("item", item).execute()
    if result.data:
        return result.data[0]["quantity"]
    return None

def send_wati_message(phone, message):
    url = f"{WATI_API_URL}/api/v1/sendSessionMessage/{phone}"
    headers = {"Authorization": WATI_API_KEY}
    message = message.replace("**", "").replace("*", "").replace("#", "").strip()
    data = {"messageText": str(message)}
    try:
        r = requests.post(url, headers=headers, json=data)
        print("Wati response:", r.text)
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
            text_field = data.get("text", "")
            if isinstance(text_field, dict):
                user_message = text_field.get("body", "")
            else:
                user_message = str(text_field) if text_field else ""
            phone = data.get("waId", "")
            
            if user_message and phone:
                # Stock context
                stock_context = ""
                try:
                    stocks = supabase.table("stock").select("*").eq("phone", phone).execute()
                    if stocks.data:
                        stock_list = ", ".join([f"{s['item']}: {s['quantity']}" for s in stocks.data])
                        stock_context = f"\nCurrent stock: {stock_list}"
                except:
                    pass
                
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT + stock_context},
                        {"role": "user", "content": user_message}
                    ]
                )
                ai_reply = response.choices[0].message.content
                
                # Transaction save karo
                try:
                    msg_lower = user_message.lower()
                    words = user_message.split()
                    if "becha" in msg_lower and len(words) >= 5:
                        qty = words[0]
                        item = words[2]
                        price = words[4]
                        customer = words[-1] if len(words) > 5 else ""
                        save_transaction(phone, item, qty, price, "sale", customer)
                    elif "aayi" in msg_lower or "aaya" in msg_lower and len(words) >= 5:
                        qty = words[0]
                        item = words[2]
                        price = words[4]
                        save_transaction(phone, item, qty, price, "purchase")
                except Exception as e:
                    print("Transaction error:", e)
                
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