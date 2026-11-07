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

FISH_MAP={
"عزتلي":"Azatli","عزتله":"Azatli",
"غساني":"Ghassani","غسانى":"Ghassani",
"غزال":"Ghazal","غزيل":"Ghazal",
"فيران":"Firan","فران":"Firan",
"بزري":"Bezri","بزرى":"Bezri",
"فيلي":"Filet","فيله":"Filet","فيليه":"Filet",
"أصفر":"Asfar","اصفر":"Asfar",
"مليفة":"Malifa","مليفه":"Malifa",
"جربيدي":"Jarbide","جربيدى":"Jarbide",
"برا":"Bra2","براق":"Bra2","برا بلادي":"Bra Balade",
"قريدس":"Jrawe","جراوي":"Jrawe",
"سلطان":"Sultan",
"غبوس":"Ghobbos","غبوص":"Ghobbos",
"سارغوس":"Sarghous",
"ابيض":"Abyad",
"ارموط":"Aarmout",
"لوء صخري":"Loq Sakhri","لو صخري":"Loq Sakhri","صخري":"Loq Sakhri",
"عجيج":"Ajej","عجاج":"Ajej","اجيج":"Ajej","اجاج":"Ajej",
"جدلا":"Jadla","جادلا":"Jadla",
"غزال بلدي":"Ghazil Baladi","غزيل بلدي":"Ghazil Baladi"
}

ARABIC_NUMS={"٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9","۰":"0","۱":"1","۲":"2","۳":"3","۴":"4","۵":"5","۶":"6","۷":"7","۸":"8","۹":"9"}
ARABIC_MONTHS={
"اكتوبر":"Oct","أكتوبر":"Oct","تشرين":"Oct","تشرين الاول":"Oct",
"نوفمبر":"Nov","تشرين الثاني":"Nov",
"ديسمبر":"Dec","كانون الاول":"Dec",
"يناير":"Jan","كانون الثاني":"Jan",
"سبتمبر":"Sep","ايلول":"Sep",
"اغسطس":"Aug","اب":"Aug",
"يوليو":"Jul","تموز":"Jul",
"يونيو":"Jun","حزيران":"Jun",
"مايو":"May","ايار":"May",
"ابريل":"Apr","نيسان":"Apr",
"مارس":"Mar","اذار":"Mar",
"فبراير":"Feb","شباط":"Feb"
}

EXACT_LOCK={"BRA":"BRA2","BRA2":"BRA2","BRA BALADE":"BRA BALADE","AJAJ":"AJEJ","AJEJ":"AJEJ","FILY":"FILET","FILET":"FILET","FILI":"FILET","GHASSANI":"GHASSANI","GHAZAL":"GHAZAL","BEZRI":"BEZRI","JADLA":"JADLA","AZATLI":"AZATLI"}

def to_arabizi_fast(text):
    for ar,en in ARABIC_NUMS.items():
        text=text.replace(ar,en)
    for ar,en in ARABIC_MONTHS.items():
        text=text.replace(ar,en)
    for ar,en in FISH_MAP.items():
        text=text.replace(ar,en)
    text=text.replace("التاريخ","Date").replace("تاريخ","Date").replace("مش","not").replace("ليس","not").replace("مو","not")
    text=text.replace("سبعة وعشرين","27").replace("سبعة وعشرون","27").replace("خمسة وعشرين","25").replace("خمسة وعشرون","25")
    return text

