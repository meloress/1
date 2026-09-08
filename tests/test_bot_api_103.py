"""Bot API 10.3 imkoniyatlari uchun tekshiruvlar.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_bot_api_103.py

Tarmoqqa ham, bazaga ham murojaat qilmaydi — hamma tashqi chaqiruv
o'rniga soxta (fake) funksiya qo'yiladi.
"""
import asyncio
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.config import MAX_MANUAL_RETRIES
from handlers import messages as msg
from handlers import pro as pro_module
from handlers import digest as digest_module
from handlers.helpers import make_retry_keyboard
import services.ai as ai_module
from services.ai import (
    build_rich_markdown, embed_images, strip_image_tokens,
    format_image_catalog, _content_size,
)

failures = []


def check(n, label, cond):
    if cond:
        print(f"[{n}] {label} OK")
    else:
        print(f"[{n}] {label} XATO")
        failures.append(label)


# ─────────────────────────────────────────────────────────────
# 1-3. O'CHIRILGAN TUGMALAR (disabled)
# ─────────────────────────────────────────────────────────────
b = pro_module.btn("Tugagan", "retry:1", disabled=True)
dump = b.model_dump(exclude_none=True)
check(1, "disabled tugmada callback_data YO'Q",
      dump.get("disabled") == {} and "callback_data" not in dump and "url" not in dump)

normal = pro_module.btn("Oddiy", "pro:open", style=pro_module.BTN_SUCCESS)
check(2, "oddiy tugma o'zgarmagan",
      normal.model_dump(exclude_none=True).get("callback_data") == "pro:open")

kb = InlineKeyboardMarkup(inline_keyboard=[[b, normal]], force_reply=True)
down = pro_module._downgrade_kb(kb)
down_dump = down.model_dump(exclude_none=True)
check(3, "_downgrade_kb disabled va force_reply'ni saqlaydi",
      down_dump["inline_keyboard"][0][0].get("disabled") == {}
      and "callback_data" not in down_dump["inline_keyboard"][0][0]
      and down_dump.get("force_reply") is True
      and down_dump["inline_keyboard"][0][1].get("callback_data") == "pro:open")


# ─────────────────────────────────────────────────────────────
# 4-6. RICH XABAR ICHIDAGI TUGMALAR
# ─────────────────────────────────────────────────────────────
rb = pro_module.rich_button("A & B <x>", type="copy_text", text='say "hi" & <b>')
check(4, "rich_button HTML qochiriladi",
      "&amp;" in rb and "&lt;x&gt;" in rb and "&quot;" in rb and "<b>" not in rb)

row = pro_module.rich_button_row([pro_module.rich_button(f"b{i}", type="callback_data",
                                                         data=str(i))
                                  for i in range(12)], align="right")
check(5, "rich_button_row 8 tadan ortig'ini kesadi",
      row.count("<tg-button ") == 8 and 'align="right"' in row)

check(6, "bo'sh qator bo'sh satr qaytaradi", pro_module.rich_button_row([]) == "")

# 6a) KO'P QATORLI NUSXA MATNI — jonli nosozlik.
# Xom `\n` atribut ichida tegni uzib qo'yardi va foydalanuvchi tugma
# o'rniga `<tg-button type="copy_text" text="...">` degan XOM MATNNI
# ko'rardi. Nusxa olingan matn esa haqiqiy qator ajratuvchi bilan
# qaytishi shart — aks holda ko'chirilgan kod ishlamaydi.
kod = 'a = int(input("son: "))\nb = 2\n\nprint(a + b)'
mb = pro_module.rich_button("Nusxa", type="copy_text", text=kod)
check("6a", "ko'p qatorli nusxa matni tegni buzmaydi",
      "\n" not in mb and "&#10;" in mb)
_val = mb.split('text="')[1].split('"')[0]
check("6b", "nusxa olingan matn qator ajratuvchini saqlaydi",
      html.unescape(_val) == kod)


# ─────────────────────────────────────────────────────────────
# 7-9. "NUSXA OLISH" TUGMASI
# ─────────────────────────────────────────────────────────────
one_block = "Mana kod:\n```python\nprint(1)\n```\nTayyor."
_one = msg._copy_button_html(one_block)
check(7, "bitta qisqa kod bloki → tugma", "copy_text" in _one)

