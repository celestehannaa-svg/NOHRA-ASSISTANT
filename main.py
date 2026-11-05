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
    return {"WHATSAPP_TOKEN": os.getenv("WHATSAPP_TOKEN",""), "PHONE_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID","1349671541570540"), "OPENAI_KEY": os.getenv("OPENAI_API_KEY",""), "GOOGLE_CREDS": gc}

STOP_WORDS = ["nohra","bernard","broumana","antelias","adma","baabda","samak","se3er","unit","$","kilo","kg","lbp"]

def extract_fish_name(raw):
    raw = raw.strip()
    if not raw: return ""
    raw = re.sub(r"\d+\s*(?:oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)", "", raw, flags=re.I)
    raw = raw.upper()
    for bad in ["NOHRA","BERNARD","BROUMANA","ANTELIAS","ADMA","BAABDA","SAMAK","SE3ER","UNIT","$","KILO","KG","LBP","L.L","ZEDLE","GHAYER","GHAYERLE","L8I","SHELLE","SHIL","REMOVE","UPDATE","INVOICE"]:
        raw = raw.replace(bad,"")
    raw = re.sub(r"\$?\d+(\.\d+)?", "", raw)
    raw = " ".join(raw.split()).strip()
    parts = raw.split()
    if len(parts) > 2: raw = " ".join(parts[:2])
    return raw[:30]

def get_week_from_date(date_str):
    try:
        dt = datetime.strptime(date_str + " 2026", "%d %b %Y")
        weekday = dt.weekday()
        if weekday == 0: tuesday = dt + timedelta(days=1)
        else: tuesday = dt - timedelta(days=(weekday - 1))
        sunday = tuesday + timedelta(days=5)
        if tuesday.month == sunday.month: return f"{tuesday.day}-{sunday.day} {tuesday.strftime('%b')}"
        else: return f"{tuesday.day} {tuesday.strftime('%b')}-{sunday.day} {sunday.strftime('%b')}"
    except: return f"{date_str} Week"

def detect_intent(text):
    if len(text) > 1500: return "ignore"
    if "def " in text and "return" in text: return "ignore"
    t = text.lower().strip()
    if t in ["yes","y","ok","eh","na3am","أه","نعم","ايه"]: return "yes_confirm"
    if t in ["no","n","la","la2","لا"]: return "no_confirm"
    if "ghassan" in t and "formula" in t: return "ghassan_q"
    if "zedle" in t or "زيدلي" in t or "زيد لي" in t or "add" in t: return "add"
    remove_words = ["l8i","shelle","shil","remove","l8e","l8ile","الغي","ألغي","الغ","شيل","امسح","مسح","احذف"]
    if any(w in t for w in remove_words): return "delete"
    update_words = ["ghayerle","ghayer","update","غير","غيرلي","عدل"]
    if any(w in t for w in update_words): return "update"
    if re.search(r"\d+(?:\.\d+)?\s*k", t): return "add"
    return "general"