def extract_fish_name(raw):
    raw=re.sub(r"\d+\s*(?:oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)","",raw,flags=re.I)
    up=raw.upper()
    if "BRA" in up and "BALADE" not in up: up=up.replace("BRA","BRA2").replace("BRA22","BRA2")
    if "AJAJ" in up: up=up.replace("AJAJ","AJEJ")
    if "FILY" in up or "FILI" in up: up=up.replace("FILY","FILET").replace("FILI","FILET")
    raw=up
    for b in ["NOHRA","BERNARD","BROUMANA","ANTELIAS","ADMA","BAABDA","SAMAK","SE3ER","UNIT","$","KILO","KG","LBP","L.L","ZEDLE","GHAYER","L8I","SHELLE","SHIL","REMOVE","UPDATE"]:
        raw=raw.replace(b,"")
    raw=re.sub(r"\$?\d+(\.\d+)?","",raw)
    raw=" ".join(raw.split()).strip()
    parts=raw.split()
    if len(parts)>3:
        if "BALADE" in raw: raw="BRA BALADE"
        elif "SAKHRI" in raw: raw="LOQ SAKHRI"
        elif "BALADI" in raw: raw="GHAZIL BALADI"
        else: raw=" ".join(parts[:3])
    if raw.upper() in EXACT_LOCK: raw=EXACT_LOCK[raw.upper()]
    if "BALADE" in raw.upper(): raw="BRA BALADE"
    if "LOQ" in raw.upper() and "SAKHRI" in raw.upper(): raw="LOQ SAKHRI"
    if "GHAZIL" in raw.upper() and "BALADI" in raw.upper(): raw="GHAZIL BALADI"
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
    if s in ["yes","y","ok","eh","na3am","aye","yes confirm"]: return "yes_confirm"
    if s in ["no","n","la","la2","no confirm"]: return "no_confirm"
    if "zedle" in s: return "add"
    if any(w in s for w in ["l8i","shelle","shil","remove","l8e","msah"]): return "delete"
    if any(w in s for w in ["ghayerle","ghayer","update"]): return "update"
    if re.search(r"\d+(?:\.\d+)?\s*(?:kilo|kg|k)\b",s): return "add"
    if any(w in s for w in ["asfar","malifa","sarghous","jrawe","abyad","aarmout","ghobbos","bezri","faride","bra2","lo2os","mwasta","sultan","azatli","ghassani","ghazal","firan","filet","ajej","jadla","ghazil"]): return "add"
    if any(w in s for w in ["date","where","not","mesh","ghayer"]): return "correction"
    return "general"

async def download_media(mid):
    env=get_env()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r=await c.get(f"https://graph.facebook.com/v19.0/{mid}",headers={"Authorization":f"Bearer {env['WHATSAPP_TOKEN']}"})
            url=r.json().get("url")
            if not url: return None
            r2=await c.get(url,headers={"Authorization":f"Bearer {env['WHATSAPP_TOKEN']}"})
            return r2.content
    except: return None

async def transcribe_voice_fast(mid):
    env=get_env()
    if not env["OPENAI_KEY"]: return None
    try:
        content=await download_media(mid)
        if not content: return None
        print(f"Voice {len(content)} bytes VOICE DATE MODE")
        with tempfile.NamedTemporaryFile(suffix=".ogg",delete=False) as f:
            f.write(content); p=f.name
        async with httpx.AsyncClient(timeout=30) as c:
            with open(p,"rb") as af:
                r=await c.post("https://api.openai.com/v1/audio/transcriptions",headers={"Authorization":f"Bearer {env['OPENAI_KEY']}"},files={"file":(p,af,"audio/ogg")},data={"model":"whisper-1","language":"ar","prompt":"Date 27 Oct not 25, Date 27 October, Jadla Ghassani Firan Filet Bezri Bra2 Ajej Azatli kilo, 27 October, 25 October, 27 Oct"})
                j=r.json()
                print(f"VOICE RAW:{j}")
                if "text" not in j or not j["text"].strip(): return None
                raw_text=j["text"].strip()
                print(f"VOICE BEFORE:{raw_text}")
                converted=to_arabizi_fast(raw_text)
                print(f"VOICE AFTER:{converted}")
                if any("\u0600" <= ch <= "\u06FF" for ch in converted):
                    try:
                        async with httpx.AsyncClient(timeout=8) as c2:
                            r2=await c2.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {env['OPENAI_KEY']}","Content-Type":"application/json"},json={"model":"gpt-4o-mini","messages":[{"role":"system","content":"You hear Lebanese voice. Extract date and fish. Convert to English Arabizi ONLY. If user says 'Date 27 Oct not 25' return exactly 'Date 27 Oct not 25'. NEVER change 27 to 25. Numbers must be exact. Fish: Ghassani Bra2 Ajej Filet Jadla."},{"role":"user","content":raw_text}],"temperature":0})
                            j2=r2.json()
                            trans=j2["choices"][0]["message"]["content"]
                            print(f"VOICE GPT FIX:{trans}")
                            return trans
                    except: pass
                return converted
    except Exception as e:
        print(f"Voice err {e}"); traceback.print_exc(); return None

