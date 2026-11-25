"""Yangi suhbatni BOT ochadi (GPT'dagi «New chat») va xotira to'lganda eslatadi.

Ishga tushirish: PYTHONIOENCODING=utf-8 python tests/test_yangi_suhbat.py

HAQIQIY HOLAT (prod, 2026-10-28..11-25): foydalanuvchi mavzudan tashqarida
yozgan har xabarga Telegram yangi mavzu ochardi — 64 kishida 608 ta, bittasida
127 ta, har biri xotirasiz. Endi foydalanuvchiga mavzu ochish yopiq (main.py),
yangi suhbat — faqat `/new` va «🆕 Yangi suhbat» tugmasi.
"""
import asyncio
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import CONTEXT_WINDOW, CONTEXT_WINDOW_PRO  # noqa: E402
from handlers import messages as m  # noqa: E402
from tests._manba import kod  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


class SoxtaBot:
    def __init__(self, rad=False):
        self.rad, self.yuborilgan, self.ochilgan = rad, [], []

    async def create_forum_topic(self, chat_id, name):
        if self.rad:
            raise RuntimeError("Bad Request: not enough rights")
        self.ochilgan.append((chat_id, name))
        return NS(message_thread_id=555)

    async def send_message(self, chat_id, text, **kw):
        self.yuborilgan.append((chat_id, text, kw))


def xabar(matn="", tur="private", thread=None):
    javoblar = []

    async def answer(text, **kw):
        javoblar.append((text, kw))
    return NS(text=matn, chat=NS(id=7, type=tur), from_user=NS(id=7, username="u", full_name="U"),
              is_topic_message=thread is not None, message_thread_id=thread,
              answer=answer, javoblar=javoblar)


def tugmalar(kw):
    kb = kw.get("reply_markup")
    return [b for qator in (kb.inline_keyboard if kb else []) for b in qator]


