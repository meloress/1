# -*- coding: utf-8 -*-
"""Avtomatik texnik ta'til (`services/avto_tatil.py`) va Business'dagi ta'til.

NEGA BOR: kredit tugasa yoki OpenAI kaliti o'chsa bot ta'tilni O'ZI yoqadi.
Eng qimmat xato — teskarisi: kichik xatoda bot o'zidan-o'zi to'xtab qolishi.

ENG MUHIM TEKSHIRUVLAR:
  2-band — daqiqalik 429, timeout, 5xx, ulanish uzilishi JIDDIY EMAS.
  4-band — bitta jiddiy xato yetmaydi; oradagi muvaffaqiyat hisobni nolaydi.
  5-band — nazorat so'rovi o'tsa yoki noaniq bo'lsa ta'til YOQILMAYDI.
  9-band — faqat O'ZI yoqqan ta'tilni o'chiradi; qo'lda yoqilganiga tegmaydi.
  12-band — Business mijozi ta'til xabarini HAR TA'TILDA bir marta oladi.

Tarmoqsiz va bazasiz: OpenAI, baza va Telegram soxta.

    PYTHONIOENCODING=utf-8 python tests/test_avto_tatil.py
"""
import asyncio
import os
import sys
import time
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod                     # noqa: E402

import httpx                               # noqa: E402
import openai                              # noqa: E402

import core.loader as loader               # noqa: E402
import handlers.biznes as b                # noqa: E402
from db import database                    # noqa: E402
from handlers.admin import daily           # noqa: E402
from services import ai                    # noqa: E402
from services import avto_tatil as at      # noqa: E402

_n = 0


def check(nom, shart):
    global _n
    _n += 1
    assert shart, f"[{_n}] {nom} — YIQILDI"
    print(f"[{_n}] {nom} OK")


_SOROV = httpx.Request("POST", "https://api.openai.com/v1/responses")


def holat_xato(cls, kod_, body=None):
    return cls("xato", response=httpx.Response(kod_, request=_SOROV), body=body)


KREDIT = holat_xato(openai.RateLimitError, 429,
                    {"code": "insufficient_quota", "type": "insufficient_quota"})
TPM = holat_xato(openai.RateLimitError, 429, {"code": "rate_limit_exceeded"})
KALIT = holat_xato(openai.AuthenticationError, 401, {"code": "invalid_api_key"})
RUXSAT = holat_xato(openai.PermissionDeniedError, 403, None)
YOQ = holat_xato(openai.NotFoundError, 404, None)
SERVER = holat_xato(openai.InternalServerError, 500, None)
ULANISH = openai.APIConnectionError(request=_SOROV)
VAQT = openai.APITimeoutError(request=_SOROV)

# ── 1-2. Tasnif ──────────────────────────────────────────────────
J = at.jiddiy_xato
check("jiddiy: kredit / kalit / ruxsat / model",
      [J(KREDIT), J(KALIT), J(RUXSAT), J(YOQ)] == ["kredit", "kalit", "ruxsat", "model"])
check("o'tkinchi: daqiqalik 429, 500, ulanish, timeout, oddiy xato — None",
      all(J(e) is None for e in (TPM, SERVER, ULANISH, VAQT, TimeoutError(),
                                 ValueError("x"), None)))

# ── Soxta dunyo ──────────────────────────────────────────────────
Q = []                    # (tur, ...) — nima yuborildi/chaqirildi
H = {"sinov": [], "active": False, "avto": None, "vaqt": "T1", "yoqildi": True}


class SoxtaResponses:
    async def create(self, model, **kw):
        Q.append(("sinov", model))
        natija = H["sinov"].pop(0) if H["sinov"] else "ok"
        if natija != "ok":
            raise natija
        return NS(status="incomplete")


class SoxtaBot:
    async def send_message(self, chat_id, text, business_connection_id=None, **kw):
        Q.append(("send", chat_id, text, business_connection_id))
        return NS(chat=NS(id=chat_id), message_id=len(Q) + 900)


async def yoq(sabab):
    Q.append(("yoq", sabab))
    return H["yoqildi"]


async def ochir():
    Q.append(("ochir",))
    return True


async def get_m():
    return {"active": H["active"], "avto": H["avto"], "vaqt": H["vaqt"],
            "message": "🛠 Bot hozirda texnik ta'til rejimida.", "avtomat": None}


async def hech(*a, **k):
    return None


async def superadmin():
    return 555


async def guruh(matn):
    Q.append(("guruh", matn))
    return True


