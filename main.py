import os, json, re, traceback, tempfile, base64
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, HTMLResponse
from dotenv import load_dotenv
import httpx
load_dotenv()

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "nohra_verify_2024")
FISH_SHEET_ID = "1_U7Mz0eKj8x3nWDvCSkRXkDgyYIEhYupJNJ0-DSskss"
PENDING = {}

def get_env():
    load_dotenv(override=True)
    gc = os.getenv("GOOGLE_CREDENTIALS_JSON","")
    if gc.startswith("'") and gc.endswith("'"): gc = gc[1:-1]
    return {
        "WHATSAPP_TOKEN": os.getenv("WHATSAPP_TOKEN",""),
        "PHONE_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID","1349671541570540"),
        "OPENAI_KEY": os.getenv("OPENAI_API_KEY",""),
        "GOOGLE_CREDS": gc,
    }

FISH_LIST = ["ghobbos","ajej","bra2","lo2os","frafir","sultan","filet","bezri","loz","jarbide","masta","ghazel","dakar","sarbout","dakr","ghzazel","msasta","kalamari","serma","erna","mesaar","ghazal","sandou","aarmout"]

def extract_fish_name(raw):
    raw_low = raw.lower()
    for f in FISH_LIST:
        if f in raw_low: return f.upper()
    name = raw.upper()
    name = re.sub(r"\d+\s*(?:OCT|NOV)", "", name)
    name = re.sub(r"ZEDLE", "", name)
    for bad in ["NOHRA","BERNARD","GHASSAN","BROUMANA","ANTELIAS","ADMA","BAABDA","SAMAK","SE3ER","UNIT","$","KILO","KG","SE3R","LBP","L.L"]:
        name = name.replace(bad,"")
    name = re.sub(r"\$?\d+(\.\d+)?", "", name)
    name = " ".join(name.split()).strip()
    if len(name) > 15:
        parts = name.split()
        for p in reversed(parts):
            if len(p) >= 2: return p
    return name

def get_week_from_date(date_str):
    try:
        dt = datetime.strptime(date_str + " 2025", "%d %b %Y")
        weekday = dt.weekday()
        if weekday == 0: tuesday = dt - timedelta(days=6)
        else:
            days_since_tue = (weekday - 1) % 7
            tuesday = dt - timedelta(days=days_since_tue)
        sunday = tuesday + timedelta(days=5)
        if tuesday.month == sunday.month:
            return f"{tuesday.day} - {sunday.day} {tuesday.strftime('%b')}"
        else:
            return f"{tuesday.day} {tuesday.strftime('%b')} - {sunday.day} {sunday.strftime('%b')}"
    except: return "20 - 25 Oct"

def detect_intent(text):
    if len(text) > 1500: return "ignore"
    if "def " in text and "return" in text: return "ignore"
    t = text.lower().strip()
    if t in ["yes","y","ok","eh","na3am","yes yes","confirm","yes confirm","yep","yes "]: return "yes_confirm"
    if t in ["no","n","la","la2","cancel","msah","no no","no confirm"]: return "no_confirm"
    if any(w in t for w in ["msah","delete","remove","shil","emsah"]): return "delete"
    if any(w in t for w in ["update","change","ghayir","badil"," to "," -> "]): return "update"
    if any(w in t for w in ["kg","kilo"]): return "add"
    if any(f in t for f in FISH_LIST): return "add"
    return "general"

async def download_whatsapp_media(media_id):
    env = get_env()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"https://graph.facebook.com/v19.0/{media_id}", headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"})
            data = r.json(); media_url = data.get("url")
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
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f: f.write(content); temp_path = f.name
        async with httpx.AsyncClient(timeout=40) as c:
            with open(temp_path, "rb") as af:
                r = await c.post("https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"},
                    files={"file": (temp_path, af, "audio/ogg")}, data={"model": "whisper-1", "language": "ar"})
                return r.json().get("text","")
    except: return None

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
                    {"type": "text","text": "Extract fish list. Return like: Zedle 22 oct adma Nohra: sultan 5kilo 3$ Ajej 30 kilo 700000 lbp Bernard: bra2 20kilo Filet 10 kilo. Caption: "+caption},
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

