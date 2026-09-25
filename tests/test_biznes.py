# -*- coding: utf-8 -*-
"""Telegram Business, 1-bosqich — ulanish va egasining buyruqlari.

Ikkita JIM nosozlikni ushlaydi (REJA.md 0.3, 0.5):

  ⛔️ (1) TSIKL: bot o'z xabariga yoki egasining oddiy gapiga javob
     bersa, chat cheksiz aylanadi. Kim yozganini FAQAT `biznes_kimdan()`
     hal qiladi.
  ⛔️ (2) Uzilgan ulanish keshda yoqiq qolsa, bot buyruq bajarishda
     davom etadi va hech narsa xato bermaydi.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes.py
"""
import asyncio
import os
import sys
from datetime import datetime
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram.types import BusinessBotRights, BusinessConnection, User  # noqa: E402

import db.history as h                   # noqa: E402
import handlers.biznes as b              # noqa: E402
import handlers.capabilities as cap      # noqa: E402
from db import database                  # noqa: E402
from services import ai                  # noqa: E402

EGASI, MIJOZ, DM = 7001, 9002, 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


def xabar(matn, kimdan=MIJOZ, bot_yubordi=False, conn="c1"):
    return NS(business_connection_id=conn, text=matn, caption=None,
              sender_business_bot=NS(id=1) if bot_yubordi else None,
              from_user=NS(id=kimdan, username="u"), chat=NS(id=MIJOZ),
              message_id=55, reply_to_message=None)


UL = {"owner_id": EGASI, "owner_chat": DM, "yoqilgan": True, "rejim": "buyruq",
      "huquqlar": {"can_reply": True, "can_read_messages": True}}


# ── Soxta tashqi dunyo ───────────────────────────────────────────
class Qayd:
    """Chaqiruvlar jurnali — tartibni ham tekshirish uchun bitta ro'yxat."""
    def __init__(self):
        self.l = []


q = Qayd()
holat = {"pro": True, "kvota": {"allowed": True, "unlimited": False},
         "model": "Hello", "send_xato": None}


class SoxtaBot:
    async def send_message(self, chat_id, text, business_connection_id=None, **kw):
        if business_connection_id and holat["send_xato"]:
            raise RuntimeError(holat["send_xato"])
        q.l.append(("send", chat_id, text, business_connection_id))

    async def delete_business_messages(self, conn_id, ids):
        q.l.append(("delete", conn_id, tuple(ids)))


async def soxta_gpt(chat_id, prompt, **kw):
    q.l.append(("gpt", chat_id, kw.get("thread_id"), kw.get("tools_enabled")))
    yield holat["model"]


async def soxta_pro(_):
    q.l.append(("pro?",))
    return holat["pro"]


async def soxta_kvota(uid, narx):
    q.l.append(("kvota", uid, narx))
    return holat["kvota"]


async def soxta_refund(uid, narx):
    q.l.append(("refund", uid, narx))


async def soxta_tarix(chat_id, content, role="user", thread_id=0, **kw):
    q.l.append(("tarix", chat_id, role, thread_id))


async def hech(*a, **kw):
    return None


b.bot = SoxtaBot()
b.get_gpt_reply = soxta_gpt
b.safe_update_history = soxta_tarix
b.track_user_activity = lambda *a: q.l.append(("faollik", a[-1]))
database.pro_tarifmi = soxta_pro
database.check_and_consume_quota = soxta_kvota
database.refund_quota = soxta_refund
database.get_maintenance_notice_for = hech


async def ulanish_bor(conn_id):
    return database.biznes_ulanish_ol(conn_id)

b._ulanish = ulanish_bor


def ishga(coro):
    q.l.clear()
    b._aytilgan.clear()
    asyncio.run(coro)
    return [x[0] for x in q.l]


# ── 1-3. Kim yozdi ───────────────────────────────────────────────
check(1, "mijoz xabari -> mijoz", b.biznes_kimdan(xabar("salom"), UL) == "mijoz")
check(2, "egasining xabari -> egasi",
      b.biznes_kimdan(xabar("salom", kimdan=EGASI), UL) == "egasi")
# Bot egasi nomidan yuborganda from_user EGASI bo'ladi — shuning uchun
# `sender_business_bot` birinchi tekshirilishi shart.
check(3, "bot yuborgan (from_user = egasi) -> bot",
      b.biznes_kimdan(xabar(".en Salom", kimdan=EGASI, bot_yubordi=True), UL) == "bot")

