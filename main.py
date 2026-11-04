import os, json, re
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, HTMLResponse
from dotenv import load_dotenv
import httpx
load_dotenv()

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "nohra_verify_2024")
FISH_SHEET_ID = "1_U7Mz0eKj8x3nWDvCSkRXkDgyYIEhYupJNJ0-DSskss"

def get_env():
    load_dotenv(override=True)
    return {
        "WHATSAPP_TOKEN": os.getenv("WHATSAPP_TOKEN",""),
        "PHONE_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID","1349671541570540"),
        "GEMINI_KEY": os.getenv("GEMINI_API_KEY",""),
        "OPENAI_KEY": os.getenv("OPENAI_API_KEY",""),
        "GOOGLE_CREDS": os.getenv("GOOGLE_CREDENTIALS_JSON",""),
    }

def detect_department(text):
    t = text.lower()
    fish_keywords = ["fish","kg","kilo","ghobbos","ajej","bra2","lo2os","frafir","sultan","samak","nohra","bernard","ghassan","broumana","antelias","adma","zedle"]
    celeste_keywords = ["celeste","cosmetic","makeup","skincare","beauty"]
    english_keywords = ["english","teach","lesson","grammar","translate"]
    secretary_keywords = ["calendar","meeting","reminder","call","email","schedule"]
    if any(k in t for k in fish_keywords):
        return "fish"
    if any(k in t for k in celeste_keywords):
        return "celeste"
    if any(k in t for k in english_keywords):
        return "english"
    if any(k in t for k in secretary_keywords):
        return "secretary"
    return "general"

async def add_to_fish_sheet(text):
    env = get_env()
    if not env["GOOGLE_CREDS"]:
        return "Fahmet! Sheet not connected yet - add GOOGLE_CREDENTIALS_JSON in Render"
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds_dict = json.loads(env["GOOGLE_CREDS"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(FISH_SHEET_ID)
        try:
            ws = sheet.worksheet("Fish Supplies 2026")
        except:
            ws = sheet.get_worksheet(0)
        lines = text.strip().split("\n")
        current_supplier = "Nohra"
        date_str = ""
        where = "Broumana"
        week = ""
        first_lower = lines[0].lower() if lines else ""
        dm = re.search(r"(\d+)\s*nov", first_lower)
        if dm:
            day = dm.group(1)
            date_str = day + " Nov"
            week = date_str
        else:
            from datetime import datetime
            date_str = datetime.now().strftime("%d %b")
            week = date_str
        if "broumana" in first_lower:
            where = "Broumana"
        elif "antelias" in first_lower:
            where = "Antelias"
        elif "adma" in first_lower:
            where = "Adma"
        if "nohra" in first_lower:
            current_supplier = "Nohra"
        elif "bernard" in first_lower:
            current_supplier = "Bernard"
        added = 0
        for line in lines:
            orig = line.strip()
            if not orig:
                continue
            low = orig.lower()
            if ":" in orig and "kilo" not in low[:20]:
                parts = orig.split(":",1)
                head = parts[0].lower()
                if "bernard" in head:
                    current_supplier = "Bernard"
                if "nohra" in head:
                    current_supplier = "Nohra"
                if len(parts)>1 and "kilo" in parts[1].lower():
                    orig = parts[1].strip()
                    low = orig.lower()
                else:
                    continue
            km = re.search(r"(\d+(?:\.\d+)?)\s*k", low)
            if not km:
                continue
            kg = km.group(1)
            fish_raw = orig[: orig.lower().find(km.group(0).lower())].strip()
            if ":" in fish_raw:
                fish_raw = fish_raw.split(":")[-1].strip()
            fish_clean = fish_raw.upper()
            for bad in ["NOHRA","BERNARD","GHASSAN","BROUMANA","ANTELIAS","ADMA","ZEDLE","SAMAK"]:
                fish_clean = fish_clean.replace(bad,"")
            fish_clean = fish_clean.strip()
            price = ""
            pm = re.search(r"(\d+(?:\.\d+)?)\$", low)
            if pm:
                price = "$" + pm.group(1)
            all_vals = ws.get_all_values()
            nr = len(all_vals) + 1
            row = [""]*13
            row[0]=week
            row[1]=date_str
            row[2]=where
            row[5]=current_supplier
            row[6]=fish_clean
            row[7]=price
            row[9]=kg
            ws.update(f"A{nr}:M{nr}", [row])
            added+=1
        return f"✅ Zedle {added} samak 3al sheet! {date_str} {where} {current_supplier} https://docs.google.com/spreadsheets/d/{FISH_SHEET_ID}"
    except Exception as e:
        import traceback; traceback.print_exc()
        return f"Sheet error: {str(e)[:400]}"

async def ai_reply(text, department="general"):
    env = get_env()
    prompts = {
        "fish": "You are Nohra Fish Manager. Expert in ghobbos, ajej, bra2, lo2os, frafir, sultan. Understand Lebanese Arabizi. Reply EXACTLY like user writes. If user writes Arabizi reply Arabizi.",
        "celeste": "You are Celeste Cosmetics Manager. Elegant.",
        "english": "You are English Teacher. Helpful.",
        "secretary": "You are Secretary. Organized.",
        "general": "You are Nohra AI - 4 depts: Fish, Celeste, English, Secretary. Detect dept. Reply same language as user."
    }
    sp = prompts.get(department, prompts["general"])
    rep = None
    if env["OPENAI_KEY"]:
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"}, json={"model":"gpt-4o-mini","messages":[{"role":"system","content":sp},{"role":"user","content":text}]})
                j=r.json()
                if "choices" in j:
                    rep=j["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"OpenAI {e}")
    if not rep and env["GEMINI_KEY"]:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={env['GEMINI_KEY']}", json={"contents":[{"parts":[{"text": sp+"\nUser: "+text}]}]})
                j=r.json()
                if "candidates" in j:
                    rep=j["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"Gemini {e}")
    return rep

app = FastAPI()

@app.get("/")
async def root():
    env = get_env()
    html = """
    <html><body style="font-family:sans-serif;padding:20px">
    <h2>Nohra AI - 4 Depts OK</h2>
    <p>Fish Sheet: 1_U7Mz0eKj8x3nWDvCSkRXkDgyYIEhYupJNJ0-DSskss</p>
    <p>has_openai: """ + str(bool(env["OPENAI_KEY"])) + """</p>
    <p>has_sheets: """ + str(bool(env["GOOGLE_CREDS"])) + """</p>
    <p>has_token: """ + str(bool(env["WHATSAPP_TOKEN"])) + """</p>
    </body></html>
    """
    return HTMLResponse(content=html)

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
    print(body)
    try:
        val = body["entry"][0]["changes"][0]["value"]
        if "messages" not in val:
            return {"ok": True}
        msg = val["messages"][0]
        from_num = msg["from"]
        text = msg["text"]["body"] if msg.get("type")=="text" else "Hello"
        dept = detect_department(text)
        print(f"Dept {dept} {text}")
        if dept=="fish" and ("kg" in text.lower() or "kilo" in text.lower() or "zedle" in text.lower()):
            reply = await add_to_fish_sheet(text)
        else:
            reply = await ai_reply(text, dept)
        if not reply:
            reply = "Nohra AI: " + text[:1000]
        env = get_env()
        if env["WHATSAPP_TOKEN"]:
            async with httpx.AsyncClient(timeout=20) as c2:
                await c2.post(f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages", headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"}, json={"messaging_product":"whatsapp","to":from_num,"type":"text","text":{"body": reply[:3000]}})
        print(f"Sent {reply}")
        return {"sent": True}
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"error": str(e)}