# Tugma YOZUVSIZ, faqat ikonka. Bo'sh yorliq esa mumkin emas — Telegram
# matnsiz tugmani qabul qilmaydi va BUTUN xabarni rad etadi.
_yorliq = _one.split(">")[2].split("<")[0]
check("7a", "nusxa tugmasi faqat ikonka (yozuvsiz, lekin bo'sh emas)",
      _yorliq == "📋")

two_blocks = one_block + "\n```js\nlet a=1\n```\n"
check(8, "ikkita blok → tugma YO'Q", msg._copy_button_html(two_blocks) == "")

long_block = "```\n" + ("x" * (msg._COPY_TEXT_LIMIT + 10)) + "\n```"
check(9, "juda uzun blok → tugma YO'Q", msg._copy_button_html(long_block) == "")


# ─────────────────────────────────────────────────────────────
# 10-14. INTERNETDAN RASM
# ─────────────────────────────────────────────────────────────
imgs = [
    {"url": "https://a.example/1.jpg", "title": "M5 CS old", "source": "a.example"},
    {"url": "https://a.example/2.jpg", "title": "M5 CS salon", "source": "a.example"},
]
out = embed_images("Old ko'rinishi [rasm:1] mana.", imgs)
check(10, "[rasm:N] media blokiga aylanadi",
      "![](https://a.example/1.jpg" in out and "[rasm:1]" not in out)

# 2-4 rasm — KOLLAJ (hammasi bir ekranda), 5+ — slideshow (surib
# ko'riladi). Kollajda sarlavha bitta, shuning uchun manbalar bitta
# <figcaption> ga yig'iladi: rasm o'zganiki, manba MAJBURIY.
gal = embed_images("Galereya: [rasmlar]", imgs)
check(11, "2 rasm kollajga yig'iladi, manba figcaption'da",
      "<tg-collage>" in gal and "<tg-slideshow>" not in gal
      and gal.count("![](") == 2
      and "<figcaption>Manba: a.example</figcaption>" in gal)

ko_p = imgs + [{"url": f"https://a.example/{n}.jpg", "title": f"M5 {n}",
                "source": "b.example"} for n in range(3, 6)]
gal5 = embed_images("Galereya: [rasmlar]", ko_p)
check("11a", "5 rasm slideshow bo'lib qoladi (kollajda juda mayda)",
      "<tg-slideshow>" in gal5 and "<tg-collage>" not in gal5
      and gal5.count("![](") == 5)

yakka = embed_images("Galereya: [rasmlar]", imgs[:1])
check("11b", "bitta rasm yakka blok bo'lib qoladi",
      "<tg-collage>" not in yakka and "<tg-slideshow>" not in yakka
      and yakka.count("![](") == 1 and "M5 CS old" in yakka)

bad = embed_images("Yo'q rasm [rasm:9] oxiri", imgs)
check(12, "mavjud bo'lmagan raqam jimgina o'chiriladi",
      "[rasm:9]" not in bad and "9" not in bad.replace("https://", ""))

check(13, "rasm topilmasa belgilar matnda qolmaydi",
      "[rasm:1]" not in embed_images("aaa [rasm:1] bbb", [])
      and strip_image_tokens("x [rasmlar] y").strip() == "x  y".strip())

catalog = format_image_catalog(imgs)
check(14, "katalogda URL YO'Q (token tejash)",
      "https://" not in catalog and "[rasm:1]" in catalog and "[rasm:2]" in catalog)

# 14a-14c) RASM QIDIRUVI SO'ROVGA MOS BO'LSIN.
# Jonli nosozlik: serverda DuckDuckGo rasm API'si 403 qaytaradi va ddgs
# Bing'ga o'tadi — natijalar esa so'rovga MUTLAQO aloqasiz bo'lishi mumkin.
# «Hongqi H5 Classic rasmini yubor» so'roviga fandom saytidagi multfilm
# fanarti kelgan, taqdimotga esa mavzuga aloqasiz suratlar tushgan.
check("14a", "veb so'rovi rasm qidiruvi uchun tozalanadi (YIL saqlanadi)",
      ai_module.image_query(
          "site:weforum.org Future of Jobs Report 2025 AI jobs 170 million"
      ) == "Future of Jobs Report 2025 AI jobs million")