async def download_media(media_id):
    env = get_env()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"https://graph.facebook.com/v19.0/{media_id}", headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"})
            url = r.json().get("url")
            if not url: return None
            r2 = await c.get(url, headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"})
            return r2.content
    except: return None

async def transcribe_voice(media_id):
    env = get_env()
    if not env["OPENAI_KEY"]: return None
    try:
        content = await download_media(media_id)
        if not content: return None
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(content); p=f.name
        async with httpx.AsyncClient(timeout=60) as c:
            with open(p, "rb") as af:
                r = await c.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"}, files={"file": (p, af, "audio/ogg")}, data={"model": "whisper-1"})
                j = r.json()
                print(f"VOICE: {j}")
                text = j.get("text","")
                text = text.replace("الغي","l8i").replace("ألغي","l8i").replace("شيل","shelle").replace("امسح","l8i").replace("زيدلي","zedle").replace("غيرلي","ghayerle").replace("غير","ghayer")
                return text
    except Exception as e:
        print(f"Voice error {e}"); return None

async def read_image(media_id, cap=""):
    env = get_env()
    if not env["OPENAI_KEY"]: return cap
    try:
        content = await download_media(media_id)
        if not content: return cap
        b64 = base64.b64encode(content).decode()
        # SUPER DETAILED PROMPT FOR YOUR TABLES!
        prompt = f"""
You are reading Lebanese fish market receipts. There are 2 TABLES stacked vertically in this image. EACH TABLE = 1 DATE.

IMPORTANT LAYOUT:
- Each table has at bottom right: تاريخ = date like 24/10/24 or 25/10/25 -> means 24 Oct, 25 Oct
- Each table has 2 sides: left side = نوهرا (Nohra) column, right side = برنار (Bernard) column
- Fish under Nohra column = supplier Nohra, fish under Bernard column = Bernard
- Sometimes table uses only one side if full.

CAPTION OVERRIDE RULE - VERY IMPORTANT:
User caption: "{cap}"
If caption says "Antelias 24/10 kelon la Bernard" or "kelon la Bernard" -> ALL fish for date 24 Oct = Bernard, even if written under Nohra column!
If says "kelon la Nohra" -> all Nohra.

YOUR TASK:
1. For each table, read its تاريخ date
2. For each fish row, read نوع (fish type) and وزن (weight in kg)
3. Assign supplier correctly based on column, BUT override if caption says kelon la X for that date

Output EXACTLY like this (example for this image):
24 Oct Antelias
Bernard: MALIFA 8kg
Bernard: 3ROUSA 10kg
Bernard: SARGI 5kg
etc
25 Oct Antelias
Bernard: AHMAR 5kg
etc

Rules:
- Arabic date ٢٤/١٠ = 24 Oct, ٢٥/١٠ = 25 Oct (NOT 30 Oct!)
- Do not invent dates like 30 Oct
- List every fish you see, weight is number before or after fish name
- Use uppercase for fish: MALIFA, 3ROUSA, etc
- No refusal!
"""
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"},
                json={
                    "model":"gpt-4o",
                    "messages":[
                        {"role":"system","content":"You are a precise data entry clerk for fish receipts. Read handwritten Arabic dates and fish names. Never refuse. Each table is one date."},
                        {"role":"user","content":[
                            {"type":"text","text":prompt},
                            {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}", "detail":"high"}}
                        ]}
                    ]
                })
            j = r.json()
            print(f"IMAGE READ: {j}")
            if "choices" not in j:
                print(f"OPENAI ERROR: {j}")
                return cap
            text = j["choices"][0]["message"]["content"]
            return text
    except Exception as e:
        print(f"read_image error {e}"); traceback.print_exc(); return cap

