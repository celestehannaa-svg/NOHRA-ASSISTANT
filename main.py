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

def detect_intent(text):
    if len(text) > 1500: 
        return "ignore"
    if "def " in text and "return" in text:
        return "ignore"
    t = text.lower()
    if any(w in t for w in ["msah","delete","remove","cancel","shil","emsah"]):
        return "delete"
    if any(w in t for w in ["update","change","ghayir","badil"," to "," -> "]):
        return "update"
    if any(w in t for w in ["kg","kilo","ghobbos","ajej","bra2","lo2os","frafir","samak","zedle"]):
        return "add"
    return "general"

async def download_whatsapp_media(media_id):
    env = get_env()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"https://graph.facebook.com/v19.0/{media_id}", headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"})
            data = r.json()
            media_url = data.get("url")
            if not media_url:
                return None
            r2 = await c.get(media_url, headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"})
            return r2.content
    except Exception as e:
        print(f"Download media error: {e}")
        return None

async def transcribe_voice(media_id):
    env = get_env()
    if not env["OPENAI_KEY"]:
        return None
    try:
        content = await download_whatsapp_media(media_id)
        if not content:
            return None
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(content)
            temp_path = f.name
        async with httpx.AsyncClient(timeout=40) as c:
            with open(temp_path, "rb") as audio_file:
                files = {"file": (temp_path, audio_file, "audio/ogg")}
                data = {"model": "whisper-1", "language": "ar"}
                r = await c.post("https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"},
                    files=files, data=data)
                result = r.json()
                print(f"Whisper result: {result}")
                return result.get("text","")
    except Exception as e:
        print(f"Voice error: {e}")
        traceback.print_exc()
        return None

async def read_image_text(media_id, caption=""):
    env = get_env()
    if not env["OPENAI_KEY"]:
        return caption
    try:
        content = await download_whatsapp_media(media_id)
        if not content:
            return caption
        b64 = base64.b64encode(content).decode()
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Read this image of fish supply list. Extract fish names like ghobbos, ajej, bra2, lo2os, frafir, sultan, etc with kilos and prices. Return ONLY in format: 'Zedle samak 5nov broumana nohra: ghobbos 5 kilo 5$ Ajej 30 kilo'. Keep Arabizi. If no fish, return empty. Caption is: " + caption},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                        ]
                    }],
                    "max_tokens": 500
                })
            result = r.json()
            text = result["choices"][0]["message"]["content"]
            print(f"Vision result: {text}")
            return text if text else caption
    except Exception as e:
        print(f"Image error: {e}")
        traceback.print_exc()
        return caption

async def get_sheet_client():
    env = get_env()
    import gspread
    from google.oauth2.service_account import Credentials
    creds_dict = json.loads(env["GOOGLE_CREDS"].strip())
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(FISH_SHEET_ID)
    all_titles = [s.title for s in sheet.worksheets()]
    target = ""
    for tt in all_titles:
        if "profit" in tt.lower() and "daily" in tt.lower():
            target = tt
            break
    if not target:
        target = "Fish Supplies 2026" if "Fish Supplies 2026" in all_titles else all_titles[0]
    ws = sheet.worksheet(target)
    return ws, target

