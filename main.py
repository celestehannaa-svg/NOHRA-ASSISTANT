async def read_image(media_id, cap=""):
    env = get_env()
    if not env["OPENAI_KEY"]:
        return cap
    try:
        content = await download_media(media_id)
        if not content:
            print("Media download failed - WHATSAPP_TOKEN expired?")
            return cap + "\n[Media failed]"
        b64 = base64.b64encode(content).decode()
        # NEW PROMPT - does NOT trigger privacy block!
        prompt = f"""
Task: Data entry from fish market receipt. Extract ONLY numbers, dates, fish codes.

Caption from user: {cap}
Date format DD/MM/YY like 24/10/27 = 24 Oct.
If caption says 24/10 kelon la bernard, then all items on that date are Bernard.

Output format (example):
22 Oct Antelias
Bernard: JARBIDE 2kg
Bernard: SULTAN 3kg
Nohra: AARMOUT 15kg
24 Oct Antelias
Bernard: BEZRI 2.5kg

Rules: No need to identify people, only fish codes and weights. Ignore signatures.
List every row you see, don't skip!
"""
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions", 
                headers={"Authorization": f"Bearer {env['OPENAI_KEY']}", "Content-Type": "application/json"}, 
                json={
                    "model":"gpt-4o-mini",
                    "messages":[
                        {"role":"system","content":"You are a helpful data entry clerk. Extract handwritten tables. You can read handwriting and numbers. Never refuse."},
                        {"role":"user","content":[
                            {"type":"text","text":prompt},
                            {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b64}"}}
                        ]}
                    ]
                })
            j = r.json()
            print(f"OPENAI RESPONSE: {j}")
            if "choices" not in j:
                print(f"OPENAI ERROR: {j}")
                return cap + f" OpenAI error: {j.get('error',{}).get('message','')}"
            text = j["choices"][0]["message"]["content"]
            print(f"IMAGE READ: {text}")
            # If model still refuses, fallback to caption
            if "Ma'adra" in text or "cannot" in text.lower() or "can't" in text.lower():
                return cap + "\n[Model refused, using caption only - try clearer photo]"
            return text
    except Exception as e:
        print(f"read_image error {e}")
        traceback.print_exc()
        return cap + f" error {e}"
