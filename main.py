import os, json, re, traceback, tempfile, base64
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

def clean_fish_name(raw):
    # Remove date, zedle, where, supplier, se3er, unit, $, kilo numbers
    name = raw.upper()
    name = re.sub(r"\d+\s*(?:OCT|NOV)", "", name)  # Remove 22 OCT, 5 NOV
    name = re.sub(r"ZEDLE", "", name)
    name = re.sub(r"\b\d{1,2}\b", "", name)  # Remove lone numbers like 22
    for bad in ["NOHRA","BERNARD","GHASSAN","BROUMANA","ANTELIAS","ADMA","BAABDA","SAMAK","SE3ER","UNIT","$","KILO","KG","SE3R"]:
        name = name.replace(bad,"")
    name = re.sub(r"\$?\d+(\.\d+)?", "", name)  # Remove $10, 10$
    name = " ".join(name.split()).strip()
    return name

def detect_intent(text):
    if len(text) > 1500: return "ignore"
    if "def " in text and "return" in text: return "ignore"
    t = text.lower()
    if any(w in t for w in ["msah","delete","remove","cancel","shil","emsah"]): return "delete"
    if any(w in t for w in ["update","change","ghayir","badil"," to "," -> "]): return "update"
    if any(w in t for w in ["kg","kilo","ghobbos","ajej","bra2","lo2os","frafir","sultan","samak","zedle"]): return "add"
    return "general"

async def download_whatsapp_media(media_id):
    env = get_env()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"https://graph.facebook.com/v19.0/{media_id}", headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"})
            data = r.json()
            media_url = data.get("url")
            if not media_url: return None
            r2 = await c.get(media_url, headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"})
            return r2.content
    except: return None

async def transcribe_voice(media_id):
    env = get_env()
    if not env["OPENAI_KEY"]: return None
    try:
        content = await download_whatsapp_media(media_id)
        if not content: return None
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(content); temp_path = f.name
        async with httpx.AsyncClient(timeout=40) as c:
            with open(temp_path, "rb") as af:
                r = await c.post("https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"},
                    files={"file": (temp_path, af, "audio/ogg")}, data={"model": "whisper-1", "language": "ar"})
                return r.json().get("text","")
    except Exception as e:
        print(f"Voice error: {e}"); return None

