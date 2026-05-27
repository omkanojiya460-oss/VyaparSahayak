import os
from flask import Flask, request, jsonify, render_template, redirect
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from flask import send_file
import io
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from supabase import create_client
except ImportError:
    create_client = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "vyapar-secret-123")
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "public-user")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if Groq and GROQ_API_KEY else None

WATI_API_KEY = os.environ.get("WATI_API_KEY", "")
WATI_API_URL = os.environ.get("WATI_API_URL", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if create_client and SUPABASE_URL and SUPABASE_KEY else None

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
# ── Main Routes ──
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/dashboard", methods=["GET"])
def dashboard():
    return redirect("/")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    user_id = DEFAULT_USER_ID

    if not client:
        return jsonify({"reply": "Groq API config missing. Set GROQ_API_KEY and install groq package."}), 500

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
        if not client:
            return jsonify({"status": "error", "error": "Groq API config missing"}), 500
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
@app.route("/invoice", methods=["POST"])
def generate_invoice():
    from datetime import datetime
    data = request.get_json()
    customer = data.get("customer", "Customer")
    items = data.get("items", [])
    business = data.get("business", "Meri Dukaan")
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    c.setFillColorRGB(0.91, 0.31, 0.04)
    c.rect(0, height-80, width, 80, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, height-45, "TAX INVOICE")
    c.setFont("Helvetica", 12)
    c.drawString(40, height-65, business)
    
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    c.drawString(40, height-110, f"Customer: {customer}")
    c.drawString(40, height-125, f"Date: {datetime.now().strftime('%d/%m/%Y')}")
    c.drawString(40, height-140, f"Invoice No: INV{datetime.now().strftime('%Y%m%d%H%M')}")
    
    c.setFillColorRGB(0.95, 0.95, 0.95)
    c.rect(40, height-175, width-80, 25, fill=True, stroke=False)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height-163, "Item")
    c.drawString(250, height-163, "Qty")
    c.drawString(330, height-163, "Rate")
    c.drawString(420, height-163, "Amount")
    
    y = height - 195
    total = 0
    c.setFont("Helvetica", 10)
    for item in items:
        name = item.get("name", "")
        qty = float(item.get("qty", 0))
        price = float(item.get("price", 0))
        amount = qty * price
        total += amount
        c.drawString(50, y, str(name))
        c.drawString(250, y, str(qty))
        c.drawString(330, y, f"Rs.{price}")
        c.drawString(420, y, f"Rs.{amount:.2f}")
        c.line(40, y-5, width-40, y-5)
        y -= 25
    
    gst = total * 0.05
    grand_total = total + gst
    c.setFont("Helvetica-Bold", 11)
    c.drawString(330, y-10, "Subtotal:")
    c.drawString(420, y-10, f"Rs.{total:.2f}")
    c.drawString(330, y-30, "GST (5%):")
    c.drawString(420, y-30, f"Rs.{gst:.2f}")
    c.setFillColorRGB(0.91, 0.31, 0.04)
    c.rect(310, y-60, width-350, 22, fill=True, stroke=False)
    c.setFillColorRGB(1, 1, 1)
    c.drawString(330, y-50, "TOTAL:")
    c.drawString(420, y-50, f"Rs.{grand_total:.2f}")
    
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.setFont("Helvetica", 9)
    c.drawCentredString(width/2, 40, "Thank you! | Vyapar Sahayak")
    
    c.save()
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"invoice_{customer}.pdf",
        mimetype="application/pdf"
    )
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
