def correct_pending(text, phone):
    if phone not in PENDING: return None
    t = text.lower()
    plist = PENDING[phone]
    changed = False
    
    # DATE CORRECTION: "l date 14/10 mesh 14/1" or "date 14/10 mesh 14/1" or "14/10 mesh 14/1"
    if "date" in t or "tarikh" in t or "mesh" in t or "mish" in t or "/" in t:
        # Find all DD/MM patterns
        dates_found = re.findall(r"(\d{1,2})[\/\.\s]+(\d{1,2})(?:[\/\.\s]+\d{2,4})?", t)
        # dates_found = [(14,10), (14,1)]
        if len(dates_found) >= 2:
            # First is NEW, second is OLD (14/10 mesh 14/1 = change 14/1 to 14/10)
            new_d, new_m = dates_found[0]
            old_d, old_m = dates_found[1]
            months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            try:
                new_month = months[int(new_m)] if 1<=int(new_m)<=12 else "Oct"
                old_month = months[int(old_m)] if 1<=int(old_m)<=12 else "Jan"
                new_date_str = f"{str(new_d).zfill(2)} {new_month}"
                old_date_str = f"{str(old_d).zfill(2)} {old_month}"
                
                # Also handle Jan vs 1 confusion: 14/1 = 14 Jan
                for it in plist:
                    # If date contains old day and old month
                    if old_d in it["date"] and old_month in it["date"] or it["date"]==old_date_str:
                        it["date"] = new_date_str
                        it["week"] = get_week_from_date(new_date_str)
                        changed = True
                    # Also handle if bot read 14/1 as "14 Jan"
                    if it["date"].lower().startswith(f"{str(old_d).zfill(2).lower()} {old_month.lower()[:3]}"):
                        it["date"] = new_date_str
                        it["week"] = get_week_from_date(new_date_str)
                        changed = True
                if changed:
                    return f"Date correction done!"
            except: pass
        elif len(dates_found) == 1:
            # "l date 14/10" = change ALL to 14/10
            if "date" in t:
                new_d, new_m = dates_found[0]
                months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                try:
                    new_month = months[int(new_m)]
                    new_date_str = f"{str(new_d).zfill(2)} {new_month}"
                    for it in plist:
                        it["date"] = new_date_str
                        it["week"] = get_week_from_date(new_date_str)
                    changed = True
                    return "Date correction done!"
                except: pass
    
    # WHERE CORRECTION: "Antelias mesh Adma"
    if "antelias" in t or "adma" in t or "broumana" in t or "baabda" in t:
        if "mesh" in t or "mish" in t:
            # Find old and new where
            wheres = []
            for w in ["antelias","adma","broumana","baabda"]:
                if w in t: wheres.append(w)
            if len(wheres) >=2:
                new_where = wheres[0].capitalize()
                old_where = wheres[1].capitalize()
                for it in plist:
                    if it["where"].lower() == old_where.lower():
                        it["where"] = new_where
                        changed = True
    
    if changed:
        return "Correction done!"
    return None