async def read_image(mid,cap=""):
    env=get_env()
    if not env["OPENAI_KEY"]: return cap
    try:
        content=await download_media(mid)
        if not content: return cap
        b64=base64.b64encode(content).decode()
        prompt=f"Caption:{cap}. Count exact rows. Weight=وزن/1000. Format English: FISH Xkg Bra2 Ajej Filet Ghassani"
        async with httpx.AsyncClient(timeout=20) as c:
            r=await c.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {env['OPENAI_KEY']}","Content-Type":"application/json"},json={"model":"gpt-4o-mini","messages":[{"role":"system","content":f"Caption:{cap} Date English only Bra2 Ajej Filet"},{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}","detail":"high"}}]}],"temperature":0})
            j=r.json()
            if "choices" in j: return f"{cap}\n{j['choices'][0]['message']['content']}"
            return cap
    except: return cap

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
    parsed=[]; cur_date="NO_DATE"; cur_where="Antelias"; cur_week=""
    low_all=text.lower()
    m=re.search(r"(\d{1,2})\s*(oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)",low_all)
    if m:
        cur_date=f"{m.group(1).zfill(2)} {m.group(2).capitalize()[:3]}"
        cur_week=get_week_from_date(cur_date)
    special={}; default="Bernard"
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
            if fish_clean and len(fish_clean)>=2:
                sup=default
                if fish_clean.upper() in special: sup=special[fish_clean.upper()]
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
        plist_sorted=sorted(plist, key=lambda x: (x["date"], x["where"]))
        for it in plist_sorted:
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
        return f"Zabtet {added} new {updated} updated! Retail+Profit copied! {plist[0]['date']} - Sorted!"
    except Exception as e:
        traceback.print_exc(); return f"Error:{e}"