async def smart_sheet_action(text):
    intent = detect_intent(text)
    if intent == "ignore":
        return None
    try:
        ws, target = await get_sheet_client()
        all_values = ws.get_all_values()
        # Find last data row (Fish column not empty)
        last_data_row = 1
        for i in range(len(all_values)-1, -1, -1):
            row = all_values[i]
            if len(row) > 5 and (row[5].strip() or (len(row)>6 and row[6].strip())):
                last_data_row = i+1
                break
        
        # GET formulas from last data row
        try:
            last_formulas = ws.get(f"A{last_data_row}:M{last_data_row}", value_render_option="FORMULA")[0]
            while len(last_formulas) < 13:
                last_formulas.append("")
        except:
            last_formulas = [""]*13

        def smart_copy(formula, new_row):
            if not formula or "=" not in str(formula):
                return ""
            f_str = str(formula)
            # Only replace last_data_row number with new_row number
            f_str = f_str.replace(str(last_data_row), str(new_row))
            return f_str

        # DELETE
        if intent == "delete":
            fish_match = re.search(r"(ghobbos|ajej|bra2|lo2os|frafir|sultan|bezri|filet|loz|jarbide|masta|ghazel|dakar|sarbout|dakr|msasta|ghzazel)", text.lower())
            date_match = re.search(r"(\d+)\s*(?:nov|oct)", text.lower())
            target_date = ""
            if date_match:
                target_date = date_match.group(1).zfill(2)
            if fish_match:
                fish_to_delete = fish_match.group(1).upper()
                deleted = 0
                # Search from bottom to top
                for i in range(len(all_values)-1, 0, -1):
                    row = all_values[i]
                    if len(row) > 6 and fish_to_delete in row[6].upper():
                        if target_date and len(row)>1 and target_date not in row[1]:
                            continue
                        ws.delete_rows(i+1)
                        deleted += 1
                        return f"✅ Deleted {fish_to_delete} row {i+1} from {target}!"
                return f"❌ Ma la2et {fish_to_delete} {target_date} to delete"
            return "❌ Shu baddak temsah? Eb3at: msah ghobbos 5 Nov"

        # UPDATE
        if intent == "update":
            fish_match = re.search(r"(ghobbos|ajej|bra2|lo2os|frafir|sultan|bezri|filet|loz|jarbide|masta|ghazel|dakar|sarbout)", text.lower())
            kilos = re.findall(r"(\d+(?:\.\d+)?)\s*k", text.lower())
            # Format: update ghobbos 5 kilo to 10 kilo -> kilos = [5,10] -> new is last
            if fish_match and kilos:
                fish_to_update = fish_match.group(1).upper()
                new_kg = kilos[-1]
                for i in range(len(all_values)-1, 0, -1):
                    row = all_values[i]
                    if len(row) > 6 and fish_to_update in row[6].upper():
                        ws.update(f"J{i+1}", new_kg)  # Qtty column is J (index 9) -> J is 10th col
                        # Actually J = column 10 = Qtty
                        return f"✅ Updated {fish_to_update} to {new_kg}kg row {i+1}!"
                return f"❌ Ma la2et {fish_to_update} to update"
            return "❌ Eb3at: update ghobbos 5 kilo to 10 kilo"

        # ADD
        lines = text.strip().split("\n")
        current_supplier = "Nohra"
        date_str = "21 Oct"
        where = "Broumana"
        week = "20 - 25 Oct"
        first_lower = lines[0].lower() if lines else ""
        dm = re.search(r"(\d+)\s*(?:nov|oct)", first_lower)
        if dm:
            day = dm.group(1).zfill(2)
            date_str = day + " Oct"
        if "broumana" in first_lower: where = "Broumana"
        if "antelias" in first_lower: where = "Antelias"
        if "adma" in first_lower: where = "Adma"
        if "baabda" in first_lower: where = "Baabda"
        if "bernard" in first_lower: current_supplier = "Bernard"

        added = 0
        summary = []
        for line in lines:
            orig = line.strip()
            if not orig: continue
            low = orig.lower()
            if len(orig) > 300: continue
            if ":" in orig and "kilo" not in low[:35]:
                parts = orig.split(":",1)
                head = parts[0].lower()
                if "bernard" in head: current_supplier = "Bernard"
                if "nohra" in head: current_supplier = "Nohra"
                if "broumana" in head: where = "Broumana"
                if "antelias" in head: where = "Antelias"
                if "adma" in head: where = "Adma"
                if "baabda" in head: where = "Baabda"
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
            for bad in ["NOHRA","BERNARD","GHASSAN","BROUMANA","ANTELIAS","ADMA","BAABDA","ZEDLE","SAMAK","SE3ER","UNIT","$","KILO"]:
                fish_clean = fish_clean.replace(bad,"")
            fish_clean = " ".join(fish_clean.split()).strip()
            if not fish_clean: continue
            price = ""
            pm = re.search(r"(\d+(?:\.\d+)?)\$", orig)
            if pm: price = "$" + pm.group(1)

            new_row_num = last_data_row + added + 1
            row = [""]*13
            row[0]=week
            row[1]=date_str
            row[2]=where
            row[3]=smart_copy(last_formulas[3], new_row_num) if len(last_formulas)>3 else ""
            row[4]=smart_copy(last_formulas[4], new_row_num) if len(last_formulas)>4 else ""
            row[5]=current_supplier
            row[6]=fish_clean
            row[7]=price
            row[9]=kg
            if len(last_formulas)>10: row[10]=smart_copy(last_formulas[10], new_row_num)
            if len(last_formulas)>11: row[11]=smart_copy(last_formulas[11], new_row_num)
            if len(last_formulas)>12: row[12]=smart_copy(last_formulas[12], new_row_num)

            ws.update(f"A{new_row_num}:M{new_row_num}", [row], value_input_option="USER_ENTERED")
            added+=1
            summary.append(fish_clean + " " + kg + "kg")

        if added==0:
            return None
        return "Zedle " + str(added) + " samak! " + " + ".join(summary) + " - " + where + " " + current_supplier

    except Exception as e:
        tb = traceback.format_exc()
        print(tb)
        return "Error: " + str(e)[:400]

