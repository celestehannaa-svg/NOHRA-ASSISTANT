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
    if gc.startswith("'") and gc.endswith("'"): gc=gc[1:-1]
    return {"WHATSAPP_TOKEN":os.getenv("WHATSAPP_TOKEN",""),"PHONE_ID":os.getenv("WHATSAPP_PHONE_NUMBER_ID","1349671541570540"),"OPENAI_KEY":os.getenv("OPENAI_API_KEY",""),"GOOGLE_CREDS":gc}

STOP=["nohra","bernard","broumana","antelias","adma","baabda","samak","se3er","unit","$","kilo","kg","lbp"]

def extract_fish_name(raw):
    raw=re.sub(r"\d+\s*(?:oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)","",raw,flags=re.I)
    raw=raw.upper()
    for b in ["NOHRA","BERNARD","BROUMANA","ANTELIAS","ADMA","BAABDA","SAMAK","SE3ER","UNIT","$","KILO","KG","LBP","L.L","ZEDLE","GHAYER","L8I","SHELLE","SHIL","REMOVE","UPDATE"]:
        raw=raw.replace(b,"")
    raw=re.sub(r"\$?\d+(\.\d+)?","",raw)
    raw=" ".join(raw.split()).strip()
    parts=raw.split()
    if len(parts)>3: raw=" ".join(parts[:3])
    return raw[:30]

def get_week_from_date(d):
    try:
        dt=datetime.strptime(d+" 2026","%d %b %Y")
        wd=dt.weekday()
        tue=dt+timedelta(days=1) if wd==0 else dt-timedelta(days=(wd-1))
        sun=tue+timedelta(days=5)
        if tue.month==sun.month: return f"{tue.day}-{sun.day} {tue.strftime('%b')}"
        else: return f"{tue.day} {tue.strftime('%b')}-{sun.day} {sun.strftime('%b')}"
    except: return f"{d} Week"

def detect_intent(t):
    if len(t)>1500: return "ignore"
    if "def " in t and "return" in t: return "ignore"
    s=t.lower().strip()
    if s in ["yes","y","ok","eh","na3am","aye","نعم","ايه"]: return "yes_confirm"
    if s in ["no","n","la","la2","لا"]: return "no_confirm"
    if "zedle" in s: return "add"
    if any(w in s for w in ["l8i","shelle","shil","remove","l8e","الغي","شيل","امسح"]): return "delete"
    if any(w in s for w in ["ghayerle","ghayer","update","غير","غيّر"]): return "update"
    if re.search(r"\d+(?:\.\d+)?\s*(?:kilo|kg|k|كيلو)\b",s): return "add"
    if any(w in s for w in ["asfar","malifa","sarghous","jrawe","abyad","aarmout","ghobbos","bezri","faride","bra2","lo2os","mwasta","sultan"]): return "add"
    return "general"

async def download_media(mid):
    env=get_env()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r=await c.get(f"https://graph.facebook.com/v19.0/{mid}",headers={"Authorization":f"Bearer {env['WHATSAPP_TOKEN']}"})
            url=r.json().get("url")
            if not url: 
                print("No url in media")
                return None
            r2=await c.get(url,headers={"Authorization":f"Bearer {env['WHATSAPP_TOKEN']}"})
            return r2.content
    except Exception as e:
        print(f"Download err {e}")
        return None

