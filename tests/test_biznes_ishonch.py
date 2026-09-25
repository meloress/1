# -*- coding: utf-8 -*-
"""Telegram Business — ishonchlilik (AUDIT.md §7, 2.3, S2).

Bot egasi NOMIDAN yozadi, shuning uchun bu yerdagi jim xatolar egasining
obro'siga tushadi:

  ⛔️ 7.1 bitta update ikki marta kelsa — avtomat IKKI javob beradi;
  ⛔️ 7.6 model yozayotganda egasi o'zi javob bersa — eski qoralama yoki
     avtojavob baribir chiqadi (suhbatdoshga ikkinchi, eskirgan javob);
  ⛔️ 7.2 Telegram 429 — egasiga qoralama jimgina yo'qoladi;
  ⛔️ 7.4 qoralama yozilmasa — egasi buni bilmaydi, suhbatdosh javobsiz.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_ishonch.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

from aiogram.exceptions import TelegramRetryAfter  # noqa: E402
from aiogram.methods import SendMessage              # noqa: E402

import handlers.biznes as b              # noqa: E402
from db import database                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EGASI, MIJOZ, DM = 7001, 9002, 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


def r429(soniya):
    return TelegramRetryAfter(method=SendMessage(chat_id=1, text="x"),
                              message="Too Many Requests", retry_after=soniya)


# ── 1-2. 429 ─────────────────────────────────────────────────────
urinish = []


async def bir_marta_429():
    urinish.append(1)
    if len(urinish) == 1:
        raise r429(0)
    return "ok"

check(1, "429: bir marta kutib qayta yuboradi", asyncio.run(b._qayta_429(bir_marta_429)) == "ok"
      and len(urinish) == 2)

urinish.clear()


async def uzoq_429():
    urinish.append(1)
    raise r429(3600)

try:
    asyncio.run(b._qayta_429(uzoq_429))
    ushlandi = False
except TelegramRetryAfter:
    ushlandi = True
check(2, "429: uzoq kutish (> 30 s) — kutmaydi, xato yuqoriga", ushlandi and len(urinish) == 1)

# ── 3-5. Dublikat ────────────────────────────────────────────────
baza = {"javob": True, "xato": None, "chaqirildi": 0}


async def birinchimi(owner, chat, msg):
    baza["chaqirildi"] += 1
    if baza["xato"]:
        raise baza["xato"]
    return baza["javob"]

database.biznes_birinchimi = birinchimi


def xabar(matn, kimdan=MIJOZ, mid=1):
    return NS(business_connection_id="c1", text=matn, caption=None,
              sender_business_bot=None, voice=None, photo=None,
              from_user=NS(id=kimdan, username="ali", full_name="Ali"),
              chat=NS(id=MIJOZ), message_id=mid, reply_to_message=None)

b._korilgan.clear()
birinchi = asyncio.run(b._birinchi_marta(EGASI, xabar("a", mid=10)))
ikkinchi = asyncio.run(b._birinchi_marta(EGASI, xabar("a", mid=10)))
check(3, "RAM: bir xil xabar ikkinchi marta — False, bazaga bormaydi",
      birinchi is True and ikkinchi is False and baza["chaqirildi"] == 1)

baza["javob"] = False
check(4, "baza: boshqa jarayon allaqachon olgan (qayta ishga tushish) — False",
      asyncio.run(b._birinchi_marta(EGASI, xabar("a", mid=11))) is False)

baza["javob"], baza["xato"] = True, RuntimeError("baza yo'q")
check(5, "baza xatosi — True (xabarni yo'qotgandan ikki marta ishlagan ma'qul)",
      asyncio.run(b._birinchi_marta(EGASI, xabar("a", mid=12))) is True)
baza["xato"] = None

# ── Soxta dunyo (avtomat / yordamchi) ────────────────────────────
q = []
holat = {"model": "Salom!", "model_xato": None, "egasi_yozadi": False}


class SoxtaBot:
    async def send_message(self, chat_id, text, business_connection_id=None, **kw):
        q.append(("send", chat_id, text, business_connection_id))
        return NS(chat=NS(id=chat_id), message_id=len(q) + 900)

    async def send_chat_action(self, *a, **k):
        pass

    async def read_business_message(self, *a, **k):
        pass


async def soxta_gpt(chat_id, prompt, **kw):
    if holat["egasi_yozadi"]:
        # Model yozayotgan paytda egasi chatga o'zi javob berdi.
        await b.biznes_xabar(xabar("o'zim yozdim", kimdan=EGASI, mid=5000))
    if holat["model_xato"]:
        raise holat["model_xato"]
    yield holat["model"]


async def hech(*a, **k):
    return None


async def rost(*a):
    return True


async def ruxsat(*a):
    return {"allowed": True, "unlimited": False}


async def bosh(*a, **k):
    return {}


async def bilim(_):
    return ""


async def chat_holati(*a):
    return {"ochirilgan": False, "pauza": False}


async def refund_quota(*a):
    q.append(("refund_quota",))


async def refund_daily(*a):
    q.append(("refund_daily",))


async def xato_voronka(chat_id, message_id, user_id, prompt, **kw):
    q.append(("xato", kw.get("reason")))


async def yarat(*a):
    q.append(("yarat",))
    return 1


async def namuna(*a):
    return 1, 0

b.bot = SoxtaBot()
b.get_gpt_reply = soxta_gpt
b.safe_update_history = hech
b.send_error_with_retry = xato_voronka
b.track_user_activity = lambda *a: None
b.BIZNES_MERGE_WAIT = 0.01
for nom, f in dict(pro_tarifmi=rost, get_maintenance_notice_for=hech,
                   biznes_mijoz_korildi=hech, check_and_consume_quota=ruxsat,
                   check_and_consume_daily=ruxsat, refund_daily=refund_daily,
                   refund_quota=refund_quota, biznes_bilim_ol=bilim,
                   biznes_uslub_ol=bosh, biznes_namuna_qosh=namuna,
                   biznes_chat_holati=chat_holati, biznes_pauza=hech,
                   biznes_loyiha_eskirt=hech, biznes_loyiha_yarat=yarat,
                   biznes_mavzu_ol=hech, biznes_kutayotgan_tanlov=hech).items():
    setattr(database, nom, f)

UL = {"owner_id": EGASI, "owner_chat": DM, "yoqilgan": True, "rejim": "avtomat",
      "ish_vaqti": None, "avto_belgi": False,
      "huquqlar": {"can_reply": True, "can_read_messages": True}}
database._biznes_kesh["c1"] = UL


async def ulanish_bor(conn_id):
    return database.biznes_ulanish_ol(conn_id)

b._ulanish = ulanish_bor


def ishga(*xabarlar):
    q.clear()
    b._aytilgan.clear()
    b._egasi_yozgan.clear()

    async def run():
        for x in xabarlar:
            await b.biznes_xabar(x)
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.1)
    asyncio.run(run())


def mijozga():
    return [x[2] for x in q if x[0] == "send" and x[3]]


# ── 6. Dublikat update avtomatda — bitta javob ───────────────────
b._korilgan.clear()
ishga(xabar("salom", mid=100), xabar("salom", mid=100))
check(6, "avtomat: bir xil update ikki marta — suhbatdoshga BITTA javob",
      mijozga() == ["Salom!"])

# ── 7-8. Poyga: egasi model yozayotganda javob berdi ─────────────
holat["egasi_yozadi"] = True
ishga(xabar("9 da kelasanmi", mid=101))
check(7, "avtomat: egasi o'zi yozdi — bot jim, sanoq qaytarildi",
      mijozga() == [] and ("refund_daily",) in q)

UL["rejim"] = "yordamchi"
ishga(xabar("9 da kelasanmi", mid=102))
check(8, "yordamchi: egasi o'zi yozdi — qoralama ko'rsatilmaydi, ball qaytdi, xato xabari yo'q",
      ("yarat",) not in q and ("refund_quota",) in q
      and not any(x[0] == "xato" for x in q)
      and not any(x[0] == "send" and x[1] == DM for x in q))
holat["egasi_yozadi"] = False

# ── 9-10. Qoralama yozilmadi — egasiga (soatiga bir) ─────────────
holat["model_xato"] = RuntimeError("OpenAI 503")
ishga(xabar("narxi?", mid=103), xabar("hali ham?", mid=104))
xatolar = [x for x in q if x[0] == "xato"]
check(9, "yordamchi: model xatosi — egasiga «qoralama yozilmadi», soatiga BIR marta",
      len(xatolar) == 1 and "qoralamasi yozilmadi" in xatolar[0][1]
      and ("refund_quota",) in q)
holat["model_xato"] = None

holat["model"] = ""
ishga(xabar("salom", mid=105))
check(10, "yordamchi: bo'sh javob ham egasiga aytiladi (jim qolmaydi)",
      any(x[0] == "xato" for x in q))
holat["model"] = "Salom!"

# ── 11. Kunlik tozalash qoralama tranzaksiyasidan chiqdi ─────────
db_manba = kod(os.path.join(ROOT, "db", "database.py"))
yarat_fn = db_manba[db_manba.index("async def biznes_loyiha_yarat("):
                    db_manba.index("async def biznes_birinchimi(")]
check(11, "S2: 30 kunlik DELETE qoralama yaratishda emas, kunlik tozalashda",
      "DELETE" not in yarat_fn and "biznes_tozala()" in kod(os.path.join(ROOT, "handlers", "biznes.py")))

print("\nHammasi o'tdi: 11/11")
