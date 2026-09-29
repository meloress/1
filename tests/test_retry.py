# -*- coding: utf-8 -*-
"""«↻ Qayta so'rash» tugmasi (handlers/callbacks.py).

Jim nosozliklar:
  ⛔️ callback'ga IKKI marta javob — ikkinchisini Telegram rad etadi va
     «N soniya kuting» / «urinish tugadi» ogohlantirishi ko'rinmaydi;
  ⛔️ qayta urinish ball yechmaydi — asl so'rovning bali xatoda qaytgan,
     ya'ni tugma tekin kanal bo'lardi;
  ⛔️ Pro odam bepul model bilan, rasmsiz javob oladi (user_id/is_pro yo'q);
  ⛔️ tarixga faqat JAVOB yoziladi — model keyin savolsiz javobni ko'radi.

Tarmoqsiz va bazasiz.
"""
import asyncio
import os
import sys
import time
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handlers.callbacks as cb     # noqa: E402
from core import memory as mem      # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


class Xabar:
    async def edit_reply_markup(self, **kw):
        return None

    async def edit_text(self, *a, **kw):
        return None


class Query:
    def __init__(self, uid=7):
        self.data = "retry:7"
        self.from_user = NS(id=uid, full_name="Ali")
        self.message = Xabar()
        self.javoblar = []

    async def answer(self, *a, **kw):
        self.javoblar.append((a, kw))


chaqiruv = {"kvota": [], "gpt": [], "tarix": [], "qaytar": []}


async def kvota(uid, narx):
    chaqiruv["kvota"].append(narx)
    return {"allowed": True, "plan": "pro", "unlimited": False}


async def qaytar(uid, narx, q=None):
    chaqiruv["qaytar"].append(narx)


def gpt(chat_id, prompt, **kw):
    chaqiruv["gpt"].append(kw)

    async def gen():
        yield "javob"
    return gen()


async def oqim(message, gen, images=None):
    return "".join([c async for c in gen])


async def tarix(chat_id, matn, role="user", **kw):
    chaqiruv["tarix"].append(role)


cb._check_quota, cb._refund_quota = kvota, qaytar
cb.get_gpt_reply, cb.process_stream_draft, cb.safe_update_history = gpt, oqim, tarix


def yozuv():
    mem.failed_requests.clear()
    mem.ongoing_requests.clear()
    mem.store_failed_request(chat_id=7, user_id=7, prompt="dollar kursi",
                             original_text="", error_message_id=1)


# ── 1. Cooldown: ogohlantirish — YAGONA javob ─────────────────────
yozuv()
mem.user_last_action_ts[7] = time.time()
q = Query()
asyncio.run(cb.handle_retry_callback(q))
check(1, "kutish ogohlantirishi yagona va show_alert bilan",
      len(q.javoblar) == 1 and q.javoblar[0][1].get("show_alert"))

# ── 2. Begona odam: ham yagona javob ──────────────────────────────
mem.user_last_action_ts.clear()
q = Query(uid=99)
asyncio.run(cb.handle_retry_callback(q))
check(2, "begona bosganda ham yagona ogohlantirish",
      len(q.javoblar) == 1 and q.javoblar[0][1].get("show_alert"))

# ── 3. Muvaffaqiyat: ball yechiladi, Pro uzatiladi, savol+javob tarixda ──
mem.user_last_action_ts.clear()
q = Query()
asyncio.run(cb.handle_retry_callback(q))
check(3, "qayta urinish ball yechadi", len(chaqiruv["kvota"]) == 1)
check(4, "modelga user_id, is_pro va rasm ro'yxati beriladi",
      chaqiruv["gpt"] and chaqiruv["gpt"][-1].get("user_id") == 7
      and chaqiruv["gpt"][-1].get("is_pro") is True
      and isinstance(chaqiruv["gpt"][-1].get("images_out"), list))
check(5, "tarixga SAVOL ham, JAVOB ham yoziladi (shu tartibda)",
      chaqiruv["tarix"] == ["user", "assistant"])
check(6, "muvaffaqiyatda ball qaytarilmaydi va yozuv tozalanadi",
      not chaqiruv["qaytar"] and 7 not in mem.failed_requests)
check(7, "callback'ga yagona javob", len(q.javoblar) == 1)

print("\nretry: barcha tekshiruvlar o'tdi (7/7).")