async def transcribe_voice(mid):
    env=get_env()
    if not env["OPENAI_KEY"]:
        print("No OPENAI_KEY")
        return None
    try:
        content=await download_media(mid)
        if not content: 
            print("Voice download failed")
            return None
        print(f"Voice size {len(content)}")
        with tempfile.NamedTemporaryFile(suffix=".ogg",delete=False) as f:
            f.write(content); p=f.name
        async with httpx.AsyncClient(timeout=90) as c:
            with open(p,"rb") as af:
                r=await c.post("https://api.openai.com/v1/audio/transcriptions",headers={"Authorization":f"Bearer {env['OPENAI_KEY']}"},files={"file":(p,af,"audio/ogg")},data={"model":"whisper-1","language":"ar","prompt":"Nohra fish Lebanese zedle l8i shelle ghayerle Asfar Malifa Jarbide Bra2 Bezri Faride Jrawe Kalamari Aarmout Sarghous Abyad Ghobbos Mwasta Sultan Bernard Nohra Antelias Adma Broumana Baabda kilo"})
                j=r.json()
                print(f"VOICE RAW:{j}")
                if "text" not in j:
                    print(f"Whisper no text {j}")
                    return None
                txt=j.get("text","").strip()
                if not txt:
                    return None
                txt=txt.replace("الغي","l8i").replace("شيل","shelle").replace("زيدلي","zedle").replace("زيد لي","zedle").replace("غيرلي","ghayerle").replace("غير لي","ghayerle").replace("نعم","yes").replace("لا","no").replace("كليو","kilo").replace("كيلو","kilo")
                txt=txt.replace("أصفر","Asfar").replace("مليفة","Malifa").replace("جربيدي","Jarbide").replace("برا","Bra2").replace("قريدس","Jrawe")
                print(f"VOICE CLEAN:{txt}")
                return txt
    except Exception as e:
        print(f"Voice err {e}"); traceback.print_exc(); return None

async def read_image(mid,cap=""):
    env=get_env()
    if not env["OPENAI_KEY"]: return cap
    try:
        content=await download_media(mid)
        if not content: return cap
        b64=base64.b64encode(content).decode()
        prompt=f"Caption is boss: {cap}. Count exact rows only, no hallucination. Weight=وزن column grams/1000. Map: ASFAR, BRA2, JARBIDE, MALIFA, BEZRI, FARIDE, JRAWE, KALAMARI"
        async with httpx.AsyncClient(timeout=45) as c:
            r=await c.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {env['OPENAI_KEY']}","Content-Type":"application/json"},json={"model":"gpt-4o","messages":[{"role":"system","content":f"Caption:{cap} Date 25 Oct Asfar Nohra rest Bernard Weight=وزن/1000"},{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}","detail":"high"}}]}],"temperature":0})
            j=r.json()
            print(f"IMG:{j}")
            if "choices" not in j: return cap
            return f"{cap}\n{j['choices'][0]['message']['content']}"
    except Exception as e:
        print(e); return cap

