# -*- coding: utf-8 -*-
"""Ovoz sintezi paytidagi status ko'rsatkichi.

JONLI SHIKOYAT (2026-09-14): foydalanuvchi ovozli xabar yuboradi,
matnli javob keladi — va keyin bot 5-10 soniya JIM qoladi. Ovoz
kelayotganini hech narsa bildirmaydi, keyin u kutilmaganda tushadi.

Kodda `send_chat_action(chat_id, "record_voice")` bor edi va u
ishlardi ham — lekin Telegram chat action'ni ATIGI 5 soniya
ko'rsatadi. Sintez undan uzoq, ya'ni ko'rsatkich o'lib, qolgan vaqt
jimlikda o'tardi.

NIMANI QO'RIQLAYDI:
  1. Ko'rsatkich ishlaydi va animatsiya aylanadi;
  2. ⛔️ CHIQISHDA TOZALANADI — draft bo'sh kontent bilan ustiga
     yoziladi, oddiy xabar o'chiriladi. Tashlab ketilgan draft
     ekranda osilib qoladi va keyingi animatsiyani ham o'ldiradi
     (bu xato bir marta allaqachon to'langan);
  3. Ish paytida XATO chiqsa ham tozalash baribir bajariladi;
  4. Status matnlari ikkala yo'lda bir manbadan olinadi.

Tarmoqsiz ishlaydi — hamma Telegram chaqiruvi soxta.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_voice_status.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handlers.messages as m  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── Soxta Telegram ───────────────────────────────────────────────
class SoxtaChat:
    def __init__(self, turi):
        self.type = turi
        self.id = 777


class SoxtaXabar:
    """message.answer() qaytaradigan xabar — o'chirilishi kuzatiladi."""

    def __init__(self):
        self.ochirildi = False
        self.matn = None

    async def delete(self):
        self.ochirildi = True

    async def edit_text(self, matn, **kw):
        self.matn = matn


class SoxtaMessage:
    def __init__(self, turi="private"):
        self.chat = SoxtaChat(turi)
        self.message_id = 42
        self.from_user = None
        self.yuborilgan: list = []

    async def answer(self, matn, **kw):
        xabar = SoxtaXabar()
        xabar.matn = matn
        self.yuborilgan.append(xabar)
        return xabar


# ── 1. Shaxsiy chat: draft yo'li ─────────────────────────────────
async def _sinov_draft():
    chaqiruvlar: list = []

    async def soxta_draft(chat_id, draft_id, *, markdown=None,
                          html_content=None, message_thread_id=None,
                          can_stop=False):
        chaqiruvlar.append({"html": html_content, "markdown": markdown,
                            "draft_id": draft_id})
        return {"ok": True}

    m._send_rich_draft = soxta_draft
    xabar = SoxtaMessage("private")

    async with m._status_indicator(xabar, "tts"):
        # Sintez taqlidi — animator bir necha marta yangilanishga ulgursin.
        await asyncio.sleep(1.5)

    animatsiya = [c for c in chaqiruvlar if c["html"]]
    check(1, f"draft bir necha marta yangilandi ({len(animatsiya)} ta)",
          len(animatsiya) >= 2)
    check(2, "status matni ovoz sintezi haqida",
          any("Ovozli javob tayyorlanmoqda" in c["html"]
              or "ovozga" in c["html"] for c in animatsiya))
    check(3, "animatsiya aylanadi (matn o'zgaradi)",
          len({c["html"] for c in animatsiya}) >= 2)

    # ⛔️ ENG MUHIMI: oxirgi chaqiruv — BO'SH kontent bilan yopish.
    check(4, "chiqishda draft bo'sh kontent bilan yopildi",
          chaqiruvlar[-1]["markdown"] == "" and chaqiruvlar[-1]["html"] is None)
    check(5, "yopish o'sha draft ustiga yozildi",
          chaqiruvlar[-1]["draft_id"] == chaqiruvlar[0]["draft_id"])
    check(6, "shaxsiy chatda ortiqcha xabar yuborilmadi",
          xabar.yuborilgan == [])


