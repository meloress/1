# -*- coding: utf-8 -*-
"""Shaxsiy chatdagi rasm to'liq halqaga kiradi — qidiruv bilan.

  ⛔️ «shu mahsulot narxi qancha?» — model rasmni ko'radi, lekin qidiruv
     tooli yo'q (eski bir raundli get_vision_reply) va narxni TAXMIN qiladi;
  ⛔️ rasm modelga yetmaydi (faqat matn ketadi) — bot rasmni ko'rmay javob beradi;
  ⛔️ handle_photo yana get_vision_reply'ga qaytadi.

Tarmoqsiz, bazasiz.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_rasm_qidiruv.py
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import kod  # noqa: E402

import services.ai as ai  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


ushlandi = {}


class Toxta(Exception):
    pass


async def soxta_oqim(stack, modellar, **kw):
    ushlandi.update(kw)
    raise Toxta()


async def bosh(*a, **k):
    return None


async def tarix(*a, **k):
    return []


async def xotira(*a, **k):
    return [], None

ai._open_response_stream = soxta_oqim
ai.safe_history_summary_message = bosh
ai.safe_get_chat_history = tarix
ai._memory_context = xotira


async def yur():
    try:
        async for _ in ai.get_gpt_reply(1, "shu narxi qancha?", user_id=1,
                                        input_image="QUJD", output_files=[],
                                        images_out=[], is_pro=True):
            pass
    except Toxta:
        pass

asyncio.run(yur())
oxirgi = [x for x in ushlandi["input"] if x["role"] == "user"][-1]
check(1, "rasm modelga yetadi: oxirgi user xabarida input_image + matn",
      oxirgi["role"] == "user" and isinstance(oxirgi["content"], list)
      and any(c.get("type") == "input_image" and "QUJD" in c.get("image_url", "")
              for c in oxirgi["content"])
      and any(c.get("type") == "input_text" for c in oxirgi["content"]))
nomlar = {t.get("name") for t in ushlandi.get("tools", [])}
check(2, "shu so'rovda internet_search biriktirilgan", "internet_search" in nomlar)

m = kod(os.path.join(ROOT, "handlers", "messages.py"))
f = m[m.index("async def handle_photo("):m.index("async def handle_document(")]
check(3, "handle_photo to'liq halqaga (get_gpt_reply + input_image), vision'ga emas",
      "get_gpt_reply(" in f and "input_image=" in f and "get_vision_reply" not in f
      and "images_out=images" in f)

print("\nHammasi o'tdi: 3/3")