ai.openai_client = NS(responses=SoxtaResponses())
loader.bot = SoxtaBot()
b.bot = loader.bot
daily._ogoh_yubor = guruh
for nom, f in dict(maintenance_avto_yoq=yoq, maintenance_avto_ochir=ochir,
                   get_maintenance=get_m, get_superadmin_id=superadmin,
                   log_error=hech).items():
    setattr(database, nom, f)


def tur(t):
    return [x for x in Q if x[0] == t]


async def kut():
    if at._sinov_vazifa is not None:
        await at._sinov_vazifa


def tozala():
    Q.clear()
    H["sinov"] = []
    at._ketma_ket = 0
    at._oxirgi_sinov = 0.0
    at._sinov_vazifa = None


async def main():
    # ── 3. sinov(): zaxira tartibi `_open_response_stream` bilan bir xil
    tozala()
    H["sinov"] = [YOQ]                      # asosiy yo'q, zaxira ishlaydi
    r1 = await at.sinov()
    n1 = len(tur("sinov"))
    tozala()
    H["sinov"] = [KREDIT] * 9
    r2 = await at.sinov()
    tozala()
    H["sinov"] = [KALIT, "ok"]              # 401 — zaxiraga O'TILMAYDI
    r3 = await at.sinov()
    n3 = len(tur("sinov"))
    tozala()
    H["sinov"] = [VAQT]
    r4 = await at.sinov()
    check("sinov: 404→zaxira ok; hammasida kredit; 401 to'xtaydi; timeout noaniq",
          r1 == ("ok", "") and n1 == 2 and r2[0] == "kredit"
          and r3[0] == "kalit" and n3 == 1 and r4[0] is None)

    # ── 4. Bitta jiddiy xato — sinov YO'Q; muvaffaqiyat hisobni nolaydi
    tozala()
    at.xato(KREDIT)
    at.yaxshi()
    at.xato(KREDIT)
    await kut()
    a = tur("sinov")
    at.xato(TPM)
    at.xato(SERVER)
    at.xato(VAQT)
    await kut()
    check("1 ta jiddiy xato, muvaffaqiyat, yana 1 ta + o'tkinchilar — sinov ham yo'q",
          a == [] and tur("sinov") == [] and tur("yoq") == [])

    # ── 5. Ikki ketma-ket — sinov; sinov o'tsa / noaniq bo'lsa yoqilmaydi
    tozala()
    at.xato(KREDIT)
    at.xato(KREDIT)
    await kut()
    ok_holat = (len(tur("sinov")) == 1 and tur("yoq") == [] and at._ketma_ket == 0)
    tozala()
    H["sinov"] = [VAQT]
    at.xato(KALIT)
    at.xato(KALIT)
    await kut()
    check("2 ta ketma-ket → sinov; sinov o'tdi / timeout — ta'til YOQILMADI",
          ok_holat and len(tur("sinov")) == 1 and tur("yoq") == [])

    # ── 6. Sinov oralig'i: noaniq sinovdan keyin darhol qayta sinalmaydi
    at.xato(KALIT)
    await kut()
    check(f"sinovlar orasida kamida {at.SINOV_ORALIGI} s — qayta sinov yo'q",
          len(tur("sinov")) == 1)

    # ── 7. Sinov ham jiddiy — yoqiladi, superadmin + guruh xabardor
    tozala()
    H["sinov"] = [KREDIT] * 9
    at.xato(KREDIT)
    at.xato(KREDIT)
    await kut()
    yuborildi = tur("send")
    check("sinov ham kredit → yoqildi; superadmin'ga va guruhga sabab + yechim",
          tur("yoq") == [("yoq", "kredit")] and yuborildi and yuborildi[0][1] == 555
          and "kredit" in yuborildi[0][2] and "Billing" in yuborildi[0][2]
          and len(tur("guruh")) == 1)

    # ── 8. Allaqachon (qo'lda) yoqilgan — xabar yo'q
    tozala()
    H["yoqildi"] = False
    H["sinov"] = [KALIT]
    at.xato(KALIT)
    at.xato(KALIT)
    await kut()
    check("ta'til qo'lda yoqilgan bo'lsa — tegilmaydi, xabar ham yo'q",
          tur("yoq") and not tur("send") and not tur("guruh"))
    H["yoqildi"] = True

    # ── 9. Tiklanish: faqat O'ZI yoqqanini o'chiradi
    tozala()
    H.update(active=True, avto=None)
    await at._tiklanish()
    qolda = list(Q)
    H.update(active=True, avto="kredit")
    H["sinov"] = [KREDIT] * 9
    await at._tiklanish()
    buzuq = tur("ochir")
    tozala()
    await at._tiklanish()                   # endi sinov o'tadi
    check("qo'lda yoqilgan — sinov ham yo'q; buzuq — o'chmaydi; tuzaldi — o'chdi + ✅",
          qolda == [] and buzuq == [] and tur("ochir")
          and any("qayta ishlayapti" in x[2] for x in tur("send")))

    # ── 10. Hali ham buzuq — eslatma ESLATMA dan keyin, oldin emas
    tozala()
    H["sinov"] = [KREDIT] * 18
    at._oxirgi_eslatma = time.monotonic()
    await at._tiklanish()
    oldin = tur("send")
    at._oxirgi_eslatma -= at.ESLATMA + 1
    await at._tiklanish()
    check("buzuqlik davom etsa — eslatma faqat 6 soatda bir",
          oldin == [] and any("hali ham" in x[2] for x in tur("send")))
    H.update(active=False, avto=None)

    # ── 11-14. Business ──────────────────────────────────────────
    chaqiruv = []

    async def notice(owner, adminga_ham=False):
        chaqiruv.append(adminga_ham)
        return "🛠 ta'til" if H["active"] else None

    hol = {"pauza": False}

    async def chat_holati(owner, chat):
        return {"ochirilgan": False, "pauza": hol["pauza"], "uzatish": False}

    database.get_maintenance_notice_for = notice
    database.biznes_chat_holati = chat_holati
    b.biznes_mavzusi = hech
    ul = {"rejim": "avtomat", "huquqlar": {"can_reply": True}, "ish_vaqti": None,
          "owner_id": 7001, "owner_chat": 7001, "avto_belgi": False}
    b.BIZNES_AVTOMAT_OCHIQ = True
    H["active"] = True
    hol["pauza"] = True
    s1 = await b._toxtash_sababi(ul, 9002)
    hol["pauza"] = False
    s2 = await b._toxtash_sababi(ul, 9002)
    check("Business: pauzadagi chat — «pauza» (ta'til xabari yo'q); ta'til — "
          "egasi admin bo'lsa ham (adminga_ham=True)",
          s1 == "pauza" and s2 == "ta'til" and chaqiruv == [True])

    Q.clear()
    await b._tatil_mijozga(9002, "conn1", ul)
    await b._tatil_mijozga(9002, "conn1", ul)
    await b._tatil_mijozga(9003, "conn1", ul)
    mijoz = [x for x in tur("send") if x[3] == "conn1"]
    egasiga = [x for x in tur("send") if x[1] == 7001]
    check("mijozga paneldagi matn — bir chatga BIR marta; egasiga ham bir marta",
          [x[1] for x in mijoz] == [9002, 9003]
          and all("texnik ta'til rejimida" in x[2] for x in mijoz)
          and len(egasiga) == 1)

    Q.clear()
    H["vaqt"] = "T2"                        # yangi ta'til
    await b._tatil_mijozga(9002, "conn1", ul)
    H["active"] = False
    await b._tatil_mijozga(9004, "conn1", ul)
    check("keyingi ta'tilda yana bir marta; ta'til tugagan bo'lsa — hech narsa",
          [x[1] for x in tur("send") if x[3] == "conn1"] == [9002])

    Q.clear()
    H["active"] = True
    b.instagram._izohlar[-77] = ("c1", 0)
    await b._tatil_mijozga(-77, b.instagram.PREFIKS + "hisob", ul)
    check("Instagram izohi — ta'til xabari YO'Q (yagona yopiq javob saqlanadi)",
          Q == [])


asyncio.run(main())

# ── 15-17. Manba qo'riqchilari (izohsiz kod) ─────────────────────
ai_kod = kod("services/ai.py")
check("get_openai_reply: muvaffaqiyatda yaxshi(), ikkala except'da xato(e)",
      "avto_tatil.yaxshi()" in ai_kod and ai_kod.count("avto_tatil.xato(e)") == 2
      and "or avto_tatil.jiddiy_xato(e):" in ai_kod)
db_kod = kod("db/database.py")
check("qo'lda o'zgartirish avtomatik belgini tushiradi, faqat matn tahriri — yo'q",
      "maintenance_avto = CASE WHEN $1 = COALESCE(maintenance_active, FALSE)" in db_kod
      and "WHERE id = 1 AND NOT COALESCE(maintenance_active, FALSE)" in db_kod
      and "maintenance_active AND maintenance_avto IS NOT NULL" in db_kod)
check("main.py kuzatuvchini ishga tushiradi",
      "avto_tatil.kuzatuvchi()" in kod("main.py"))

print(f"\nNATIJA: {_n}/{_n} OK")