def parse_fish_message(text):
    lines = text.strip().split("\n")
    current_supplier = "Nohra"
    date_str = "22 Oct"
    where = "Adma"
    first_lower = lines[0].lower() if lines else ""
    dm = re.search(r"(\d+)\s*(?:nov|oct)", first_lower)
    if dm: date_str = dm.group(1).zfill(2) + " Oct"
    if "broumana" in first_lower: where="Broumana"
    if "antelias" in first_lower: where="Antelias"
    if "adma" in first_lower: where="Adma"
    if "baabda" in first_lower: where="Baabda"
    if "bernard" in first_lower: current_supplier="Bernard"

    parsed = []
    for line in lines:
        orig = line.strip()
        if not orig: continue
        if ":" in orig:
            parts = orig.split(":",1)
            head = parts[0].lower()
            if "bernard" in head: current_supplier="Bernard"
            if "nohra" in head: current_supplier="Nohra"
            if len(parts)>1 and ("kilo" in parts[1].lower() or any(f in parts[1].lower() for f in FISH_LIST)):
                orig = parts[1].strip()
            else:
                if len(parts)>1 and parts[1].strip()=="": continue
                if "kilo" not in orig.lower() and not any(f in orig.lower() for f in FISH_LIST):
                    continue
        low = orig.lower()
        km = re.search(r"(\d+(?:\.\d+)?)\s*k", low)
        if not km: continue
        kg = km.group(1)
        idx = low.find(km.group(0).lower())
        fish_raw = orig[:idx]
        if ":" in fish_raw: fish_raw = fish_raw.split(":")[-1]
        fish_clean = extract_fish_name(fish_raw)
        if not fish_clean: continue
        
        # Price detection: $ vs LBP
        price_dollar = ""
        price_lbp = ""
        price_type = "none"
        # Check for $ price: se3er 3$ or $3 or 3$
        pm_dollar = re.search(r"(\d+(?:\.\d+)?)\s*\$", orig)
        pm_dollar2 = re.search(r"\$\s*(\d+(?:\.\d+)?)", orig)
        # Check for LBP price: 700 LBP, 700000 lbp, LBP 700
        pm_lbp = re.search(r"(\d+(?:\.\d+)?)\s*(?:lbp|l\.l|LL)", low)
        pm_lbp2 = re.search(r"(?:lbp|l\.l|LL)\s*(\d+(?:\.\d+)?)", low)
        
        if pm_dollar:
            price_dollar = "$" + pm_dollar.group(1)
            price_type = "dollar"
        elif pm_dollar2:
            price_dollar = "$" + pm_dollar2.group(1)
            price_type = "dollar"
        elif pm_lbp:
            price_lbp = pm_lbp.group(1)
            price_type = "lbp"
        elif pm_lbp2:
            price_lbp = pm_lbp2.group(1)
            price_type = "lbp"
        else:
            # If number before $ is missing, check if any number after se3er without $ and small (<100) -> treat as $
            # If big number >1000 without $ -> treat as LBP
            pm_se3er = re.search(r"se3er\s+(\d+(?:\.\d+)?)", low)
            if pm_se3er:
                val = pm_se3er.group(1)
                try:
                    num = float(val)
                    if num >= 1000:  # Likely LBP
                        price_lbp = val
                        price_type = "lbp"
                    else:  # Likely $
                        price_dollar = "$" + val
                        price_type = "dollar"
                except: pass

        week = get_week_from_date(date_str)
        parsed.append({"fish": fish_clean, "kg": kg, "price_dollar": price_dollar, "price_lbp": price_lbp, "price_type": price_type, "supplier": current_supplier, "where": where, "date_str": date_str, "week": week})
    return parsed

