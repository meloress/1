"""Status kadri: qisqa 1-qator, bosqichlar oldinga yuradi, tafsilot 2-qatorda,
har bir tool O'Z statusini oladi.
Ishga tushirish: python tests/test_status_matn.py

MUAMMO TARIXI (2026-11-19):
1) Ob-havo, valyuta, namoz, yaqin joylar, rasm tahrirlash — hammasi
   «Internetdan ma'lumot qidirilmoqda» derdi: services/ai.py dagi bare
   `elif not search_performed` nomi yozilmagan HAR toolni qidiruvga
   tushirardi (xotira uchun xuddi shu xato 2026 yozida tuzatilgan edi).
2) Matnlar 2,4 s da aylanib qaytardi — 10 s dan keyin ro'yxat boshidan
   boshlanib, bot qotgandek ko'rinardi.
3) Telefonda qatorga ~30 harf sig'adi; «Eng so'nggi ma'lumotlar
   tekshirilmoqda» (38) + o'zgaruvchan nuqtalar qatorni sakratib turardi.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import json

from handlers import messages as m
from handlers import guest
from services import ai
from core.config import INTERNAL_TOOL_NAMES

T = m.STATUS_TEXTS_BY_TYPE

# ── 1) Har 1-qator telefonga sig'adi ─────────────────────────────────
uzun = [(tur, s) for tur, l in T.items() for s in l if len(s) > m.STATUS_QATOR_MAX]
assert not uzun, f"1-qator {m.STATUS_QATOR_MAX} harfdan uzun: {uzun}"
assert m.STATUS_QATOR_MAX <= 26, "chegara 26 dan oshmasin — nuqtalar bilan ~30 harf"
assert all(l and not any(s.endswith(".") for s in l) for l in T.values()), \
    "bo'sh ro'yxat yoki nuqta bilan tugagan matn (nuqtani animatsiya qo'shadi)"
assert all(t in m.EMOJI_ID_BY_TYPE for t in T), "emojisiz status turi"
print(f"[1] {sum(map(len, T.values()))} ta matn ≤ {m.STATUS_QATOR_MAX} harf, emojisi bor OK")

# ── 2) Bosqichlar oldinga yuradi va OXIRGISIDA to'xtaydi ─────────────
ust = lambda *a, **k: m.holat_kadri(*a, **k)[0].rstrip(".")
assert ust("text", 0.1) == T["text"][0]
assert ust("text", 300) == T["text"][-1], "uzoq kutishda boshiga qaytmasin"
assert [ust("photo", i * m.STATUS_INTERVAL + 0.1) for i in range(5)] == \
    T["photo"] + [T["photo"][-1]] * 2
print("[2] bosqichlar aylanmaydi, oxirgisida to'xtaydi OK")

# ── 3) Tur almashsa bosqich boshidan; /research sekin yuradi ─────────
assert ust("manbalar", 40, bosqich=0.2) == T["manbalar"][0], \
    "8-soniyada boshlangan qidiruv darhol oxirgi bosqichidan ko'rinmasin"
assert ust("research", 10) == T["research"][0], "tadqiqot 10 s da oxiriga yetmasin"
assert ust("research", 31) == T["research"][2]
print("[3] yangi tur boshidan, tadqiqot o'z sur'atida OK")

# ── 4) 2-qator: tafsilot, uzoq kutish gapi, soniya ───────────────────
past = lambda *a, **k: m.holat_kadri(*a, **k)[1]
assert past("text", 2) == "", "birinchi soniyalarda 2-qator bo'sh"
assert past("text", 7) == "7s"
assert past("text", 25) == "Savol chuqur, yana ozgina · 25s"
assert past("search", 6, "«dollar kursi»") == "«dollar kursi» · 6s"
assert past("search", 25, "«x»", bosqich=25) == "«x» · 25s", "tafsilot gapdan ustun"
eng_uzun = past("text", 3599, "x" * 200)
assert len(eng_uzun) <= 32, (len(eng_uzun), eng_uzun)
toza = m._tafsilot("a_b*c`d[e]<f>|g\\h\n  i")
assert not set(toza) & set("_*`[]<>|\\") and "  " not in toza, toza
assert m._tafsilot("y" * 50).endswith("…") and len(m._tafsilot("y" * 50)) == m.TAFSILOT_MAX
print(f"[4] 2-qator ≤ 32 harf, belgilari tozalangan OK")

# ── 5) Uch ko'rinish bitta kadrdan; Markdown buzilmaydi ──────────────
h = m._thinking_html_for("search", 6, "«a & b»")
assert h.startswith("<tg-thinking>") and "«a &amp; b» · 6s" in h and "<br/>" in h, h
assert "<br/>" not in m._thinking_html_for("text", 1), "bo'sh 2-qator — bo'sh joy yo'q"
p = m._thinking_plain_for("search", 6, "«snake_case*»")
assert p.count("*") == 2 and "_" not in p, p
g = guest._guest_status_md("ob_havo", 6, "Samarqand")
assert "**Ob-havoni tekshiryapman" in g and "_Samarqand · 6s_" in g, g
assert guest._guest_thinking_html("text", 1) == m._thinking_html_for("text", 1)
print("[5] HTML / Markdown / guest bitta kadrdan, maxsus belgi buzmaydi OK")

# ── 6) Tool → status: nomi bor HAR tool o'z statusini oladi ──────────
assert all(v in T for v in ai._TOOL_HOLATI.values()), ai._TOOL_HOLATI


class Ev:
    def __init__(self, type_, item=None):
        self.type, self.item, self.delta = type_, item, None


class It:
    def __init__(self, name):
        self.type, self.name, self.arguments, self.call_id = "function_call", name, "{}", "c"


async def birinchi_status(nom: str) -> str:
    class S:
        def __aiter__(self):
            async def g():
                yield Ev("response.output_item.added", It(nom))
            return g()

    async def ochuvchi(stack, models, **kw):
        return S(), "soxta"

    async def bosh(*a, **k):
        return []

    async def xotira(*a, **k):
        return [], None

    asl = (ai._open_response_stream, ai.safe_get_chat_history, ai._memory_context)
    ai._open_response_stream, ai.safe_get_chat_history, ai._memory_context = ochuvchi, bosh, xotira
    gen = ai.get_openai_reply(1, "salom", user_id=7, output_files=[], is_pro=True)
    try:
        async for c in gen:
            if c.startswith("[STATUS]"):
                return c
        return ""
    finally:
        await gen.aclose()
        ai._open_response_stream, ai.safe_get_chat_history, ai._memory_context = asl


async def tool_holatlari():
    natija = {nom: await birinchi_status(nom) for nom in INTERNAL_TOOL_NAMES}
    yolgon = [n for n, s in natija.items()
              if n != "internet_search" and s in ("[STATUS]search", "")]
    assert not yolgon, f"«Qidiryapman» deb yolg'on gapiradigan toollar: {yolgon}"
    assert natija["internet_search"] == "[STATUS]search", natija
    assert natija["ob_havo"] == "[STATUS]ob_havo" and natija["edit_image"] == "[STATUS]image_edit"
    for s in natija.values():
        assert s[len("[STATUS]"):] in T, s
    return len(natija)

print(f"[6] {asyncio.run(tool_holatlari())} ta tool — hammasi o'z statusida OK")

# ── 7) 2-qator signali: faqat foydalanuvchi so'ragani ────────────────
th = ai._holat_tafsiloti
assert th("ob_havo", {"joy": "Samarqand"}) == "[STATUS]ob_havo|Samarqand"
assert th("namoz_vaqti", {"joy": "Namangan"}) == "[STATUS]namoz|Namangan"
assert th("valyuta", {"kodlar": ["USD", "EUR"]}) == "[STATUS]valyuta|USD, EUR"
assert th("valyuta", {"kodlar": "USD"}) is None, "ro'yxat emas — model chiqishi ishonchsiz"
assert th("internet_search", {"primary_query": "dollar | kursi"}) == "[STATUS]search|«dollar   kursi»"
assert th("internet_search", {"url": "https://www.kun.uz/x"}) == "[STATUS]manbalar|kun.uz"
assert th("internet_search", {}) is None and th("find_nearby", {"categories": ["a=b"]}) is None
assert th("ob_havo", "buzuq") is None
d = ai._domenlar("https://www.kun.uz/1 https://kun.uz/2 https://gazeta.uz/3 "
                 "https://uz.wikipedia.org/4")
assert d == "kun.uz, gazeta.uz", d
print("[7] tafsilot signallari to'g'ri, butun sayt nomlari OK")


# ── 8) Oqimda: «image» so'zi rasm statusini yoqmaydi, research o'zida ─
class Chat:
    id, type = 111, "private"


class Msg:
    chat, message_id, message_thread_id = Chat(), 42, None

    async def answer(self, text, **kw):
        return self


async def oqim(chunks, content_type="text"):
    kadrlar = []

    async def draft(chat_id, draft_id, *, markdown=None, html_content=None, **kw):
        if html_content:
            kadrlar.append(__import__("html").unescape(html_content))
        return {"ok": True}

    async def rich(chat_id, **kw):
        return {"message_id": 1}

    async def gen():
        for c in chunks:
            if isinstance(c, float):
                await asyncio.sleep(c)
            else:
                yield c

    asl = (m._send_rich_draft, m._send_rich_message)
    m._send_rich_draft, m._send_rich_message = draft, rich
    try:
        await m.process_stream_draft(Msg(), gen(), content_type=content_type)
    finally:
        m._send_rich_draft, m._send_rich_message = asl
    return kadrlar


async def oqim_sinovi():
    k = await oqim(["[STATUS]search", "[STATUS]search|«image editor»", 1.4, "Javob."])
    oxirgi = k[-1]
    assert "Qidiryapman" in oxirgi and "«image editor»" in oxirgi, k
    assert not any("G'oyani" in x for x in k), "so'rovdagi «image» rasm statusini yoqdi"
    k = await oqim(["[STATUS]search|«yangi tadqiqot»", 1.4, "Javob."], "research")
    assert "Reja tuzyapman" in k[-1] and "«yangi tadqiqot»" in k[-1], k
    k = await oqim(["[STATUS]ob_havo", "[STATUS]ob_havo|Samarqand", 1.4, "Javob."])
    assert "Ob-havoni tekshiryapman" in k[-1] and "Samarqand" in k[-1], k
    # 2,6 s dan keyin «O'ylayapman» (2-bosqich); keyin qidiruv — u O'Z
    # birinchi bosqichidan boshlanadi, «solishtiryapman» dan emas.
    k = await oqim([2.7, "[STATUS]manbalar|kun.uz", 0.9, "Javob."])
    assert any("O'ylayapman" in x for x in k), k
    assert "Manbalarni o'qiyapman" in k[-1], k

asyncio.run(oqim_sinovi())
print("[8] oqimda tur to'g'ri ajratildi, yangi tur boshidan, research o'z holatida OK")

# ── 9) ai.py tool ISHLAYOTGANDA 2-qator signalini yuboradi ───────────
async def toliq(chaqiruv, args):
    raundlar = [[Ev("response.output_item.added", It(chaqiruv)),
                 Ev("response.output_item.done", It(chaqiruv))], []]
    raundlar[0][0].item.arguments = raundlar[0][1].item.arguments = json.dumps(args)

    class S:
        def __init__(self, ev): self.ev = ev
        def __aiter__(self):
            async def g():
                for e in self.ev:
                    yield e
            return g()
        async def get_final_response(self):
            class F: status, incomplete_details, usage = "completed", None, None
            return F()

    async def ochuvchi(stack, models, **kw):
        return S(raundlar.pop(0) if raundlar else []), "soxta"

    async def bosh(*a, **k): return []
    async def xotira(*a, **k): return [], None
    async def qidiruv(**k): return "https://www.kun.uz/a https://gazeta.uz/b matn"
    async def obhavo(args, vidjet_out): return "quyoshli"

    nomlar = ("_open_response_stream", "safe_get_chat_history", "_memory_context",
              "multi_source_deep_search", "_run_obhavo_task")
    asl = {n: getattr(ai, n) for n in nomlar}
    for n, f in zip(nomlar, (ochuvchi, bosh, xotira, qidiruv, obhavo)):
        setattr(ai, n, f)
    try:
        return [c async for c in ai.get_openai_reply(
            1, "salom", user_id=7, output_files=[], is_pro=True)]
    finally:
        for n, f in asl.items():
            setattr(ai, n, f)


async def signal_sinovi():
    c = await toliq("ob_havo", {"joy": "Samarqand"})
    assert "[STATUS]ob_havo|Samarqand" in c, c
    c = await toliq("internet_search", {"primary_query": "dollar kursi"})
    assert "[STATUS]search|«dollar kursi»" in c and "[STATUS]manbalar|kun.uz, gazeta.uz" in c, c
    assert c.index("[STATUS]search|«dollar kursi»") < c.index("[STATUS]manbalar|kun.uz, gazeta.uz")

asyncio.run(signal_sinovi())
print("[9] tool ishlayotganda so'rov, keyin o'qilgan saytlar yuborildi OK")

# ── 10) Signal o'qish (oddiy bot + guest) va guest 2-qatori ──────────
assert m.holat_signali("[STATUS]search|«image editor»") == ("search", "«image editor»")
assert m.holat_signali("[STATUS]search") == ("search", "")
assert m.holat_signali("[STATUS]yoq|x") is None
assert guest.holat_signali is m.holat_signali, "guest o'z nusxasini yasamasin"
kadrlar = []


async def guest_sinovi():
    stop = asyncio.Event()

    async def tahrir(text, html):
        kadrlar.append(html)
        stop.set()
        return False
    await asyncio.wait_for(guest._run_guest_status_animator(
        tahrir, lambda: ("ob_havo", "Andijon"), stop, interval=0.01, rich=True), 2)

asyncio.run(guest_sinovi())
assert "Ob-havoni tekshiryapman" in kadrlar[0] and "Andijon" in kadrlar[0], kadrlar
print("[10] signal bitta funksiyada o'qiladi, guest 2-qatorni ko'rsatadi OK")

print("\nstatus_matn: barcha tekshiruvlar o'tdi (10/10).")
