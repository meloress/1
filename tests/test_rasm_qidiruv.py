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

# ── 4. Albom rasmlari modelga BITTA xabarda ──────────────────────
ushlandi.clear()


async def yur_albom():
    try:
        async for _ in ai.get_gpt_reply(1, "solishtir", user_id=1,
                                        input_image=["QQ==", "Qg==", "Qw=="],
                                        images_out=[], is_pro=True):
            pass
    except Toxta:
        pass

asyncio.run(yur_albom())
oxirgi = [x for x in ushlandi["input"] if x["role"] == "user"][-1]
check(4, "albom: uchala rasm bitta user xabarida",
      sum(c.get("type") == "input_image" for c in oxirgi["content"]) == 3)

# ── 5. handle_photo: albom = BITTA so'rov, BITTA ball ─────────────
from types import SimpleNamespace as NS  # noqa: E402
import handlers.messages as hm  # noqa: E402

qayd = {"kvota": 0, "gpt": [], "tarix": []}


class Bot:
    async def get_file(self, fid):
        return NS(file_path=fid)

    async def download_file(self, path, dest):
        dest.write(path.encode())

    async def send_chat_action(self, *a, **k):
        pass


async def kvota(uid, narx):
    qayd["kvota"] += 1
    return {"allowed": True, "plan": "pro", "unlimited": False}


def gpt(chat_id, prompt, **kw):
    qayd["gpt"].append((prompt, kw))

    async def g():
        yield "javob"
    return g()


async def oqim(message, gen, **kw):
    return "".join([c async for c in gen])


async def tarix2(chat_id, matn, role="user", **kw):
    qayd["tarix"].append((role, matn))


async def hech(*a, **k):
    return None


class Holat:
    async def set_state(self, s):
        pass

    async def clear(self):
        pass


hm.bot = Bot()
hm._check_quota, hm.get_gpt_reply, hm.process_stream_draft = kvota, gpt, oqim
hm.safe_update_history, hm.check_and_clear_session = tarix2, hech
hm._after_file_task, hm._maybe_warn_long = hech, hech
hm.track_user_activity = hm.notify_watchers = lambda *a, **k: None
hm._navbatni_uygot = lambda *a, **k: None
hm.ALBOM_KUTISH = 0.05


def rasm(mid, izoh=None):
    return NS(message_id=mid, media_group_id="G1", caption=izoh,
              photo=[NS(file_id=f"f{mid}")], chat=NS(id=5),
              from_user=NS(id=5, username="u", full_name="Ali"),
              is_topic_message=False, message_thread_id=None)


async def albom():
    await asyncio.gather(hm.handle_photo(rasm(11, "qaysi biri arzon?"), Holat()),
                         hm.handle_photo(rasm(12), Holat()),
                         hm.handle_photo(rasm(13), Holat()))

asyncio.run(albom())
prompt, kw = qayd["gpt"][0] if qayd["gpt"] else ("", {})
check(5, "albom (3 rasm): bitta so'rov, bitta ball, 3 rasm, izoh saqlangan",
      len(qayd["gpt"]) == 1 and qayd["kvota"] == 1
      and len(kw.get("input_image") or []) == 3
      and "qaysi biri arzon?" in prompt and "3 ta rasm" in prompt
      and not hm._albomlar)

print("\nHammasi o'tdi: 5/5")