database._biznes_kesh["c1"] = dict(UL)
izlar = ishga(b.biznes_xabar(xabar(".en Salom", kimdan=EGASI, bot_yubordi=True)))
check(4, "bot o'z xabariga HECH NARSA qilmaydi (na model, na tarix)", izlar == [])

# ── 5-6. Mavzu nomi va tarix kaliti ──────────────────────────────
check(5, "manfiy thread_id -> nomlash_kerakmi False",
      ai.nomlash_kerakmi(MIJOZ, b.biznes_thread(EGASI), "assistant", 2) is False
      and ai.nomlash_kerakmi(MIJOZ, 55, "assistant", 2) is True)

h._cache[(MIJOZ, 0)] = [{"role": "user", "content": "DM gapi"}]
h._cache[(MIJOZ, b.biznes_thread(EGASI))] = [{"role": "user", "content": "biznes gapi"}]
dm = asyncio.run(h.get_chat_history(MIJOZ, 10))
bz = asyncio.run(h.get_chat_history(MIJOZ, 10, thread_id=b.biznes_thread(EGASI)))
check(6, "mijoz chati tarixi uning DM tarixi bilan aralashmaydi",
      dm[0]["content"] == "DM gapi" and bz[0]["content"] == "biznes gapi"
      and b.biznes_thread(EGASI) < 0 and b.biznes_thread(EGASI) != b.biznes_thread(EGASI + 1))

# ── 7-8. Buyruq ajratish ─────────────────────────────────────────
check(7, "ro'yxatda yo'q .so'z -> None",
      b.buyruq_ajrat(".net haqida") is None and b.buyruq_ajrat("...") is None
      and b.buyruq_ajrat(".") is None and b.buyruq_ajrat("salom .en") is None)
check(8, "apostrof turlari bir xil: .to‘g‘rila",
      b.buyruq_ajrat(".to‘g‘rila  mani matn") == ("to'g'rila", "mani matn")
      and b.buyruq_ajrat(".EN Salom") == ("en", "Salom"))

izlar = ishga(b.biznes_xabar(xabar(".salom dunyo", kimdan=EGASI)))
check(9, "noma'lum .so'z modelni chaqirmaydi, oddiy gap bo'lib tarixga",
      "gpt" not in izlar and "kvota" not in izlar and "tarix" in izlar)

# ── 10. Asosiy yo'l: .en Salom ───────────────────────────────────
holat["model"] = "Mana tarjima:\nHello"
izlar = ishga(b.biznes_xabar(xabar(".en Salom", kimdan=EGASI)))
yuborish = [x for x in q.l if x[0] == "send"]
check(10, ".en Salom -> buyruq o'chadi, keyin «Hello» chatga, muqaddimasiz",
      izlar.index("delete") < izlar.index("send")
      and yuborish == [("send", MIJOZ, "Hello", "c1")])
gpt = next(x for x in q.l if x[0] == "gpt")
check(11, "buyruq tool'siz va tarixsiz (.en)", gpt[3] is False and gpt[1] == 0)
check(12, "chatga ketgan javob tarixga egasi (assistant) sifatida",
      ("tarix", MIJOZ, "assistant", b.biznes_thread(EGASI)) in q.l
      and ("faollik", "biznes_buyruq") in q.l)
holat["model"] = "Hello"

# ── 13. .javob tarix bilan ishlaydi ──────────────────────────────
ishga(b.biznes_xabar(xabar(".javob ertaga olib kelaman", kimdan=EGASI)))
gpt = next(x for x in q.l if x[0] == "gpt")
check(13, ".javob mijoz chati tarixini o'qiydi (chat, -egasi)",
      gpt[1] == MIJOZ and gpt[2] == b.biznes_thread(EGASI))

# ── 14. Bepul ega ────────────────────────────────────────────────
holat["pro"] = False
izlar = ishga(b.biznes_xabar(xabar(".en Salom", kimdan=EGASI)))
check(14, "bepul egada buyruq ishlamaydi, ball yechilmaydi",
      "kvota" not in izlar and "gpt" not in izlar and "delete" not in izlar
      and any(x[0] == "send" and x[1] == DM for x in q.l))
holat["pro"] = True