async def main():
    # ── Chegara: oyna to'lgan javobda BIR marta ──────────────────
    tf = m.xotira_toldimi
    check(1, f"bepul: {CONTEXT_WINDOW} ta qatorda eslatadi, undan oldin/keyin yo'q",
          tf(CONTEXT_WINDOW, CONTEXT_WINDOW) and tf(CONTEXT_WINDOW + 1, CONTEXT_WINDOW)
          and not tf(CONTEXT_WINDOW - 1, CONTEXT_WINDOW) and not tf(CONTEXT_WINDOW + 2, CONTEXT_WINDOW))
    # Siqishdan keyin qatorlar 80 ga tushadi, keyingi juftlik 82 — qayta chiqmaydi.
    check(2, "Pro: siqishdan keyin (80 → 82) har 20 xabarda qayta chiqmaydi",
          tf(CONTEXT_WINDOW_PRO, CONTEXT_WINDOW_PRO) and not tf(CONTEXT_WINDOW_PRO + 2, CONTEXT_WINDOW_PRO)
          and not tf(None, CONTEXT_WINDOW_PRO))

    # ── Eslatma: tugma faqat shaxsiy chatda, bir marta ───────────
    m.TOPICS_ENABLED = True
    m._XOTIRA_ESLATILGAN.clear()
    x = xabar()
    await m._maybe_warn_long(x, 0, CONTEXT_WINDOW, False)
    b = tugmalar(x.javoblar[0][1]) if x.javoblar else []
    check(3, "shaxsiy chat: «🆕 Yangi suhbat» tugmasi bilan",
          len(x.javoblar) == 1 and b and b[0].callback_data == m.YANGI_SUHBAT_CB)
    await m._maybe_warn_long(x, 0, CONTEXT_WINDOW + 1, False)
    check(4, "shu suhbatda ikkinchi marta chiqmaydi", len(x.javoblar) == 1)

    g = xabar(tur="supergroup")
    g.chat.id = -100
    await m._maybe_warn_long(g, 0, CONTEXT_WINDOW, False)
    check(5, "guruhda tugma yo'q, «/new» deyiladi (bot u yerda mavzu ocholmaydi)",
          g.javoblar and not tugmalar(g.javoblar[0][1]) and "/new" in g.javoblar[0][0])
    p = xabar()
    p.chat.id = 8
    await m._maybe_warn_long(p, 0, CONTEXT_WINDOW, True)
    check(6, "Pro'da 30-qatorda chiqmaydi — uning oynasi 80", not p.javoblar)

    # ── /new — yangi mavzu, eskisi o'chmaydi ─────────────────────
    tozalangan = []

    async def soxta_tozala(chat_id, thread_id=0):
        tozalangan.append((chat_id, thread_id))
    m.clear_chat_history = soxta_tozala
    m.pro_module.BOT_USERNAME = "vexonai"
    m.bot = SoxtaBot()
    y = xabar("/new", thread=289441)
    await m.handle_text(y, None)
    url = tugmalar(y.javoblar[0][1])[0].url if y.javoblar else ""
    check(7, "/new: yangi mavzu ochiladi, ESKI suhbat tozalanmaydi, havola beriladi",
          m.bot.ochilgan == [(7, m.YANGI_SUHBAT_NOMI)] and not tozalangan
          and url == "https://t.me/vexonai/555"
          and m.bot.yuborilgan and m.bot.yuborilgan[0][2].get("message_thread_id") == 555)

    m.bot = SoxtaBot(rad=True)
    z = xabar("/new", thread=289441)
    await m.handle_text(z, None)
    check(8, "mavzu ochilmasa — eski yo'l: SHU mavzu tozalanadi", tozalangan == [(7, 289441)])

    m.TOPICS_ENABLED = False
    m.bot = SoxtaBot()
    await m.handle_text(xabar("/new"), None)
    check(9, "mavzu rejimi yo'q botda /new mavzu ochmaydi", not m.bot.ochilgan)
    m.TOPICS_ENABLED = True

    # ── Tugma bosildi ────────────────────────────────────────────
    m.bot = SoxtaBot()
    holat = {}

    async def q_answer(text=None, **kw):
        holat["answer"] = text

    async def edit_markup(reply_markup=None):
        holat["kb"] = reply_markup
    q = NS(message=NS(chat=NS(id=7, type="private"), edit_reply_markup=edit_markup), answer=q_answer)
    await m.handle_yangi_suhbat_callback(q)
    check(10, "tugma: mavzu ochiladi, tugma o'rniga havola",
          m.bot.ochilgan and holat["kb"].inline_keyboard[0][0].url.endswith("/555"))
    m.bot = SoxtaBot()
    holat.clear()
    q.message.chat.type = "supergroup"
    await m.handle_yangi_suhbat_callback(q)
    check(11, "guruhda tugma mavzu OCHMAYDI", not m.bot.ochilgan and "kb" not in holat)

    # ── main.py: sozlamalar va ro'yxat ───────────────────────────
    asosiy = kod(os.path.join(ROOT, "main.py"))
    sozlama = asosiy[asosiy.index("if messages_module.TOPICS_ENABLED:\n            kerak"):]
    sozlama = sozlama[:sozlama.index("except Exception as e:")]
    check(12, "ishga tushganda: foydalanuvchiga mavzu ochish yopiladi, yon panel yoqiladi",
          'kerak["allows_users_to_create_topics"] = False' in sozlama
          and 'kerak["has_topic_sidebar"] = True' in sozlama
          and "has_topics_enabled" not in sozlama)
    check(13, "«🆕 Yangi suhbat» callback ro'yxatdan o'tgan",
          "messages_module.handle_yangi_suhbat_callback" in asosiy)

    ai = kod(os.path.join(ROOT, "services", "ai.py"))
    fn = ai[ai.index("async def safe_update_history"):ai.index("def nomlash_kerakmi")]
    check(14, "safe_update_history qatorlar sonini qaytaradi (eslatma shunga qaraydi)",
          "return jami" in fn)
    # ── 24 soatlik tozalash: mavzuda YO'Q, mavzusiz oqimda bor ───
    tozalangan.clear()
    m.bot = SoxtaBot()
    m.forget_sent_images = lambda *a, **k: None
    m.forget_location = lambda *a, **k: None
    eski = m.time.time() - m.SESSION_TIMEOUT - 60
    m.chat_last_interaction[(7, 555)] = eski
    m.chat_last_interaction[(7, 0)] = eski
    await m.check_and_clear_session(7, 555)
    check(15, "mavzu 24 soatdan keyin ham xotirasi bilan qoladi",
          not tozalangan and m.chat_last_interaction[(7, 555)] > eski)
    await m.check_and_clear_session(7, 0)
    check(16, "mavzusiz oqim 24 soatdan keyin toza boshlanadi", tozalangan == [(7, 0)])
    print("\nyangi suhbat: barcha tekshiruvlar o'tdi (16/16).")


asyncio.run(main())
