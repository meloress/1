"""Uzun javob YO'QOLMASLIGI kerak.
Ishga tushirish: python tests/test_long_reply.py

MUAMMO TARIXI: MAX_OUTPUT_TOKENS = 16000, ya'ni javob 15-20 ming belgi
bo'lishi mumkin, Telegram esa bitta xabarga 4096 belgi beradi. Bo'lish
umuman yo'q edi va yakuniy yuborishda faqat BITTA Markdown urinishi bor
edi — u rad etilsa javob izsiz yo'qolardi: foydalanuvchi 40 soniya
animatsiyani ko'rib, oxirida bo'sh ekran bilan qolardi.

Bu yerdagi eng muhim tekshiruv — 5-band: rich yo'l ham, Markdown ham
yiqilganda matn BARIBIR yetib borishi.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio

from handlers import messages as m


# ── Soxta Telegram xabari ────────────────────────────────────────────
class FakeChat:
    def __init__(self, chat_type="private"):
        self.id = 111
        self.type = chat_type


class FakeSent:
    """message.answer() qaytaradigan xabar — tahrirlash ham shu qoidalar bo'yicha."""
    def __init__(self, text, owner):
        self.text = text
        self.message_id = 999
        self._owner = owner

    async def edit_text(self, text, **kwargs):
        self._owner._check(kwargs.get("parse_mode"))
        self._owner.sent.append(("edit", text, kwargs.get("parse_mode")))
        self.text = text
        return self


class FakeMessage:
    def __init__(self, chat_type="private", reject_markdown=False, reject_all=False):
        self.chat = FakeChat(chat_type)
        self.message_id = 42
        self.message_thread_id = None
        self.sent = []          # ("answer"|"edit", matn, parse_mode)
        self.reject_markdown = reject_markdown
        self.reject_all = reject_all

    def _check(self, parse_mode):
        if self.reject_all:
            raise RuntimeError("Telegram rad etdi")
        if self.reject_markdown and parse_mode == "Markdown":
            raise RuntimeError("can't parse entities")

    async def answer(self, text, **kwargs):
        parse_mode = kwargs.get("parse_mode")
        self._check(parse_mode)
        self.sent.append(("answer", text, parse_mode))
        return FakeSent(text, self)

    def delivered(self) -> list[str]:
        """Foydalanuvchi haqiqatda ko'rgan matnlar (status ramkalarisiz)."""
        return [t for _, t, _ in self.sent if set(t.strip()) <= set("ABC…")]


async def _gen(chunks):
    for c in chunks:
        # Son berilsa — shuncha soniya "o'ylanadi". Animatorga ish
        # berish uchun kerak: u draft yiqilganini FAQAT bir necha
        # ping'dan keyin aniqlaydi va zaxira kutish xabarini o'sha
        # yerda yasaydi (haqiqiy hayotdagidek).
        if isinstance(c, (int, float)):
            await asyncio.sleep(c)
            continue
        yield c


async def run_stream(message, chunks, *, rich_ok):
    """process_stream_draft'ni soxta muhitda ishga tushiradi."""
    real_rich = m._send_rich_message
    real_api = m._telegram_api_request
    rich_calls = []

    async def fake_rich(chat_id, **kwargs):
        rich_calls.append(kwargs.get("markdown"))
        return {"message_id": 1} if rich_ok else None

    async def fake_api(method, payload):
        return None          # draft/animatsiya yo'li o'chiq

    m._send_rich_message = fake_rich
    m._telegram_api_request = fake_api
    try:
        text = await m.process_stream_draft(message, _gen(chunks))
    finally:
        m._send_rich_message = real_rich
        m._telegram_api_request = real_api
    return text, rich_calls


class FakeBot:
    """`bot.delete_message` uchun — testda tarmoqqa chiqmaslik kerak."""
    def __init__(self):
        self.deleted = []

    async def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)


async def main():
    LIMIT = m.MAX_PLAIN_CHARS
    real_bot, m.bot = m.bot, FakeBot()
    try:
        await _checks(LIMIT)
    finally:
        m.bot = real_bot


async def _checks(LIMIT):

    # ── 1) Har bir bo'lak chegaraga sig'adi ─────────────────────────
    long_text = "\n\n".join(f"{i}-xat boshi. " + "so'z " * 120 for i in range(40))
    parts = m._split_for_telegram(long_text)
    assert len(parts) > 1, "uzun matn bo'linishi kerak"
    assert all(len(p) <= LIMIT for p in parts), [len(p) for p in parts]
    print(f"[1] {len(long_text)} belgi {len(parts)} ta bo'lakka bo'lindi, hammasi <= {LIMIT} OK")

    # ── 2) Matn yo'qolmaydi ────────────────────────────────────────
    joined = " ".join(parts).split()
    assert joined == long_text.split(), "bo'lishda so'zlar yo'qoldi yoki takrorlandi"
    print("[2] bo'lishda birorta so'z yo'qolmadi OK")

    # ── 3) Chegarasiz matn ham qattiq kesiladi (cheksiz sikl yo'q) ──
    parts = m._split_for_telegram("x" * (LIMIT * 2 + 5))
    assert len(parts) == 3, len(parts)
    assert all(len(p) <= LIMIT for p in parts)
    print("[3] chegarasiz (bo'shliqsiz) matn ham kesildi OK")

    # ── 4) Kod bloki bo'lak chegarasida yopiladi va qayta ochiladi ──
    code = "```python\n" + "print('salom')\n" * 700 + "```"
    parts = m._split_for_telegram(code)
    assert len(parts) > 1
    for i, p in enumerate(parts):
        assert p.count("```") % 2 == 0, f"{i}-bo'lakda kod bloki ochiq qoldi"
    assert parts[1].startswith("```python"), (
        f"keyingi bo'lak kod blokini tiklashi kerak: {parts[1][:30]!r}")
    print("[4] kod bloki bo'laklar orasida buzilmadi OK")

    # ═══════════════════════════════════════════════════════════════
    # 5) ENG MUHIM: rich ham, Markdown ham rad etsa — matn YETIB BORADI
    # ═══════════════════════════════════════════════════════════════
    msg = FakeMessage(reject_markdown=True)
    text, _ = await run_stream(msg, ["A" * 5000], rich_ok=False)
    delivered = msg.delivered()
    assert delivered, (
        "KRITIK: rich va Markdown yiqilganda javob UMUMAN yuborilmadi — "
        "parse_mode'siz ikkinchi urinish shart"
    )
    assert all(pm is None for _, t, pm in msg.sent if t in delivered), (
        "yetkazilgan matn Markdown'siz yuborilishi kerak edi")
    assert sum(len(p) for p in delivered) >= 5000, (
        f"matnning bir qismi yo'qoldi: {sum(len(p) for p in delivered)} < 5000")
    print("[5] rich + Markdown rad etilganda ham javob to'liq yetib bordi OK")

    # ── 6) Rich xabarga 9000 belgi BITTA bo'lib sig'adi ────────────
    # Ilgari chegara 4000 edi va bu javob UCHTA xabarga bo'linardi. Har
    # bo'linish — kod bloki va markdown havolasi uchun xavf, shuning
    # uchun rich yo'lda 32768 chegarasi ishlatiladi.
    msg = FakeMessage()
    text, rich_calls = await run_stream(msg, ["B" * 9000], rich_ok=True)
    assert len(rich_calls) == 1, f"9000 belgi bitta xabar bo'lishi kerak: {len(rich_calls)}"
    assert all(len(c) <= m.MAX_RICH_CHARS + 200 for c in rich_calls), [len(c) for c in rich_calls]
    print("[6] 9000 belgi bitta rich xabarga sig'di OK")

    # ── 7) Qisqa javob AVVALGIDEK bitta xabar bo'lib qoladi ────────
    msg = FakeMessage()
    text, rich_calls = await run_stream(msg, ["Salom, qalaysiz?"], rich_ok=True)
    assert len(rich_calls) == 1, rich_calls
    assert text == "Salom, qalaysiz?", text
    assert msg.sent == [], "qisqa javobda zaxira yo'liga tushmasligi kerak"
    print("[7] qisqa javob yo'li o'zgarmadi OK")

    # ── 8) Hamma yo'l yiqilsa ham oqim yiqilmaydi (istisno chiqmaydi) ─
    msg = FakeMessage(reject_all=True)
    text, _ = await run_stream(msg, ["C" * 6000], rich_ok=False)
    assert text.startswith("C"), "matn baribir qaytarilishi kerak (tarixga yoziladi)"
    print("[8] hamma kanal yiqilganda ham istisno ko'tarilmadi OK")

    # ═══════════════════════════════════════════════════════════════
    # 9) FAYL VAZIFASIDA BITTA XABAR — oraliq xabar YO'Q
    #
    # Fayl tayyorlanayotganda ekranda faqat status turadi. Tool'dan
    # oldingi matn [CLEAR_TEXT] bilan tashlanadi, foydalanuvchi esa
    # yakuniy javobni BIR MARTA oladi.
    # ═══════════════════════════════════════════════════════════════
    msg = FakeMessage()
    text, rich_calls = await run_stream(msg, [
        "Taqdimot tayyorlayapman, biroz kuting.",
        "[STATUS]file_task",
        "[CLEAR_TEXT]",
        "Tayyor — faylni yubordim.",
    ], rich_ok=True)
    assert len(rich_calls) == 1, f"bitta xabar kutilgan edi: {rich_calls}"
    assert "biroz kuting" not in rich_calls[0], (
        "tool'dan oldingi matn ekranga chiqmasligi kerak")
    assert text.strip() == "Tayyor — faylni yubordim.", text
    print("[9] fayl vazifasida faqat yakuniy javob yuborildi OK")

    # ═══════════════════════════════════════════════════════════════
    # 10) "⏳ Javob tayyorlanmoqda..." xabari OSILIB QOLMAYDI
    #
    # Draft yiqilganda o'rniga oddiy kutish xabari yaratiladi va unga
    # yarim javob yoziladi ("...12 sl ✍️"). Yakuniy javob rich yo'l bilan
    # ketsa, o'sha yarim xabar chatda o'sha holida qolib ketardi.
    # ═══════════════════════════════════════════════════════════════
    m.bot.deleted.clear()
    msg = FakeMessage()
    text, rich_calls = await run_stream(msg, [1.6, "D" * 200], rich_ok=True)
    kutish = [t for _, t, _ in msg.sent
              if "tayyorlanmoqda" in t or "tahlil" in t or "kuting" in t]
    assert kutish, "zaxira kutish xabari yaratilmagan — test sharti buzilgan"
    assert m.bot.deleted == [999], (
        f"yarim qolgan kutish xabari o'chirilmadi: {m.bot.deleted}")
    print("[10] osilib qolgan kutish xabari o'chirildi OK")

    # ═══════════════════════════════════════════════════════════════
    # 11) MARKDOWN HAVOLASI BO'LAKLAR ORASIDA BUZILMAYDI
    #
    # Jonli nosozlik: manbalar ro'yxati aynan havola ichida bo'lingan va
    # foydalanuvchi bitta xabarda «• [OLX», keyingisida
    # «Uzbekistan](https://...)» degan buzuq matnni ko'rgan.
    # ═══════════════════════════════════════════════════════════════
    havola = "[OLX Uzbekistan](https://www.olx.uz/d/obyavlenie/h5-ID4lE3l.html)"
    uzun = "x" * (LIMIT - 40) + " " + havola + " oxirgi so'z"
    bolaklar = m._split_for_telegram(uzun)
    assert len(bolaklar) == 2, len(bolaklar)
    assert any(havola in b for b in bolaklar), (
        f"havola ikkiga bo'lingan: {[b[-60:] for b in bolaklar]}")
    print("[11] markdown havolasi bo'laklar orasida buzilmadi OK")

    # ═══════════════════════════════════════════════════════════════
    # 11a) IZOH HAVOLASI VA TA'RIFI BIR XABARDA QOLADI
    #
    # `[^1]` matn ichida, `[^1]: ...` esa javob OXIRIDA turadi. Bo'linish
    # ularni ajratsa, birinchi xabardagi havola HECH QAYERGA olib
    # bormaydi. Kesish nuqtasi juftlikdan oldinga suriladi.
    # ═══════════════════════════════════════════════════════════════
    izohli = ("so'z " * ((LIMIT - 100) // 5)
              + "Muhim da'vo[^1] va uning davomi. " + "yana " * 40
              + "\n\n[^1]: Manba — Wikipedia")
    bolaklar = m._split_for_telegram(izohli)
    assert len(bolaklar) == 2, len(bolaklar)
    tarifli = [b for b in bolaklar if "[^1]: Manba" in b]
    assert len(tarifli) == 1, [b[-80:] for b in bolaklar]
    assert "da'vo[^1]" in tarifli[0], (
        f"havola ta'rifidan ajralib qoldi: {[b[-80:] for b in bolaklar]}")
    print("[11a] izoh havolasi va ta'rifi bir xabarda qoldi OK")

    # ── 12) Rich chegarasidan ham uzun javob bo'linadi ─────────────
    msg = FakeMessage()
    text, rich_calls = await run_stream(msg, ["B" * 40000], rich_ok=True)
    assert len(rich_calls) == 2, f"40000 belgi 2 ta xabar: {len(rich_calls)}"
    assert all(len(c) <= m.MAX_RICH_CHARS + 200 for c in rich_calls), [len(c) for c in rich_calls]
    print("[12] rich chegarasidan uzun javob bo'lindi OK")

    # ═══════════════════════════════════════════════════════════════
    # 13) ENG XAVFLI HOLAT: rich rad etilganda BO'LAK QAYTA BO'LINADI
    #
    # Bo'lak rich o'lchamida (30000 gacha) kesilgan. Zaxira yo'li esa
    # oddiy xabar — 4096. Qayta bo'lish unutilsa, rich rad etilgan uzun
    # javob BUTUNLAY yo'qoladi. Bu 5-tekshiruvning uzun varianti.
    # ═══════════════════════════════════════════════════════════════
    msg = FakeMessage(reject_markdown=True)
    text, _ = await run_stream(msg, ["A" * 30000], rich_ok=False)
    delivered = msg.delivered()
    assert delivered, "KRITIK: uzun javob zaxira yo'lida umuman yuborilmadi"
    assert all(len(t) <= m.MAX_PLAIN_CHARS for t in delivered), (
        f"oddiy xabar 4096 dan oshdi: {[len(t) for t in delivered]}")
    assert sum(len(t) for t in delivered) >= 30000, (
        f"matnning bir qismi yo'qoldi: {sum(len(t) for t in delivered)} < 30000")
    print("[13] rich rad etilgan 30000 belgilik javob to'liq yetib bordi OK")

    # ═══════════════════════════════════════════════════════════════
    # 14) YANGI KONSTRUKTSIYALAR RAD ETILSA HAM JAVOB YETIB BORADI
    #
    # <details>, <aside>, <tg-map/> va premium emoji — hammasi Telegram
    # QABUL QILADI degan taxminga tayanadi. Taxmin noto'g'ri chiqsa
    # (teg shakli boshqa, obuna tugagan) Telegram BUTUN xabarni rad
    # etadi. Oxirgi pog'ona shu sababdan XOM matndan quriladi: unda
    # birorta ham teg yo'q, faqat belgilar oddiy matnga o'giriladi.
    # ═══════════════════════════════════════════════════════════════
    xom = ("Toshkent 🤖 haqida.\n\n"
           "[batafsil: Texnik]\n- aholi: 3 mln\n[/batafsil]\n\n"
           "[iqtibos: Shahar tinch | Kimdir]\n\n[xarita:41.3111,69.2797,14]")
    msg = FakeMessage(reject_markdown=True)
    await run_stream(msg, [xom], rich_ok=False)
    yetkazilgan = " ".join(t for _, t, _ in msg.sent
                           if "tayyorlanmoqda" not in t)
    for teg in ("<details", "<aside", "<tg-map", "tg://emoji",
                "[batafsil", "[/batafsil]", "[iqtibos", "[xarita"):
        assert teg not in yetkazilgan, f"zaxira xabarda {teg} qoldi:\n{yetkazilgan}"
    for soz in ("Toshkent", "aholi: 3 mln", "Shahar tinch"):
        assert soz in yetkazilgan, f"matn yo'qoldi ({soz}):\n{yetkazilgan}"
    print("[14] rich rad etilganda yangi konstruktsiyalar oddiy matnga tushdi OK")

    print("\nlong_reply: barcha tekshiruvlar o'tdi (15/15).")


if __name__ == "__main__":
    asyncio.run(main())