async def write_pending_to_sheet(phone):
    if phone not in PENDING or not PENDING[phone]:
        return "❌ Ma fi shi pending"
    pending_list = PENDING[phone]
    try:
        ws, target = await get_sheet_client()
        all_values = ws.get_all_values()
        all_formulas = ws.get(f"A1:M{len(all_values)}", value_render_option="FORMULA")

        # Find existing GHASSAN for same DATE+Where
        existing_ghassan = None
        existing_profit = None
        for i, row in enumerate(all_values):
            if len(row) > 2 and len(pending_list)>0:
                if row[1].strip() == pending_list[0]["date_str"] and row[2].strip().lower() == pending_list[0]["where"].lower():
                    if len(row) > 3 and row[3].strip():
                        existing_ghassan = all_formulas[i][3] if len(all_formulas[i])>3 else row[3]
                    if len(row) > 4 and row[4].strip():
                        existing_profit = all_formulas[i][4] if len(all_formulas[i])>4 else row[4]
                    if existing_ghassan: break

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

        added=0; updated=0; summary=[]
        for item in pending_list:
            # Check duplicate: same Fish + DATE + Where + supplier
            found_idx = -1
            for i, row in enumerate(all_values):
                if len(row) > 6:
                    if row[1].strip() == item["date_str"] and row[2].strip().lower() == item["where"].lower() and row[5].strip().lower() == item["supplier"].lower() and row[6].strip().upper() == item["fish"].upper():
                        found_idx = i+1  # 1-indexed
                        break
            if found_idx != -1:
                # UPDATE existing row - half info edit!
                # Update Qtty if provided
                ws.update(f"J{found_idx}", [[item["kg"]]], value_input_option="USER_ENTERED")
                # Update price based on type
                if item["price_type"] == "dollar" and item["price_dollar"]:
                    ws.update(f"H{found_idx}", [[item["price_dollar"]]], value_input_option="USER_ENTERED")
                    ws.update(f"I{found_idx}", [[""]], value_input_option="USER_ENTERED")  # Clear LBP
                elif item["price_type"] == "lbp" and item["price_lbp"]:
                    ws.update(f"I{found_idx}", [[item["price_lbp"]]], value_input_option="USER_ENTERED")
                    # Keep Fish Price as formula - copy from last_formulas if needed
                    if last_formulas[7] and "=" in str(last_formulas[7]):
                        ws.update(f"H{found_idx}", [[smart_copy(last_formulas[7], found_idx)]], value_input_option="USER_ENTERED")
                updated+=1
                summary.append(f"Updated {item['fish']} {item['kg']}kg")
            else:
                # ADD new row
                new_row_num = last_data_row+added+1 + updated  # careful
                # Recalculate last_data_row each time
                new_row_num = len(ws.get_all_values()) + 1
                row=[""]*13
                row[0]=item["week"]; row[1]=item["date_str"]; row[2]=item["where"]
                if existing_ghassan:
                    row[3]=existing_ghassan.replace(str(last_data_row), str(new_row_num)) if "=" in str(existing_ghassan) else existing_ghassan
                else:
                    row[3]=smart_copy(last_formulas[3], new_row_num) if len(last_formulas)>3 else ""
                if existing_profit:
                    row[4]=existing_profit.replace(str(last_data_row), str(new_row_num)) if "=" in str(existing_profit) else existing_profit
                else:
                    row[4]=smart_copy(last_formulas[4], new_row_num) if len(last_formulas)>4 else ""
                row[5]=item["supplier"]; row[6]=item["fish"]
                # Price handling: $ vs LBP
                if item["price_type"] == "dollar":
                    row[7]=item["price_dollar"]  # Fish Price $
                    row[8]=""  # LBP blank
                elif item["price_type"] == "lbp":
                    row[7]=smart_copy(last_formulas[7], new_row_num) if len(last_formulas)>7 and last_formulas[7] and "=" in str(last_formulas[7]) else ""  # Keep formula in $
                    row[8]=item["price_lbp"]  # LBP value
                else:
                    row[7]=smart_copy(last_formulas[7], new_row_num) if len(last_formulas)>7 else ""
                    row[8]=""
                row[9]=item["kg"]
                if len(last_formulas)>10: row[10]=smart_copy(last_formulas[10], new_row_num)
                if len(last_formulas)>11: row[11]=smart_copy(last_formulas[11], new_row_num)
                if len(last_formulas)>12: row[12]=smart_copy(last_formulas[12], new_row_num)
                ws.update(f"A{new_row_num}:M{new_row_num}", [row], value_input_option="USER_ENTERED")
                added+=1
                summary.append(f"{item['fish']} {item['kg']}kg {item['supplier']}")

        del PENDING[phone]
        if updated>0 and added==0:
            return f"Updated {updated} samak (no duplicate)! {' + '.join(summary)} - {pending_list[0]['where']} {pending_list[0]['date_str']}"
        elif added>0 and updated>0:
            return f"Added {added} + Updated {updated}! {' + '.join(summary)}"
        else:
            return f"Zedle {added} samak! {' + '.join(summary)} - {pending_list[0]['where']} {pending_list[0]['date_str']} Week {pending_list[0]['week']}"
    except Exception as e:
        traceback.print_exc(); return f"Error writing: {e}"