async def read_image_text(media_id, caption=""):
    env = get_env()
    if not env["OPENAI_KEY"]: return caption
    try:
        content = await download_whatsapp_media(media_id)
        if not content: return caption
        b64 = base64.b64encode(content).decode()
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini","messages": [{"role": "user","content": [
                    {"type": "text","text": "Extract fish list. Return like: Zedle 22 oct nohra broumana sultan 5 kilo 10$ Ajej 20kilo 7$. Caption: "+caption},
                    {"type": "image_url","image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]})
            return r.json()["choices"][0]["message"]["content"]
    except: return caption

async def get_sheet_client():
    env = get_env()
    import gspread
    from google.oauth2.service_account import Credentials
    creds_dict = json.loads(env["GOOGLE_CREDS"].strip())
    creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    sheet = client.open_by_key(FISH_SHEET_ID)
    titles = [s.title for s in sheet.worksheets()]
    target = ""
    for tt in titles:
        if "profit" in tt.lower() and "daily" in tt.lower(): target=tt; break
    if not target: target = "Fish Supplies 2026" if "Fish Supplies 2026" in titles else titles[0]
    ws = sheet.worksheet(target)
    return ws, target

async def smart_sheet_action(text):
    intent = detect_intent(text)
    if intent=="ignore": return None
    try:
        ws, target = await get_sheet_client()
        all_values = ws.get_all_values()
        last_data_row = 1
        for i in range(len(all_values)-1, -1, -1):
            row = all_values[i]
            if len(row)>5 and (row[5].strip() or (len(row)>6 and row[6].strip())):
                last_data_row = i+1; break
        try:
            last_formulas = ws.get(f"A{last_data_row}:M{last_data_row}", value_render_option="FORMULA")[0]
            while len(last_formulas)<13: last_formulas.append("")
        except: last_formulas=[""]*13
        def smart_copy(formula, new_row):
            if not formula or "=" not in str(formula): return ""
            return str(formula).replace(str(last_data_row), str(new_row))

        # DELETE
        if intent=="delete":
            fm = re.search(r"(ghobbos|ajej|bra2|lo2os|frafir|sultan|bezri|filet|loz|jarbide|masta|ghazel|dakar|sarbout)", text.lower())
            if fm:
                ft = fm.group(1).upper()
                for i in range(len(all_values)-1,0,-1):
                    row = all_values[i]
                    if len(row)>6 and ft in row[6].upper():
                        ws.delete_rows(i+1); return f"✅ Deleted {ft} row {i+1}!"
                return f"❌ Ma la2et {ft}"
            return "❌ Eb3at: msah sultan"

        # UPDATE - FIXED to find last matching fish
        if intent=="update":
            fm = re.search(r"(ghobbos|ajej|bra2|lo2os|frafir|sultan|bezri|filet|loz|jarbide|masta|ghazel|dakar|sarbout)", text.lower())
            kilos = re.findall(r"(\d+(?:\.\d+)?)\s*k", text.lower())
            if fm and kilos:
                ft = fm.group(1).upper()
                new_kg = kilos[-1]
                for i in range(len(all_values)-1,0,-1):
                    row = all_values[i]
                    if len(row)>6 and ft in row[6].upper():
                        # Qtty column J = 10th column = index 9 but J is 10th letter
                        ws.update(f"J{i+1}", [[new_kg]], value_input_option="USER_ENTERED")
                        return f"✅ Updated {ft} to {new_kg}kg row {i+1}!"
                return f"❌ Ma la2et {ft}"
            return "❌ Eb3at: update sultan 5 kilo to 10 kilo"

        # ADD - FIXED PARSER
        lines = text.strip().split("\n")
        current_supplier = "Nohra"; date_str="21 Oct"; where="Broumana"; week="20 - 25 Oct"
        first_lower = lines[0].lower() if lines else ""
        dm = re.search(r"(\d+)\s*(?:nov|oct)", first_lower)
        if dm: date_str = dm.group(1).zfill(2) + " Oct"
        if "broumana" in first_lower: where="Broumana"
        if "antelias" in first_lower: where="Antelias"
        if "adma" in first_lower: where="Adma"
        if "baabda" in first_lower: where="Baabda"
        if "bernard" in first_lower: current_supplier="Bernard"
        if "nohra" in first_lower: current_supplier="Nohra"

        added=0; summary=[]
        for line in lines:
            orig = line.strip()
            if not orig: continue
            if len(orig)>300: continue
            low = orig.lower()
            if ":" in orig and "kilo" not in low[:40]:
                parts = orig.split(":",1)
                head = parts[0].lower()
                if "bernard" in head: current_supplier="Bernard"
                if "nohra" in head: current_supplier="Nohra"
                if "broumana" in head: where="Broumana"
                if "antelias" in head: where="Antelias"
                if "adma" in head: where="Adma"
                if "baabda" in head: where="Baabda"
                if len(parts)>1 and "kilo" in parts[1].lower():
                    orig = parts[1].strip(); low=orig.lower()
                else: continue
            km = re.search(r"(\d+(?:\.\d+)?)\s*k", low)
            if not km: continue
            kg = km.group(1)
            idx = low.find(km.group(0).lower())
            fish_raw = orig[:idx]
            if ":" in fish_raw: fish_raw = fish_raw.split(":")[-1]
            fish_clean = clean_fish_name(fish_raw)
            if not fish_clean: continue
            if len(fish_clean)>20: fish_clean = fish_clean.split()[-1]  # Take last word if still long like "22 OCT SULTAN" -> SULTAN
            price=""
            pm = re.search(r"(\d+(?:\.\d+)?)\$", orig)
            if pm: price = "$"+pm.group(1)
            new_row_num = last_data_row+added+1
            row=[""]*13
            row[0]=week; row[1]=date_str; row[2]=where
            row[3]=smart_copy(last_formulas[3], new_row_num) if len(last_formulas)>3 else ""
            row[4]=smart_copy(last_formulas[4], new_row_num) if len(last_formulas)>4 else ""
            row[5]=current_supplier; row[6]=fish_clean; row[7]=price; row[9]=kg
            if len(last_formulas)>10: row[10]=smart_copy(last_formulas[10], new_row_num)
            if len(last_formulas)>11: row[11]=smart_copy(last_formulas[11], new_row_num)
            if len(last_formulas)>12: row[12]=smart_copy(last_formulas[12], new_row_num)
            ws.update(f"A{new_row_num}:M{new_row_num}", [row], value_input_option="USER_ENTERED")
            added+=1; summary.append(fish_clean+" "+kg+"kg")
        if added==0: return None
        return "Zedle "+str(added)+" samak! "+" + ".join(summary)+" - "+where+" "+current_supplier+" "+date_str
    except Exception as e:
        traceback.print_exc(); return "Error: "+str(e)[:400]

app=FastAPI()
@app.get("/")
async def root(): return HTMLResponse("<h2>Nohra SMART - Fixed parser 22 oct = DATE not fish</h2>")
@app.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode"); token = request.query_params.get("hub.verify_token"); challenge = request.query_params.get("hub.challenge")
    if mode=="subscribe" and token==VERIFY_TOKEN: return PlainTextResponse(content=challenge or "", status_code=200)
    from fastapi import HTTPException; raise HTTPException(status_code=403)

@app.post("/webhook/whatsapp")
async def receive_message(request: Request):
    body = await request.json(); print(body)
    try:
        val = body["entry"][0]["changes"][0]["value"]
        if "messages" not in val: return {"ok": True}
        msg = val["messages"][0]; from_num=msg["from"]; msg_type=msg.get("type","text"); text=""
        if msg_type=="text": text=msg["text"]["body"]
        elif msg_type in ["audio","voice"]: 
            media_id = msg[msg_type]["id"]
            transcribed = await transcribe_voice(media_id)
            text = transcribed if transcribed else ""
        elif msg_type=="image":
            media_id=msg["image"]["id"]; caption=msg["image"].get("caption","")
            text = await read_image_text(media_id, caption)
        else: text=msg.get("text",{}).get("body","Hello")
        if not text: return {"ok": True}
        print(f"Processing ({msg_type}): {text[:300]}")
        reply = await smart_sheet_action(text)
        if not reply:
            env=get_env()
            if env["OPENAI_KEY"] and detect_intent(text)=="general":
                try:
                    async with httpx.AsyncClient(timeout=20) as c:
                        r=await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"},
                            json={"model":"gpt-4o-mini","messages":[{"role":"user","content":f"You are Nohra personal assistant, reply short Arabizi: {text}"}]})
                        reply=r.json()["choices"][0]["message"]["content"][:500]
                except: reply="OK Nohra"
            else: reply="Ma fhemet: "+text[:100]
        env=get_env()
        if env["WHATSAPP_TOKEN"]:
            async with httpx.AsyncClient(timeout=20) as c2:
                url=f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages"
                headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"}
                payload={"messaging_product":"whatsapp","to":from_num,"type":"text","text":{"body": reply[:1000]}}
                await c2.post(url, headers=headers, json=payload)
        return {"sent": True}
    except Exception as e: traceback.print_exc(); return {"error": str(e)}
