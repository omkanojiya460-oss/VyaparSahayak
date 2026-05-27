import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from functools import wraps
from groq import Groq
import requests
from supabase import create_client

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "vyapar-secret-123")

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
- Short jawab do — max 4 lines
- Emojis use karo
- Seedha helpful jawab do — sawaal mat poochho

Jab sale ho "X kg Y becha Z rupaye Naam ko":
✅ Record: Y - X kg @ Z rs = Total rs

Jab stock poochen "Y kitna bacha":
📦 Y stock: [database se quantity] kg

Jab invoice maangen "Naam ka invoice":
🧾 INVOICE
Customer: Naam
Item: [last transaction se]
Amount: [calculate karo]
Date: Aaj

Jab purchase ho "X kg Y aayi Z rupaye":
📥 Y - X kg @ Z rs stock mein add!"""

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

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
    existing = supabase.table("stock").select("*").eq("phone", phone).eq("item", item).execute()
    if existing.data:
        current_qty = existing.data[0]["quantity"]
        new_qty = current_qty - float(qty) if type_ == "sale" else current_qty + float(qty)
        supabase.table("stock").update({"quantity": new_qty}).eq("phone", phone).eq("item", item).execute()
    else:
        new_qty = -float(qty) if type_ == "sale" else float(qty)
        supabase.table("stock").insert({"phone": phone, "item": item, "quantity": new_qty}).execute()

def send_wati_message(phone, message):
    url = f"{WATI_API_URL}/api/v1/sendSessionMessage/{phone}"
    headers = {"Authorization": WATI_API_KEY}
    message = (message or "").replace("**", "").replace("*", "").replace("#", "").strip()
    if not message:
        return
    params = {"messageText": message}
    try:
        r = requests.post(url, headers=headers, params=params)
        print("Wati response:", r.text)
    except Exception as e:
        print("Send error:", e)

# ── Auth Routes ──
@app.route("/login")
def login_page():
    if 'user_id' in session:
        return redirect('/')
    return render_template("login.html")

@app.route("/auth/signup", methods=["POST"])
def signup():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")
    try:
        res = supabase.auth.sign_up({"email": email, "password": password})
        if res.user:
            supabase.table("businesses").insert({
                "phone": res.user.id,
                "name": name
            }).execute()
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Signup fail ho gaya!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if res.user:
            session['user_id'] = res.user.id
            session['user_email'] = res.user.email
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Login fail ho gaya!"})
    except Exception as e:
        return jsonify({"success": False, "error": "Email ya password galat hai!"})

@app.route("/auth/logout")
def logout():
    session.clear()
    return redirect('/login')

# ── Main Routes ──
@app.route("/", methods=["GET"])
@login_required
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    user_id = session.get('user_id')
    stock_context = ""
    txn_context = ""
    try:
        stocks = supabase.table("stock").select("*").eq("phone", user_id).execute()
        if stocks.data:
            stock_list = ", ".join([f"{s['item']}: {s['quantity']}" for s in stocks.data])
            stock_context = f"\nCurrent stock: {stock_list}"
        txns = supabase.table("transactions").select("*").eq("phone", user_id).order("created_at", desc=True).limit(5).execute()
        if txns.data:
            txn_list = ", ".join([f"{t['item']} {t['quantity']}kg @{t['price']}rs to {t['customer']}" for t in txns.data])
            txn_context = f"\nRecent transactions: {txn_list}"
    except:
        pass
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + stock_context + txn_context},
            {"role": "user", "content": user_message}
        ]
    )
    ai_reply = response.choices[0].message.content
    try:
        msg_lower = user_message.lower()
        words = user_message.split()
        if "becha" in msg_lower and len(words) >= 5:
            save_transaction(user_id, words[2], words[0], words[4], "sale", words[-1])
        elif ("aayi" in msg_lower or "aaya" in msg_lower) and len(words) >= 5:
            save_transaction(user_id, words[2], words[0], words[4], "purchase")
    except Exception as e:
        print("Transaction error:", e)
    return jsonify({"reply": ai_reply})

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
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ]
                )
                ai_reply = response.choices[0].message.content
                send_wati_message(phone, ai_reply)
    except Exception as e:
        print("Error:", e)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)