_tok = ai_module._query_tokens("Hongqi H5 Classic")
check("14b", "mos rasm o'tadi",
      ai_module._image_relevant(_tok, {
          "title": "2022 Hongqi H5 Classic Walkaround",
          "url": "https://i.ytimg.com/x.jpg", "source": "youtube.com"}))
check("14c", "aloqasiz rasm TASHLANADI (rasmsiz — aloqasizdan yaxshiroq)",
      not ai_module._image_relevant(_tok, {
          "title": "Here's the Neverseen Fanart Version",
          "url": "https://lost-cities-keeper.fandom.com/a.png",
          "source": "fandom.com"}))

# 14d-14f) TAKRORIY RASM SO'ROVI ISHLASHI KERAK.
# Jonli nosozlik: "rasm yubor" -> keldi; "yana yubor" / "yangi modelini
# ko'rsat" -> rasm o'rniga havola yoki hech narsa. Uch sabab bor edi.
#
# 14d — [rasm:N] TARIXGA yozilardi. Keyingi so'rovda katalog yo'q, model esa
#       belgini tirik deb o'ylab qidiruvni chaqirmay yana [rasm:1] yozardi;
#       embed_images() uni indamay o'chirardi -> bo'sh javob.
_yozilgan: list = []


async def _fake_update(chat_id, content, role="user"):
    _yozilgan.append((role, content))


_asl_update = ai_module.update_chat_history
ai_module.update_chat_history = _fake_update
try:
    asyncio.run(ai_module.safe_update_history(
        1, "Mana Hongqi H5 [rasm:1] va yana [rasmlar]", role="assistant"))
    asyncio.run(ai_module.safe_update_history(1, "[rasm:1]", role="assistant"))
finally:
    ai_module.update_chat_history = _asl_update

check("14d", "[rasm:N] tarixga TUSHMAYDI",
      len(_yozilgan) == 1
      and "[rasm:" not in _yozilgan[0][1]
      and "[rasmlar]" not in _yozilgan[0][1]
      and "Hongqi H5" in _yozilgan[0][1])

# 14e — Commons SO'ZMA-SO'Z qidiradi. Ilgari faqat 3 so'zga qisqartirilardi,
#       ya'ni «Hongqi H5 new model» -> «Hongqi H5 new» — bu ham bo'sh
#       qaytardi va foydalanuvchi rasmsiz qolardi. Endi 2 so'zgacha tushadi.
#
#       ⚠️ QISQARTIRISH ENDI OXIRGI CHORA: u faqat IKKALA manba ham
#       (Commons va ddgs) bo'sh qaytargandagina ishlaydi. Shuning uchun
#       bu yerda ddgs ham bo'sh qilib qo'yiladi — aks holda test tarmoqqa
#       chiqib, tasodifiy natijaga bog'liq bo'lib qolardi.
_sorovlar: list = []


def _fake_commons(q, n):
    _sorovlar.append(q)
    return [{"url": "https://upload.wikimedia.org/a.jpg",
             "title": q, "source": "commons"}] if len(q.split()) == 2 else []


_asl_commons = ai_module._commons_images_sync
_asl_ddg = ai_module._ddg_images_sync
ai_module._commons_images_sync = _fake_commons
ai_module._ddg_images_sync = lambda q, n: []
try:
    _natija = ai_module._images_sync("Hongqi H5 new model", 4)
finally:
    ai_module._commons_images_sync = _asl_commons
    ai_module._ddg_images_sync = _asl_ddg

check("14e", "topilmasa so'rov 3, keyin 2 so'zga qisqaradi",
      _sorovlar == ["Hongqi H5 new model", "Hongqi H5 new", "Hongqi H5"]
      and len(_natija) == 1)

# 14f — model rasm o'rniga HAVOLA berardi. Katalog buni aniq taqiqlaydi.
check("14f", "katalog havola berishni taqiqlaydi va belgi bir martaligini aytadi",
      "URL YOZMANG" in catalog and "HAVOLA" in catalog
      and "FAQAT shu javob uchun" in catalog)