# ── 15. Huquq yo'q ───────────────────────────────────────────────
database._biznes_kesh["c1"] = dict(UL, huquqlar={"can_read_messages": True})
izlar = ishga(b.biznes_xabar(xabar(".en Salom", kimdan=EGASI)))
check(15, "can_reply yo'q -> kvota ham, model ham yo'q, egasiga tushuntirish",
      "kvota" not in izlar and "gpt" not in izlar
      and any("Xabarlarga javob berish" in x[2] for x in q.l if x[0] == "send"))
database._biznes_kesh["c1"] = dict(UL)

# ── 16. Model bo'sh -> ball qaytadi ──────────────────────────────
holat["model"] = ""
izlar = ishga(b.biznes_xabar(xabar(".en Salom", kimdan=EGASI)))
check(16, "natija bo'sh -> ball qaytariladi, chatga hech narsa",
      "refund" in izlar and not any(x[0] == "send" and x[3] for x in q.l))
holat["model"] = "Hello"

# ── 17. Chatga yuborib bo'lmadi (24 soat) ────────────────────────
holat["send_xato"] = "Bad Request: message can't be sent"
ishga(b.biznes_xabar(xabar(".en Salom", kimdan=EGASI)))
check(17, "chatga yuborilmasa matn egasiga boradi, tarixga yozilmaydi",
      any(x[0] == "send" and x[1] == DM and "Hello" in x[2] for x in q.l)
      and not any(x[0] == "tarix" for x in q.l))
holat["send_xato"] = None

# ── 18. Limit tugagan ────────────────────────────────────────────
holat["kvota"] = {"allowed": False}
izlar = ishga(b.biznes_xabar(xabar(".en Salom", kimdan=EGASI)))
check(18, "limit tugasa chatga hech narsa, buyruq o'chmaydi",
      "gpt" not in izlar and "delete" not in izlar
      and all(x[3] is None for x in q.l if x[0] == "send"))
holat["kvota"] = {"allowed": True, "unlimited": False}


# ── 19-20. Ulanish uzildi -> kesh DARHOL ─────────────────────────
class SoxtaConn:
    def __init__(self, xato=None):
        self.xato = xato

    async def fetchrow(self, *a):
        if self.xato:
            raise self.xato
        return {"rejim": "buyruq", "ish_vaqti": None}


class SoxtaPool:
    def __init__(self, xato=None):
        self.c = SoxtaConn(xato)

    def acquire(self):
        pool = self

        class Ctx:
            async def __aenter__(self):
                return pool.c

            async def __aexit__(self, *a):
                return False
        return Ctx()


def ulanish(yoqilgan):
    return BusinessConnection(
        id="c1", user=User(id=EGASI, is_bot=False, first_name="E"),
        user_chat_id=DM, date=datetime.now(), is_enabled=yoqilgan,
        rights=BusinessBotRights(can_reply=True, can_read_messages=True))


database.pool = SoxtaPool()
ishga(b.ulanish_yangilandi(ulanish(False)))
izlar = ishga(b.biznes_xabar(xabar(".en Salom", kimdan=EGASI)))
check(19, "is_enabled=False -> kesh darhol yangilanadi, buyruq ishlamaydi",
      database.biznes_ulanish_ol("c1")["yoqilgan"] is False and izlar == [])

database._biznes_kesh["c1"] = dict(UL)
database.pool = SoxtaPool(xato=ValueError("baza yiqildi"))
izlar = ishga(b.ulanish_yangilandi(ulanish(False)))
check(20, "baza yiqilsa ham kesh uzilgan deb biladi va egasi xabar oladi",
      database.biznes_ulanish_ol("c1")["yoqilgan"] is False and "send" in izlar)

# ── 21-22. Ulanish matni va /help ────────────────────────────────
check(21, "ulanish matni: uzildi / Pro kerak / yetishmagan huquq",
      "o'chirildi" in b.ulanish_matni(False, {}, True)
      and "/pro" in b.ulanish_matni(True, {}, False)
      and "Xabarlarni o'qish" in b.ulanish_matni(True, {"can_reply": True}, True))
bolim = cap._section_text("biznes", True)
check(22, "/help Biznes bo'limi har bir buyruqni sanaydi (bitta manba)",
      all(f".{nom}" in bolim for nom in b.BUYRUQ_HUQUQI)
      and ".xulosa" in cap.model_uchun(True))

print("\nHammasi o'tdi: 22/22")
