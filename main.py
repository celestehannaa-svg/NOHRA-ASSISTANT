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
    if gc.startswith("'") and gc.endswith("'"):
        gc = gc[1:-1]
    return {
        "WHATSAPP_TOKEN": os.getenv("WHATSAPP_TOKEN",""),
        "PHONE_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID","1349671541570540"),
        "OPENAI_KEY": os.getenv("OPENAI_API_KEY",""),
        "GOOGLE_CREDS": gc,
    }

def detect_department(text):
    if len(text) > 800:
        return "ignore"
    if "def " in text and "return" in text:
        return "ignore"
    t = text.lower()
    if "kg" in t or "kilo" in t or "ghobbos" in t or "ajej" in t or "bra2" in t or "lo2os" in t or "frafir" in t or "samak" in t or "zedle" in t:
        return "fish"
    return "general"

async def add_to_fish_sheet(text):
    env = get_env()
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds_dict = json.loads(env["GOOGLE_CREDS"].strip())
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(FISH_SHEET_ID)
        all_sheets = [s.title for s in sheet.worksheets()]
        print(all_sheets)
        target_title = ""
        for title in all_sheets:
            low = title.lower()
            if "profit" in low and "daily" in low:
                target_title = title
                break
        if target_title == "":
            for title in all_sheets:
                if "Fish Supplies" in title and "2026" in title:
                    target_title = title
                    break
        if target_title == "":
            target_title = all_sheets[0]
        ws = sheet.worksheet(target_title)
        print("Using tab: " + target_title)
        lines = text.strip().split("\n")
        current_supplier = "Nohra"
        date_str = "05 Nov"
        where = "Broumana"
        week = "20 - 25 Oct"
        first_lower = lines[0].lower() if lines else ""
        dm = re.search(r"(\d+)\s*nov", first_lower)
        if dm:
            day = dm.group(1).zfill(2)
            date_str = day + " Oct"
            week = date_str
        if "broumana" in first_lower:
            where = "Broumana"
        if "antelias" in first_lower:
            where = "Antelias"
        if "adma" in first_lower:
            where = "Adma"
        if "bernard" in first_lower:
            current_supplier = "Bernard"
        added = 0
        summary = []
        for line in lines:
            orig = line.strip()
            if not orig:
                continue
            low = orig.lower()
            if len(orig) > 200:
                continue
            if ":" in orig and "kilo" not in low[:35]:
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
            idx = low.find(km.group(0).lower())
            fish_raw = orig[:idx].strip()
            if ":" in fish_raw:
                fish_raw = fish_raw.split(":")[-1].strip()
            fish_clean = fish_raw.upper()
            for bad in ["NOHRA","BERNARD","GHASSAN","BROUMANA","ANTELIAS","ADMA","ZEDLE","SAMAK","SE3ER","UNIT","$","KILO"]:
                fish_clean = fish_clean.replace(bad,"")
            fish_clean = " ".join(fish_clean.split()).strip()
            if not fish_clean:
                continue
            price = ""
            pm = re.search(r"(\d+(?:\.\d+)?)\$", orig)
            if pm:
                price = "$" + pm.group(1)
            row = [""]*13
            row[0]=week
            row[1]=date_str
            row[2]=where
            row[5]=current_supplier
            row[6]=fish_clean
            row[7]=price
            row[9]=kg
            ws.append_row(row, value_input_option="USER_ENTERED")
            added+=1
            summary.append(fish_clean + " " + kg + "kg")
            print("Added: " + str(row))
        if added==0:
            return None
        summary_text = " + ".join(summary)
        return "Zedle " + str(added) + " samak 3al " + target_title + "! " + summary_text + " - " + where + " " + current_supplier + " " + date_str
    except Exception as e:
        tb = traceback.format_exc()
        print(tb)
        return "Error: " + str(e)[:400]

app = FastAPI()

@app.get("/")
async def root():
    env = get_env()
    has_token = str(bool(env["WHATSAPP_TOKEN"]))
    creds_len = str(len(env["GOOGLE_CREDS"]))
    html = "<h2>Nohra Live OK - profit daily</h2><p>token:" + has_token + " creds:" + creds_len + "</p>"
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
        txt = msg["text"]["body"] if msg.get("type")=="text" else "Hello"
        dept = detect_department(txt)
        if dept=="ignore":
            return {"ok": True}
        reply = await add_to_fish_sheet(txt)
        if not reply:
