"""Jonli oqim: progressiv draft, throttle, flood chidamliligi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_streaming.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram.exceptions import TelegramRetryAfter  # noqa: E402
import handlers.messages as m  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


class FakeChat:
    id = 555
    type = "private"


class FakeMessage:
    message_id = 1
    chat = FakeChat()

    async def answer(self, text, **kw):
        raise AssertionError("zaxira xabar kerak emas edi")


async def _run(chunks, chaqiruvlar, javob=lambda method, payload: {"ok": True}):
    """process_stream_draft'ni soxta Telegram API bilan ishga tushiradi."""
    async def fake_api(method, payload, *, outcome=None, timeout=None):
        chaqiruvlar.append((method, payload))
        return javob(method, payload)

    async def gen():
        for c in chunks:
            yield c

    asl = m._telegram_api_request
    m._telegram_api_request = fake_api
    try:
        return await m.process_stream_draft(FakeMessage(), gen())
    finally:
        m._telegram_api_request = asl


def draftlar(chaqiruvlar):
    """Faqat MATN draftlari (animatsiya kadrlari `html` bilan ketadi)."""
    return [p["rich_message"]["markdown"]
            for meth, p in chaqiruvlar
            if meth == "sendRichMessageDraft" and "markdown" in p["rich_message"]]


# ── 1. Throttle: bir zumda kelgan 30 bo'lak draftni bombardimon qilmaydi ──
chaqiruvlar = []
matn = asyncio.run(_run(["bo'lak " * 3 for _ in range(30)], chaqiruvlar))
push = draftlar(chaqiruvlar)
check(1, "tez kelgan bo'laklar throttle qilinadi (flood yo'q)", len(push) <= 2)
check(2, "birinchi bo'lak DARHOL ekranga chiqadi (kutish hissi yo'q)",
      len(push) >= 1 and "bo'lak" in push[0])
check(3, "oqim tugagach yakuniy xabar yuboriladi",
      any(meth == "sendRichMessage" for meth, _ in chaqiruvlar))
check(4, "javob matni to'liq qaytadi", matn.count("bo'lak") == 90)

# ── 2. Yarim fence draftda buzuq HTML bermaydi ───────────────────
chaqiruvlar = []
asyncio.run(_run(["Kod:\n```python\nprint(1)", "\nprint(2)\n```"], chaqiruvlar))
birinchi = draftlar(chaqiruvlar)[0]
check(5, "ochiq qolgan fence yopilib <pre> ga o'giriladi",
      "<pre><code" in birinchi and "```" not in birinchi)

# ── 3. Bitta rad etish jonli draftni o'chirmaydi ─────────────────
holat = {"n": 0}


def bir_marta_rad(method, payload):
    # Faqat MATN draftini bir marta rad etamiz (429 flood wait taqlidi).
    if method == "sendRichMessageDraft" and "markdown" in payload["rich_message"]:
        holat["n"] += 1
        if holat["n"] == 1:
            return None
    return {"ok": True}


# [CLEAR_TEXT] har safar "darhol ko'rsat" bayrog'ini qo'yadi, ya'ni
# throttle'ni kutmasdan uchta haqiqiy push olamiz.
chaqiruvlar = []
asyncio.run(_run(["aaa", "[CLEAR_TEXT]", "bbb", "[CLEAR_TEXT]", "ccc"],
                 chaqiruvlar, javob=bir_marta_rad))
check(6, "rad etilgandan keyin ham draft yo'li ishlatiladi",
      holat["n"] >= 2)
# FakeMessage.answer() xato otadi — zaxira yo'liga tushilganida sinov
# shu yerga yetib kelmagan bo'lardi.
check(7, "oddiy zaxira xabarga tushib ketmadi", True)


# ── 4. _edit_message_fallback 429 ni kutib qayta uradi ───────────
class FloodMessage:
    def __init__(self):
        self.urinishlar = 0

    async def edit_text(self, text, **kw):
        self.urinishlar += 1
        if self.urinishlar == 1:
            raise TelegramRetryAfter(method=None, message="flood", retry_after=0)
        return "OK"


fm = FloodMessage()
check(8, "429 dan keyin tahrirlash qayta uriniladi",
      asyncio.run(m._edit_message_fallback(fm, "matn")) == "OK")

print("\nHammasi o'tdi: 8/8")