check(15, "Content-Range'dan haqiqiy hajm o'qiladi",
      _content_size({"Content-Range": "bytes 0-0/123456", "Content-Length": "1"}) == 123456
      and _content_size({"Content-Length": "42"}) == 42
      and _content_size({}) is None)


# ─────────────────────────────────────────────────────────────
# 16-19. RICH MARKDOWN: JADVAL VA MANBALAR
# ─────────────────────────────────────────────────────────────
table_md = "| A | B |\n|---|---|\n| **1** | `x` |\n"
res = build_rich_markdown(table_md)
check(16, "GFM jadvali <table compact> ga o'giriladi",
      "<table compact>" in res and "<b>1</b>" in res and "<code>x</code>" in res)

broken = "| A | B |\n|---|---|\n| faqat bitta |\n"
check(17, "ustunlar mos kelmasa jadvalga TEGILMAYDI",
      "<table" not in build_rich_markdown(broken))

code_pipe = "```python\na = 1 | 2\nb = '| x | y |'\n```"
check(18, "kod bloki ichidagi `|` jadval deb o'qilmaydi",
      "<table" not in build_rich_markdown(code_pipe))

src = ("Javob matni.\n\nManbalar:\n"
       "- [BMW](https://bmw.com/a)\n- [Kun.uz](https://kun.uz/b?x=1&y=2)\n")
res_src = build_rich_markdown(src)
check(19, "manbalar yig'iladigan sitataga o'raladi",
      "<blockquote" in res_src and "Manbalar (2 ta)" in res_src
      and 'href="https://bmw.com/a"' in res_src and "&amp;" in res_src)

check(20, "bitta manba yig'ilmaydi (yashirishning ma'nosi yo'q)",
      "<blockquote" not in build_rich_markdown(
          "Javob.\n\nManbalar:\n- [BMW](https://bmw.com/a)\n"))

check(21, "o'rtadagi ro'yxat manba deb hisoblanmaydi",
      "<blockquote" not in build_rich_markdown(
          "Manbalar:\n- [A](https://a.com)\n- [B](https://b.com)\n\nDavomi bor."))


# ─────────────────────────────────────────────────────────────
# 22-24. TO'XTATISH TUGMASI
# ─────────────────────────────────────────────────────────────
check(22, "noma'lum draft uchun request_stop False qaytaradi",
      msg.request_stop(999_999_999) is False)


async def _stop_flow():
    """To'xtatish signali TIQILIB QOLGAN oqimni ham uzadimi?"""
    async def gen():
        yield "salom"
        await asyncio.sleep(60)     # qidiruv ketayotgan holat
        yield "hech qachon"

    it = gen().__aiter__()
    stop = asyncio.Event()

    chunk, stopped, finished = await msg._next_or_stop(it, stop)
    first_ok = (chunk == "salom" and not stopped and not finished)

    async def _press():
        await asyncio.sleep(0.05)
        stop.set()

    asyncio.create_task(_press())
    started = asyncio.get_event_loop().time()
    chunk2, stopped2, finished2 = await msg._next_or_stop(it, stop)
    elapsed = asyncio.get_event_loop().time() - started
    return first_ok, stopped2, finished2, elapsed


first_ok, stopped2, finished2, elapsed = asyncio.run(_stop_flow())
check(23, "oqimdan birinchi bo'lak normal o'qiladi", first_ok)
check(24, "tiqilib qolgan oqim 60s kutmasdan uziladi",
      stopped2 is True and finished2 is False and elapsed < 5)


async def _finish_flow():
    async def gen():
        yield "a"

    it = gen().__aiter__()
    stop = asyncio.Event()
    await msg._next_or_stop(it, stop)
    return await msg._next_or_stop(it, stop)


_, s_fin, f_fin = asyncio.run(_finish_flow())
check(25, "oqim tabiiy tugaganda finished=True", f_fin is True and s_fin is False)


# ─────────────────────────────────────────────────────────────
# 26-27. DRAFT PAYLOAD'IDA can_stop
# ─────────────────────────────────────────────────────────────
captured = {}


async def _fake_api(method, payload):
    captured["method"] = method
    captured["payload"] = payload
    return {"ok": True}


_real_api = msg._telegram_api_request
msg._telegram_api_request = _fake_api
try:
    asyncio.run(msg._send_rich_draft(1, 42, markdown="x", can_stop=True))
    check(26, "can_stop + keep_on_stop payloadga tushadi",
          captured["method"] == "sendRichMessageDraft"
          and captured["payload"].get("can_stop") is True
          and captured["payload"].get("keep_on_stop") is True)

    captured.clear()
    asyncio.run(msg._send_rich_draft(1, 42, markdown="x"))
    check(27, "can_stop=False bo'lsa maydonlar umuman yuborilmaydi",
          "can_stop" not in captured["payload"]
          and "keep_on_stop" not in captured["payload"])
finally:
    msg._telegram_api_request = _real_api


# ─────────────────────────────────────────────────────────────
# 28-29. EPHEMERAL (guruhda shaxsiy javob)
# ─────────────────────────────────────────────────────────────
class _Chat:
    def __init__(self, t):
        self.type = t


class _User:
    id = 777


class _Msg:
    def __init__(self, chat_type):
        self.chat = _Chat(chat_type)
        self.from_user = _User()


check(28, "shaxsiy chatda ephemeral QO'YILMAYDI",
      msg.ephemeral_params(_Msg("private")) == {})
check(29, "guruhda ephemeral qo'yiladi va oluvchi to'g'ri",
      msg.ephemeral_params(_Msg("supergroup"))
      == {"ephemeral_message_parameters": {"receiver_user_id": 777}})


# ─────────────────────────────────────────────────────────────
# 30-31. QAYTA URINISH VA DAYDJEST KLAVIATURALARI
# ─────────────────────────────────────────────────────────────
kb_live = make_retry_keyboard(1, attempts=0).model_dump(exclude_none=True)
kb_dead = make_retry_keyboard(1, attempts=MAX_MANUAL_RETRIES).model_dump(exclude_none=True)
check(30, "urinishlar tugagach tugma o'chiriladi",
      kb_live["inline_keyboard"][0][0].get("callback_data") == "retry:1"
      and kb_dead["inline_keyboard"][0][0].get("disabled") == {}
      and "callback_data" not in kb_dead["inline_keyboard"][0][0])

locked = digest_module._hours_keyboard(None, locked=True).model_dump(exclude_none=True)
hour_rows = [r for r in locked["inline_keyboard"]
             if all(btn_.get("text", "").strip("✅").isdigit() for btn_ in r)]
check(31, "bepul tarifda soat panjarasi ko'rinadi, lekin bosilmaydi",
      hour_rows and all(b.get("disabled") == {} for r in hour_rows for b in r)
      and any(b.get("callback_data") == "pro:open"
              for r in locked["inline_keyboard"] for b in r))


# ─────────────────────────────────────────────────────────────
# 32-34. NATIJA FAYLLARINI BITTA RICH XABARGA YIG'ISH
# ─────────────────────────────────────────────────────────────
mp_captured = {}


async def _fake_multipart(method, payload, files):
    mp_captured["method"] = method
    mp_captured["payload"] = payload
    mp_captured["files"] = files
    return {"message_id": 5}


_real_mp = msg._telegram_api_multipart
msg._telegram_api_multipart = _fake_multipart
try:
    single = asyncio.run(msg._send_output_files_rich(1, [("a.pdf", b"x")]))
    check(32, "bitta fayl uchun rich to'plam ISHLATILMAYDI", single is False)

    ok = asyncio.run(msg._send_output_files_rich(
        1, [("hisobot.pdf", b"pdf"), ("grafik.png", b"png")]))
    md = mp_captured["payload"]["rich_message"]["markdown"]
    media = mp_captured["payload"]["rich_message"]["media"]
    check(33, "2+ fayl bitta rich xabarga yig'iladi",
          ok is True
          and "tg://document?id=f0" in md and "tg://photo?id=f1" in md
          and [m["id"] for m in media] == ["f0", "f1"]
          and media[0]["media"]["media"] == "attach://f0"
          and set(mp_captured["files"]) == {"f0", "f1"})

    huge = [("a.bin", b"0" * 10), ("b.bin", b"0" * 10)]
    msg_max = msg.MAX_RICH_BUNDLE_SIZE
    msg.MAX_RICH_BUNDLE_SIZE = 5
    try:
        too_big = asyncio.run(msg._send_output_files_rich(1, huge))
    finally:
        msg.MAX_RICH_BUNDLE_SIZE = msg_max
    check(34, "hajm chegarasidan oshsa eski yo'lga qaytiladi", too_big is False)
