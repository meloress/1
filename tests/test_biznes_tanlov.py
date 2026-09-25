# -*- coding: utf-8 -*-
"""Telegram Business — faqat egasi biladigan savol va «🤖 avtojavob» belgisi.

Jonli sinovda (2026-09-25) bot egasi nomidan "menda ham sigaret qolmagan"
(egasi chekmaydi) va "boramiz, 9:00 da" (egasining vaqtini bilmay) deb
yozdi. Bu test ushlaydigan jim nosozliklar:

  ⛔️ `[tanlov:]` markeri (yoki buzilgani) suhbatdoshga ko'rinsa;
  ⛔️ shaxsiy savolga soxta javob qoralama bo'lib egasiga "Yuborish"
     tugmasi bilan kelsa (bir bosishda yolg'on ketadi);
  ⛔️ egasi tanlagan variant o'rniga boshqa matn yuborilsa, yoki model
     yozgan variant egasining "namunasi" bo'lib o'rganilsa;
  ⛔️ avtomat javobida belgi bo'lmasa yoki belgi TARIXGA tushsa (model uni
     o'z uslubi deb takrorlaydi);
  ⛔️ biznesi yo'q egaga bot narx/mahsulot haqida gapirsa (qoida yo'qolsa).

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_tanlov.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers.biznes as b              # noqa: E402
from db import database                  # noqa: E402
from services import ai                  # noqa: E402

EGASI, MIJOZ, DM = 7001, 9002, 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1-3. Marker ajratish ─────────────────────────────────────────
ta = ai.tanlov_ajrat
check(1, "to'g'ri marker: savol + variantlar, matndan olib tashlanadi",
      ta("[tanlov: 9:00 da borasizmi? | boramiz | bugun chiqolmayman] keyinroq yozaman")
      == ("keyinroq yozaman", "9:00 da borasizmi?", ["boramiz", "bugun chiqolmayman"]))
check(2, "buzilgan marker ham tanlov (variantsiz), qator oxirigacha tashlanadi",
      ta("Salom [tanlov: sigaret bormi | yo'q") == ("Salom", "—", [])
      and ta("oddiy javob") == ("oddiy javob", None, []))
check(3, "variantlar 3 tadan oshmaydi, bo'shlari tashlanadi, bo'sh savol «—»",
      ta("[TANLOV:  | a |  | b | c | d ]")[1:] == ("—", ["a", "b", "c"]))

# ── 4-5. Prompt qoidalari ────────────────────────────────────────
bi = ai.BIZNES_INSTRUCTIONS
check(4, "instructions: shaxsiy fakt to'qima, va'da berma, [tanlov:] formati",
      "O'YLAB TOPMA" in bi and "VA'DA" in bi and "[tanlov:" in bi
      and "sigaret" not in bi)   # misol emas, qoida — model so'zni ko'chirmasin
check(5, "instructions: biznes faqat yozilgan bo'lsa; suhbatdosh do'st/oila ham bo'ladi",
      "yozilmagan bo'lsa ular haqida gapirma" in bi and "oila" in bi
      and "[EGASI HAQIDA" in b.mijoz_yoriqnomasi("")
      and "(egasi hali yozmagan)" in b.mijoz_yoriqnomasi(""))

# ── 6-7. Belgi ───────────────────────────────────────────────────
check(6, "avto_matn: belgi yoqilgan — kursiv, matn html-escape; o'chiq — xom",
      b.avto_matn("a<b>", True) == {"text": "a&lt;b&gt;\n\n<i>🤖 avtojavob</i>",
                                    "parse_mode": "HTML"}
      and b.avto_matn("a<b>", False) == {"text": "a<b>", "parse_mode": None})

# ── Soxta dunyo ──────────────────────────────────────────────────
q = []
holat = {"model": ""}
loyihalar = {}


class SoxtaBot:
    async def send_message(self, chat_id, text, business_connection_id=None, **kw):
        q.append(("send", chat_id, text, business_connection_id,
                  kw.get("parse_mode"), kw.get("reply_markup")))
        return NS(chat=NS(id=chat_id), message_id=len(q) + 500)

    async def send_chat_action(self, *a, **k):
        pass

    async def read_business_message(self, *a, **k):
        pass

    async def delete_business_messages(self, *a, **k):
        pass


async def soxta_gpt(chat_id, prompt, **kw):
    yield holat["model"]


async def soxta_tarix(chat_id, content, role="user", thread_id=0, **kw):
    q.append(("tarix", content, role))


async def hech(*a, **k):
    return None


async def rost(*a):
    return True


async def ruxsat(*a):
    return {"allowed": True, "unlimited": False}


async def bosh_uslub(*a, **k):
    return {}


async def bilim(_):
    return ""


async def chat_holati(*a):
    return {"ochirilgan": False, "pauza": False}


async def yarat(owner, conn_id, chat_id, matn, loyiha, variantlar=None):
    lid = len(loyihalar) + 1
    loyihalar[lid] = dict(id=lid, owner_id=owner, conn_id=conn_id, chat_id=chat_id,
                          loyiha=loyiha, variantlar=variantlar or [], holat="kutmoqda")
    q.append(("yarat", loyiha, variantlar))
    return lid


async def band(lid, owner, holat_="kutmoqda", yangi="yuborilmoqda"):
    r = loyihalar.get(lid)
    if not r or r["owner_id"] != owner or r["holat"] != holat_:
        return None
    r["holat"] = yangi
    return dict(r)


async def yakun(lid, owner, holat_, yakuniy=None):
    loyihalar[lid]["holat"] = holat_
    q.append(("yakun", lid, holat_))


async def eskirt(owner, chat):
    q.append(("eskirt", chat))


async def pauza(owner, chat, soat):
    q.append(("pauza", chat))


async def namuna(egasi, matn):
    q.append(("namuna", matn))
    return 1, 0

b.bot = SoxtaBot()
b.get_gpt_reply = soxta_gpt
b.safe_update_history = soxta_tarix
b.track_user_activity = lambda *a: None
b.TEXT_MERGE_WAIT = 0.01
b.BIZNES_AVTOMAT_OCHIQ = True   # avtomat oqimini sinash uchun
b._hozir = lambda: __import__("datetime").datetime(2026, 9, 25, 14, 0)
# Dublikat himoyasi (AUDIT 7.1) — test_biznes_ishonch.py da; bu yerda
# har xabar birinchi (bazaga bormaydi).
b._birinchi_marta = lambda *a, **k: _birinchi()


async def _birinchi():
    return True


for nom, f in dict(pro_tarifmi=rost, get_maintenance_notice_for=hech,
                   biznes_mijoz_korildi=hech, check_and_consume_quota=ruxsat,
                   check_and_consume_daily=ruxsat, refund_daily=hech, refund_quota=hech,
                   biznes_bilim_ol=bilim, biznes_uslub_ol=bosh_uslub,
                   biznes_namuna_qosh=namuna, biznes_chat_holati=chat_holati,
                   biznes_pauza=pauza, biznes_loyiha_eskirt=eskirt,
                   biznes_loyiha_yarat=yarat, biznes_loyiha_band=band,
                   biznes_loyiha_yakun=yakun, biznes_mavzu_ol=hech).items():
    setattr(database, nom, f)

UL = {"owner_id": EGASI, "owner_chat": DM, "yoqilgan": True, "rejim": "yordamchi",
      "ish_vaqti": None, "huquqlar": {"can_reply": True, "can_read_messages": True}}
database._biznes_kesh["c1"] = UL


async def ulanish_bor(conn_id):
    return database.biznes_ulanish_ol(conn_id)

b._ulanish = ulanish_bor


def xabar(matn, kimdan=MIJOZ):
    return NS(business_connection_id="c1", text=matn, caption=None,
              sender_business_bot=None, voice=None, photo=None,
              from_user=NS(id=kimdan, username="ali", full_name="Ali"),
              chat=NS(id=MIJOZ), message_id=77, reply_to_message=None)


def ishga(*xabarlar):
    q.clear()

    async def run():
        for x in xabarlar:
            await b.biznes_xabar(x)
        await asyncio.sleep(0.1)
    asyncio.run(run())


def mijozga():
    return [x for x in q if x[0] == "send" and x[3]]


def egasiga():
    return [x for x in q if x[0] == "send" and not x[3]]


def tugmalar(x):
    return [t.callback_data for qator in x[5].inline_keyboard for t in qator] if x[5] else []


# ── 7-8. Yordamchi: soxta javob o'rniga tanlov ───────────────────
holat["model"] = "[tanlov: bugun 9:00 da CS2 ga borasizmi? | boramiz, 9 da | bugun chiqolmayman]"
ishga(xabar("bugun cs2 ga boramizmi 9:00 larga"))
e = egasiga()
check(7, "yordamchi: variantlar saqlandi, egasiga savol + variant tugmalari, «Yuborish» yo'q",
      ("yarat", "boramiz, 9 da", ["boramiz, 9 da", "bugun chiqolmayman"]) in q
      and len(e) == 1 and "faqat siz bilasiz" in e[0][2]
      and tugmalar(e[0])[:2] == ["bz:yv:1:0", "bz:yv:1:1"]
      and not any(t.startswith("bz:y:") for t in tugmalar(e[0])))
check(8, "yordamchi: suhbatdoshga HECH NARSA, marker hech qayerda",
      not mijozga() and not any("[tanlov" in str(x) for x in q if x[0] in ("send", "tarix")))

# ── 9-11. Variant yuborish ───────────────────────────────────────
q.clear()
javob = asyncio.run(b.loyihani_yubor(1, EGASI, variant=1))
m = mijozga()
check(9, "tanlangan variant AYNAN o'zi ketadi, belgisiz, `yuborildi`",
      javob.startswith("✅") and len(m) == 1 and m[0][2] == "bugun chiqolmayman"
      and m[0][4] is None and ("yakun", 1, "yuborildi") in q)
check(10, "model yozgan variant egasining namunasi EMAS",
      not any(x[0] == "namuna" for x in q))

loyihalar[1]["holat"] = "kutmoqda"
q.clear()
r1 = asyncio.run(b.loyihani_yubor(1, EGASI, variant=5))
r2 = asyncio.run(b.loyihani_yubor(1, EGASI, variant=True))
check(11, "chegaradan tashqari va bool variant — yuborilmaydi, loyiha kutishga qaytadi",
      not mijozga() and "yo'q" in r1 and "yo'q" in r2
      and loyihalar[1]["holat"] == "kutmoqda")

# ── 12. Variantsiz (buzilgan) tanlov — bo'sh matn yuborilmaydi ────
holat["model"] = "[tanlov: sigaret"
ishga(xabar("sigareting bormi"))
lid = max(loyihalar)
q.clear()
r = asyncio.run(b.loyihani_yubor(lid, EGASI))
check(12, "variantsiz tanlovni «Yuborish» — hech narsa ketmaydi, «O'zim yozaman»",
      not mijozga() and "O'zim yozaman" in r and loyihalar[lid]["holat"] == "kutmoqda")

# ── 13-15. Avtomat: neytral gap + belgi, egasiga tanlov ──────────
UL["rejim"] = "avtomat"
holat["model"] = ("[tanlov: sigaret chekasizmi? | yo'q, chekmayman | ha] "
                  "keyinroq yozaman")
ishga(xabar("sigareting bormi menda qolmadi"))
m, e = mijozga(), egasiga()
check(13, "avtomat: suhbatdoshga faqat neytral gap + 🤖 belgisi (HTML), marker yo'q",
      len(m) == 1 and m[0][2] == "keyinroq yozaman\n\n<i>🤖 avtojavob</i>"
      and m[0][4] == "HTML" and "tanlov" not in m[0][2])
check(14, "avtomat: tarixga BELGISIZ matn; chat pauzada; egasiga tanlov tugmalari",
      ("tarix", "keyinroq yozaman", "assistant") in q and ("pauza", MIJOZ) in q
      and len(e) == 1 and any(t.startswith("bz:yv:") for t in tugmalar(e[0]))
      and "keyinroq yozaman" in e[0][2])

holat["model"] = "[tanlov: nimadir buzuq"
ishga(xabar("ertaga kelasanmi"))
m = mijozga()
check(15, "avtomat: buzilgan marker — neytral gap, marker sizmaydi",
      len(m) == 1 and m[0][2].startswith(b.NEYTRAL_JAVOB) and "tanlov" not in m[0][2])

UL["avto_belgi"] = False
holat["model"] = "Salom!"
ishga(xabar("salom"))
check(16, "belgi o'chiq — oddiy javob xom matn, parse_mode yo'q",
      [(x[2], x[4]) for x in mijozga()] == [("Salom!", None)])
UL["avto_belgi"] = True

# ── 17. Egasi o'zi yozdi (avtomat) — kutayotgan tanlov eskiradi ────
ishga(xabar("kelaman", kimdan=EGASI))
check(17, "avtomatda egasi yozsa: tanlov eskiradi VA pauza",
      ("eskirt", MIJOZ) in q and ("pauza", MIJOZ) in q)

# ── 18. .javob: marker chatga ketmaydi ───────────────────────────
holat["model"] = "boraman [tanlov: aniq vaqt | 9 da]"
q.clear()
asyncio.run(b._bajar(xabar(".javob boraman de", kimdan=EGASI), UL, "javob", "boraman de"))
check(18, ".javob natijasidan marker olib tashlanadi",
      [x[2] for x in mijozga()] == ["boraman"])

# ── 19. /biznes ekrani: avtomatda belgi tugmasi ──────────────────
kb = str(b._ekran_kb(UL))
check(19, "avtomat ekranida «🤖 belgisi» tugmasi va holati",
      "bz:bl" in kb and "avtojavob" in b.ekran_matni(UL, ""))

print("\nHammasi o'tdi: 19/19")
