async def read_image(media_id, cap=""):
    env = get_env()
    if not env["OPENAI_KEY"]:
        return cap
    try:
        content = await download_media(media_id)
        if not content:
            return cap
        b64 = base64.b64encode(content).decode()
        # NEW PROMPT - forces to read ALL 3 tables + caption override
        prompt = f"""
This is Daily Purchased Fish - 3 TABLES stacked vertically in ONE photo!

Each table:
- Top: date like 22/10/27 = 22 Oct, 24/10/27 = 24 Oct, 25/10/27 = 25 Oct
- Left column: برنار = Bernard : نوع=fish name وزن=weight سعر=price
- Right column: نوهرا = Nohra : نوع وزن سعر
- TOTAL at bottom of each table

CAPTION OVERRIDE: "{cap}"
If caption says "for section 24:10 kel Isamak la bernard" means ALL fish on date 24 Oct are Bernard supplier, even if written in Nohra column!
If says "kel la nohra" then all Nohra.

YOUR JOB: Read EVERY row! Do not skip!
Top table (22/10/27): Bernard 5 fish: جربيدي=JARBIDE 2,000g? سلطان=SULTAN 3,000 رملي=RAMLE 2,700 etc + Nohra 3 fish: عرموت=AARMOUT 15,000 19,500$ etc
Middle table (24/10/27): Bernard 2? Nohra 5? Bottom table (25/10/27): etc

Arabic map: جربيدي=JARBIDE سلطان=SULTAN رملي=RAMLE مرادع=MARADE3 براك=BARRAK فريدي=FARIDE عجاج=AJEJ مليفة=MALIFA جربيدي=JARBIDE اصفر=ASFAR حليفة=HALIFA لعز_هوري=LO2OS_HOURI كحايلي=KHAILE سمن_روح=SAMAN_ROUH مرجان=MARJAN لكرز=LKERZ بزري=BEZRI حمرا=HAMRA ملينا=MALINA عرموت=AARMOUT كعدو=KAADE سرغوس=SERGOS مرادع=MARADE3 اسبق=ASBAG

Return EXACTLY this format, 1 line per fish, with date on separate line:
22 Oct Antelias
Bernard: JARBIDE 2kg se3er 2000
Bernard: SULTAN 3kg se3er 3000
Nohra: AARMOUT 15kg se3er 19500$
... etc
24 Oct Antelias
Bernard: BEZRI 2.5kg ...
25 Oct Antelias
Bernard: ...

If caption says all for Bernard on 24 Oct, then write Bernard for all those.

Include ALL 15+ fish, do not summarize to 2!
"""
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"}, json={"model":"gpt-4o","messages":[{"role":"user","content":[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}"}}]}]})
            j = r.json()
            text = j["choices"][0]["message"]["content"]
            print(f"IMAGE READ: {text}")
            # If caption override says all Bernard for 24/10
            if "24:10" in cap or "24/10" in cap or "24.10" in cap:
                if "bernard" in cap.lower() and "kel" in cap.lower():
                    text = text.replace("Nohra:", "Bernard:").replace("NOHRA:", "Bernard:") if "24 Oct" in text else text
                    # Better: we will handle override in parse_msg
                    text += "\nOVERRIDE: 24 Oct = Bernard"
            return text
    except Exception as e:
        print(f"read_image error {e}")
        traceback.print_exc()
        return cap