async def get_ws():
    env = get_env()
    import gspread
    from google.oauth2.service_account import Credentials
    creds = json.loads(env["GOOGLE_CREDS"].strip())
    creds = Credentials.from_service_account_info(creds, scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    sheet = client.open_by_key(FISH_SHEET_ID)
    titles = [s.title for s in sheet.worksheets()]
    target = ""
    for tt in titles:
        if "profit" in tt.lower() and "daily" in tt.lower(): target=tt; break
    if not target: target = titles[0]
    return sheet.worksheet(target), target

def parse_msg(text):
    lines = text.strip().split("\n")
    parsed=[]; cur_supplier="Nohra"; cur_date="24 Oct"; cur_where="Antelias"; cur_week=get_week_from_date(cur_date)
    # Check for kelon override
    overrides = {}
    if "kelon" in text.lower():
        # Find dates mentioned in kelon context
        for m in re.finditer(r"(\d{1,2})[\/\s]*10.*?bernard", text.lower()):
            day = m.group(1)
            overrides[f"{day.zfill(2)} Oct"] = "Bernard"
        if "24" in text and "bernard" in text.lower():
            overrides["24 Oct"] = "Bernard"
    
    for line in lines:
        orig=line.strip()
        if not orig: continue
        low=orig.lower()
        # Date detection - handle both formats
        dm=re.search(r"(\d{1,2})\s*(oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)", low)
        dm2=re.search(r"(\d{1,2})[\/\.\s]+(\d{1,2})[\/\.\s]+\d{2,4}", low)
        dm3=re.search(r"(\d{1,2})\s+oct\s+antelias", low)
        if dm or dm2 or dm3:
            if dm: day=dm.group(1).zfill(2); mon=dm.group(2).capitalize()[:3]; cur_date=f"{day} {mon}"; cur_week=get_week_from_date(cur_date)
            elif dm3: day=dm3.group(1).zfill(2); cur_date=f"{day} Oct"; cur_week=get_week_from_date(cur_date)
            elif dm2:
                day=dm2.group(1).zfill(2); m=int(dm2.group(2)); months=["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                if 1<=m<=12: cur_date=f"{day} {months[m]}"; cur_week=get_week_from_date(cur_date)
            if "broumana" in low: cur_where="Broumana"
            if "antelias" in low: cur_where="Antelias"
            if "adma" in low: cur_where="Adma"
            if "baabda" in low: cur_where="Baabda"
            if "kilo" not in low and "kg" not in low and "antelias" not in low: 
                continue
        if "antelias" in low or "adma" in low or "broumana" in low or "baabda" in low:
            if "broumana" in low: cur_where="Broumana"
            if "antelias" in low: cur_where="Antelias"
            if "adma" in low: cur_where="Adma"
            if "baabda" in low: cur_where="Baabda"
            # If line is just location+date without kg, skip but keep context
            if "kilo" not in low and "kg" not in low and ":" not in orig:
                if re.search(r"^\d{1,2}\s+oct", low): continue
        
        if ":" in orig:
            parts=orig.split(":",1); head=parts[0].lower()
            if "bernard" in head: cur_supplier="Bernard"
            if "nohra" in head: cur_supplier="Nohra"
            if len(parts)>1:
                orig=parts[1].strip()
                if not orig: continue
        
        # Apply override for this date
        if cur_date in overrides:
            cur_supplier = overrides[cur_date]
        
        km=re.search(r"(\d+(?:\.\d+)?)\s*k", low)
        if not km: continue
        kg=km.group(1); idx=low.find(km.group(0).lower()); fish_raw=orig[:idx]
        if ":" in fish_raw: fish_raw=fish_raw.split(":")[-1]
        fish_clean=extract_fish_name(fish_raw)
        if not fish_clean or fish_clean.lower() in STOP_WORDS: continue
        price_d=""; price_l=""; ptype="none"
        pd=re.search(r"(\d+(?:\.\d+)?)\s*\$", orig)
        if pd: price_d="$"+pd.group(1); ptype="dollar"
        pl=re.search(r"(\d+(?:\.\d+)?)\s*(?:lbp|l\.l|ll|alf)", low)
        if pl and not price_d:
            val=pl.group(1)
            if "alf" in low and float(val)<1000: val=str(int(float(val)*1000))
            price_l=val; ptype="lbp"
        parsed.append({"fish":fish_clean,"kg":kg,"price_d":price_d,"price_l":price_l,"ptype":ptype,"supplier":cur_supplier,"where":cur_where,"date":cur_date,"week":cur_week})
    return parsed

def correct_pending(text, phone):
    if phone not in PENDING: return None
    return None

async def write_pending(phone):
    if phone not in PENDING: return "Ma fi pending"
    plist=PENDING[phone]
    def date_key(it):
        try: parts=it["date"].split(); day=int(parts[0]); mon_str=parts[1][:3].lower(); months={"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}; mon=months.get(mon_str,10); return (mon, day)
        except: return (10,99)
    plist=sorted(plist, key=lambda x: (date_key(x), x["where"]))
    try:
        ws,target=await get_ws(); vals=ws.get_all_values(); forms=ws.get(f"A1:M{len(vals)}", value_render_option="FORMULA")
        last=1
        for i in range(len(vals)-1,-1,-1):
            r=vals[i]
            if len(r)>5 and (r[5].strip() or (len(r)>6 and r[6].strip())): last=i+1; break
        try: last_f=ws.get(f"A{last}:M{last}", value_render_option="FORMULA")[0]
        except: last_f=[""]*13
        while len(last_f)<13: last_f.append("")
        def sc(f,nr):
            if not f or "=" not in str(f): return ""
            return str(f).replace(str(last), str(nr))
        last_g_formula=""; last_g_row=0; last_p_formula=""; last_p_row=0
        for i in range(len(forms)-1,-1,-1):
            if len(forms[i])>3 and forms[i][3].strip() and "SUM" in forms[i][3].upper():
                if not last_g_formula: last_g_formula=forms[i][3]; last_g_row=i+1
            if len(forms[i])>4 and forms[i][4].strip() and "SUM" in forms[i][4].upper():
                if not last_p_formula: last_p_formula=forms[i][4]; last_p_row=i+1
            if last_g_formula and last_p_formula: break
        existing_keys=set()
        for r in vals:
            if len(r)>2 and r[1].strip() and r[2].strip(): existing_keys.add((r[1].strip(), r[2].strip().lower()))
        added=0; prev_date=""; seen=set()
        for it in plist:
            if prev_date and it["date"]!=prev_date: ws.append_row([""]*13, value_input_option="USER_ENTERED")
            prev_date=it["date"]
            key=(it["date"], it["where"].lower())
            is_first=key not in seen
            fidx=-1; cur_vals=ws.get_all_values()
            for i,row in enumerate(cur_vals):
                if len(row)>6 and row[1].strip()==it["date"] and row[2].strip().lower()==it["where"].lower() and row[5].strip().lower()==it["supplier"].lower() and row[6].strip().upper()==it["fish"].upper(): fidx=i+1; break
            if fidx!=-1: ws.update(f"J{fidx}", [[it["kg"]]], value_input_option="USER_ENTERED")
            else:
                nr=len(ws.get_all_values())+1; row=[""]*13; row[0]=it["week"]; row[1]=it["date"]; row[2]=it["where"]
                if is_first and key not in existing_keys:
                    if last_g_formula: row[3]=last_g_formula.replace(str(last_g_row), str(nr))
                    else: row[3]=sc(last_f[3], nr)
                    if last_p_formula: row[4]=last_p_formula.replace(str(last_p_row), str(nr))
                    else: row[4]=sc(last_f[4], nr)
                else: row[3]=""; row[4]=""
                seen.add(key); existing_keys.add(key)
                row[5]=it["supplier"]; row[6]=it["fish"]
                if it["ptype"]=="dollar": row[7]=it["price_d"]
                elif it["ptype"]=="lbp": row[8]=it["price_l"]; row[7]=f"=I{nr}/89"
                else: row[7]=sc(last_f[7], nr) if len(last_f)>7 else ""
                row[9]=it["kg"]
                ws.update(f"A{nr}:M{nr}", [row], value_input_option="USER_ENTERED")
                added+=1
        del PENDING[phone]
        return f"Zabtet {added}! {plist[0]['date']} la {plist[-1]['date']}"
    except Exception as e: traceback.print_exc(); return f"Error: {e}"

async def handle(text, phone):
    print(f"HANDLE: {text}")
    intent=detect_intent(text)
    print(f"INTENT: {intent}")
    if intent=="ignore": return None
    if intent=="ghassan_q": return "Eh Ghassan column D hiye SUM formula, bt7seb total profit lal nhar, ma t2arba fiha!"
    if intent=="yes_confirm":
        if phone in PENDING: return await write_pending(phone)
        return "Ma fi pending"
    if intent=="no_confirm":
        if phone in PENDING: del PENDING[phone]; return "Ok ma zedet"
        return "Ok"
    try:
        ws,_=await get_ws(); vals=ws.get_all_values()
        if intent=="delete":
            t=text.lower(); target=t
            for w in ["l8i","shelle","shil","remove","l8e","l8ile","الغي","شيل","امسح","الغ"]: target=target.replace(w, "")
            target=target.strip(); target=re.sub(r"\d+\s*(?:oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)", "", target).strip()
            for w in ["adma","broumana","antelias","baabda"]: target=target.replace(w, "")
            target=target.strip(); parts=[p for p in target.split() if len(p)>=3]
            if not parts: return "Eb3at: L8i sultan"
            search_term=parts[0].upper()
            for i in range(len(vals)-1,0,-1):
                r=vals[i]
                if len(r)>6 and search_term in r[6].upper(): ws.delete_rows(i+1); return f"Chilt {search_term} row {i+1}!"
            return f"Ma la2et {search_term}"
        if intent in ["add","update"]:
            parsed=parse_msg(text)
            if not parsed: return "Eh ma fehmet, eb3at: zedle sultan 5 kilo - voice kamen!"
            PENDING[phone]=parsed; lines=[]
            for p in parsed:
                pr=p["price_d"] or (p["price_l"]+" LBP" if p["price_l"] else "")
                lines.append(f"{p['fish']} {p['kg']}kg {p['supplier']} {p['date']} {p['where']} {pr}".strip())
            summ="\n".join(lines); dates=list(set([p["date"] for p in parsed]))
            action=f"Rah zid hek - {len(parsed)} samke, Dates: {', '.join(dates)}:"
            return f"{action}\n{summ}\n\nConfirm? YES / NO"
    except Exception as e: traceback.print_exc(); return f"Error: {e}"
    env=get_env()
    if env["OPENAI_KEY"]:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r=await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"}, json={"model":"gpt-4o-mini","messages":[{"role":"system","content":"You are Nohra Assistant. Speak ONLY Lebanese Arabizi. Short 1-2 lines."},{"role":"user","content": text}]})
                return r.json()["choices"][0]["message"]["content"][:400]
        except: return "Eh ma fehmet"
    return "Eh ma fehmet"

app=FastAPI()
@app.get("/")
async def root(): return HTMLResponse("<h2>Nohra FINAL - 2 tables = 2 dates + kelon override</h2>")
@app.get("/webhook/whatsapp")
async def verify(request: Request):
    mode=request.query_params.get("hub.mode"); token=request.query_params.get("hub.verify_token"); chal=request.query_params.get("hub.challenge")
    if mode=="subscribe" and token==VERIFY_TOKEN: return PlainTextResponse(content=chal or "", status_code=200)
    from fastapi import HTTPException; raise HTTPException(status_code=403)
@app.post("/webhook/whatsapp")
async def receive(request: Request):
    body=await request.json(); print(body)
    try:
        val=body["entry"][0]["changes"][0]["value"]
        if "messages" not in val: return {"ok": True}
        msg=val["messages"][0]; frm=msg["from"]; mtype=msg.get("type","text"); txt=""
        if mtype=="text": txt=msg["text"]["body"]
        elif mtype in ["audio","voice"]: txt=await transcribe_voice(msg[mtype]["id"]) or ""
        elif mtype=="image": txt=await read_image(msg["image"]["id"], msg["image"].get("caption",""))
        else: txt=msg.get("text",{}).get("body","Hello")
        if not txt: return {"ok": True}
        reply=await handle(txt, frm)
        env=get_env()
        if env["WHATSAPP_TOKEN"]:
            async with httpx.AsyncClient(timeout=20) as c2:
                url=f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages"
                headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"}
                payload={"messaging_product":"whatsapp","to":frm,"type":"text","text":{"body": reply[:1500]}}
                await c2.post(url, headers=headers, json=payload)
        return {"sent": True}
    except Exception as e: traceback.print_exc(); return {"error": str(e)}
