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
    if gc.startswith("'") and gc.endswith("'"):
        gc = gc[1:-1]
    return {
        "WHATSAPP_TOKEN": os.getenv("WHATSAPP_TOKEN",""),
        "PHONE_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID","1349671541570540"),
        "OPENAI_KEY": os.getenv("OPENAI_API_KEY",""),
        "GEMINI_KEY": os.getenv("GEMINI_API_KEY",""),
        "GOOGLE_CREDS": gc,
    }

def detect_department(text):
    if len(text) > 800 or ("def " in text and "return" in text):
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
        
        all_sheets = [s.title for s in sheet.worksheets()]
        print(f"All tabs: {all_sheets}")
        
        # Find profit daily tab - EXACT structure you showed
        target_title = None
        for title in all_sheets:
            low = title.lower()
            if "profit" in low and "daily" in low:
                target_title = title
                break
        if not target_title:
            # fallback to Fish Supplies 2026 or first sheet with Week/DATE structure
            for title in all_sheets:
                if "Fish Supplies" in title and "2026" in title:
                    target_title = title
                    break
        if not target_title:
            target_title = all_sheets[0]
        
        ws = sheet.worksheet(target_title)
        print(f"Using tab: {target_title} with structure Week/DATE/Where/GHASSAN/Total PROFIT/Fish who?/Fish/Fish Price/Qtty...")

        lines = text.strip().split("\n")
        current_supplier = "Nohra"
        date_str = "05 Nov"
        where = "Broumana"
        week = "20 - 25 Oct"
        # Try extract date like 5nov
        first_lower = lines[0].lower() if lines else ""
        dm = re.search(r"(\d+)\s*nov", first_lower)
        if dm:
            day = dm.group(1).zfill(2)
            date_str = day + " Oct"
            # Week format like 20-25 Oct from your photo
            week = f"{day} Oct"
        # Where
        if "broumana" in first_lower: where = "Broumana"
        elif "antelias" in first_lower: where = "Antelias"
        elif "adma" in first_lower: where = "Adma"
        if "bernard" in first_lower: current_supplier = "Bernard"
        if "nohra" in first_lower: current_supplier = "Nohra"

        added = 0
        summary = []
        for line in lines:
            orig = line.strip()
            if not orig: continue
            low = orig.lower()
            if len(orig) > 200: continue
            #
