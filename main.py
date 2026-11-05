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

STOP_WORDS = ["nohra","bernard","broumana","antelias","adma","baabda","samak","se3er","unit","$","kilo","kg","lbp","zedle"]

def extract_fish_name(raw):
    raw = raw.strip()
    if not raw: return ""
    raw = re.sub(r"\d+\s*(?:oct|nov)", "", raw, flags=re.I)
    raw = raw.upper()
    for bad in ["NOHRA","BERNARD","BROUMANA","ANTELIAS","ADMA","BAABDA","SAMAK","SE3ER","UNIT","$","KILO","KG","LBP","L.L","ZEDLE","GHAYER","GHAYERLE","L8I","SHELLE","SHIL","REMOVE","UPDATE"]:
        raw = raw.replace(bad,"")
    raw = re.sub(r"\$?\d+(\.\d+)?", "", raw)
    raw = " ".join(raw.split()).strip()
    parts = raw.split()
    if len(parts) > 2: raw = " ".join(parts[:2])
    return raw[:30]

def get_week_from_date(date_str):
    try:
        dt = datetime.strptime(date_str + " 2025", "%d %b %Y")
        weekday = dt.weekday()
        if weekday == 0: tuesday = dt + timedelta(days=1)
        else: tuesday = dt - timedelta(days=(weekday - 1))
        sunday = tuesday + timedelta(days=5)
        if tuesday.month == sunday.month:
            return f"{tuesday.day} - {sunday.day} {tuesday.strftime('%b')}"
        else:
            return f"{tuesday.day} {tuesday.strftime('%b')} - {sunday.day} {sunday.strftime('%b')}"
    except: return "28 Oct - 2 Nov"

def detect_intent(text):
    if len(text) > 1500: return "ignore"
    if "def " in text and "return" in text: return "ignore"
    t = text.lower().strip()
    if t in ["yes","y","ok","eh","na3am","YES","Yes","Y"]: return "yes_confirm"
    if t in ["no","n","la","la2","NO","No","N"]: return "no_confirm"
    
    # ADD = zedle
    if "zedle" in t: return "add"
    
    # REMOVE = L8i / shelle / shil / remove = SAME COMMAND
    remove_words = ["l8i", "shelle", "shil", "remove"]
    first = t.split()[0] if t.split() else ""
    if first in remove_words or any(t.startswith(w) for w in remove_words):
        return "delete"
    
    # UPDATE = ghayer / ghayerle / update = SAME COMMAND
    update_words = ["ghayerle", "ghayer", "update"]
    if first in update_words or any(t.startswith(w) for w in update_words):
        return "update"
    
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
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f: f.write(content); p=f.name
        async with httpx.AsyncClient(timeout=40) as c:
            with open(p, "rb") as af:
                r = await c.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"}, files={"file": (p, af, "audio/ogg")}, data={"model": "whisper-1", "language": "ar"})
                return r.json().get("text","")
    except: return None

async def read_image(media_id, cap=""):
    env = get_env()
    if not env["OPENAI_KEY"]: return cap
    try:
        content = await download_media(media_id)
        if not content: return cap
        b64 = base64.b64encode(content).decode()
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"}, json={"model":"gpt-4o-mini","messages":[{"role":"user","content":[{"type":"text","text":"Extract fish like 'sultan 5kilo 3$' from image. Cap: "+cap},{"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}"}}]}]})
            return r.json()["choices"][0]["message"]["content"]
    except: return cap

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
    cur = "Nohra"; date_str="28 Oct"; where="Adma"
    first = lines[0].lower() if lines else ""
    dm = re.search(r"(\d+)\s*(?:oct|nov)", first)
    if dm: date_str = dm.group(1).zfill(2)+" Oct"
    if "broumana" in first: where="Broumana"
    if "antelias" in first: where="Antelias"
    if "adma" in first: where="Adma"
    if "baabda" in first: where="Baabda"
    if "bernard" in first: cur="Bernard"
    parsed=[]
    for line in lines:
        orig = line.strip()
        if not orig: continue
        if ":" in orig:
            parts = orig.split(":",1)
            head = parts[0].lower()
            if "bernard" in head: cur="Bernard"
            if "nohra" in head: cur="Nohra"
            if len(parts)>1 and "kilo" in parts[1].lower():
                orig = parts[1].strip()
            else:
                if len(parts)>1 and parts[1].strip()=="": continue
                if "kilo" not in orig.lower(): continue
        low = orig.lower()
        km = re.search(r"(\d+(?:\.\d+)?)\s*k", low)
        if not km: continue
        kg = km.group(1)
        idx = low.find(km.group(0).lower())
        fish_raw = orig[:idx]
        if ":" in fish_raw: fish_raw = fish_raw.split(":")[-1]
        fish_clean = extract_fish_name(fish_raw)
        if not fish_clean: continue
        if fish_clean.lower() in STOP_WORDS: continue
        price_d=""; price_l=""; ptype="none"
        pd = re.search(r"(\d+(?:\.\d+)?)\s*\$", orig)
        pd2 = re.search(r"\$\s*(\d+(?:\.\d+)?)", orig)
        pl = re.search(r"(\d+(?:\.\d+)?)\s*(?:lbp|l\.l|LL)", low)
        if pd: price_d="$"+pd.group(1); ptype="dollar"
        elif pd2: price_d="$"+pd2.group(1); ptype="dollar"
        elif pl: price_l=pl.group(1); ptype="lbp"
        else:
            ps = re.search(r"se3er\s+(\d+(?:\.\d+)?)", low)
            if ps:
                v=ps.group(1)
                try:
                    n=float(v)
                    if n>=1000: price_l=v; ptype="lbp"
                    else: price_d="$"+v; ptype="dollar"
                except: pass
        week = get_week_from_date(date_str)
        parsed.append({"fish":fish_clean,"kg":kg,"price_d":price_d,"price_l":price_l,"ptype":ptype,"supplier":cur,"where":where,"date":date_str,"week":week})
    return parsed