async def handle(text,phone):
    print(f"HANDLE:{text}")
    if not text or len(text.strip())<2:
        return "Eh ma fehmet, eb3at voice: Zedle Asfar 4 kilo 27 Oct Antelias Bernard"
    text=to_arabizi_fast(text)
    low=text.lower()
    intent=detect_intent(text)
    print(f"INTENT:{intent} TEXT:{low}")
    # === MIND: PENDING CORRECTION - VOICE + TEXT ===
    if phone in PENDING and PENDING[phone]:
        all_dates=re.findall(r"(\d{1,2})\s*(oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)",low)
        if all_dates and any(w in low for w in ["date","not","mesh","ghayer"]):
            new_day=all_dates[0][0].zfill(2)
            new_mon=all_dates[0][1].capitalize()[:3]
            new_date=f"{new_day} {new_mon}"
            print(f"VOICE CORRECTION: {low} -> {new_date} all={all_dates}")
            new_week=get_week_from_date(new_date)
            for it in PENDING[phone]:
                it["date"]=new_date
                it["week"]=new_week
            lines=[f"{p['fish']} {p['kg']}kg {p['supplier']} {p['date']} {p['where']}" for p in PENDING[phone]]
            return f"Zabtet! Fehmet - ghayart date la {new_date} (mesh 25):\n"+"\n".join(lines)+"\n\nConfirm? YES / NO"
        where_corr=re.search(r"(?:where|l where|ghayer where)?\s*(adma|broumana|baabda|antelias)\s*(?:not|mesh|la2|badal)?",low)
        if where_corr and any(w in low for w in ["where","mesh","not"]):
            new_where=where_corr.group(1).capitalize()
            for it in PENDING[phone]: it["where"]=new_where
            lines=[f"{p['fish']} {p['kg']}kg {p['supplier']} {p['date']} {p['where']}" for p in PENDING[phone]]
            return f"Zabtet! Ghayart where la {new_where}:\n"+"\n".join(lines)+"\n\nConfirm? YES / NO"
        qty_corr=re.search(r"(?:ghayer|ghayerle)?\s*(\w+(?:\s+\w+)?)\s*(\d+(?:\.\d+)?)\s*kg\s*(?:la|to|badal|mesh)\s*(\d+(?:\.\d+)?)",low)
        if qty_corr:
            fish_target=qty_corr.group(1).strip().upper()
            new_kg=qty_corr.group(3)
            fish_target=re.sub(r"(ADMA|BROUMANA|BAABDA|ANTELIAS|OCT|NOV|DEC)","",fish_target).strip()
            if len(fish_target)>=2:
                for it in PENDING[phone]:
                    if fish_target in it["fish"].upper() or it["fish"].upper() in fish_target: it["kg"]=new_kg
                lines=[f"{p['fish']} {p['kg']}kg {p['supplier']} {p['date']} {p['where']}" for p in PENDING[phone]]
                return f"Zabtet! Ghayart {fish_target} la {new_kg}kg:\n"+"\n".join(lines)+"\n\nConfirm? YES / NO"
        if "kamen" in low or "zid" in low:
            extra=parse_msg(text)
            if extra:
                PENDING[phone].extend(extra)
                lines=[f"{p['fish']} {p['kg']}kg {p['supplier']} {p['date']} {p['where']}" for p in PENDING[phone]]
                return f"Zedle kamen! Total {len(PENDING[phone])} samke:\n"+"\n".join(lines)+"\n\nConfirm? YES / NO"
    if intent=="yes_confirm":
        if phone in PENDING:
            # Check date still NO_DATE
            if PENDING[phone][0]["date"]=="NO_DATE":
                return "Shu el DATE? Oul voice: Date 27 Oct - mesh ana bna2e!"
            return await write_pending(phone)
        return "Ma fi pending, eb3at: Zedle Asfar 4 kilo 27 Oct Antelias Bernard"
    if intent=="no_confirm":
        if phone in PENDING: del PENDING[phone]; return "Ok ma zedet, pending cleared!"
        return "Ok"
    if intent=="correction" and phone in PENDING:
        env=get_env()
        if env["OPENAI_KEY"]:
            try:
                async with httpx.AsyncClient(timeout=8) as c:
                    plist_str="\n".join([f"{p['fish']} {p['kg']}kg {p['date']} {p['where']}" for p in PENDING[phone]])
                    r=await c.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {env['OPENAI_KEY']}","Content-Type":"application/json"},json={"model":"gpt-4o-mini","messages":[{"role":"system","content":f"You are Nohra smart assistant. Pending:\n{plist_str}\nExtract correction. Reply JSON only: {{\"type\":\"date\",\"value\":\"27 Oct\"}} or {{\"type\":\"where\",\"value\":\"Adma\"}} or {{\"type\":\"qty\",\"fish\":\"JADLA\",\"kg\":\"5\"}}. If not clear, {{\"type\":\"unknown\"}}"},{"role":"user","content":text}],"temperature":0})
                    j=r.json()
                    content=j["choices"][0]["message"]["content"]
                    print(f"SMART AI:{content}")
                    try:
                        data=json.loads(content)
                        if data["type"]=="date":
                            nd=data["value"]; nw=get_week_from_date(nd)
                            for it in PENDING[phone]: it["date"]=nd; it["week"]=nw
                            lines=[f"{p['fish']} {p['kg']}kg {p['date']} {p['where']}" for p in PENDING[phone]]
                            return f"Zabtet! AI fehmet - ghayart date la {nd}:\n"+"\n".join(lines)+"\n\nConfirm? YES / NO"
                        elif data["type"]=="where":
                            nw=data["value"]
                            for it in PENDING[phone]: it["where"]=nw
                            lines=[f"{p['fish']} {p['kg']}kg {p['date']} {p['where']}" for p in PENDING[phone]]
                            return f"Zabtet! AI fehmet - ghayart where la {nw}:\n"+"\n".join(lines)+"\n\nConfirm? YES / NO"
                        elif data["type"]=="qty":
                            for it in PENDING[phone]:
                                if data["fish"].upper() in it["fish"].upper(): it["kg"]=data["kg"]
                            lines=[f"{p['fish']} {p['kg']}kg {p['date']} {p['where']}" for p in PENDING[phone]]
                            return f"Zabtet! AI fehmet - ghayart {data['fish']} la {data['kg']}kg:\n"+"\n".join(lines)+"\n\nConfirm? YES / NO"
                    except: pass
            except: pass
    try:
        ws,_=await get_ws(); vals=ws.get_all_values()
        if intent=="delete":
            t=text.lower()
            for w in ["l8i","shelle","shil","remove","l8e"]: t=t.replace(w,"")
            t=re.sub(r"\d+\s*(?:oct|nov|dec)","",t).strip()
            parts=[p for p in t.split() if len(p)>=3]
            if not parts: return "Eb3at: L8i sultan"
            st=parts[0].upper()
            for i in range(len(vals)-1,0,-1):
                r=vals[i]
                if len(r)>6 and st in r[6].upper(): ws.delete_rows(i+1); return f"Chilt {st} row {i+1}!"
            return f"Ma la2et {st}"
        if intent in ["add","update"]:
            parsed=parse_msg(text)
            if not parsed: return "Eh ma fehmet, eb3at: Zedle Asfar 4 kilo 27 Oct Antelias Bernard"
            if parsed[0]["date"]=="NO_DATE":
                PENDING[phone]=parsed
                lines=[f"{p['fish']} {p['kg']}kg {p['supplier']}" for p in parsed]
                return f"Eh fehmet el samak:\n"+"\n".join(lines)+f"\n\nBas shu el DATE? Oul voice: Date 27 Oct - mesh ana bna2e!"
            PENDING[phone]=parsed; lines=[]
            for p in parsed: lines.append(f"{p['fish']} {p['kg']}kg {p['supplier']} {p['date']} {p['where']}")
            summ="\n".join(lines); dates=list(set([p["date"] for p in parsed]))
            return f"Rah zid hek - {len(parsed)} samke, Dates: {', '.join(dates)}:\n{summ}\n\nConfirm? YES / NO - fik t2oul voice: Date 27 Oct not 25"
    except Exception as e:
        traceback.print_exc(); return f"Error:{e}"
    env=get_env()
    if env["OPENAI_KEY"]:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r=await c.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {env['OPENAI_KEY']}","Content-Type":"application/json"},json={"model":"gpt-4o-mini","messages":[{"role":"system","content":"You are Nohra smart fish assistant. Speak ONLY Lebanese Arabizi English alphabet. Use: eh, zabtet, chilt, hek. Help add fish. Example: Zedle Asfar 4 kilo 27 Oct Antelias Bernard. Never Arabic script."},{"role":"user","content":text}]})
                j=r.json()
                txt=j["choices"][0]["message"]["content"][:500]
                if any("\u0600" <= ch <= "\u06FF" for ch in txt):
                    return "Eh ma fehmet, eb3at: Zedle Asfar 4 kilo 27 Oct Antelias Bernard"
                return txt
        except: return "Eh ma fehmet, eb3at: Zedle Asfar 4 kilo 27 Oct Antelias Bernard"
    return "Eh ma fehmet, eb3at: Zedle Asfar 4 kilo 27 Oct Antelias Bernard"

