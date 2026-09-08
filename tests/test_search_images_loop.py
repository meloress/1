"""Rasm qidiruvi tool-loop ichida: takror va TPM limiti.
Ishga tushirish: python tests/test_search_images_loop.py

JONLI NOSOZLIK (Chevrolet Malibu so'rovi, Railway loglari):

  [SEARCH] ... images=True round=1   -> [IMAGES] Commons 10 ta berdi
  [SEARCH] ... images=True round=2   -> (hech narsa)
  [SEARCH] ... images=True round=3   -> (hech narsa)
  ERROR: Rate limit reached ... Requested 79025 ... TPM Limit 200000

Rasm FAQAT bir marta qidiriladi (ro'yxat almashsa model yozib bo'lgan
[rasm:2] boshqa rasmga tegib ketardi), lekin ikkinchi chaqiruv JIMGINA
bo'sh qaytardi. Model buni "rasm topilmadi" deb tushunib qidiruvni
takrorlardi, har bir takror esa butun sahifa matnini kontekstga
qo'shardi — uchinchi raundda so'rov 79 ming tokenga yetib TPM limitiga
urilardi va 50 soniya ishlangan javob BUTUNLAY yo'qolardi.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import json

import httpx
from openai import RateLimitError

from services import ai as services


class FakeItem:
    def __init__(self, name, arguments, call_id="call_1"):
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


class FakeStream:
    """`raise_at` berilsa — oqim O'RTASIDA xato ko'taradi (aynan TPM holati)."""
    def __init__(self, events, raise_at=None):
        self._events = events
        self._raise = raise_at

    def __aiter__(self):
        async def gen():
            if self._raise is not None:
                raise self._raise
            for e in self._events:
                yield e
        return gen()

    async def get_final_response(self):
        return FakeFinal()


async def _empty_history():
    return []


async def run_case(rounds, *, tool_outputs, topiladi=True):
    """`rounds` — har bir raund uchun (events, raise_at) juftligi.

    `topiladi=False` — rasm qidiruvi bo'sh qaytgan holat.
    """
    holat = {"i": 0}

    async def fake_open(stack, candidate_models, **kwargs):
        idx = holat["i"]
        holat["i"] += 1
        tool_outputs.setdefault("so'rovlar", []).append(kwargs)
        events, raise_at = rounds[idx] if idx < len(rounds) else ([], None)
        return FakeStream(events, raise_at), "fake-model"

    async def fake_search(**kwargs):
        tool_outputs.setdefault("veb", []).append(kwargs.get("primary_query"))
        return "SOXTA QIDIRUV NATIJASI"

    # ⚠️ Imzo haqiqiy `search_images` bilan bir xil bo'lishi SHART:
    # mos kelmasa tool-loop TypeError'ni yutadi va qidiruv umuman
    # bo'lmagandek ko'rinadi (aynan shu holat bir marta yuz bergan).
    async def fake_images(query, limit=None, request="", skip_urls=None):
        tool_outputs.setdefault("qidiruvlar", []).append(query)
        if not topiladi:
            return []
        return [{"url": "https://upload.wikimedia.org/malibu.jpg",
                 "title": "Chevrolet Malibu 2013", "source": "commons"}]

    asl = {
        "open": services._open_response_stream,
        "hist": services.safe_get_chat_history,
        "search": services.multi_source_deep_search,
        "images": services.search_images,
        "delay": services.RATE_LIMIT_RETRY_DELAY,
    }
    services._open_response_stream = fake_open
    services.safe_get_chat_history = lambda *a, **k: _empty_history()
    services.multi_source_deep_search = fake_search
    services.search_images = fake_images
    services.RATE_LIMIT_RETRY_DELAY = 0      # testda kutib o'tirmaymiz
    rasmlar: list = []
    try:
        chunks = []
        async for c in services.get_openai_reply(
                1, "Chevrolet Malibu haqida rasmlari bilan ayt",
                user_id=7, images_out=rasmlar, is_pro=True):
            chunks.append(c)
    finally:
        services._open_response_stream = asl["open"]
        services.safe_get_chat_history = asl["hist"]
        services.multi_source_deep_search = asl["search"]
        services.search_images = asl["images"]
        services.RATE_LIMIT_RETRY_DELAY = asl["delay"]
    return chunks, rasmlar


def _search_call(cid, query="Chevrolet Malibu"):
    return FakeItem("internet_search", json.dumps(
        {"primary_query": query, "want_images": True}), call_id=cid)


async def main():
    # ═══════════════════════════════════════════════════════════
    # 1) TAKRORIY want_images — katalog QAYTA ko'rsatiladi
    # ═══════════════════════════════════════════════════════════
    c1, c2 = _search_call("a"), _search_call("b", "Chevrolet Malibu 2 avlod")
    kuzatuv: dict = {}
    chunks, rasmlar = await run_case([
        ([FakeEvent("response.output_item.added", item=c1),
          FakeEvent("response.output_item.done", item=c1)], None),
        ([FakeEvent("response.output_item.added", item=c2),
          FakeEvent("response.output_item.done", item=c2)], None),
        ([FakeEvent("response.output_text.delta", delta="Mana [rasm:1]")], None),
    ], tool_outputs=kuzatuv)

    assert len(kuzatuv.get("qidiruvlar", [])) == 1, (
        f"rasm BIR MARTA qidirilishi kerak: {kuzatuv.get('qidiruvlar')}")
    assert len(rasmlar) == 1, f"ro'yxat o'smasligi kerak: {rasmlar}"
    print("[1] rasm bir marta qidirildi, ro'yxat o'zgarmadi OK")

    # Ikkinchi raundning tool javobi katalogni QAYTA ko'rsatishi shart —
    # aks holda model qidiruvni yana takrorlaydi.
    katalog = services.format_image_catalog(rasmlar)
    assert "[rasm:1]" in katalog and "https://" not in katalog
    print("[2] katalog matni URL'siz va belgili OK")

    assert "Mana [rasm:1]" in "".join(chunks), chunks
    print("[3] yakuniy javob yetib bordi OK")

    # ═══════════════════════════════════════════════════════════
    # 4) TPM LIMITI — bir marta kutib qayta uriniladi
    #
    # Ilgari bu xato butun javobni yo'q qilardi: foydalanuvchi 50 soniya
    # animatsiyani ko'rib, oxirida hech narsa olmasdi.
    # ═══════════════════════════════════════════════════════════
    xato = RateLimitError(
        "Rate limit reached ... Please try again in 1.074s",
        response=httpx.Response(429, request=httpx.Request(
            "POST", "https://api.openai.com/v1/responses")),
        body=None)
    chunks, _ = await run_case([
        ([], xato),
        ([FakeEvent("response.output_text.delta", delta="Javob keldi")], None),
    ], tool_outputs={})
    assert "".join(chunks).strip() == "Javob keldi", chunks
    print("[4] TPM limitidan keyin qayta urinildi, javob yetib bordi OK")

    # ── 5) Ikki marta yiqilsa — xato yuqoriga chiqadi (jim yutilmaydi) ──
    yiqildi = False
    try:
        await run_case([([], xato), ([], xato)], tool_outputs={})
    except RateLimitError:
        yiqildi = True
    assert yiqildi, "ikkinchi urinish ham yiqilsa xato ko'tarilishi kerak"
    print("[5] ikki marta yiqilsa xato yashirilmadi OK")

    # ═══════════════════════════════════════════════════════════
    # 6) MATN KETGANDAN KEYIN QAYTA URINILMAYDI
    #
    # Aks holda foydalanuvchi javob boshini IKKI marta ko'rardi.
    # ═══════════════════════════════════════════════════════════
    class YarimStream(FakeStream):
        def __aiter__(self):
            async def gen():
                yield FakeEvent("response.output_text.delta", delta="Boshi...")
                raise xato
            return gen()

    holat = {"i": 0}

    async def fake_open(stack, candidate_models, **kwargs):
        holat["i"] += 1
        return YarimStream([]), "fake-model"

    asl_open = services._open_response_stream
    asl_hist = services.safe_get_chat_history
    services._open_response_stream = fake_open
    services.safe_get_chat_history = lambda *a, **k: _empty_history()
    try:
        got = []
        try:
            async for c in services.get_openai_reply(1, "salom", user_id=7):
                got.append(c)
        except RateLimitError:
            pass
    finally:
        services._open_response_stream = asl_open
        services.safe_get_chat_history = asl_hist

    assert holat["i"] == 1, (
        f"matn ketgandan keyin QAYTA urinilmasligi kerak: {holat['i']} urinish")
    print("[6] matn ketgach qayta urinilmadi (takror javob yo'q) OK")

    # ═══════════════════════════════════════════════════════════
    # 7-9) images_only — VEB QIDIRUVSIZ RASM
    #
    # Rasm ilgari faqat internet_search chaqirilganda topilardi: model
    # savolga o'z bilimidan javob bersa, rasm chiqishi JISMONAN mumkin
    # emas edi ("Eyfel minorasi haqida ayt" — hech qachon rasmsiz).
    # ═══════════════════════════════════════════════════════════
    faqat_rasm = FakeItem("internet_search", json.dumps(
        {"primary_query": "Eyfel minorasi", "want_images": True,
         "images_only": True}), call_id="c")
    kuzatuv = {}
    chunks, rasmlar = await run_case([
        ([FakeEvent("response.output_item.added", item=faqat_rasm),
          FakeEvent("response.output_item.done", item=faqat_rasm)], None),
        ([FakeEvent("response.output_text.delta", delta="Mana [rasm:1]")], None),
    ], tool_outputs=kuzatuv)

    assert kuzatuv.get("veb") is None, (
        f"images_only'da veb qidiruv CHAQIRILMASLIGI kerak: {kuzatuv.get('veb')}")
    print("[7] images_only'da multi_source_deep_search chaqirilmadi OK")

    assert len(rasmlar) == 1 and len(kuzatuv.get("qidiruvlar", [])) == 1, (
        f"rasm baribir qidirilishi kerak: {rasmlar}")
    chiqishlar = [m["output"] for so in kuzatuv["so'rovlar"]
                  for m in so["input"] if m.get("type") == "function_call_output"]
    assert any("[rasm:1]" in o for o in chiqishlar), (
        f"tool javobida katalog bo'lishi kerak: {chiqishlar}")
    assert not any("SOXTA QIDIRUV NATIJASI" in o for o in chiqishlar), chiqishlar
    print("[8] images_only'da ham katalog qaytdi, veb natijasi yo'q OK")

    # Byudjet: aks holda model cheksiz rasm so'rab tura oladi.
    # MAX_SEARCH_ROUNDS = 3 (research emas) — 4-so'rovda tool tushishi kerak.
    kuzatuv = {}
    raund = [([FakeEvent("response.output_item.added", item=faqat_rasm),
               FakeEvent("response.output_item.done", item=faqat_rasm)], None)]
    await run_case(raund * 3 + [
        ([FakeEvent("response.output_text.delta", delta="Tayyor")], None),
    ], tool_outputs=kuzatuv)

    nomlar = [[t.get("name") for t in (so.get("tools") or [])]
              for so in kuzatuv["so'rovlar"]]
    assert "internet_search" in nomlar[0], nomlar[0]
    assert "internet_search" not in nomlar[3], (
        f"images_only search_rounds byudjetini YEYISHI kerak: {nomlar[3]}")
    print("[9] images_only chaqiruvi qidiruv byudjetini yedi OK")

    # ── 10) Rasm topilmasa ham tool JIM QAYTMAYDI ──────────────────
    # images_only'da veb natijasi yo'q, ya'ni rasm ham topilmasa javob
    # bo'sh bo'lardi — bu esa modelga "topilmadi, yana qidir" signali
    # (aynan TPM limitiga olib kelgan xatti-harakat).
    kuzatuv = {}
    await run_case([
        ([FakeEvent("response.output_item.added", item=faqat_rasm),
          FakeEvent("response.output_item.done", item=faqat_rasm)], None),
        ([FakeEvent("response.output_text.delta", delta="Tayyor")], None),
    ], tool_outputs=kuzatuv, topiladi=False)
    chiqishlar = [m["output"] for so in kuzatuv["so'rovlar"]
                  for m in so["input"] if m.get("type") == "function_call_output"]
    assert chiqishlar and all(o.strip() for o in chiqishlar), chiqishlar
    assert "topilmadi" in chiqishlar[0], chiqishlar
    print("[10] rasm topilmaganda tool aniq matn qaytardi OK")

    print("\nsearch_images_loop: barcha tekshiruvlar o'tdi (10/10).")


if __name__ == "__main__":
    asyncio.run(main())