async def get_ws():
    env=get_env()
    import gspread
    from google.oauth2.service_account import Credentials
    creds=json.loads(env["GOOGLE_CREDS"].strip())
    creds=Credentials.from_service_account_info(creds,scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"])
    client=gspread.authorize(creds)
    sheet=client.open_by_key(FISH_SHEET_ID)
    titles=[s.title for s in sheet.worksheets()]
    target=""
    for tt in titles:
        if "profit" in tt.lower() and "daily" in tt.lower(): target=tt; break
    if not target: target=titles[0]
    return sheet.worksheet(target),target

def parse_msg(text):
    lines=text.strip().split("\n")
    parsed=[]; cur_sup="Bernard"; cur_date="25 Oct"; cur_where="Antelias"; cur_week=get_week_from_date(cur_date)
    low_all=text.lower()
    m=re.search(r"(\d{1,2})\s*oct",low_all)
    if m: cur_date=f"{m.group(1).zfill(2)} Oct"; cur_week=get_week_from_date(cur_date)
    special={}
    default="Bernard"
    if "asfar" in low_all and "nohra" in low_all: special["ASFAR"]="Nohra"
    if "antelias" in low_all: cur_where="Antelias"
    if "adma" in low_all: cur_where="Adma"
    if "broumana" in low_all: cur_where="Broumana"
    if "baabda" in low_all: cur_where="Baabda"
    if "nohra" in low_all and "bernard" not in low_all: default="Nohra"
    for orig in lines:
        orig=orig.strip()
        if not orig: continue
        low=orig.lower()
        if "no3" in low and "wazen" in low: continue
        dm=re.search(r"(\d{1,2})\s*(oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)",low)
        dm2=re.search(r"(\d{1,2})[\/\:\-\.\s]+(\d{1,2})",low)
        if dm: cur_date=f"{dm.group(1).zfill(2)} {dm.group(2).capitalize()[:3]}"; cur_week=get_week_from_date(cur_date)
        elif dm2:
            day=dm2.group(1).zfill(2); mm=int(dm2.group(2)); months=["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            if 1<=mm<=12: cur_date=f"{day} {months[mm]}"; cur_week=get_week_from_date(cur_date)
        matches=list(re.finditer(r"(\d+(?:\.\d+)?)\s*(?:kilo|kilos|kg|k)\b",low))
        if not matches: continue
        last=0
        for mm in matches:
            kg=mm.group(1); st=mm.start()
            fish_raw=orig[last:st].strip()
            fish_raw=re.sub(r"^\d+(?:\.\d+)?\s*(?:kilo|kg|k)\s*","",fish_raw,flags=re.I).strip()
            fish_raw=re.sub(r"^(and|w|\+|,|asfar:|bernard:|nohra:)\s*","",fish_raw,flags=re.I).strip()
            if ":" in fish_raw and len(fish_raw.split(":")[0])<10: fish_raw=fish_raw.split(":")[-1]
            fish_clean=extract_fish_name(fish_raw)
            if fish_clean and fish_clean.lower() not in [s.lower() for s in STOP] and len(fish_clean)>=2:
                sup=cur_sup
                if fish_clean.upper() in special: sup=special[fish_clean.upper()]
                elif fish_clean.upper()!="ASFAR" and "rest la bernard" in low_all: sup="Bernard"
                elif default and fish_clean.upper() not in special: sup=default
                parsed.append({"fish":fish_clean,"kg":kg,"supplier":sup,"where":cur_where,"date":cur_date,"week":cur_week})
            last=mm.end()
    return parsed

async def write_pending(phone):
    if phone not in PENDING: return "Ma fi pending"
    plist=PENDING[phone]
    try:
        ws,target=await get_ws(); vals=ws.get_all_values(); forms=ws.get(f"A1:M{len(vals)}",value_render_option="FORMULA")
        last=1
        for i in range(len(vals)-1,-1,-1):
            r=vals[i]
            if len(r)>5 and (r[5].strip() or (len(r)>6 and r[6].strip())): last=i+1; break
        try: last_f=ws.get(f"A{last}:M{last}",value_render_option="FORMULA")[0]
        except: last_f=[""]*13
        while len(last_f)<13: last_f.append("")
        def sc(f,nr):
            if not f or "=" not in str(f): return f if "=" in str(f) else ""
            return str(f).replace(str(last),str(nr))
        last_g=""; last_g_r=0; last_p=""; last_p_r=0
        for i in range(len(forms)-1,-1,-1):
            if len(forms[i])>3 and forms[i][3].strip() and "SUM" in forms[i][3].upper():
                if not last_g: last_g=forms[i][3]; last_g_r=i+1
            if len(forms[i])>4 and forms[i][4].strip() and "SUM" in forms[i][4].upper():
                if not last_p: last_p=forms[i][4]; last_p_r=i+1
            if last_g and last_p: break
        existing=set()
        for r in vals:
            if len(r)>2 and r[1].strip() and r[2].strip(): existing.add((r[1].strip(),r[2].strip().lower()))
        added=0; updated=0; prev=""; seen=set()
        for it in plist:
            if prev and it["date"]!=prev: ws.append_row([""]*13,value_input_option="USER_ENTERED")
            prev=it["date"]
            key=(it["date"],it["where"].lower())
            is_first=key not in seen
            fidx=-1; cur_vals=ws.get_all_values()
            for i,row in enumerate(cur_vals):
                if len(row)>6 and row[1].strip()==it["date"] and row[2].strip().lower()==it["where"].lower() and row[5].strip().lower()==it["supplier"].lower() and row[6].strip().upper()==it["fish"].upper(): fidx=i+1; break
            if fidx!=-1:
                ws.update(f"J{fidx}",[[it["kg"]]],value_input_option="USER_ENTERED")
                cf=ws.get(f"K{fidx}:M{fidx}",value_render_option="FORMULA")
                if cf:
                    if not cf[0][0]: ws.update(f"K{fidx}",[[sc(last_f[10],fidx)]],value_input_option="USER_ENTERED")
                    if not cf[0][1]: ws.update(f"L{fidx}",[[sc(last_f[11],fidx)]],value_input_option="USER_ENTERED")
                    if not cf[0][2]: ws.update(f"M{fidx}",[[sc(last_f[12],fidx)]],value_input_option="USER_ENTERED")
                updated+=1
            else:
                nr=len(ws.get_all_values())+1; row=[""]*13; row[0]=it["week"]; row[1]=it["date"]; row[2]=it["where"]
                if is_first and key not in existing:
                    row[3]=last_g.replace(str(last_g_r),str(nr)) if last_g else sc(last_f[3],nr)
                    row[4]=last_p.replace(str(last_p_r),str(nr)) if last_p else sc(last_f[4],nr)
                else: row[3]=""; row[4]=""
                seen.add(key); existing.add(key)
                row[5]=it["supplier"]; row[6]=it["fish"]; row[7]=sc(last_f[7],nr) if "=" in str(last_f[7]) else ""; row[9]=it["kg"]
                row[10]=sc(last_f[10],nr); row[11]=sc(last_f[11],nr); row[12]=sc(last_f[12],nr)
                ws.update(f"A{nr}:M{nr}",[row],value_input_option="USER_ENTERED")
                added+=1
        del PENDING[phone]
        if added==0 and updated>0: return f"Updated {updated}! Wazen + Retail formulas fixed! {plist[0]['date']}"
        return f"Zabtet {added} new {updated} updated! Retail+Profit formulas copied! {plist[0]['date']}"
    except Exception as e:
        traceback.print_exc(); return f"Error:{e}"

async def handle(text,phone):
    print(f"HANDLE:{text}")
    if not text or len(text.strip())<2:
        return "Eh ma fehmet, eb3at voice wadih: Zedle Asfar 4 kilo 25 Oct Antelias Bernard"
    intent=detect_intent(text)
    print(f"INTENT:{intent}")
    if intent=="ignore": return None
    if intent=="yes_confirm":
        if phone in PENDING: return await write_pending(phone)
        return "Ma fi pending"
    if intent=="no_confirm":
        if phone in PENDING: del PENDING[phone]; return "Ok ma zedet"
        return "Ok"
    try:
        ws,_=await get_ws(); vals=ws.get_all_values()
        if intent=="delete":
            t=text.lower()
            for w in ["l8i","shelle","shil","remove","l8e","الغي","شيل","امسح"]: t=t.replace(w,"")
            t=re.sub(r"\d+\s*(?:oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)","",t).strip()
            for w in ["adma","broumana","antelias","baabda"]: t=t.replace(w,"")
            parts=[p for p in t.split() if len(p)>=3]
            if not parts: return "Eb3at: L8i sultan - voice kamen byemche!"
            st=parts[0].upper()
            for i in range(len(vals)-1,0,-1):
                r=vals[i]
                if len(r)>6 and st in r[6].upper(): ws.delete_rows(i+1); return f"Chilt {st} row {i+1}!"
            return f"Ma la2et {st}"
        if intent in ["add","update"]:
            parsed=parse_msg(text)
            if not parsed: 
                if any(w in text.lower() for w in ["asfar","malifa","sarghous","jrawe","abyad","aarmout"]):
                    return "Eh sem3et el samak bas ma fehmet el wazen, erja3 oul: Asfar 4 kilo 25 Oct Antelias Bernard - oul kilo wadih!"
                return "Eh ma fehmet, eb3at: Zedle sultan 5 kilo 25 Oct Antelias Bernard"
            PENDING[phone]=parsed; lines=[]
            for p in parsed: lines.append(f"{p['fish']} {p['kg']}kg {p['supplier']} {p['date']} {p['where']}")
            summ="\n".join(lines); dates=list(set([p["date"] for p in parsed]))
            return f"Rah zid hek - {len(parsed)} samke, Dates: {', '.join(dates)}:\n{summ}\n\nConfirm? YES / NO"
    except Exception as e:
        traceback.print_exc(); return f"Error:{e}"
    env=get_env()
    if env["OPENAI_KEY"]:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r=await c.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {env['OPENAI_KEY']}","Content-Type":"application/json"},json={"model":"gpt-4o-mini","messages":[{"role":"system","content":"You are Nohra Assistant. You MUST reply ONLY in Lebanese Arabizi using Latin letters. Use: eh, chou, kif, ma fehmet, zabtet, hek, wadih, erja3. NEVER use Arabic script, NEVER use Fusha Arabic. If user voice unclear say: Eh ma sem3tak mnih, erja3 oul: Zedle Asfar 4 kilo 25 Oct Antelias Bernard - oul el kilo wadih! Keep short 1-2 lines."},{"role":"user","content":text}]})
                j=r.json()
                txt=j["choices"][0]["message"]["content"][:400]
                if any("\u0600" <= ch <= "\u06FF" for ch in txt):
                    return "Eh ma fehmet, erja3 eb3at: Zedle Asfar 4 kilo 25 Oct Antelias Bernard - voice kamen!"
                return txt
        except Exception as e:
            print(e)
            return "Eh ma sem3tak mnih, erja3 oul: Zedle Asfar 4 kilo 25 Oct Antelias Bernard"
    return "Eh ma fehmet, eb3at: Zedle Asfar 4 kilo 25 Oct Antelias Bernard"

app=FastAPI()
@app.get("/")
async def root(): return HTMLResponse("<h2>Nohra FULL - Voice+Retail+Arabizi Only - LIVE</h2>")
@app.get("/webhook/whatsapp")
async def verify(request: Request):
    mode=request.query_params.get("hub.mode"); token=request.query_params.get("hub.verify_token"); chal=request.query_params.get("hub.challenge")
    if mode=="subscribe" and token==VERIFY_TOKEN: return PlainTextResponse(content=chal or "",status_code=200)
    from fastapi import HTTPException; raise HTTPException(status_code=403)
@app.post("/webhook/whatsapp")
async def receive(request: Request):
    body=await request.json(); print(body)
    try:
        val=body["entry"][0]["changes"][0]["value"]
        if "messages" not in val: return {"ok":True}
        msg=val["messages"][0]; frm=msg["from"]; mtype=msg.get("type","text"); txt=""
        if mtype=="text": txt=msg["text"]["body"]
        elif mtype in ["audio","voice"]: txt=await transcribe_voice(msg[mtype]["id"]) or ""
        elif mtype=="image": txt=await read_image(msg["image"]["id"],msg["image"].get("caption",""))
        else: txt=msg.get("text",{}).get("body","Hello")
        if not txt:
            print("Empty txt after transcription")
            txt="ma fehmet voice"
        reply=await handle(txt,frm)
        if not reply:
            return {"ok":True}
        print(f"REPLY:{reply}")
        env=get_env()
        if env["WHATSAPP_TOKEN"]:
            async with httpx.AsyncClient(timeout=20) as c2:
                url=f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages"
                headers={"Authorization":f"Bearer {env['WHATSAPP_TOKEN']}"}
                payload={"messaging_product":"whatsapp","to":frm,"type":"text","text":{"body":reply[:1500]}}
                r=c2.post(url,headers=headers,json=payload)
                resp=await r
                print(f"WA send {resp.status_code}")
        return {"sent":True}
    except Exception as e:
        traceback.print_exc(); return {"error":str(e)}
