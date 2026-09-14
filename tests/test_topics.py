# -*- coding: utf-8 -*-
"""MAVZU (topic) — shaxsiy chatdagi ayrim suhbatlar.

Telegram shaxsiy chatda ham mavzu ochishga ruxsat beradi (Bot API 9.4)
va har bir mavzu — AYRIM SUHBAT. Shuning uchun tarix, xulosa, sessiya
taymeri va natija fayllari `(chat_id, thread_id)` juftligi bo'yicha
ishlashi kerak.

Bu tuzilmaviy qo'riqchi test — u ikkita JIM nosozlikni ushlaydi:

  ⛔️ (1) Javob bir mavzuga ketib, tarix boshqasiga yozilishi. Bunda bot
     o'z javobini keyingi savolda ko'rmaydi va foydalanuvchi buni
     "bot meni eshitmayapti" deb ko'radi — xato ham otilmaydi, log ham
     jim. Shu sababli `_thread_key()` aiogram'ning O'Z sharti bilan
     bir xil bo'lishi shart.

  ⛔️ (2) Natija fayllari mavzuga emas, chatning asosiy oqimiga tushishi.
     `message.answer()` ga aiogram mavzuni o'zi qo'shadi, xom
     `bot.send_document()` ga esa QO'SHMAYDI.

Tarmoqsiz va bazasiz ishlaydi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_topics.py
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db.history as h                 # noqa: E402
import handlers.messages as m          # noqa: E402
import services.ai as ai               # noqa: E402
from aiogram.types import Message      # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


class SoxtaXabar:
    def __init__(self, thread_id=None, topic=False):
        self.message_thread_id = thread_id
        self.is_topic_message = topic


# ── 1-4. Kalit ───────────────────────────────────────────────────
check(1, "mavzusiz xabar -> 0", m._thread_key(SoxtaXabar()) == 0)
check(2, "mavzudagi xabar -> mavzu id",
      m._thread_key(SoxtaXabar(55, topic=True)) == 55)
# ⚠️ Forum guruhdagi asosiy oqim (General) `message_thread_id` beradi,
# lekin `is_topic_message` False bo'ladi. Bu holat 0 bo'lishi SHART,
# aks holda "General" alohida suhbat bo'lib ajralib ketardi.
check(3, "is_topic_message=False bo'lsa id e'tiborsiz",
      m._thread_key(SoxtaXabar(55, topic=False)) == 0)
# Umuman maydonsiz obyekt (eski test yoki boshqa update turi) yiqilmasin.
check(4, "maydoni yo'q obyektda ham yiqilmaydi",
      m._thread_key(object()) == 0)


# ── 5. ⛔️ aiogram bilan AYNAN bir xil shart ──────────────────────
# Ikki joyda ikki xil shart bo'lsa, javob bir mavzuga ketib tarix
# boshqasiga yozilardi — va buni hech qanday xato ko'rsatmasdi.
_AIOGRAM = inspect.getsource(Message.answer)
check(5, "aiogram ham `is_topic_message` shartini ishlatadi",
      "message_thread_id=self.message_thread_id if self.is_topic_message"
      in _AIOGRAM.replace("\n", " ").replace("  ", " "))
check(6, "_thread_key ham aynan shu shartda",
      "is_topic_message" in inspect.getsource(m._thread_key))


# ── 7-9. Tarix qatlami juftlik bo'yicha ──────────────────────────
for nom, fn in (("update_chat_history", h.update_chat_history),
                ("get_chat_history", h.get_chat_history),
                ("get_chat_summary", h.get_chat_summary),
                ("clear_history", h.clear_history),
                ("_compress_old", h._compress_old),
                ("_hard_trim", h._hard_trim)):
    p = inspect.signature(fn).parameters
    assert "thread_id" in p, f"{nom} da thread_id yo'q"
    # Standart qiymat SHART: busiz mavjud chaqiruvlar yiqilardi.
    assert p["thread_id"].default in (0, None), f"{nom}: standart qiymat yo'q"
check(7, "tarix funksiyalari mavzuni biladi (standart qiymat bilan)", True)

for nom, fn in (("safe_update_history", ai.safe_update_history),
                ("safe_get_chat_history", ai.safe_get_chat_history),
                ("safe_history_summary_message", ai.safe_history_summary_message),
                ("clear_chat_history", ai.clear_chat_history),
                ("get_openai_reply", ai.get_openai_reply),
                ("get_vision_reply", ai.get_vision_reply),
                ("get_gpt_reply", ai.get_gpt_reply)):
    assert "thread_id" in inspect.signature(fn).parameters, f"{nom} da yo'q"
check(8, "ai.py o'rovlari ham mavzuni biladi", True)

# get_gpt_reply — shunchaki o'rov; uzatmasa mavzu shu yerda YO'QOLARDI.
check(9, "get_gpt_reply mavzuni get_openai_reply ga uzatadi",
      "thread_id=thread_id" in inspect.getsource(ai.get_gpt_reply))


# ── 10-12. Handlerlar: har BESH javob yo'li ham uzatadi ──────────
_YOLLAR = {
    "matn": m._process_merged_text,
    "tadqiqot": m.handle_research,
    "rasm": m.handle_photo,
    "hujjat": m.handle_document,
    "ovoz": m.handle_voice,
}
for nom, fn in _YOLLAR.items():
    src = inspect.getsource(fn)
    assert "_thread_key(" in src, f"{nom}: mavzu o'qilmayapti"
    assert "thread_id=thread_id" in src, f"{nom}: modelga uzatilmayapti"
    assert "thread_id=thread_id)" in src or "thread_id=thread_id," in src, nom
check(10, f"beshala javob yo'li ham mavzuni uzatadi ({', '.join(_YOLLAR)})", True)

# ⚠️ Bu yerda `message.answer()` emas, xom `bot.send_document/photo/message`
# ishlatiladi — aiogram mavzuni O'ZI qo'shib bermaydi.
_FAYL = inspect.getsource(m._send_output_files)
check(11, "natija fayllari mavzuga yuboriladi",
      "message_thread_id" in _FAYL and _FAYL.count("**mavzu") >= 4)

# Sessiya taymeri ham juftlik bo'yicha: bitta faol mavzu qolganlarini
# "tirik" ko'rsatib turmasin.
check(12, "sessiya taymeri kaliti juftlik",
      "(chat_id, thread_id)" in inspect.getsource(m.check_and_clear_session))


# ── 13. /new faqat O'Z mavzusini tozalaydi ───────────────────────
_TEXT = inspect.getsource(m.handle_text)
check(13, "/new faqat shu mavzuni tozalaydi",
      "clear_chat_history(chat_id, thread_id=thread_id)" in _TEXT)


# ── 14-15. «Suhbat uzayib ketdi» ─────────────────────────────────
h._long_warn.clear()
h._long_warn.add((1, 0))
check(14, "ogohlantirish BIR MARTA beriladi",
      h.take_long_warning(1) is True and h.take_long_warning(1) is False)

# Ogohlantirish matni mavzu rejimiga qarab o'zgarishi kerak: mavzu
# ocholmaydigan odamga "yangi mavzu oching" deyish bajarilmaydigan
# maslahat bo'lardi.
_OGOH = inspect.getsource(m._maybe_warn_long)
check(15, "matn TOPICS_ENABLED ga qarab tanlanadi",
      "TOPICS_ENABLED" in _OGOH and "/new" in _OGOH)


# ── 16. Migratsiya idempotent ────────────────────────────────────
# init_db() HAR ishga tushishda chaqiriladi. PRIMARY KEY almashtirish
# shartsiz yozilsa, ikkinchi deployda xato berardi.
_INIT = inspect.getsource(h.init_db)
check(16, "mavzu migratsiyasi idempotent (IF NOT EXISTS / DO $$)",
      "ADD COLUMN IF NOT EXISTS thread_id" in _INIT
      and "indisprimary" in _INIT
      and "CREATE INDEX IF NOT EXISTS idx_chat_messages_thread" in _INIT)


# ── 17. Bayroq BotFather'dan o'qiladi, koddan yoqilmaydi ─────────
_MAIN = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
check(17, "TOPICS_ENABLED getMe dan to'ldiriladi",
      "messages_module.TOPICS_ENABLED" in _MAIN
      and "has_topics_enabled" in _MAIN)


# ── 18-19. Eslab qolingan fayl ham mavzu bo'yicha ────────────────
# ⚠️ Fayl ISTALGAN qisqa xabarga biriktiriladi va 10 daqiqa yashaydi.
# Faqat chat bo'yicha saqlansa, A-mavzuda olingan PPTX B-mavzudagi
# «rahmat» ga ham ilashib ketardi — model esa foydalanuvchi fayl
# yuborgan deb o'ylardi.
m._pending_files.clear()
m._remember_file(1, b"AAA", "a.pptx", thread_id=10)
m._remember_file(1, b"BBB", "b.pdf", thread_id=20)
check(18, "har mavzuning fayli AYRIM",
      m._get_pending_file(1, 10)["name"] == "a.pptx"
      and m._get_pending_file(1, 20)["name"] == "b.pdf"
      and m._get_pending_file(1, 0) is None)

m.clear_pending_file(1, 10)
check(19, "bitta mavzuning fayli o'chdi, qolgani joyida",
      m._get_pending_file(1, 10) is None
      and m._get_pending_file(1, 20) is not None)
m._pending_files.clear()


# ── 20. Draft va status BIR MANBADAN o'qiydi ─────────────────────
# Xom `message_thread_id` ni o'qish — aynan 5-tekshiruvdagi drift:
# animatsiya bir joyga, javob boshqasiga tushardi.
for _nom, _fn in (("status ko'rsatkichi", m._status_indicator),
                  ("oqim drafti", m.process_stream_draft)):
    _src = inspect.getsource(_fn)
    assert "_thread_key(message)" in _src, f"{_nom}: _thread_key yo'q"
    assert 'getattr(message, "message_thread_id"' not in _src, \
        f"{_nom}: hali xom maydonni o'qiyapti"
check(20, "draft va status ham _thread_key dan o'qiydi", True)


print("\ntopics: barcha tekshiruvlar o'tdi (20/20).")
