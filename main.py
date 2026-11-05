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
    if not env["OPENAI_KEY"]: 
        print("No OPENAI_KEY")
        return None
    try:
        content = await download_media(media_id)
        if not content: return None
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(content); p=f.name
        async with httpx.AsyncClient(timeout=60) as c:
            with open(p, "rb") as af:
                r = await c.post("https://api.openai.com/v1/audio/transcriptions", 
                    headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"}, 
                    files={"file": (p, af, "audio/ogg")}, 
                    data={"model": "whisper-1", "prompt": "Nohra fish shop Lebanese.
