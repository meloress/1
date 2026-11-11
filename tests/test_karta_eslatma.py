# -*- coding: utf-8 -*-
"""Karta to'lovi: «to'lovim qayerda?», chek eslatmasi va «vaqt tugadi».

  ⛔️ chek yuborgan odam /pro da holatini ko'radi — ikkinchi to'lov ochmasin;
  ⛔️ oyna tugaganda odamga «vaqt tugadi, to'lagan bo'lsangiz — adminga»
     xabari ADMIN TUGMASI bilan boradi (pul ketgan bo'lishi mumkin);
  ⛔️ eskirgan so'rov summani band qilmaydi va chek qabul qilmaydi;
  ⛔️ eslatma va «tugadi» bir martalik — belgilash bitta UPDATE … RETURNING da.

Tarmoqsiz va bazasiz (`database.*` soxta). SQL'i pgserver'da ham tekshirilgan.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_karta_eslatma.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.config as c                  # noqa: E402
import handlers.pro as p                 # noqa: E402
from db import database                  # noqa: E402
from tests._manba import kod             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_URL = f"https://t.me/{c.ADMIN_USERNAME}"
HOZIR = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)      # Toshkentda 14:00


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


def tugmalar(qatorlar):
    return [t.callback_data or t.url for q in qatorlar for t in q]


# ── 1-3. «To'lovim qayerda?» bloki ────────────────────────────────
tek = {"id": 42, "holat": "tekshirilmoqda", "days": 30, "summa": 25_047, "sabab": None,
       "yaratilgan": HOZIR, "chek_vaqti": HOZIR + timedelta(minutes=32)}
blok, tugma = p.karta_holat_matni(tek)
check(1, "tekshirilmoqda: #raqam, summa, chek vaqti <tg-time>, «qayta to'lash shart emas», tugmasiz",
      "#42" in blok and "25 047" in blok and 'format="t">14:32</tg-time>' in blok
      and "qayta to'lash" in blok and tugma == [])

blok, tugma = p.karta_holat_matni({**tek, "holat": "rad", "sabab": "summa <mos emas>"})
check(2, "rad: sabab (escape) va «Chekni yuborish»",
      "summa &lt;mos emas&gt;" in blok and tugmalar([tugma]) == ["pro:chek:42"])

blok, tugma = p.karta_holat_matni({**tek, "holat": "kutmoqda", "chek_vaqti": None})
check(3, "kutmoqda: qachongacha ochiq (yaratilgan + oyna) va «Chekni yuborish»",
      'format="t">17:00</tg-time> gacha' in blok and tugmalar([tugma]) == ["pro:chek:42"])


# ── 4. /pro ekrani tepasida ───────────────────────────────────────
OCHIQ = {"v": None}


async def faol(uid, oyna):
    assert oyna == p.KARTA_CHEK_OYNA
    return OCHIQ["v"]


async def yoq(*a):
    return None


async def profil(uid):
    return {"plan_type": "free", "premium_until": None}

database.karta_faol_sorov = faol
database.pro_obuna_ol = yoq
database.karta_ol = yoq
database.get_full_user_profile = profil

oddiy, kb0 = asyncio.run(p._render_pro_screen(1))
OCHIQ["v"] = {**tek, "holat": "kutmoqda"}
matn, kb = asyncio.run(p._render_pro_screen(1))
check(4, "ochiq so'rov — blok ekran TEPASIDA, «Chekni yuborish» birinchi qatorda; yo'q bo'lsa — o'zgarmaydi",
      matn.startswith("💳 <b>Ochiq to'lovingiz bor</b>") and matn.endswith(oddiy)
      and tugmalar(kb.inline_keyboard)[0] == "pro:chek:42"
      and tugmalar(kb.inline_keyboard)[1:] == tugmalar(kb0.inline_keyboard))


async def yiqil(uid, oyna):
    raise RuntimeError("baza yo'q")
database.karta_faol_sorov = yiqil
matn, _ = asyncio.run(p._render_pro_screen(1))
check("4a", "baza xatosi — /pro yiqilmaydi, blok shunchaki yo'q", matn == oddiy)


# ── 5-6. Watcher: eslatma va «vaqt tugadi» ────────────────────────
YUBORILDI = []


async def send_message(uid, matn, **kw):
    YUBORILDI.append((uid, matn, kw["reply_markup"].inline_keyboard))
p.bot = NS(send_message=send_message)


async def eslatmalar(eslat, oyna):
    assert (eslat, oyna) == (p.KARTA_ESLATMA, p.KARTA_CHEK_OYNA)
    return {"eslat": [{"id": 7, "user_id": 11, "days": 30, "summa": 25_011, "yaratilgan": HOZIR}],
            "tugadi": [{"id": 8, "user_id": 12, "days": 90, "summa": 75_123, "yaratilgan": HOZIR}]}
database.karta_eslatmalar = eslatmalar
asyncio.run(p.karta_tekshir())

(u1, m1, kb1), (u2, m2, kb2) = YUBORILDI
check(5, "eslatma: o'sha odamga, #raqam, summa, qachongacha; «Chekni yuborish» + «Bekor qilish»",
      u1 == 11 and "#7" in m1 and "25 011" in m1 and "17:00</tg-time> gacha" in m1
      and tugmalar(kb1) == ["pro:chek:7", "pro:kb:7"])
check(6, "vaqt tugadi: #raqam, «to'lagan bo'lsangiz — adminga», ADMIN tugmasi va «Yangi to'lov» "
          "(pro:qayta:<id> — eski xabarlar o'chib, muddatlar yangi ekranda)",
      u2 == 12 and "To'lov vaqti tugadi" in m2 and "#8" in m2 and "adminga" in m2
      and tugmalar(kb2) == [ADMIN_URL, "pro:qayta:8"])


async def bloklagan(uid, matn, **kw):
    raise RuntimeError("Forbidden: bot was blocked by the user")
p.bot = NS(send_message=bloklagan)
asyncio.run(p.karta_tekshir())           # yiqilmasligi kerak
check("6a", "botni bloklagan odam — qolganlarga xalal bermaydi (watcher yiqilmaydi)", True)


# ── 7. Oyna shu daqiqada yopilgan — chek adminga yo'naltiriladi ───
class Holat:
    async def get_data(self):
        import time
        return {"karta_id": 9, "karta_t": time.time()}

    async def clear(self):
        pass


class Xabar:
    def __init__(self):
        self.from_user = NS(id=11, full_name="Ali", username=None)
        self.photo = [NS(file_id="f", file_unique_id="u")]
        self.javob = None

    async def answer(self, matn, **kw):
        self.javob = (matn, kw.get("reply_markup"))


async def chek_yoz(*a):
    return None
database.karta_chek_yoz = chek_yoz
x = Xabar()
asyncio.run(p.process_karta_chek(x, Holat()))
check(7, "yopilgan so'rovga chek: «pul o'tkazgan bo'lsangiz — adminga» + admin tugmasi",
      "yopilgan" in x.javob[0] and "adminga" in x.javob[0]
      and tugmalar(x.javob[1].inline_keyboard) == [ADMIN_URL])


# ── 8. Matnlar: raqam, muddat, va'da ──────────────────────────────
m = p.karta_sorov_matni(30, 25_047, "8600123412341234", "ALI", 42)
check(8, "so'rov matni: #raqam va «3 soat amal qiladi»; va'da «odatda bir necha soat … 24 soat»",
      "#42" in m and "3 soat amal qiladi" in m and p.KARTA_VADA in m
      and "24 soat" in p.KARTA_VADA and p.KARTA_VADA in p.karta_tariflar_matni()
      and "#42" not in p.karta_sorov_matni(30, 25_047, "8600123412341234", "ALI"))


# ── 9. SQL: bir martalik, eskirgan so'rov faol emas ───────────────
src = kod(os.path.join(ROOT, "db", "database.py"))
f = src[src.index("async def karta_eslatmalar"):]
f = f[:f.index("\n\n\n")]
check(9, "eslatma bir marta (NOT eslatildi), tugagan → 'eskirdi'; eskirgan summa band emas va chek olmaydi",
      "SET eslatildi = TRUE WHERE holat = 'kutmoqda' AND NOT eslatildi" in f
      and "SET holat = 'eskirdi'" in f and "RETURNING" in f
      and "eskirdi" not in database._KARTA_FAOL
      and "ADD COLUMN IF NOT EXISTS eslatildi" in src)

print("\nHammasi o'tdi: 9 + 3")