async def smart_sheet_action(text, phone):
    intent = detect_intent(text)
    if intent=="ignore": return None
    if intent=="yes_confirm":
        if phone in PENDING: return await write_pending_to_sheet(phone)
        else: return "Ma fi shi pending"
    if intent=="no_confirm":
        if phone in PENDING: del PENDING[phone]; return "❌ Ok ma zedet - eb3at list jdide"
        else: return "Ok"

    try:
        ws, target = await get_sheet_client()
        all_values = ws.get_all_values()

        if intent=="delete":
            fm = re.search(r"(ghobbos|ajej|bra2|lo2os|frafir|sultan|filet|bezri|loz|jarbide|masta|ghazel|dakar|sarbout)", text.lower())
            if fm:
                ft = fm.group(1).upper()
                for i in range(len(all_values)-1,0,-1):
                    row = all_values[i]
                    if len(row)>6 and ft in row[6].upper():
                        ws.delete_rows(i+1); return f"✅ Deleted {ft} row {i+1}!"
                return f"❌ Ma la2et {ft}"
            return "❌ Eb3at: msah sultan"

        if intent=="update":
            fm_all = re.findall(r"(ghobbos|ajej|bra2|lo2os|frafir|sultan|filet|bezri|loz|jarbide|masta|ghazel|dakar|sarbout)", text.lower())
            new_supplier = "Bernard" if "bernard" in text.lower() else "Nohra" if "nohra" in text.lower() else None
            kilos = re.findall(r"(\d+(?:\.\d+)?)\s*k", text.lower())
            if fm_all:
                updated=[]
                for fish in fm_all:
                    ft = fish.upper()
                    for i in range(len(all_values)-1,0,-1):
                        row = all_values[i]
                        if len(row)>6 and ft in row[6].upper():
                            if new_supplier: ws.update(f"F{i+1}", [[new_supplier]], value_input_option="USER_ENTERED")
                            if kilos: ws.update(f"J{i+1}", [[kilos[-1]]], value_input_option="USER_ENTERED")
                            updated.append(ft); break
                if updated: return f"✅ Updated {', '.join(updated)} to {new_supplier if new_supplier else ''} {kilos[-1]+'kg' if kilos else ''}"
                return f"❌ Ma la2et {', '.join(fm_all)}"
            return "❌ Eb3at: update bra2 for bernard"

        if intent=="add":
            parsed = parse_fish_message(text)
            if not parsed: return None
            PENDING[phone] = parsed
            lines = []
            for p in parsed:
                if p["price_type"]=="dollar": price_show = p["price_dollar"]
                elif p["price_type"]=="lbp": price_show = p["price_lbp"]+" LBP"
                else: price_show = "no price yet"
                lines.append(f"{p['fish']} {p['kg']}kg {price_show} {p['supplier']}")
            summary = "\n".join(lines)
            # Check duplicates preview
            dup_check = []
            for p in parsed:
                for row in all_values:
                    if len(row)>6 and row[1].strip()==p["date_str"] and row[2].strip().lower()==p["where"].lower() and row[5].strip().lower()==p["supplier"].lower() and row[6].strip().upper()==p["fish"].upper():
                        dup_check.append(p["fish"])
                        break
            dup_msg = f"\n⚠️ {', '.join(dup_check)} already exists - will UPDATE not duplicate!" if dup_check else ""
            return f"Rah zid hek:\n{summary}\nWhere: {parsed[0]['where']} Date: {parsed[0]['date_str']} Week: {parsed[0]['week']}{dup_msg}\n\nGHASSAN same for whole day {parsed[0]['where']} {parsed[0]['date_str']}\n\nConfirm? Eb3at YES aw NO"

    except Exception as e:
        traceback.print_exc(); return f"Error: {e}"
    return None

app=FastAPI()
@app.get("/")
async def root(): return HTMLResponse("<h2>Nohra SMART - No duplicate + LBP/$ formula + Week Tue-Sun + BRA2 + YES/NO</h2>")
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
        reply = await smart_sheet_action(text, from_num)
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