async def write_pending(phone):
    if phone not in PENDING: return "❌ Ma fi pending"
    plist = PENDING[phone]
    try:
        ws, target = await get_ws()
        vals = ws.get_all_values()
        forms = ws.get(f"A1:M{len(vals)}", value_render_option="FORMULA")
        date_where_exists=False; exist_g=None; exist_p=None
        check_key = (plist[0]["date"].strip(), plist[0]["where"].strip().lower())
        for i,row in enumerate(vals):
            if len(row)>2 and row[1].strip() and row[2].strip().lower():
                k = (row[1].strip(), row[2].strip().lower())
                if k == check_key:
                    date_where_exists=True
                    if len(row)>3 and row[3].strip() and not exist_g:
                        exist_g = forms[i][3] if len(forms[i])>3 else row[3]
                    if len(row)>4 and row[4].strip() and not exist_p:
                        exist_p = forms[i][4] if len(forms[i])>4 else row[4]
                    break
        last=1
        for i in range(len(vals)-1,-1,-1):
            r=vals[i]
            if len(r)>5 and (r[5].strip() or (len(r)>6 and r[6].strip())): last=i+1; break
        try:
            last_f = ws.get(f"A{last}:M{last}", value_render_option="FORMULA")[0]
            while len(last_f)<13: last_f.append("")
        except: last_f=[""]*13
        def sc(f,nr):
            if not f or "=" not in str(f): return ""
            return str(f).replace(str(last), str(nr))
        added=0; upd=0; summ=[]
        for idx,it in enumerate(plist):
            fidx=-1
            for i,row in enumerate(vals):
                if len(row)>6 and row[1].strip()==it["date"] and row[2].strip().lower()==it["where"].lower() and row[5].strip().lower()==it["supplier"].lower() and row[6].strip().upper()==it["fish"].upper():
                    fidx=i+1; break
            if fidx!=-1:
                ws.update(f"J{fidx}", [[it["kg"]]], value_input_option="USER_ENTERED")
                if it["ptype"]=="dollar" and it["price_d"]:
                    ws.update(f"H{fidx}", [[it["price_d"]]], value_input_option="USER_ENTERED")
                    ws.update(f"I{fidx}", [[""]], value_input_option="USER_ENTERED")
                elif it["ptype"]=="lbp" and it["price_l"]:
                    ws.update(f"I{fidx}", [[it["price_l"]]], value_input_option="USER_ENTERED")
                    ws.update(f"H{fidx}", [[f"=I{fidx}/89"]], value_input_option="USER_ENTERED")
                upd+=1; summ.append(f"{it['fish']} {it['kg']}kg")
            else:
                nr = len(ws.get_all_values())+1
                row=[""]*13
                row[0]=it["week"]; row[1]=it["date"]; row[2]=it["where"]
                if date_where_exists or idx>0: row[3]=""; row[4]=""
                else:
                    if exist_g: row[3]=exist_g.replace(str(last), str(nr)) if "=" in str(exist_g) else exist_g
                    else: row[3]=sc(last_f[3], nr) if len(last_f)>3 else ""
                    if exist_p: row[4]=exist_p.replace(str(last), str(nr)) if "=" in str(exist_p) else exist_p
                    else: row[4]=sc(last_f[4], nr) if len(last_f)>4 else ""
                row[5]=it["supplier"]; row[6]=it["fish"]
                if it["ptype"]=="dollar": row[7]=it["price_d"]; row[8]=""
                elif it["ptype"]=="lbp": row[8]=it["price_l"]; row[7]=f"=I{nr}/89"
                else: row[7]=sc(last_f[7], nr) if len(last_f)>7 else ""; row[8]=""
                row[9]=it["kg"]
                if len(last_f)>10: row[10]=sc(last_f[10], nr)
                if len(last_f)>11: row[11]=sc(last_f[11], nr)
                if len(last_f)>12: row[12]=sc(last_f[12], nr)
                ws.update(f"A{nr}:M{nr}", [row], value_input_option="USER_ENTERED")
                added+=1; summ.append(f"{it['fish']} {it['kg']}kg {it['supplier']}")
                date_where_exists=True
        del PENDING[phone]
        if upd>0 and added==0: return f"Updated {upd}! {' + '.join(summ)}"
        elif added>0 and upd>0: return f"Added {added} + Updated {upd}! {' + '.join(summ)}"
        else: return f"Zedle {added}! {' + '.join(summ)} - {plist[0]['where']} {plist[0]['date']}"
    except Exception as e:
        traceback.print_exc(); return f"Error: {e}"

