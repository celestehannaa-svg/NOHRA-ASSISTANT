async def write_pending(phone):
    if phone not in PENDING: return "Ma fi pending"
    plist = PENDING[phone]
    def date_key(it):
        try:
            parts = it["date"].split()
            day = int(parts[0])
            mon_str = parts[1][:3].lower()
            months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            mon = months.get(mon_str,10)
            return (mon, day)
        except:
            return (10,99)
    # SORT BY DATE, then Where: 21 Oct Adma next to 21 Oct Antelias + 21 Oct Broumana
    plist = sorted(plist, key=lambda x: (date_key(x), x["where"]))

    try:
        ws, target = await get_ws()
        vals = ws.get_all_values()
        forms = ws.get(f"A1:M{len(vals)}", value_render_option="FORMULA")

        last=1
        for i in range(len(vals)-1,-1,-1):
            r=vals[i]
            if len(r)>5 and (r[5].strip() or (len(r)>6 and r[6].strip())): last=i+1; break
        try:
            last_f = ws.get(f"A{last}:M{last}", value_render_option="FORMULA")[0]
            while len(last_f)<13: last_f.append("")
        except: last_f=[""]*13
        def sc(f,nr):
            if not f or "=" not in str(f): return ""
            return str(f).replace(str(last), str(nr))

        # Find last GHASSAN formulas
        last_g_formula=""; last_g_row=0
        last_p_formula=""; last_p_row=0
        for i in range(len(forms)-1, -1, -1):
            if len(forms[i])>3 and forms[i][3].strip() and "SUM" in forms[i][3].upper():
                if not last_g_formula: last_g_formula = forms[i][3]; last_g_row = i+1
            if len(forms[i])>4 and forms[i][4].strip() and "SUM" in forms[i][4].upper():
                if not last_p_formula: last_p_formula = forms[i][4]; last_p_row = i+1
            if last_g_formula and last_p_formula: break

        # Build set of existing DATE+Where in sheet
        existing_keys = set()
        for r in vals:
            if len(r)>2 and r[1].strip() and r[2].strip():
                existing_keys.add((r[1].strip(), r[2].strip().lower()))

        added=0; upd=0
        prev_date=""
        seen_in_this_batch = set()  # DATE+Where already written in this photo

        for idx,it in enumerate(plist):
            # Blank row between different DATES (21 Oct -> 22 Oct)
            if prev_date and it["date"] != prev_date:
                ws.append_row([""]*13, value_input_option="USER_ENTERED")
            prev_date=it["date"]

            key = (it["date"], it["where"].lower())
            is_first_of_group = key not in seen_in_this_batch
            
            fidx=-1
            cur_vals = ws.get_all_values()
            for i,row in enumerate(cur_vals):
                if len(row)>6 and row[1].strip()==it["date"] and row[2].strip().lower()==it["where"].lower() and row[5].strip().lower()==it["supplier"].lower() and row[6].strip().upper()==it["fish"].upper():
                    fidx=i+1; break
            
            if fidx!=-1:
                ws.update(f"J{fidx}", [[it["kg"]]], value_input_option="USER_ENTERED")
                upd+=1
            else:
                nr = len(ws.get_all_values())+1
                row=[""]*13
                row[0]=it["week"]; row[1]=it["date"]; row[2]=it["where"]
                
                # GHASSAN LOGIC FIXED: One per DATE+Where
                if is_first_of_group and key not in existing_keys:
                    # First time we see this DATE+Where -> write GHASSAN
                    if last_g_formula: row[3]=last_g_formula.replace(str(last_g_row), str(nr))
                    else: row[3]=sc(last_f[3], nr) or "=SUM(K{0}:K{0})".format(nr)
                    if last_p_formula: row[4]=last_p_formula.replace(str(last_p_row), str(nr))
                    else: row[4]=sc(last_f[4], nr) or "=SUM(L{0}:L{0})".format(nr)
                else:
                    # Same DATE+Where already in sheet or already written in this batch -> blank
                    row[3]=""; row[4]=""

                seen_in_this_batch.add(key)
                existing_keys.add(key)

                row[5]=it["supplier"]; row[6]=it["fish"]
                if it["ptype"]=="dollar": row[7]=it["price_d"]
                elif it["ptype"]=="lbp": row[8]=it["price_l"]; row[7]=f"=I{nr}/89"
                else: row[7]=sc(last_f[7], nr) if len(last_f)>7 else ""
                row[9]=it["kg"]
                ws.update(f"A{nr}:M{nr}", [row], value_input_option="USER_ENTERED")
                added+=1

        del PENDING[phone]
        return f"Zedle {added} sorted by date! GHASSAN fixed for each Where! {plist[0]['date']} to {plist[-1]['date']}"
    except Exception as e:
        traceback.print_exc(); return f"Error: {e}"
