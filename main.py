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
    if gc and gc.startswith("'") and gc.endswith("'"):
        gc = gc[1:-1]
    return {
        "WHATSAPP_TOKEN": os.getenv("WHATSAPP_TOKEN",""),
        "PHONE_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID","1349671541570540"),
        "OPENAI_KEY": os.getenv("OPENAI_API_KEY",""),
        "GEMINI_KEY": os.getenv("GEMINI_API_KEY",""),
        "GOOGLE_CREDS": gc,
    }

def detect_department(text):
    if len(text) > 800 or "def " in text or "return \"" in text or "import " in text:
        return "ignore"
    t = text.lower()
    if any(k in t for k in ["kg","kilo","ghobbos","ajej","bra2","lo2os","frafir","sultan","samak","nohra","bernard","zedle","se3er"]):
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
        try:
            ws = sheet.worksheet("Fish Supplies 2026")
        except:
            ws = sheet.get_worksheet(0)
        lines = text.strip().split("\n")
        current_supplier = "Nohra"
        date_str = "05 Nov"
        where = "Broumana"
        week = "05 Nov"
        first_lower = lines[0].lower() if lines else ""
        dm = re.search(r"(\d+)\s*nov", first_lower)
        if dm:
            day = dm.group(1).zfill(2)
            date_str = f"{day} Nov"
            week = date_str
        if "broumana" in first_lower: where = "Broumana"
        elif "antelias" in first_lower: where = "Antelias"
        elif "adma" in first_lower: where = "Adma"
        if "bernard" in first_lower: current_supplier = "Bernard"
        added = 0
        summary = []
        for line in lines:
            orig = line.strip()
            if not orig: continue
            low = orig.lower()
            if len(orig) > 200: continue
            if ":" in orig and "kilo" not in low[:35]:
                parts = orig.split(":",1)
                head = parts[0].lower()
                if "bernard" in head: current_supplier = "Bernard"
                if "nohra" in head: current_supplier = "Nohra"
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
            for bad in ["NOHRA","BERNARD","GHASSAN","BROUMANA","ANTELIAS","ADMA","ZEDLE","SAMAK","SE3ER","UNIT","$","KILO"]:
                fish_clean = fish_clean.replace(bad,"")
            fish_clean = " ".join(fish_clean.split()).strip()
            if not fish_clean: continue
            price = ""
            pm = re.search(r"(\d+(
