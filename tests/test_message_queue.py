"""Navbat va oqim timeout'i: xabar yo'qolmaydi, bot qotmaydi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_message_queue.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import TEXT_MERGE_MAX_PARTS, TEXT_MERGE_WAIT  # noqa: E402
from core.memory import text_merge_buffers, TEXT_MERGE_BUFFER_TTL  # noqa: E402
import handlers.messages as m  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


CHAT = 777_777


class FakeChat:
    id = CHAT
    type = "private"


class FakeUser:
    id = CHAT
    username = "sinov"
    full_name = "Sinov"


class FakeMessage:
    """busy_handler ishlatadigan minimal Message."""

    def __init__(self, text, javoblar):
        self.text = text
        self.chat = FakeChat()
        self.from_user = FakeUser()
        self._javoblar = javoblar

    async def answer(self, text, **kwargs):
        self._javoblar.append(text)
        return None


async def sinov_navbat():
    text_merge_buffers.pop(CHAT, None)
    javoblar = []

    # Javob ketayotganda kelgan uchta xabar — hammasi navbatga tushadi.
    for t in ["birinchi", "ikkinchi", "uchinchi"]:
        await m.busy_handler(FakeMessage(t, javoblar))

    buf = text_merge_buffers.get(CHAT) or {}
    check(1, "uchta xabar ham navbatga olindi (yo'qolmadi)",
          buf.get("parts") == ["birinchi", "ikkinchi", "uchinchi"])
    check(2, "har biriga navbat haqida javob berildi",
          len(javoblar) == 3 and all("Navbatga" in j for j in javoblar))

    # Buyruq navbatga TUSHMAYDI — u AI so'rovi emas.
    await m.busy_handler(FakeMessage("/pro", javoblar))
    check(3, "buyruq navbatga qo'shilmadi",
          len(text_merge_buffers[CHAT]["parts"]) == 3
          and "Iltimos kuting" in javoblar[-1])

    # Chegara: to'lgan navbat muloyim ogohlantiradi, cheksiz o'smaydi.
    text_merge_buffers[CHAT]["parts"] = ["x"] * TEXT_MERGE_MAX_PARTS
    await m.busy_handler(FakeMessage("ortiqcha", javoblar))
    check(4, "navbat chegarasi ushlanadi",
          len(text_merge_buffers[CHAT]["parts"]) == TEXT_MERGE_MAX_PARTS
          and "to'ldi" in javoblar[-1])

    text_merge_buffers.pop(CHAT, None)


async def sinov_timeout():
    async def jim_oqim():
        await asyncio.sleep(30)      # hech qachon bo'lak bermaydi
        yield "kech"

    asl = m.STREAM_IDLE_TIMEOUT
    m.STREAM_IDLE_TIMEOUT = 0.2
    try:
        try:
            await m._next_or_stop(jim_oqim().__aiter__(), asyncio.Event())
            xato = None
        except TimeoutError as e:
            xato = e
        check(5, "jim oqim TimeoutError beradi (handler qotib qolmaydi)",
              xato is not None)

        # Tirik oqim tegilmaydi.
        async def tirik():
            yield "salom"

        chunk, stopped, finished = await m._next_or_stop(
            tirik().__aiter__(), asyncio.Event())
        check(6, "tirik oqim odatdagidek ishlaydi",
              chunk == "salom" and not stopped and not finished)
    finally:
        m.STREAM_IDLE_TIMEOUT = asl


check(7, "har bir xabar debounce oynasidan o'tadi (darhol yo'l yo'q)",
      TEXT_MERGE_WAIT <= 2.0 and not hasattr(m, "TEXT_MERGE_INSTANT_THRESHOLD"))
check(8, "navbatdagi bufer generatsiya davomida yashaydi",
      TEXT_MERGE_BUFFER_TTL >= 300)

asyncio.run(sinov_navbat())
asyncio.run(sinov_timeout())

print("\nHammasi o'tdi: 8/8")
