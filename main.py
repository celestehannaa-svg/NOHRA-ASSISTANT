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
        "GOOGLE_CREDS": gc,
    }

def detect_department(text):
    if len(text) > 800:
        return "ignore"
    if "def " in text and "return" in text:
        return "ignore"
    t = text.lower()
    if "kg" in t or "kilo" in t or "ghobbos" in t or "ajej" in t or "bra2" in t or "lo2os" in t or "frafir" in t or "samak" in t or "zedle" in t:
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
        target_title = ""
        for title in all_sheets:
            low = title.lower()
            if "profit" in low and "daily" in low:
                target_title = title
                break
        if target_title == "":
            for title in all_sheets:
                if "Fish Supplies" in title and "2026" in title:
                    target_title = title
                    break
        if target_title == "":
            target_title = all_sheets[0]
        ws = sheet.worksheet(target_title)
        print("Using tab: " + target_title)

        # Get last row with data to copy formulas and dropdowns
        all_values = ws.get_all_values()
        last_row_num = len(all_values)
        # Find last non-empty row
        while last_row_num > 1 and all(not v.strip() for v in all_values[last_row_num-1]):
            last_row_num -= 1
        
        # Get formulas from last row (to copy GHASSAN, Total PROFIT, Fish Retail, etc.)
        try:
            last_row_formulas = ws.get(f"A{last_row_num}:M{last_row_num}", value_render_option="FORMULA")[0]
        except:
            last_row_formulas = [""]*13
        print("Last row formulas: " + str(last_row_formulas))

        lines = text.strip().split("\n")
        current_supplier = "Nohra"
        date_str = "21 Oct"
        where = "Broumana"
        week = "20 - 25 Oct"
        first_lower = lines[0].lower() if lines else ""
        dm = re.search(r"(\d+)\s*nov", first_lower)
        if dm:
            day = dm.group(1).zfill(2)
            date_str = day + " Oct"
            week = "20 - 25 Oct"
        if "broumana" in first_lower:
            where = "Broumana"
