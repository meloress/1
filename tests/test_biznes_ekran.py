# -*- coding: utf-8 -*-
"""Telegram Business — /biznes ekrani soddaligi (egasi: "juda murakkab").

  ⛔️ bosh ekran yana tugmalarga to'lsa (13 ta edi) — egasi adashadi;
  ⛔️ statistika o'qilmasa ekran umuman ochilmay qoladi (bezak — darvoza emas);
  ⛔️ foiz noto'g'ri hisoblanadi (0 ga bo'lish, tanlov qatorlari aralashishi).

Tarmoqsiz va bazasiz.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_ekran.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handlers.biznes as b              # noqa: E402
from db import database                  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


def tugmalar(kb):
    return [t.callback_data for q in kb.inline_keyboard for t in q]


UL = {"owner_id": 1, "owner_chat": 1, "yoqilgan": True, "rejim": "avtomat",
      "ish_vaqti": None, "avto_belgi": True, "huquqlar": {"can_reply": True}}

kb = b._ekran_kb(UL)
bosh = tugmalar(kb)
# Egasi: "qo'pol tuyulyapti" (2026-09-29) — ikki qator, rangsiz, rejimlar ichkarida.
check(1, "bosh ekran: Rejim + Bilim + Uslub + Sozlamalar, 2 qator, rangsiz",
      bosh == ["bz:rm", "bz:k", "bz:us", "bz:s"] and len(kb.inline_keyboard) == 2
      and all(t.style is None for q in kb.inline_keyboard for t in q)
      and "Avtomat" in kb.inline_keyboard[0][0].text)
rj = tugmalar(b._rejim_kb(UL))
check("1b", "rejim menyusi: to'rt rejim + orqaga, tanlangani ✓",
      rj == [f"bz:r:{r}" for r in b.BIZNES_REJIMLAR] + ["bz:e"]
      and b._rejim_kb(UL).inline_keyboard[3][0].text.startswith("✓")
      and all(b.REJIM_NOMI[r][0] in b.rejim_matni(UL) for r in b.BIZNES_REJIMLAR))
soz = tugmalar(b._sozlama_kb(UL))
check(2, "Sozlamalar: ish vaqti, chatlar, belgi, profil, orqaga",
      {"bz:w", "bz:c", "bz:bl", "bz:pf:bio", "bz:pf:story", "bz:e"} <= set(soz))
check(3, "Sozlamalar yordamchida: avtomatga oid tugmalar yo'q",
      "bz:w" not in tugmalar(b._sozlama_kb(dict(UL, rejim="yordamchi"))))

m = b.ekran_matni(UL, "bilim", {"javob": 5, "uzatish": 2, "tahrirsiz": 7, "yuborilgan": 10}, 34)
check(4, "statistika: bugungi javob/uzatish, 30 kunlik foiz, namuna soni",
      "<b>5</b> ta javob" in m and "<b>2</b> ta savolni sizga" in m and "<b>70%</b>" in m
      and "<b>34</b> ta namuna" in m)
m0 = b.ekran_matni(UL, "", {"javob": 0, "uzatish": 0, "tahrirsiz": 0, "yuborilgan": 0})
check(5, "yuborilgan qoralama yo'q — foiz qatori yo'q (0 ga bo'linmaydi)", "%" not in m0)
check(6, "statistikasiz ham ekran (eski chaqiruvchilar)", "Rejim" in b.ekran_matni(UL, ""))


async def yiqiladi(*a, **k):
    raise RuntimeError("baza yo'q")


async def bilim(_):
    return "bilim"

database.biznes_bilim_ol = bilim
database.biznes_ekran_stat = yiqiladi
database.biznes_uslub_ol = yiqiladi
database._biznes_kesh["c1"] = UL
matn, kb = asyncio.run(b._ekran(1))
check(7, "statistika o'qilmasa ham ekran ochiladi (bezak — darvoza emas)",
      "Rejim" in matn and kb is not None)

# ── 8-11. Ulanmagan ekran: to'g'ri holat, Premium yo'q, menyu egasining tilida ──
from types import SimpleNamespace as NS  # noqa: E402

yoq = b.ekran_matni(None, "", uid=501, bot_nomi="uzchatgptaibot")
check(8, "ulanmagan: qadamlar, bot nomi, Premium haqida GAP YO'Q",
      "Hali ulanmagan" in yoq and "@uzchatgptaibot" in yoq and "Premium" not in yoq
      and "Sozlamalar → Telegram Business → Chatbotlar" in yoq)
check(9, "ilgari ulangan, hozir o'chirilgan — boshqacha aytiladi",
      "o'chirilgan" in b.ekran_matni({**UL, "yoqilgan": False}, ""))
b.til_eslab(NS(id=502, language_code="ru"))
b.til_eslab(NS(id=503, language_code="en"))
b.til_eslab(NS(id=504, language_code="tr"))
ru = b.ekran_matni(None, "", uid=502)
check(10, "rus Telegram: tushuntirish o'zbekcha, bosiladigan nomlar ruscha",
      "Настройки → Telegram для бизнеса → Чат-боты" in ru and "Qanday ulash" in ru
      and "Ответ на сообщения" in ru)
check(11, "en va tanilmagan til (tr) — inglizcha menyu; profil huquqi ham tarjima",
      "Settings → Telegram Business → Chatbots" in b.ekran_matni(None, "", uid=503)
      and "Settings" in b.sozlama_yoli(504)
      and b.huquq_nomi(503, "can_edit_bio") == "Edit Bio"
      and b.huquq_nomi(None, "can_edit_bio") == "Bio'ni o'zgartirish")
check(12, "bepul egaga: ulanmagan bo'lsa «ulandim» DEMAYDI",
      "ulandim" not in b._probez_matni(999) and "/pro" in b._probez_matni(999))

# ── 13-17. Premium emoji: egasiga — ha, mijozga — hech qachon ────
from aiogram.exceptions import TelegramBadRequest  # noqa: E402
from aiogram.methods import SendMessage  # noqa: E402
from aiogram.types import InlineKeyboardMarkup  # noqa: E402

import services.ai as ai  # noqa: E402

ai.apply_emoji_pack({"✅": "111", "⚠️": "222", "📝": "333"})
p = ai.html_premium('✅ <b>Tayyor</b> ⚠️ <code>✅</code> <a href="x✅">📝</a>')
check(13, "html_premium: matn emojisi animatsiyali, kod va atribut tegilmaydi, ikki marta — zararsiz",
      p.count('emoji-id="111"') == 1 and 'emoji-id="222"' in p and "<code>✅</code>" in p
      and 'href="x✅"' in p and 'emoji-id="333"' in p and ai.html_premium(p) == p)

kb = InlineKeyboardMarkup(inline_keyboard=[[b.pro_module.btn("📝 Bilim", "bz:k"),
                                             b.pro_module.btn("Orqaga", "bz:e")]])
egaga = b.premiumlash(SendMessage(chat_id=1, text="✅ Saqlandi", reply_markup=kb))
t = egaga.reply_markup.inline_keyboard[0]
check(14, "egasiga: matn premium, tugma emojisi ikonka bo'ladi (matnda takrorlanmaydi)",
      'emoji-id="111"' in egaga.text and t[0].icon_custom_emoji_id == "333"
      and t[0].text == "Bilim" and t[1].text == "Orqaga" and not t[1].icon_custom_emoji_id)
check(15, "mijozga (business_connection_id) va oddiy matn (parse_mode=None) — TEGILMAYDI",
      b.premiumlash(SendMessage(chat_id=1, text="✅ ok", business_connection_id="c1")) is None
      and b.premiumlash(SendMessage(chat_id=1, text="✅ ok", parse_mode=None)) is None)

yuborildi = []


async def rad_etuvchi(bot_, method):
    yuborildi.append(method.text)
    if "tg-emoji" in method.text:
        raise TelegramBadRequest(method=method, message="Bad Request: premium kerak")
    return "ok"


async def sina():
    b.premium_biznes()
    return await b.PremiumEmojiMiddleware()(rad_etuvchi, None,
                                            SendMessage(chat_id=1, text="✅ Saqlandi"))

natija = asyncio.run(sina())
check(16, "Telegram rad etsa — asl xabar qayta ketadi, yo'qolmaydi",
      natija == "ok" and len(yuborildi) == 2 and yuborildi[1] == "✅ Saqlandi")
yuborildi.clear()


async def kontekstsiz():
    return await b.PremiumEmojiMiddleware()(rad_etuvchi, None,
                                            SendMessage(chat_id=1, text="✅ Salom"))

asyncio.run(kontekstsiz())
check(17, "Business'dan tashqaridagi xabarga (kontekst yoqilmagan) tegilmaydi",
      yuborildi == ["✅ Salom"])

# ── 18-19. AI javobi MIJOZGA ham premium emoji bilan ─────────────
mijoz_q = []


class MijozBot:
    rad = False

    async def send_message(self, chat_id, text, business_connection_id=None, parse_mode=None,
                           link_preview_options=None):
        mijoz_q.append((text, parse_mode, business_connection_id))
        if self.rad and parse_mode == "HTML":
            raise TelegramBadRequest(method=None, message="Bad Request: premium yo'q")
        return "ok"

asl_bot, b.bot = b.bot, MijozBot()
try:
    asyncio.run(b._mijozga(5, "c1", "Narxi 5 < 10 ✅"))
    birinchi = list(mijoz_q)
    mijoz_q.clear()
    b.bot.rad = True
    asyncio.run(b._mijozga(5, "c1", "Tayyor ✅"))
    rad = list(mijoz_q)
    mijoz_q.clear()
    asyncio.run(b._mijozga(5, "c1", "Salom <b>"))
    emojisiz = list(mijoz_q)
finally:
    b.bot = asl_bot
check(18, "mijozga: emoji animatsiyali (HTML), matn escape — «<» buzilmaydi, ulanish orqali",
      birinchi == [('Narxi 5 &lt; 10 <tg-emoji emoji-id="111">✅</tg-emoji>', "HTML", "c1")])
check(19, "rad etilsa — o'sha matn oddiy qayta; emojisiz javob — to'g'ridan oddiy (bitta so'rov)",
      rad[-1] == ("Tayyor ✅", None, "c1") and len(rad) == 2
      and emojisiz == [("Salom <b>", None, "c1")])

# ── 20-21. Avtojavob belgisi: bot havolasi + logo, pog'onali zaxira ──
from types import SimpleNamespace as NS2  # noqa: E402


class BelgiBot(MijozBot):
    rad_logo = rad_html = False

    async def me(self):
        return NS2(username="uzchatgptaibot")

    async def send_message(self, chat_id, text, business_connection_id=None, parse_mode=None,
                           link_preview_options=None):
        mijoz_q.append((text, parse_mode, link_preview_options))
        if parse_mode == "HTML" and (self.rad_html or (self.rad_logo and "tg-emoji" in text)):
            raise TelegramBadRequest(method=None, message="Bad Request: rad")
        return "ok"

b.LOGO_EMOJI["kichik"] = "LOGO1"
asl_bot, b.bot = b.bot, BelgiBot()
try:
    mijoz_q.clear()
    asyncio.run(b._mijozga(5, "c1", "Salom", belgi=True))
    toliq = list(mijoz_q)
    mijoz_q.clear()
    b.bot.rad_logo = True
    asyncio.run(b._mijozga(5, "c1", "Salom", belgi=True))
    logosiz = list(mijoz_q)
    mijoz_q.clear()
    b.bot.rad_html = True
    asyncio.run(b._mijozga(5, "c1", "Salom", belgi=True))
    oddiy = list(mijoz_q)
finally:
    b.bot = asl_bot
    b.LOGO_EMOJI.clear()
t = toliq[0][0]
check(20, "belgi — t.me/uzchatgptaibot havolasi, oxirida bot logosi; preview o'chiq",
      len(toliq) == 1 and t.startswith("Salom\n")
      and f'<a href="https://t.me/uzchatgptaibot">{b.AVTO_BELGI}</a>' in t
      and t.endswith('<tg-emoji emoji-id="LOGO1">🤖</tg-emoji>')
      and toliq[0][2].is_disabled)
check(21, "logo rad etilsa — havola qoladi; HTML ham rad etilsa — oddiy belgi, javob yo'qolmaydi",
      "tg-emoji" not in logosiz[-1][0] and "t.me/uzchatgptaibot" in logosiz[-1][0]
      and oddiy[-1] == ("Salom\n" + b.AVTO_BELGI, None, None))

# ── 22-24. Bekor qilish: tugma, qaytish ekrani, tashlab ketilgan holat ──
import handlers.biznes_uslub as bu  # noqa: E402


class Holat:
    def __init__(self, h=None):
        self.h = h

    async def get_state(self):
        return self.h

    async def set_state(self, h):
        self.h = getattr(h, "state", h)

    async def clear(self):
        self.h = None

    async def get_data(self):
        return {}


class Xabar:
    def __init__(self):
        self.tahrir = self.yangi = None

    async def edit_text(self, matn, reply_markup=None):
        self.tahrir = (matn, reply_markup)

    async def answer(self, matn, reply_markup=None):
        self.yangi = (matn, reply_markup)


class So:
    def __init__(self, data):
        self.data, self.from_user, self.message = data, NS(id=1, language_code="uz"), Xabar()
        self.alert = None

    async def answer(self, *a, **k):
        self.alert = a


async def uslub(uid, n=None):
    return {"namunalar": [], "tahrirlar": [], "uslub": "", "uslub_egasi": "siz deb yoz"}

async def _rost(*_):
    return True

database.biznes_uslub_ol = uslub
database.pro_tarifmi = _rost

h = Holat(bu.UslubStates.qoidalar.state)
q1 = So("bz:bk")
asyncio.run(b.handle_biznes_callback(q1, h))
check(22, "«✖️ Bekor qilish»: holat tozalanadi, so'rov o'rniga Uslubim ekrani chiqadi",
      h.h is None and q1.message.tahrir and "USLUBIM" in q1.message.tahrir[0])

h = Holat(bu.UslubStates.qoidalar.state)
asyncio.run(b.handle_biznes_callback(So("bz:e"), h))
check(23, "qoida kutilayotganda boshqa tugma (Orqaga) — holat tozalanadi (gap qoida bo'lib ketmaydi)",
      h.h is None)

kb = bu._sorov_kb(True)
tugma = [t.callback_data for q in kb.inline_keyboard for t in q]
check(24, "qoidalar so'rovida: «❌ Qoidalarni o'chirish» va «✖️ Bekor qilish» tugmalari, /bekor matni yo'q",
      tugma == ["bz:uyx", "bz:bk"] and "/bekor" not in bu._SOROV
      and "/bekor" not in b._BILIM_SOROVI)

print("\nHammasi o'tdi: 24/24")