asyncio.run(_sinov_draft())


# ── 2. Guruh: oddiy xabar yo'li ──────────────────────────────────
async def _sinov_guruh():
    async def hech_qachon(*a, **kw):
        raise AssertionError("guruhda draft chaqirilmasligi kerak")

    m._send_rich_draft = hech_qachon
    xabar = SoxtaMessage("supergroup")

    async with m._status_indicator(xabar, "tts"):
        await asyncio.sleep(1.2)

    check(7, "guruhda oddiy xabar yuborildi", len(xabar.yuborilgan) == 1)
    check(8, "xabarda status matni bor",
          "🔄" in (xabar.yuborilgan[0].matn or ""))
    check(9, "⛔️ chiqishda xabar O'CHIRILDI",
          xabar.yuborilgan[0].ochirildi is True)


asyncio.run(_sinov_guruh())


# ── 3. Xato chiqsa ham tozalanadi ────────────────────────────────
async def _sinov_xato():
    tozalandi: list = []

    async def soxta_draft(chat_id, draft_id, *, markdown=None,
                          html_content=None, message_thread_id=None,
                          can_stop=False):
        if markdown == "":
            tozalandi.append(True)
        return {"ok": True}

    m._send_rich_draft = soxta_draft
    xabar = SoxtaMessage("private")

    # ⚠️ Sintez yiqilsa ham draft ekranda QOLMASLIGI kerak.
    try:
        async with m._status_indicator(xabar, "tts"):
            await asyncio.sleep(0.3)
            raise RuntimeError("sintez yiqildi")
    except RuntimeError:
        pass

    check(10, "xato chiqsa ham draft yopildi", tozalandi == [True])


asyncio.run(_sinov_xato())


# ── 4. Juda tez tugagan ish ──────────────────────────────────────
async def _sinov_tez():
    chaqiruvlar: list = []

    async def soxta_draft(chat_id, draft_id, *, markdown=None,
                          html_content=None, message_thread_id=None,
                          can_stop=False):
        chaqiruvlar.append(markdown)
        return {"ok": True}

    m._send_rich_draft = soxta_draft
    xabar = SoxtaMessage("private")

    # Ovoz keshdan darhol kelsa — ko'rsatkich ko'rinib ulgurmasa ham,
    # tozalash BARIBIR bajarilishi kerak.
    async with m._status_indicator(xabar, "tts"):
        pass

    check(11, "bir zumlik ishda ham draft yopiladi", chaqiruvlar[-1] == "")


asyncio.run(_sinov_tez())


# ── 5. Status matnlari bitta manbadan ────────────────────────────
check(12, "`tts` status ro'yxati mavjud", "tts" in m.STATUS_TEXTS_BY_TYPE)
check(13, "unda bir nechta bosqich bor", len(m.STATUS_TEXTS_BY_TYPE["tts"]) >= 3)
check(14, "`tts` uchun emoji belgilangan", "tts" in m.EMOJI_ID_BY_TYPE)

# ⚠️ Ikkala yo'l ham BITTA funksiyadan o'qiydi. Ilgari status matni
# process_stream_draft() ichida, lokal nusxada yasalardi; ikkinchi
# nusxa yozilsa ohang va tezlik ikki joyda ayri o'zgarib ketardi.
check(15, "oqim va ovoz bir xil manbadan o'qiydi",
      m._status_texts_for("tts") is m.STATUS_TEXTS_BY_TYPE["tts"])
check(16, "noma'lum tur matnga tushadi",
      m._status_texts_for("yoq") is m.STATUS_TEXTS_BY_TYPE["text"])

# Draft uchun HTML, guruh uchun oddiy matn — ikkisi ayri.
_h = m._thinking_html_for("tts", 2.0)
check(17, "draft varianti <tg-thinking> ishlatadi", _h.startswith("<tg-thinking>"))
check(18, "oddiy variantda HTML teg yo'q",
      "<" not in m._thinking_plain_for("tts", 2.0))

print("\nvoice_status: barcha tekshiruvlar o'tdi (18/18).")
