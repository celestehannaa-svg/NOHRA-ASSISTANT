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
        "OPENAI_KEY": os.getenv("OPENAI_API_KEY",""),
    }

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def root():
    env = get_env()
    return f"<html><body style='font-family:sans-serif;padding:20px'><h2>🤖 Nohra Bot Running FULL ✅</h2><p>has_gemini: {bool(env['GEMINI_KEY'])}<br>has_openai: {bool(env['OPENAI_KEY'])}<br>has_token: {bool(env['WHATSAPP_TOKEN'])}</p><p>Webhook: /webhook/whatsapp<br>Live on Render 🚀</p></body></html>"

@app.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge or "", status_code=200)
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
        text = msg["text"]["body"] if msg.get("type") == "text" else "Hello"
        env = get_env()
        reply = None
        
        # Try OpenAI first (more reliable)
        if env["OPENAI_KEY"]:
            try:
                async with httpx.AsyncClient(timeout=20) as c:
                    r = await c.post("https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"},
                        json={
                            "model": "gpt-4o-mini",
                            "messages": [
                                {"role": "system", "content": "You are Nohra assistant, multilingual helpful, 4 departments: Fish Business (Nohra/Bernard supply, Ghassan broker), Cosmetics (【entity-Celeste¦canonical_name=Celeste】), English Teaching, Secretary. Reply same language user uses. Support Lebanese Arabic + Arabizi. Keep replies short, friendly."},
                                {"role": "user", "content": text}
                            ]
                        })
                    data = r.json()
                    print(f"OpenAI: {data}")
                    if "choices" in data:
                        reply = data["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"OpenAI error: {e}")
        
        # Try Gemini if OpenAI failed
        if not reply and env["GEMINI_KEY"]:
            try:
                async with httpx.AsyncClient(timeout=20) as c:
                    r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={env['GEMINI_KEY']}",
                        json={"contents": [{"parts": [{"text": f"You are Nohra assistant, multilingual, 4 departments. User: {text}"}]}]})
                    data = r.json()
                    print(f"Gemini: {data}")
                    if "candidates" in data:
                        reply = data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                print(f"Gemini error: {e}")
        
        if not reply:
            reply = f"You said: {text} - I am Nohra Bot 🤖 How can I help with Fish Business, Cosmetics, Teaching, or Secretary?"
        
        # Send reply
        if env["WHATSAPP_TOKEN"]:
            async with httpx.AsyncClient(timeout=20) as c2:
                await c2.post(f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages",
                    headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"},
                    json={"messaging_product": "whatsapp", "to": from_num, "type": "text", "text": {"body": reply[:3000]}})
        print(f"Sent: {reply}")
        return {"sent": True}
    except Exception as e:
        print(f"Error: {e}")
        import traceback; traceback.print_exc()
        return {"error": str(e)}