def parse_msg(text):
    lines = text.strip().split("\n")
    parsed=[]
    cur_supplier = "Nohra"
    cur_date = "14 Oct"
    cur_where = "Antelias"
    cur_week = get_week_from_date(cur_date)
    
    # Check for override: "OVERRIDE: 24 Oct = Bernard" or caption "kel Isamak la bernard for 24:10"
    override_date = None
    override_supplier = None
    if "OVERRIDE" in text:
        m = re.search(r"(\d{1,2})\s*Oct.*Bernard", text, re.I)
        if m:
            override_date = f"{m.group(1).zfill(2)} Oct"
            override_supplier = "Bernard"
    if "kel" in text.lower() and "bernard" in text.lower():
        # Find date near kel
        d = re.findall(r"24[:\/\.]\s*10", text)
        if d:
            override_date = "24 Oct"
            override_supplier = "Bernard"
    if "kel" in text.lower() and "nohra" in text.lower():
        d = re.findall(r"24[:\/\.]\s*10", text)
        if d:
            override_date = "24 Oct"
            override_supplier = "Nohra"

    for line in lines:
        orig = line.strip()
        if not orig:
            continue
        low = orig.lower()
        
        # DATE line: "22 Oct Antelias" or "24 Oct Antelias" or "22/10/27"
        dm = re.search(r"(\d{1,2})\s*(oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)", low)
        dm2 = re.search(r"(\d{1,2})[\/\.\s]+(\d{1,2})[\/\.\s]+\d{2,4}", low)
        if dm or dm2 or "antelias" in low or "adma" in low or "broumana" in low or "baabda" in low:
            # This line sets context, not a fish
            if dm:
                day = dm.group(1).zfill(2)
                mon = dm.group(2).capitalize()[:3]
                cur_date = f"{day} {mon}"
                cur_week = get_week_from_date(cur_date)
            if dm2 and not dm:
                day = dm2.group(1).zfill(2)
                m = int(dm2.group(2))
                months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                if 1<=m<=12:
                    cur_date = f"{day} {months[m]}"
                    cur_week = get_week_from_date(cur_date)
            if "broumana" in low: cur_where="Broumana"
            if "antelias" in low: cur_where="Antelias"
            if "adma" in low: cur_where="Adma"
            if "baabda" in low: cur_where="Baabda"
            if "bernard" in low and "nohra" not in low and ":" not in orig:
                cur_supplier="Bernard"
                continue
            if "nohra" in low and "bernard" not in low and ":" not in orig:
                cur_supplier="Nohra"
                continue
            if "kilo" not in low:
                continue
        
        # Supplier prefix: "Bernard: JARBIDE 2kg"
        if ":" in orig:
            parts = orig.split(":",1)
            head = parts[0].lower()
            if "bernard" in head: cur_supplier="Bernard"
            if "nohra" in head: cur_supplier="Nohra"
            # Override for specific date
            if override_date and override_date in cur_date:
                cur_supplier = override_supplier
            if len(parts)>1:
                orig = parts[1].strip()
                if not orig:
                    continue
        
        # Apply override
        if override_date and override_date == cur_date and override_supplier:
            cur_supplier = override_supplier

        km = re.search(r"(\d+(?:\.\d+)?)\s*k", low)
        if not km:
            continue
        kg = km.group(1)
        idx = low.find(km.group(0).lower())
        fish_raw = orig[:idx]
        if ":" in fish_raw:
            fish_raw = fish_raw.split(":")[-1]
        fish_clean = extract_fish_name(fish_raw)
        if not fish_clean or fish_clean.lower() in STOP_WORDS:
            continue
        
        price_d=""; price_l=""; ptype="none"; invoice=""
        pd = re.search(r"(\d+(?:\.\d+)?)\s*\$", orig)
        if pd:
            price_d="$"+pd.group(1); ptype="dollar"
        pl = re.search(r"(\d+(?:\.\d+)?)\s*(?:lbp|l\.l|ll|alf)", low)
        if pl and not price_d:
            val = pl.group(1)
            if "alf" in low and float(val) < 1000:
                val = str(int(float(val)*1000))
            price_l=val; ptype="lbp"
        # If no $ but number before kg is price? like "19,500$ 15,000" -> first is price
        # Search for price pattern in line
        if not price_d and not price_l:
            # Look for numbers like 19500 or 2000
            nums = re.findall(r"(\d{3,})", orig)
            if nums:
                # Assume last num is price? Actually weight already taken
                pass
        
        parsed.append({"fish":fish_clean,"kg":kg,"price_d":price_d,"price_l":price_l,"ptype":ptype,"supplier":cur_supplier,"where":cur_where,"date":cur_date,"week":cur_week,"invoice":invoice})
    
    return parsed