finally:
    msg._telegram_api_multipart = _real_mp


# ─────────────────────────────────────────────────────────────
# 35-38. TAKROR XABARNING OLDINI OLISH
# ─────────────────────────────────────────────────────────────
# Rasmli rich xabarda Telegram har bir havolani O'ZI yuklab oladi va
# 10s'lik umumiy chegaradan oshib ketadi. Ilgari bu "yiqildi" deb
# hisoblanib, javob RASMSIZ qayta yuborilardi — foydalanuvchi bir xil
# javobni IKKI marta olardi (jonli sinovda kuzatilgan).
class _FakeResp:
    def __init__(self, status, data):
        self.status, self._data = status, data

    async def json(self, content_type=None):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, mode):
        self.mode, self.kwargs = mode, None

    def post(self, url, **kwargs):
        self.kwargs = kwargs
        if self.mode == "timeout":
            raise asyncio.TimeoutError()
        if self.mode == "rejected":
            return _FakeResp(400, {"ok": False, "description": "bad media"})
        return _FakeResp(200, {"ok": True, "result": {"message_id": 7}})


def _with_session(mode, coro_factory):
    session = _FakeSession(mode)

    async def fake_get_session():
        return session

    real = msg._get_http_session
    msg._get_http_session = fake_get_session
    try:
        return asyncio.run(coro_factory()), session
    finally:
        msg._get_http_session = real


out_ok: list = []
res, sess = _with_session("ok", lambda: msg._send_rich_message(
    1, markdown="x", outcome=out_ok))
check(35, "muvaffaqiyatda natija qaytadi, outcome bo'sh qoladi",
      res == {"message_id": 7} and out_ok == [])

out_rej: list = []
res, _ = _with_session("rejected", lambda: msg._send_rich_message(
    1, markdown="x", outcome=out_rej))
check(36, "Telegram ANIQ rad etsa — 'rejected' (qayta urinish xavfsiz)",
      res is None and out_rej == [msg.OUTCOME_REJECTED])

out_unk: list = []
res, _ = _with_session("timeout", lambda: msg._send_rich_message(
    1, markdown="x", outcome=out_unk))
check(37, "timeout — 'unknown' (xabar yetib borgan bo'lishi MUMKIN)",
      res is None and out_unk == [msg.OUTCOME_UNKNOWN])

_, sess_media = _with_session("ok", lambda: msg._send_rich_message(
    1, markdown="x", timeout=msg.RICH_MEDIA_TIMEOUT))
_, sess_plain = _with_session("ok", lambda: msg._send_rich_message(
    1, markdown="x"))
check(38, "rasmli xabarga uzunroq timeout beriladi, oddiysiga tegilmaydi",
      sess_media.kwargs.get("timeout") is not None
      and sess_media.kwargs["timeout"].total == msg.RICH_MEDIA_TIMEOUT
      and "timeout" not in sess_plain.kwargs)


# ─────────────────────────────────────────────────────────────
# 39. stopped_message_generation OBSERVER'DAN O'ZI TOPILADI
# ─────────────────────────────────────────────────────────────
# main.py'da allowed_updates endi qo'lda to'ldirilmaydi. Bu xavfsiz
# bo'lishi uchun aiogram observer'ga yozilgan handlerdan update turini
# O'ZI chiqara olishi shart — aks holda Telegram bu update'ni hech
# qachon yubormaydi va to'xtatish tugmasi jimgina ishlamay qo'yadi.
_dp = Dispatcher()


@_dp.stopped_message_generation()
async def _stop_handler(event):
    return None


check(39, "handler borligida resolve_used_update_types uni topadi",
      "stopped_message_generation" in _dp.resolve_used_update_types())


# ─────────────────────────────────────────────────────────────
print("─" * 55)
if failures:
    print(f"❌ {len(failures)} ta tekshiruv yiqildi:")
    for f in failures:
        print(f"   • {f}")
    sys.exit(1)
print("✅ Bot API 10.3 tekshiruvlari — hammasi o'tdi")
