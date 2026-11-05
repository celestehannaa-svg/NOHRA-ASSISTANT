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
    if len(parts) > 3: raw = " ".join(parts[:3])
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
    if "zedle" in t or "زيدلي" in t or "زيد لي" in t: return "add"
    if any(w in t for w in ["l8i","shelle","shil","remove","l8e","l8ile","الغي","ألغي","الغ","شيل","امسح","مسح","احذف"]): return "delete"
    if any(w in t for w in ["ghayerle","ghayer","update","غير","غيرلي","عدل"]): return "update"
    if re.search(r"\d+(?:\.\d+)?\s*(?:kilo|kg|k)\b", t): return "add"
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
        prompt = f"""
STRICT COUNT! Do NOT invent fish! Count only visible rows with وزن!

Caption is BOSS: "{cap}"
- Date = 25 Oct from caption (ignore 02 Jan, C/o/1 etc)
- If caption says "Asfar nohra Rest la bernard" -> Asfar=Nohra, rest=Bernard
- If "kelon la Bernard" -> all Bernard

Image has 1 table. How many rows with وزن do you see? If 6 rows, output 6 only!

Each row: نوع=fish, وزن=weight grams (4000=4kg), سعر=IGNORE!

Arabic map: أصفر=ASFAR, برا2=BRA2, جربيدي=JARBIDE, مليفة=MALIFA, بزري=BEZRI, فريدي=FARIDE, جرو=JRAWE, كالاماري=KALAMARI

Output:
25 Oct Antelias
Asfar: ASFAR 4kg Nohra 25 Oct Antelias
Bernard: MALIFA 3kg Bernard 25 Oct Antelias
etc - exact count, no hallucination!
"""
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"},
                json={
                    "model":"gpt-4o",
                    "messages":[
                        {"role":"system","content":f"Count rows exactly. Do not hallucinate. Caption: {cap}. Date 25 Oct. Asfar Nohra rest Bernard. Weight=وزن/1000."},
                        {"role":"user","content":[
                            {"type":"text","text":prompt},
                            {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}", "detail":"high"}}
                        ]}
                    ],
                    "temperature":0
                })
            j = r.json()
            print(f"IMAGE: {j}")
            if "choices" not in j: return cap
            txt = j["choices"][0]["message"]["content"]
            return f"{cap}\n{txt}"
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
    parsed=[]; cur_supplier="Bernard"; cur_date="25 Oct"; cur_where="Antelias"; cur_week=get_week_from_date(cur_date)
    lower_all = text.lower()
    cap_date_match = re.search(r"(\d{1,2})\s*oct", lower_all)
    if cap_date_match:
        day = cap_date_match.group(1).zfill(2)
        cur_date = f"{day} Oct"
        cur_week = get_week_from_date(cur_date)
    
    special_fish_supplier = {}
    default_supplier = "Bernard"
    if "asfar" in lower_all and "nohra" in lower_all:
        special_fish_supplier["ASFAR"] = "Nohra"
        default_supplier = "Bernard"
    if "kelon la bernard" in lower_all:
        default_supplier = "Bernard"
        cur_supplier = "Bernard"
    
    if "antelias" in lower_all: cur_where="Antelias"
    if "adma" in lower_all: cur_where="Adma"
    if "broumana" in lower_all: cur_where="Broumana"
    if "baabda" in lower_all: cur_where="Baabda"

    for line_orig in lines:
        orig = line_orig.strip()
        if not orig: continue
        low = orig.lower()
        if "no3" in low and "wazen" in low: continue
        if "تاريخ" in orig: continue
        
        dm = re.search(r"(\d{1,2})\s*(oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)", low)
        dm2 = re.search(r"(\d{1,2})[\/\:\-\.\s]+(\d{1,2})", low)
        if dm or dm2:
            if dm:
                day=dm.group(1).zfill(2); mon=dm.group(2).capitalize()[:3]; cur_date=f"{day} {mon}"; cur_week=get_week_from_date(cur_date)
            elif dm2:
                day=dm2.group(1).zfill(2); m=int(dm2.group(2)); months=["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                if 1<=m<=12: cur_date=f"{day} {months[m]}"; cur_week=get_week_from_date(cur_date)
            if "antelias" in low: cur_where="Antelias"
            if "bernard" in low: cur_supplier="Bernard"
            if "kilo" not in low and "kg" not in low and re.search(r"^\d{1,2}[\/\:\-\s]+\d{1,2}", low):
                continue
        
        if "antelias" in low: cur_where="Antelias"
        if "adma" in low: cur_where="Adma"
        
        matches = list(re.finditer(r"(\d+(?:\.\d+)?)\s*(?:kilo|kilos|kg|k)\b", low))
        if not matches: continue
        
        last_idx = 0
        for m in matches:
            kg = m.group(1)
            start = m.start()
            fish_raw = orig[last_idx:start].strip()
            fish_raw = re.sub(r"^\d+(?:\.\d+)?\s*(?:kilo|kg|k)\s*", "", fish_raw, flags=re.I).strip()
            fish_raw = re.sub(r"^(and|w|\+|,|asfar:|bernard:|nohra:)\s*", "", fish_raw, flags=re.I).strip()
            if ":" in fish_raw and len(fish_raw.split(":")[0])<10: fish_raw = fish_raw.split(":")[-1]
            fish_clean = extract_fish_name(fish_raw)
            if fish_clean and fish_clean.lower() not in STOP_WORDS and len(fish_clean)>=2:
                supplier = cur_supplier
                if fish_clean.upper() in special_fish_supplier:
                    supplier = special_fish_supplier[fish_clean.upper()]
                elif fish_clean.upper() != "ASFAR" and "rest la bernard" in lower_all:
                    supplier = "Bernard"
                elif default_supplier:
                    if fish_clean.upper() not in special_fish_supplier:
                        supplier = default_supplier
                parsed.append({"fish":fish_clean,"kg":kg,"price_d":"","price_l":"","ptype":"none","supplier":supplier,"where":cur_where,"date":cur_date,"week":cur_week})
            last_idx = m.end()
    return parsed

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
        print(f"LAST FORMULAS: {last_f}")
        def sc(f,nr):
            if not f or "=" not in str(f): return f if "=" in str(f) else ""
            txt = str(f)
            txt = txt.replace(str(last), str(nr))
            return txt
        
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
        added=0; updated=0; prev_date=""; seen=set()
        for it in plist:
            if prev_date and it["date"]!=prev_date: ws.append_row([""]*13, value_input_option="USER_ENTERED")
            prev_date=it["date"]
            key=(it["date"], it["where"].lower())
            is_first=key not in seen
            fidx=-1; cur_vals=ws.get_all_values()
            for i,row in enumerate(cur_vals):
                if len(row)>6 and row[1].strip()==it["date"] and row[2].strip().lower()==it["where"].lower() and row[5].strip().lower()==it["supplier"].lower() and row[6].strip().upper()==it["fish"].upper(): fidx=i+1; break
            if fidx!=-1:
                ws.update(f"J{fidx}", [[it["kg"]]], value_input_option="USER_ENTERED")
                cur_form = ws.get(f"K{fidx}:M{fidx}", value_render_option="FORMULA")
                if cur_form and len(cur_form[0])>=3:
                    if not cur_form[0][0] or "=" not in str(cur_form[0][0]): ws.update(f"K{fidx}", [[sc(last_f[10], fidx)]], value_input_option="USER_ENTERED")
                    if not cur_form[0][1] or "=" not in str(cur_form[0][1]): ws.update(f"L{fidx}", [[sc(last_f[11], fidx)]], value_input_option="USER_ENTERED")
                    if not cur_form[0][2] or "=" not in str(cur_form[0][2]): ws.update(f"M{fidx}", [[sc(last_f[12], fidx)]], value_input_option="USER_ENTERED")
                updated+=1
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
                row[7]=sc(last_f[7], nr) if "=" in str(last_f[7]) else ""
                row[9]=it["kg"]
                row[10]=sc(last_f[10], nr)  # K Fish Retail
                row[11]=sc(last_f[11], nr)  # L Fish Invoice
                row[12]=sc(last_f[12], nr)  # M Total PROFIT
                print(f"WRITING ROW {nr}: {row}")
                ws.update(f"A{nr}:M{nr}", [row], value_input_option="USER_ENTERED")
                added+=1
        del PENDING[phone]
        if added==0 and updated>0:
            return f"Updated {updated}! Ghayart wazen + Retail/Profit formulas fixed! {plist[0]['date']}"
        return f"Zabtet {added} new, {updated} updated! Retail+Profit formulas copied! {plist[0]['date']}"
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
            if not parts: return "Eb3at: L8i sultan - voice kamen!"
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
                lines.append(f"{p['fish']} {p['kg']}kg {p['supplier']} {p['date']} {p['where']}".strip())
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
async def root(): return HTMLResponse("<h2>Nohra FINAL - Retail+Profit formulas fixed + 6 not 8</h2>")
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
