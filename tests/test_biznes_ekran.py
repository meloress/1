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

print("\nHammasi o'tdi: 17/17")