app=FastAPI()
@app.get("/")
async def root(): return HTMLResponse("<h2>Nohra REAL SMART - VOICE DATE FIXED - BRA2 AJEJ FILET GHASSANI - Has Mind</h2>")
@app.get("/webhook/whatsapp")
async def verify(request: Request):
    mode=request.query_params.get("hub.mode"); token=request.query_params.get("hub.verify_token"); chal=request.query_params.get("hub.challenge")
    if mode=="subscribe" and token==VERIFY_TOKEN: return PlainTextResponse(content=chal or "",status_code=200)
    from fastapi import HTTPException; raise HTTPException(status_code=403)
@app.post("/webhook/whatsapp")
async def receive(request: Request):
    body=await request.json()
    try:
        val=body["entry"][0]["changes"][0]["value"]
        if "messages" not in val: return {"ok":True}
        msg=val["messages"][0]; frm=msg["from"]; mtype=msg.get("type","text"); txt=""
        if mtype=="text": txt=msg["text"]["body"]
        elif mtype in ["audio","voice"]: txt=await transcribe_voice_fast(msg[mtype]["id"]) or ""
        elif mtype=="image": txt=await read_image(msg["image"]["id"],msg["image"].get("caption",""))
        else: txt=msg.get("text",{}).get("body","Hello")
        if not txt: txt="ma fehmet voice"
        print(f"INCOMING:{txt}")
        reply=await handle(txt,frm)
        if not reply: return {"ok":True}
        print(f"REPLY:{reply}")
        env=get_env()
        if env["WHATSAPP_TOKEN"]:
            async with httpx.AsyncClient(timeout=15) as c2:
                url=f"https://graph.facebook.com/v19.0/{env['PHONE_ID']}/messages"
                headers={"Authorization":f"Bearer {env['WHATSAPP_TOKEN']}"}
                payload={"messaging_product":"whatsapp","to":frm,"type":"text","text":{"body":reply[:1500]}}
                await c2.post(url,headers=headers,json=payload)
        return {"sent":True}
    except Exception as e:
        traceback.print_exc(); return {"error":str(e)}
