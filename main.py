import os
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, HTMLResponse
from dotenv import load_dotenv
import httpx
load_dotenv()
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "nohra_verify_2024")
def get_env():
    load_dotenv(override=True)
    return {
        "WHATSAPP_TOKEN": os.getenv("WHATSAPP_TOKEN",""),
        "PHONE_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID","1349671541570540"),
        "GEMINI_KEY": os.getenv("GEMINI_API_KEY",""),
    }
app = FastAPI()
@app.get("/", response_class=HTMLResponse)
async def root():
    env = get_env()
    return f"<html><body style='font-family:sans-serif;padding:20px'><h2>🤖 Nohra Bot Running FULL ✅</h2><p>has_gemini: {bool(env['GEMINI_KEY'])}<br>has_token: {bool(env['WHATSAPP_TOKEN'])}<br>phone_id: {env['PHONE_ID']}</p><p><a href='/setup' style='background:green;color:white;padding:10px 20px;text-decoration:none;border-radius:8px'>⚙️ SETUP KEYS HERE - Click</a></p><p>Webhook: /webhook/whatsapp<br>Verify: nohra_verify_2024</p></body></html>"
@app.get("/setup", response_class=HTMLResponse)
async def setup_page():
    return "<html><body style='font-family:sans-serif;padding:20px;max-width:600px'><h2>⚙️ Setup Keys - Paste in Browser</h2><form method='post' action='/setup'><p>Gemini Key (from aistudio.google.com - starts with AIza or aq):<br><input name='gemini' style='width:100%;padding:10px;font-size:16px'></p><p>WhatsApp Temporary Token (from developers.facebook.com -> WhatsApp -> Step 1 - starts with EAA):<br><input name='whatsapp' style='width:100%;padding:10px;font-size:16px'></p><p><button type='submit' style='background:blue;color:white;padding:12px 30px;border:none;border-radius:8px;font-size:16px'>💾 SAVE KEYS</button></p></form></body></html>"
@app.post("/setup", response_class=HTMLResponse)
async def save_setup(request: Request):
    form = await request.form()
    gemini = form.get("gemini","").strip()
    whatsapp = form.get("whatsapp","").strip()
    with open(".env","w") as f:
        if gemini: f.write(f"GEMINI_API_KEY={gemini}\n")
        if whatsapp: f.write(f"WHATSAPP_TOKEN={whatsapp}\n")
        f.write("WHATSAPP_PHONE_NUMBER_ID=1349671541570540\n")
        f.write("WHATSAPP_BUSINESS_ACCOUNT_ID=1107604465214184\n")
        f.write("WHATSAPP_VERIFY_TOKEN=nohra_verify_2024\n")
    return "<html><body style='font-family:sans-serif;padding:20px'><h2>✅ Keys Saved!</h2><p>Go to <a href='/'>Home</a> - should say has_gemini: true has_token: true</p><p>Now send Hello on WhatsApp!</p></body></html>"
@app.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge, status_code=200)
    from fastapi import HTTPException
    raise HTTPException(status_code=403)
@app.post("/webhook/whatsapp")
async def receive_message(request: Request):
    body = await request.json()
    print(f"Webhook: {body}")
    try:
        val = body["entry"][0]["changes"][0]["value"]
        if "messages" not in val:
            return {"ok": True}
        msg = val["messages"][0]
        from_num = msg["from"]
        text = msg["text"]["body"] if msg["type"] == "text" else "Hello"
        env = get_env()
        reply = "Hello! I am Nohra Bot 🤖 How can I help?"
        if env["GEMINI_KEY"]:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={env['GEMINI_KEY']}", json={"contents": [{"parts": [{"text": f"You are Nohra assistant, multilingual helpful, 4 departments: Fish Business, Cosmetics, English Teaching, Secretary. Reply same language user uses. User: {text}"}]}]})
                data = r.json()
                print(f"Gemini: {data}")
                if "candidates" in data:
                    reply = data["candidates"][0]["content"]["parts"][0]["text"]
        async with httpx.AsyncClient(timeout=20) as c2:
            await c2.post(f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages", headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"}, json={"messaging_product": "whatsapp", "to": from_num, "type": "text", "text": {"body": reply[:3000]}})
        print(f"Sent reply: {reply}")
        return {"sent": True}
    except Exception as e:
        print(f"Error: {e}")
        import traceback; traceback.print_exc()
        return {"error": str(e)}
