import os, json, re
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, HTMLResponse
from dotenv import load_dotenv
import httpx
load_dotenv()

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "nohra_verify_2024")
FISH_SHEET_ID = "1_U7Mz0eKj8x3nWDvCSkRXkDgyYIEhYupJNJ0-DSskss"

def get_env():
    load_dotenv(override=True)
    return {
        "WHATSAPP_TOKEN": os.getenv("WHATSAPP_TOKEN",""),
        "PHONE_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID","1349671541570540"),
        "GEMINI_KEY": os.getenv("GEMINI_API_KEY",""),
        "OPENAI_KEY": os.getenv("OPENAI_API_KEY",""),
        "GOOGLE_CREDS": os.getenv("GOOGLE_CREDENTIALS_JSON",""),
    }

def detect_department(text):
    t = text.lower()
    fish_keywords = ["fish","kg","kilo","ghobbos","ajej","bra2","lo2os","frafir","sultan","samak","nohra","bernard","ghassan","broumana","antelias","adma","zedle"]
    celeste_keywords = ["celeste","cosmetic","makeup","skincare","beauty"]
    english_keywords = ["english","teach","lesson","grammar","translate"]
    secretary_keywords = ["calendar","meeting","reminder","call","email","schedule"]
    if any(k in t for k in fish_keywords):
        return "fish"
    if any(k in t for k in celeste_keywords):
        return "celeste"
    if any(k in t for k in english_keywords):
        return "english"
    if any(k in t for k in secretary_keywords):
        return "secretary"
    return "general"