async def handle(text, phone):
    intent = detect_intent(text)
    if intent=="ignore": return None
    if intent=="yes_confirm":
        if phone in PENDING: return await write_pending(phone)
        return "Ma fi pending"
    if intent=="no_confirm":
        if phone in PENDING: del PENDING[phone]; return "❌ Ok ma zedet"
        return "Ok"
    try:
        ws,_ = await get_ws()
        vals = ws.get_all_values()
        if intent=="delete":
            t = text.lower()
            target = t
            for w in ["l8i","shelle","shil","remove"]:
                target = target.replace(w, "")
            target = target.strip()
            target = re.sub(r"\d+\s*(?:oct|nov)", "", target).strip()
            for w in ["adma","broumana","antelias","baabda"]:
                target = target.replace(w, "")
            target = target.strip()
            parts = [p for p in target.split() if len(p)>=3]
            if not parts: return "Eb3at: L8i sultan, shelle mwasta, shil aarmout, remove bezri"
            search_term = parts[0].upper()
            search_term_full = (parts[0]+" "+parts[1]).upper() if len(parts)>=2 else search_term
            kilos = re.findall(r"(\d+(?:\.\d+)?)\s*k", t)
            is_return = "return" in t
            for search_try in [search_term, search_term_full]:
                for i in range(len(vals)-1,0,-1):
                    r=vals[i]
                    if len(r)>6 and search_try in r[6].upper():
                        if "oct" in t or "nov" in t:
                            dm = re.search(r"(\d+)\s*(?:oct|nov)", t)
                            if dm and len(r)>1 and dm.group(1).zfill(2) not in r[1]: continue
                        if "adma" in t and len(r)>2 and "adma" not in r[2].lower(): continue
                        if "broumana" in t and len(r)>2 and "broumana" not in r[2].lower(): continue
                        if "antelias" in t and len(r)>2 and "antelias" not in r[2].lower(): continue
                        if is_return and kilos:
                            try:
                                cur_q = float(r[9]) if len(r)>9 and r[9] else 0
                                ret_q = float(kilos[0])
                                new_q = cur_q - ret_q
                                if new_q <= 0:
                                    ws.delete_rows(i+1)
                                    return f"✅ Deleted {search_try} row {i+1}!"
                                else:
                                    ws.update(f"J{i+1}", [[str(new_q)]], value_input_option="USER_ENTERED")
                                    return f"✅ Updated {search_try} {new_q}kg row {i+1}!"
                            except:
                                ws.delete_rows(i+1)
                                return f"✅ Deleted {search_try} row {i+1}!"
                        else:
                            ws.delete_rows(i+1)
                            return f"✅ Deleted {search_try} row {i+1}!"
            return f"❌ Ma la2et {search_term}"
        if intent in ["add","update"]:
            parsed = parse_msg(text)
            if not parsed: return None
            PENDING[phone]=parsed
            lines=[]
            for p in parsed:
                if p["ptype"]=="dollar": pr=p["price_d"]
                elif p["ptype"]=="lbp": pr=p["price_l"]+" LBP"
                else: pr=""
                lines.append(f"{p['fish']} {p['kg']}kg {pr} {p['supplier']}".strip())
            summ="\n".join(lines)
            action = "Rah ghayir hek:" if intent=="update" else "Rah zid hek:"
            return f"{action}\n{summ}\nWhere: {parsed[0]['where']} Date: {parsed[0]['date']} Week: {parsed[0]['week']}\n\nConfirm? YES / NO"
    except Exception as e:
        traceback.print_exc(); return f"Error: {e}"
    return None

app=FastAPI()
@app.get("/")
async def root(): return HTMLResponse("<h2>Nohra FINAL - ADD zedle | REMOVE L8i shelle shil remove | UPDATE ghayer ghayerle</h2>")
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
        if not reply:
            env=get_env()
            if env["OPENAI_KEY"]:
                try:
                    async with httpx.AsyncClient(timeout=20) as c:
                        r=await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"}, json={"model":"gpt-4o-mini","messages":[{"role":"user","content":f"Reply short Arabizi: {txt}"}]})
                        reply=r.json()["choices"][0]["message"]["content"][:500]
                except: reply="OK Nohra"
            else: reply=None
            if not reply: return {"ok": True}
        env=get_env()
        if env["WHATSAPP_TOKEN"]:
            async with httpx.AsyncClient(timeout=20) as c2:
                url=f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages"
                headers={"Authorization": f"Bearer {env['WHATSAPP_TOKEN']}"}
                payload={"messaging_product":"whatsapp","to":frm,"type":"text","text":{"body": reply[:1000]}}
                await c2.post(url, headers=headers, json=payload)
        return {"sent": True}
    except Exception as e: traceback.print_exc(); return {"error": str(e)}
