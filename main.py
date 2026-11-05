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
                # No language lock - understands Arabizi + Arabic!
                r = await c.post("https://api.openai.com/v1/audio/transcriptions", 
                    headers={"Authorization": f"Bearer {env['OPENAI_KEY']}"}, 
                    files={"file": (p, af, "audio/ogg")}, 
                    data={"model": "whisper-1", "prompt": "Nohra fish shop Lebanese. Words: zedle, l8i, shelle, ghayerle, Asfar, Malifa, Jarbide, Bra, Bezri, Faride, Jrawe, Kalamari, Bernard, Nohra, Antelias, Adma, Broumana, Baabda, kilo"})
                j = r.json()
                print(f"VOICE RAW: {j}")
                text = j.get("text","")
                # Normalize Arabic voice to bot commands
                text = text.replace("الغي","l8i").replace("ألغي","l8i").replace("الغ","l8i")
                text = text.replace("شيل","shelle").replace("امسح","l8i").replace("احذف","l8i")
                text = text.replace("زيدلي","zedle").replace("زيد لي","zedle").replace("زيد","zedle")
                text = text.replace("غيرلي","ghayerle").replace("غير","ghayer").replace("عدل","ghayer")
                text = text.replace("نعم","yes").replace("ايه","yes").replace("أه","yes")
                text = text.replace("لا","no")
                # Arabic fish map for voice
                text = text.replace("أصفر","Asfar").replace("اصفر","Asfar")
                text = text.replace("مليفة","Malifa").replace("جربيدي","Jarbide").replace("برا","Bra")
                text = text.replace("بزري","Bezri").replace("فريدي","Faride").replace("جرو","Jrawe")
                text = text.replace("كالاماري","Kalamari").replace("كالامار","Kalamari")
                print(f"VOICE CLEAN: {text}")
                return text
    except Exception as e:
        print(f"Voice error {e}"); traceback.print_exc(); return None