async def add_to_fish_sheet(text):
    env = get_env()
    if not env["GOOGLE_CREDS"]:
        return f"🐟 Fahmet! You wrote:\n{text}\n\nSheet not connected yet! Add GOOGLE_CREDENTIALS_JSON in Render. I understood your format, will add exactly like your sheet once connected!"
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds_dict = json.loads(env["GOOGLE_CREDS"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(FISH_SHEET_ID)
        try:
            ws = sheet.worksheet("Fish Supplies 2026")
        except:
            try:
                ws = sheet.worksheet("Fish Supplies 2026 ")
            except:
                ws = sheet.get_worksheet(0)
        
        lines = text.strip().split('\n')
        current_supplier = ""
        date_str = ""
        where = "Broumana"
        week = ""
        
        first_lower = lines[0].lower() if lines else ""
        date_match = re.search(r'(\d+)\s*nov', first_lower)
        if date_match:
            day = date_match.group(1)
            date_str = f"{day} Oct"
            week = f"{day} Oct"
        else:
            from datetime import datetime
            date_str = datetime.now().strftime("%d %b")
            week = date_str
        
        if "broumana" in first_lower:
            where = "Broumana"
        elif "antelias" in first_lower:
            where = "Antelias"
        elif "adma" in first_lower:
            where = "Adma"
        
        if "nohra" in first_lower:
            current_supplier = "Nohra"
        elif "bernard" in first_lower:
            current_supplier = "Bernard"
        
        added_count = 0
        for line in lines:
            orig_line = line.strip()
            if not orig_line:
                continue
            low = orig_line.lower()
            
            if low.startswith("zedle") and "kilo" not in low.split()[:4]:
                if ":" in orig_line:
                    after = orig_line.split(":",1)[1].strip()
                    if "kilo" in after.lower():
                        orig_line = after
                        low = after.lower()
                    else:
                        if "nohra" in orig_line.split(":")[0].lower():
                            current_supplier = "Nohra"
                        elif "bernard" in orig_line.split(":")[0].lower():
                            current_supplier = "Bernard"
                        continue
                else:
                    continue
            
            if ":" in orig_line:
                header = orig_line.split(":")[0].strip()
                if len(header.split()) <= 2:
                    lh = header.lower()
                    if "bernard" in lh:
                        current_supplier = "Bernard"
                        rest = ":".join(orig_line.split(":")[1:]).strip()
                        if rest:
                            orig_line = rest
                            low = rest.lower()
                        else:
                            continue
                    elif "nohra" in lh:
                        current_supplier = "Nohra"
                        rest = ":".join(orig_line.split(":")[1:]).strip()
                        if rest:
                            orig_line = rest
                            low = rest.lower()
                        else:
                            continue
            
            kg_match = re.search(r'(\d+(?:\.\d+)?)\s*k', low)
            if not kg_match:
                continue
            
            kg = kg_match.group(1)
            fish_name_raw = orig_line[:orig_line.lower().find(kg_match.group(0).lower())].strip()
            if ":" in fish_name_raw:
                fish_name_raw = fish_name_raw.split(":")[-1].strip()
            words = fish_name_raw.split()
            filtered = [w for w in words if w.lower() not in ["nohra","bernard","ghassan","broumana","antelias","adma","zedle","samak"]]
            fish_name = " ".join(filtered[-2:]) if len(filtered) >= 2 else (filtered[-1] if filtered else "Fish")
            fish_name_sheet = fish_name.upper()
            
            price = ""
            price_match = re.search(r'se3er\s*unit\s*(\d+(?:\.\d+)?)\$?|(\d+(?:\.\d+)?)\$\s*unit|(\d+(?:\.\d+)?)\$', low)
            if price_match:
                price = price_match.group(1) or price_match.group(2) or price_match.group(3)
                price = f"${price}" if price else ""
            
            all_values = ws.get_all_values()
            next_row = len(all_values) + 1
            
            row = [""] * 13
            row[0] = week
            row[1] = date_str
            row[2] = where
            row[5] = current_supplier
            row[6] = fish_name_sheet
            row[7] = price
            row[9] = kg
            
            ws.update(f"A{next_row}:M{next_row}", [row])
            added_count += 1
        
        if added_count == 0:
            return f"🤔 Ma fhemet: {text}"
        
        return f"✅ Zedle {added_count} samak 3al sheet EXACTLY like you write!\n📅 {date_str} {where}\n🏭 {current_supplier}\n🔗 https://docs.google.com/spreadsheets/d/{FISH_SHEET_ID}"
    
    except Exception as e:
        import traceback; traceback.print_exc()
        return f"❌ Sheet error: {str(e)[:500]}"

async def ai_reply(text, department="general"):
    env = get_env()
    prompts = {
        "fish": f"You are Nohra Fish Business Manager. Expert in fish supply Nohra/Bernard, Ghassan broker. Sheet ID {FISH_SHEET_ID}. Understand Lebanese Arabizi fish: ghobbos, ajej, bra2, lo2os, frafir, sultan, etc. Understand format: 'Zedle samak 5nov broumana nohra: ghobbos 5 kilo se3er unit 5$'. Reply EXACTLY like user writes: if user writes Arabizi, reply Arabizi; if Arabic, reply Arabic. Don't translate fish names. Be short, friendly.",
        "celeste": "You are Celeste Cosmetics Manager. Expert in makeup, skincare, beauty. Reply same language as user. Short, elegant.",
        "english": "You are English Teaching Assistant. Help with English/Arabic/Lebanese translation, grammar. Encouraging.",
        "secretary": "You are Personal Secretary. Help with calendar, meetings, reminders. Professional, organized.",
        "general": "You are Nohra AI Assistant - 4 depts: Fish (ghobbos, ajej, bra2, lo2os), Celeste Cosmetics, English Teaching, Secretary. Detect dept. Reply same language user uses: English, Arabic, Lebanese, Arabizi. Write EXACTLY like user writes. Short friendly."
    }
    system_prompt = prompts.get(department, prompts["general"])
    reply = None
    if env["OPENAI_KEY"]:
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.post("https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"},
                    json={"model": "gpt-4o-mini","messages": [{"role": "system","content": system_prompt},{"role": "user","content": text}]})
                data = r.json()
                if "choices" in data:
                    reply = data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"OpenAI error: {e}")
    if not reply and env["GEMINI_KEY"]:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={env['GEMINI_KEY']}",json={"contents": [{"parts": [{"text": f"{system_prompt}\nUser: {text}"}]}]})
                data = r.json()
                if "candidates" in data:
                    reply = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"Gemini error: {e}")
    return reply

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def root():
    env = get_env()
    return f"<html><body style='font-family:sans-serif;padding:20