app = FastAPI()

@app.get("/")
async def root():
    return HTMLResponse("<h2>Nohra SMART - Voice + Pic + Update/Delete + Fixed Columns</h2>")

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
        msg_type = msg.get("type","text")
        text = ""
        if msg_type == "text":
            text = msg["text"]["body"]
        elif msg_type == "audio":
            media_id = msg["audio"]["id"]
            print(f"Audio received: {media_id}")
            transcribed = await transcribe_voice(media_id)
            if transcribed:
                text = transcribed
                print(f"Voice transcribed: {text}")
            else:
                text = "voice error"
        elif msg_type == "voice":
            media_id = msg["voice"]["id"]
            transcribed = await transcribe_voice(media_id)
            if transcribed:
                text = transcribed
            else:
                text = "voice error"
        elif msg_type == "image":
            media_id = msg["image"]["id"]
            caption = msg["image"].get("caption","")
            print(f"Image received: {media_id} caption: {caption}")
            image_text = await read_image_text(media_id, caption)
            text = image_text if image_text else caption
        else:
            text = msg.get("text",{}).get("body","Hello")

        if not text or text=="voice error":
            reply = "Ma fhemet voice/picture - jareb marra tenye"
        else:
            print(f"Processing ({msg_type}): {text[:300]}")
            reply = await smart_sheet_action(text)
            if not reply:
                # General chat with OpenAI
                env = get_env()
                if env["OPENAI_KEY"] and detect_intent(text)=="general":
                    try:
                        async with httpx.AsyncClient(timeout=20) as c:
                            r = await c.post("https://api.openai.com/v1/chat/completions",
                                headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"},
                                json={"model":"gpt-4o-mini","messages":[{"role":"user","content":f"You are Nohra personal assistant for Lebanese fish business. User speaks Arabizi. Reply short Arabizi same style. User says: {text}"}]})
                            reply = r.json()["choices"][0]["message"]["content"][:500]
                    except:
                        reply = "OK Nohra"
                else:
                    reply = "Ma fhemet: " + text[:100]

        env = get_env()
        if env["WHATSAPP_TOKEN"]:
            async with httpx.AsyncClient(timeout=20) as c2:
                url = f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages"
                headers = {"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"}
                payload = {"messaging_product":"whatsapp","to":from_num,"type":"text","text":{"body": reply[:1000]}}
                await c2.post(url, headers=headers, json=payload)
        return {"sent": True, "reply": reply}
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}
