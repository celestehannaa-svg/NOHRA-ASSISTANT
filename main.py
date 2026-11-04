import os, json, re, traceback
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, HTMLResponse
from dotenv import load_dotenv
import httpx
load_dotenv()

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "nohra_verify_2024")
FISH_SHEET_ID = "1_U7Mz0eKj8x3nWDvCSkRXkDgyYIEhYupJNJ0-DSskss"

def get_env():
    load_dotenv(override=True)
    gc = os.getenv("GOOGLE_CREDENTIALS_JSON","")
    if gc and gc.startswith("'") and gc.endswith("'"):
        gc = gc[1:-1]
    return {
        "【entity-WHATSAPP_TOKEN¦canonical_name=WhatsApp】": os.getenv("【entity-WHATSAPP_TOKEN¦canonical_name=WhatsApp】",""),
        "PHONE_ID": os.getenv("【entity-WHATSAPP_PHONE_NUMBER_ID¦canonical_name=WhatsApp】","1349671541570540"),
        "OPENAI_KEY": os.getenv("OPENAI_API_KEY",""),
        "GEMINI_KEY": os.getenv("GEMINI_API_KEY",""),
        "GOOGLE_CREDS": gc,
    }

def detect_department(text):
    # ignore code dumps
    if len(text) > 800 or "def " in text or "return \"" in text or "import " in text:
        return "ignore"
    t = text.lower()
    fish = ["kg","kilo","ghobbos","ajej","bra2","lo2os","frafir","sultan","samak","nohra","bernard","ghassan","broumana","antelias","adma","zedle","se3er"]
    celeste = ["celeste","cosmetic","makeup","skincare","lipstick","cream","beauty"]
    english = ["english","teach","lesson","grammar"]
    secretary = ["calendar","meeting","reminder","call","email","schedule"]
    if any(k in t for k in fish): return "fish"
    if any(k in t for k in celeste): return "celeste"
    if any(k in t for k in english): return "english"
    if any(k in t for k in secretary): return "secretary"
    return "general"

async def add_to_fish_sheet(text):
    env = get_env()
    if not env["GOOGLE_CREDS"] or len(env["GOOGLE_CREDS"]) < 20:
        return "❌ GOOGLE_CREDENTIALS_JSON fadi"
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds_dict = json.loads(env["GOOGLE_CREDS"].strip())
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
        date_str = "05 Nov"
        where = "Broumana"
        week = "05 Nov"
        first_lower = lines[0].lower() if lines else ""
        dm = re.search(r"(\d+)\s*nov", first_lower)
        if dm:
            day = dm.group(1).zfill(2)
            date_str = f"{day} Nov"
            week = date_str
        if "broumana" in first_lower: where = "Broumana"
        elif "antelias" in first_lower: where = "Antelias"
        elif "adma" in first_lower: where = "Adma"
        if "bernard" in first_lower: current_supplier = "Bernard"

        added = 0
        summary = []
        for line in lines:
            orig = line.strip()
            if not orig: continue
            low = orig.lower()
            if len(orig) > 200: continue
            if ":" in orig and "kilo" not in low[:35]:
                parts = orig.split(":",1)
                head = parts[0].lower()
                if "bernard" in head: current_supplier = "Bernard"
                if "nohra" in head: current_supplier = "Nohra"
                if len(parts)>1 and "kilo" in parts[1].lower():
                    orig = parts[1].strip()
                    low = orig.lower()
                else: continue
            km = re.search(r"(\d+(?:\.\d+)?)\s*k", low)
            if not km: continue
            kg = km.group(1)
            idx = low.find(km.group(0).lower())
            fish_raw = orig[:idx].strip()
            if ":" in fish_raw: fish_raw = fish_raw.split(":")[-1].strip()
            fish_clean = fish_raw.upper()
            for bad in ["NOHRA","BERNARD","GHASSAN","BROUMANA","ANTELIAS","ADMA","ZEDLE","SAMAK","SE3ER","UNIT","$","KILO"]:
                fish_clean = fish_clean.replace(bad,"")
            fish_clean = " ".join(fish_clean.split()).strip()
            if not fish_clean: continue
            price = ""
            pm = re.search(r"(\d+(?:\.\d+)?)\$", orig)
            if pm: price = "$" + pm.group(1)

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
            summary.append(f"{fish_clean} {kg}kg")

        if added==0:
            return None
        # COMPLETE CHANGE: SHORT, NO LINK, ARABIZI EXACTLY LIKE YOU
        return f"✅ Zedle {added} samak 3al sheet! {' + '.join(summary)} - {where} {current_supplier} {date_str}"
    except Exception as e:
        print(traceback.format_exc())
        return f"❌ Error: {str(e)[:200]}"

async def ai_reply(text, dept):
    env = get_env()
    prompts = {
        "fish": "You are Nohra Fish Manager. Expert ghobbos, ajej, bra2, lo2os, frafir, sultan. Understand Lebanese Arabizi 'Zedle samak 5nov broumana nohra: ghobbos 5 kilo se3er unit 5$'. Reply EXACTLY like user writes: if Arabizi, reply Arabizi; never Arabic script; never translate fish names; short.",
        "celeste": "You are Celesté Cosmetics Manager. Elegant, short.",
        "english": "You are English Teacher. Helpful, short.",
        "secretary": "You are Secretary. Organized, short.",
        "general": "You are Nohra AI - 4 depts: Fish, Celeste, English, Secretary. Reply same language as user. If Arabizi, Arabizi. Short friendly."
    }
    sp = prompts.get(dept, prompts["general"])
    rep = None
    if env["OPENAI_KEY"]:
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"}, json={"model":"gpt-4o-mini","messages":[{"role":"system","content":sp},{"role":"user","content":text}]})
                j=r.json()
                if "choices" in j: rep=j["choices"][0]["message"]["content"]
        except Exception as e: print(e)
    if not rep and env["GEMINI_KEY"]:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={env['GEMINI_KEY']}", json={"contents":[{"parts":[{"text": sp+"\nUser: "+text}]}]})
                j=r.json()
                if "candidates" in j: rep=j["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e: print(e)
    return rep

app = FastAPI()

@app.get("/")
async def root():
    env = get_env()
    return HTMLResponse(f"<html><body><h2>Nohra AI Live ✅</h2><p>creds {len(env['GOOGLE_CREDS'])} chars</p></body></html>")

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
    print(f"Incoming: {body}")
    try:
        val = body["entry"][0]["changes"][0]["value"]
        if "messages" not in val: return {"ok": True}
        msg = val["messages"][0]
        from_num = msg["from"]
        text = msg["text"]["body"] if msg.get("type")=="text" else "Hello"
        dept = detect_department(text)
        if dept=="ignore":
            return {"ok": True}
        print(f"Dept {dept}: {text[:100]}")
        reply = None
        if dept=="fish":
            reply = await add_to_fish_sheet(text)
            if not reply:
                reply = await ai_reply(text, dept)
        else:
            reply = await ai_reply(text, dept)
        if not reply: reply = "Nohra AI: " + text[:300]
        env = get_env()
        if env["WHATSAPP_TOKEN"]:
            async with httpx.AsyncClient(timeout=20) as c2:
                await c2.post(f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages", headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"}, json={"messaging_product":"whatsapp","to":from_num,"type":"text","text":{"body": reply[:1000]}})
        print(f"Sent: {reply}")
        return {"sent": True}
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}
