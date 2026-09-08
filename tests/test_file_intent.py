"""Fayl tooli endi ikki bosqichli: arzon "eshik", keyin to'liq qo'llanma.

NEGA: `run_python_sandbox` tavsifi ~4 000 token (butun maket qo'llanmasi)
va u HAR BIR shaxsiy chat so'roviga biriktirilardi — `file_task_enabled`
tarifga emas, `output_files is not None` ga bog'liq. Bazadagi o'lchov:
fayl vazifasi 1 210 so'rovdan 17 tasida (1.4%) chaqirilgan. Ya'ni
qo'llanma so'rovlarning 98.6% ida bekorga ketardi — kuniga ~890 ming
token, kunlik grantning uchdan biri.

Endi avval `start_file_task` (~176 token) biriktiriladi va model o'zi
fayl kerakligini aytganda to'liq tool keladi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_file_intent.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import ai as services  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


class FakeItem:
    def __init__(self, name, arguments="{}", call_id="c1"):
        self.type = "function_call"
        self.name = name
        self.arguments = arguments
        self.call_id = call_id


class FakeEvent:
    def __init__(self, type_, item=None, delta=None):
        self.type = type_
        self.item = item
        self.delta = delta


class FakeFinal:
    status = "completed"
    incomplete_details = None
    usage = None


class FakeStream:
    def __init__(self, events):
        self._events = events

    def __aiter__(self):
        async def gen():
            for e in self._events:
                yield e
        return gen()

    async def get_final_response(self):
        return FakeFinal()


captured = []


def make_opener(rounds):
    state = {"i": 0}

    async def fake_open(stack, candidate_models, **kwargs):
        idx = state["i"]
        state["i"] += 1
        captured.append([t["name"] for t in (kwargs.get("tools") or [])])
        return FakeStream(rounds[idx] if idx < len(rounds) else []), "fake"

    return fake_open


async def _empty_history(*a, **k):
    return []


async def collect(gen):
    return [c async for c in gen]


async def run_case(rounds):
    captured.clear()
    fayl_chaqiruvlari = []
    qidiruvlar = []

    async def fake_file_task(code, **kwargs):
        fayl_chaqiruvlari.append(code)
        return "Fayl tayyor."

    async def fake_search(**kwargs):
        qidiruvlar.append(kwargs)
        return "SOXTA QIDIRUV"

    asl = {"open": services._open_response_stream,
           "hist": services.safe_get_chat_history,
           "file": services._run_file_task,
           "search": services.multi_source_deep_search}
    services._open_response_stream = make_opener(rounds)
    services.safe_get_chat_history = _empty_history
    services._run_file_task = fake_file_task
    services.multi_source_deep_search = fake_search
    try:
        matn = await collect(services.get_openai_reply(
            1, "menga taqdimot qilib ber", user_id=7, is_pro=True,
            output_files=[]))
    finally:
        services._open_response_stream = asl["open"]
        services.safe_get_chat_history = asl["hist"]
        services._run_file_task = asl["file"]
        services.multi_source_deep_search = asl["search"]
    return matn, fayl_chaqiruvlari, qidiruvlar


DONE = FakeEvent("response.output_item.done")
TEXT = FakeEvent("response.output_text.delta", delta="Tayyor.")


def call_round(name, args="{}"):
    # ⚠️ IKKALA hodisa ham shart: `added` da `got_function_call` yoqiladi
    # (busiz sikl birinchi raunddayoq tugaydi), `done` da esa chaqiruvning
    # o'zi yig'iladi.
    it = FakeItem(name, args)
    return [FakeEvent("response.output_item.added", item=it),
            FakeEvent("response.output_item.done", item=it)]


# ── 1. Oddiy so'rovda qimmat tavsif YO'Q ─────────────────────────
async def sinov():
    _, _, _ = await run_case([[TEXT]])
    check(1, "birinchi raundda arzon 'eshik' biriktiriladi",
          "start_file_task" in captured[0])
    check(2, "qimmat tool biriktirilmaydi",
          "run_python_sandbox" not in captured[0])

    # ── 2. Model fayl so'rasa — keyingi raundda to'liq tool ──────
    _, fayllar, qidiruvlar = await run_case([
        call_round("start_file_task"),
        call_round("run_python_sandbox", json.dumps({"code": "print(1)"})),
        [TEXT],
    ])
    check(3, "eshik chaqirilgach to'liq tool keladi",
          "run_python_sandbox" in captured[1])
    check(4, "fayl vazifasi haqiqatan bajarildi", fayllar == ["print(1)"])
    # ⚠️ ENG MUHIM: `start_file_task` pastdagi bare `else` ga tushib
    # ketmasligi kerak — u har qanday tanilmagan nomni VEB QIDIRUVGA
    # yo'naltiradi va "taqdimot qilib ber" jimgina DuckDuckGo so'roviga
    # aylanib qolardi.
    check(5, "eshik chaqiruvi veb qidiruvga TUSHMAYDI", qidiruvlar == [])
    check(6, "fayl rejimi so'rov oxirigacha saqlanadi",
          "run_python_sandbox" in captured[2])


asyncio.run(sinov())


# ── 3. O'lchamlar ────────────────────────────────────────────────
def tok(x):
    return int(len(json.dumps(x, ensure_ascii=False)) / 3.6)


eshik = tok(services._FILE_INTENT_TOOL)
toliq = tok(services._FILE_TASK_TOOL)
check(7, "eshik kichik (300 tokendan kam)", eshik < 300)
check(8, "to'liq tavsif haqiqatan qimmat (3000+)", toliq > 3000)
check(9, f"tejash sezilarli ({toliq - eshik} token/raund)",
      toliq - eshik > 3500)

# ── 4. Manifest CHAQIRILADIGAN nomni aytishi kerak ───────────────
man = services._capability_manifest(
    file_task_enabled=True, image_enabled=False,
    reminder_enabled=False, memory_enabled=True)["content"]
check(10, "manifest eshik nomini aytadi", "start_file_task" in man)
check(11, "manifest mavjud bo'lmagan nomni va'da qilmaydi",
      "run_python_sandbox" not in man)

man2 = services._capability_manifest(
    file_task_enabled=False, image_enabled=False,
    reminder_enabled=False, memory_enabled=True)["content"]
check(12, "guruhda fayl imkoniyati yo'q deb aytiladi",
      "start_file_task" in man2 and "NOT available" in man2)

print("\nHammasi o'tdi: 12/12")
