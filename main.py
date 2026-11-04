async def add_to_fish_sheet(text):
    env = get_env()
    if not env["GOOGLE_CREDS"]:
        return f"🐟 Fahmet! You wrote:\n{text}\n\nBut Sheet not connected yet! Add GOOGLE_CREDENTIALS_JSON in Render. I understood {len(text.split())} words. Once connected, I will add exactly as you write!"
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds_dict = json.loads(env["GOOGLE_CREDS"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(FISH_SHEET_ID)
        try:
            ws = sheet.worksheet("Fish Log")
        except:
            ws = sheet.add_worksheet(title="Fish Log", rows=1000, cols=20)
            ws.append_row(["Date","Supplier","Fish Type","KG","Price Unit","Total","Location","Original Text","Added via"])

        # Parse your format: multi-line, suppliers as headers
        # Example: "Zedle samak 5nov broumana nohra: ghobbos 5 kilo se3er unit 5$"
        lines = text.strip().split('\n')
        current_supplier = ""
        date_info = ""
        location = ""
        added_rows = []
        
        # Extract date and location from first line
        first_line = lines[0].lower() if lines else ""
        if "nov" in first_line or "broumana" in first_line or "zedle" in first_line:
            # Extract date like 5nov
            date_match = re.search(r'(\d+)\s*nov', first_line)
            if date_match:
                date_info = f"2026-11-{date_match.group(1)}"
            if "broumana" in first_line:
                location = "Broumana"
            # Extract supplier from first line if "nohra:" in it
            if "nohra" in first_line:
                current_supplier = "Nohra"
            elif "bernard" in first_line:
                current_supplier = "Bernard"
        
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not date_info:
            date_info = now_str

        for line in lines:
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            
            # Check if line is supplier header: "Bernard:" or "nohra:"
            if ":" in line and len(line.split(":")[0].strip().split()) <= 2:
                header = line.split(":")[0].lower()
                if "nohra" in header:
                    current_supplier = "Nohra"
                    # Also parse fish after colon in same line
                    rest = ":".join(line.split(":")[1:]).strip()
                    if rest:
                        line = rest
                        low = rest.lower()
                    else:
                        continue
                elif "bernard" in header:
                    current_supplier = "Bernard"
                    rest = ":".join(line.split(":")[1:]).strip()
                    if rest:
                        line = rest
                        low = rest.lower()
                    else:
                        continue
                elif "ghassan" in header:
                    current_supplier = "Ghassan"
                    continue
            
            # Skip lines that are just "Zedle samak..."
            if low.startswith("zedle") and "kilo" not in low.split()[:5]:
                # This line might contain fish after colon
                if ":" in line:
                    parts = line.split(":",1)
                    if len(parts) > 1 and "kilo" in parts[1].lower():
                        line = parts[1]
                        low = line.lower()
                    else:
                        continue
                else:
                    continue
            
            # Now parse fish line: e.g. "ghobbos 5 kilo se3er unit 5$" or "Ajej 30 kilo 7$ unit" or "Lo2os 3kilo"
            # Find fish name - first word that is not number/kg/price
            # Your fish: ghobbos, ajej, frafir, lo2os, bra2, sultan, etc.
            kg_match = re.search(r'(\d+(?:\.\d+)?)\s*k(?:ilo)?', low)
            if not kg_match:
                continue
            
            kg = kg_match.group(1)
            
            # Fish type is text before kg
            fish_part = low[:kg_match.start()].strip()
            # Remove numbers and common words
            fish_type = fish_part
            # Clean fish type - take first 1-2 words
            fish_type = re.sub(r'^\d+\s*', '', fish_type)  # remove leading numbers
            fish_type = fish_type.strip()
            if not fish_type:
                fish_type = "fish"
            
            # Keep original fish name exactly as user wrote (preserve case from original line)
            # Find fish name in original line before kg
            orig_kg_pos = re.search(r'(\d+(?:\.\d+)?)\s*k', line, re.IGNORECASE)
            if orig_kg_pos:
                orig_fish = line[:orig_kg_pos.start()].strip()
                # If original has colon, take after last colon or take last words
                if ":" in orig_fish:
                    orig_fish = orig_fish.split(":")[-1].strip()
                # Take last 1-2 words as fish name
                words = orig_fish.split()
                if words:
                    fish_type = " ".join(words[-2:]) if len(words) >= 2 else words[-1]
                    # Remove if it's supplier name
                    if fish_type.lower() in ["nohra","bernard","ghassan","broumana","zedle","samak"]:
                        fish_type = "fish"
            
            # Price: se3er unit 5$ or 7$ unit or 5$
            price = ""
            price_match = re.search(r'se3er\s*unit\s*(\d+(?:\.\d+)?)\$?|(\d+(?:\.\d+)?)\$\s*unit|(\d+(?:\.\d+)?)\$', low)
            if price_match:
                price = price_match.group(1) or price_match.group(2) or price_match.group(3)
            
            total = ""
            if kg and price:
                try:
                    total = str(float(kg) * float(price))
                except:
                    pass
            
            # Preserve exact original line
            row = [date_info, current_supplier, fish_type, kg, price, total, location, line, "WhatsApp"]
            ws.append_row(row)
            added_rows.append(f"• {fish_type} {kg}kg {price}$ ({current_supplier})")

        if not added_rows:
            return f"🤔 Ma fhemet ktir: {text}\nTry like: 'ghobbos 5 kilo 5$' or 'nohra: ghobbos 5 kilo'"
        
        return f"✅ Zedle {len(added_rows)} samak 3al Sheet!\n📅 {date_info} {location}\n" + "\n".join(added_rows) + f"\n🔗 https://docs.google.com/spreadsheets/d/{FISH_SHEET_ID}"
    
    except Exception as e:
        import traceback; traceback.print_exc()
        return f"❌ Sheet error: {str(e)[:500]}\nYour text: {text[:100]}"
