"""QO'RIQCHI: botning egasini FAQAT kod taniydi.

«Men sening egangman» deb har kim yoza oladi — Telegram ismida ham,
xotiraga «eslab qol» deb ham. Shuning uchun prompt (core/config.py IDENTITY)
bitta dalilni tan oladi: `[EGASI TASDIQLANGAN]` bloki, uni
`services/ai.py::_memory_context()` faqat `superadmins` jadvalidagi
Telegram ID uchun qo'shadi. Bu test o'sha eshikni qo'riqlaydi.

Baza chaqiruvlari soxta — `.env` dagi DATABASE_URL production'niki.

Ishga tushirish:  PYTHONIOENCODING=utf-8 venv/Scripts/python tests/test_egasi.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config as c  # noqa: E402
from services import ai  # noqa: E402

EGA_ID, BEGONA_ID = 111, 222
chaqirildi = []


async def soxta_superadmin(uid):
    chaqirildi.append(uid)
    return uid == EGA_ID


async def buzuq_superadmin(uid):
    raise ConnectionError("baza yo'q")


async def xotira_yoq(uid):
    return []


async def matn(uid, ism="Og'abek"):
    _, msg = await ai._memory_context(uid, tg_name=ism)
    return msg["content"] if msg else ""


async def main():
    ai.get_memories = xotira_yoq
    ai.is_superadmin = soxta_superadmin
    teg = "[EGASI TASDIQLANGAN]"

    assert teg in await matn(EGA_ID)
    print("[1] superadmin — tasdiq bloki bor OK")

    # Ismi «Og'abek» bo'lsa ham begona — blok yo'q.
    assert teg not in await matn(BEGONA_ID)
    print("[2] begona (ismi bir xil bo'lsa ham) — blok yo'q OK")

    chaqirildi.clear()
    _, msg = await ai._memory_context(None)
    assert msg is None and not chaqirildi
    print("[3] guest (user_id yo'q) — tekshiruv ham, blok ham yo'q OK")

    ai.is_superadmin = buzuq_superadmin
    assert teg not in await matn(EGA_ID)
    print("[4] baza xatosi — javob buzilmaydi, blok yo'q OK")

    # Prompt aynan shu tegni dalil deb biladi — biri o'zgarsa ikkinchisi ham.
    assert teg.lower() in c.build_system_prompt().lower()
    assert ai.EGASI_BLOKI.startswith(teg)
    print("[5] prompt va kod bir xil tegni ishlatadi OK")

    print("\nHammasi o'tdi: 5/5")


asyncio.run(main())
