"""Guest rejimda reply qilingan xabar konteksti va flood limit himoyasi.
Ishga tushirish: python tests/test_guest_reply.py

NEGA KERAK: guruhda bot a'zo emas va tarixni ko'rmaydi. Reply qilingan
xabar — botga yetib boradigan YAGONA kontekst. U yo'qolsa, foydalanuvchi
savolga reply qilib botni chaqirganda bot "nima haqida gap ketyapti?" deb
so'raydi va Guest Mode'ning eng tabiiy ishlatilishi buziladi.

12-13-band — HAQIQIY loglardan chiqqan xato: status animatsiyasi inline
xabarni juda tez tahrirlab 429 flood limitiga urdi va shu sabab YAKUNIY
JAVOB ham yuborilmay qoldi. Foydalanuvchi 35 soniya kutib hech narsa olmadi.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio

import handlers.guest as guest
from handlers.guest import (
    _quoted_context, _media_source, _detect_guest_content_type, _QUOTE_MAX_CHARS,
    _run_guest_status_animator, _edit_guest_inline_message,
)


class FakeUser:
    def __init__(self, full_name, is_bot=False):
        self.full_name = full_name
        self.is_bot = is_bot


class FakeMsg:
    def __init__(self, text=None, caption=None, from_user=None,
                 reply_to_message=None, quote=None,
                 photo=None, document=None, voice=None):
        self.text = text
        self.caption = caption
        self.from_user = from_user
        self.reply_to_message = reply_to_message
        self.quote = quote
        self.photo = photo
        self.document = document
        self.voice = voice


class FakeQuote:
    def __init__(self, text):
        self.text = text


def main():
    aziz = FakeUser("Aziz Karimov")

    # ── 1) Reply yo'q — kontekst ham yo'q ────────────────────────────
    assert _quoted_context(FakeMsg(text="@bot salom")) == ""
    print("[1] reply yo'q bo'lsa bo'sh qaytadi OK")

    # ── 2) Oddiy reply: matn ham, muallif ham kontekstga tushadi ─────
    m = FakeMsg(text="@bot", reply_to_message=FakeMsg(
        text="Python'da list va tuple farqi nima?", from_user=aziz))
    ctx = _quoted_context(m)
    assert "Aziz Karimov" in ctx, ctx
    assert "list va tuple" in ctx, ctx
    print("[2] reply qilingan savol matni va muallifi olindi OK")

    # ── 3) Caption ham matn sifatida qabul qilinadi ──────────────────
    m = FakeMsg(text="@bot", reply_to_message=FakeMsg(
        caption="Bu grafikni tushuntiring", from_user=aziz))
    assert "grafikni" in _quoted_context(m)
    print("[3] rasm/hujjat caption'i kontekstga tushdi OK")

    # ── 4) Belgilangan bo'lak (quote) butun xabardan USTUN ───────────
    # Uzun xabardan foydalanuvchi aynan bitta jumlani ajratgan bo'lsa,
    # savol o'sha jumla haqida — qolgani shovqin.
    m = FakeMsg(text="@bot", quote=FakeQuote("faqat shu jumla"),
                reply_to_message=FakeMsg(text="juda uzun matn " * 50,
                                         from_user=aziz))
    ctx = _quoted_context(m)
    assert "faqat shu jumla" in ctx, ctx
    assert "juda uzun matn" not in ctx, "belgilangan bo'lak ustun turishi kerak"
    print("[4] belgilangan bo'lak butun xabardan ustun OK")

    # ── 5) Bo'sh/matnsiz reply (masalan stiker) kontekst bermaydi ────
    assert _quoted_context(FakeMsg(text="@bot", reply_to_message=FakeMsg(
        from_user=aziz))) == ""
    assert _quoted_context(FakeMsg(text="@bot", reply_to_message=FakeMsg(
        text="   ", from_user=aziz))) == ""
    print("[5] matnsiz reply kontekst bermadi OK")

    # ── 6) Bot o'z xabariga reply — "Bot" deb belgilanadi ────────────
    m = FakeMsg(text="@bot davom et", reply_to_message=FakeMsg(
        text="Javob shu edi", from_user=FakeUser("AI Bot", is_bot=True)))
    assert _quoted_context(m).startswith("Bot yozgan"), _quoted_context(m)
    print("[6] botning o'z xabari 'Bot' deb belgilandi OK")

    # ═══════════════════════════════════════════════════════════════
    # 7) UZUN XABAR KESILADI — aks holda bitta forward qilingan uzun
    #    matn butun kunlik token limitini yeb qo'yishi mumkin.
    # ═══════════════════════════════════════════════════════════════
    m = FakeMsg(text="@bot", reply_to_message=FakeMsg(
        text="q" * 50000, from_user=aziz))
    ctx = _quoted_context(m)
    assert ctx.count("q") == _QUOTE_MAX_CHARS, ctx.count("q")
    print(f"[7] {_QUOTE_MAX_CHARS} belgidan uzun xabar kesildi OK")

    # ── 8) Muallifi noma'lum (anonim admin) yiqilmaydi ──────────────
    m = FakeMsg(text="@bot", reply_to_message=FakeMsg(text="Savol", from_user=None))
    assert "Kimdir" in _quoted_context(m)
    print("[8] anonim muallifda yiqilmadi OK")

    # ═══════════════════════════════════════════════════════════════
    # 9) MEDIA REPLY'DAN OLINADI — rasm/hujjat/ovozga reply qilib
    #    savol berilganda bot o'sha faylni ISHLATISHI kerak. Aks holda
    #    ko'rmagan rasm haqida taxmin qilib javob berardi.
    #    Bu content_type'ni ham belgilaydi, ya'ni KUNLIK LIMIT ham
    #    to'g'ri turdagi narx bilan yechiladi (matn emas, rasm narxi).
    # ═══════════════════════════════════════════════════════════════
    for kind in ("photo", "document", "voice"):
        src = FakeMsg(from_user=aziz, **{kind: object() if kind != "photo" else ["p"]})
        caller = FakeMsg(text="@bot bu nima?", reply_to_message=src)
        assert _media_source(caller) is src, kind
        assert _detect_guest_content_type(_media_source(caller)) == kind, kind
    print("[9] rasm/hujjat/ovozga reply → media reply'dan olindi OK")

    # ── 10) O'z medias'i reply'dan USTUN ────────────────────────────
    # O'zi yangi rasm yuborib, eski rasmga reply qilgan bo'lsa —
    # savol YANGI rasm haqida.
    own = FakeMsg(text="@bot", photo=["yangi"],
                  reply_to_message=FakeMsg(photo=["eski"], from_user=aziz))
    assert _media_source(own) is own
    print("[10] chaqiruvchining o'z rasmi reply'dan ustun turdi OK")

    # ── 11) Media'siz reply content_type'ni o'zgartirmaydi ──────────
    m = FakeMsg(text="@bot", reply_to_message=FakeMsg(text="oddiy savol", from_user=aziz))
    assert _detect_guest_content_type(_media_source(m)) == "text"
    print("[11] matnli reply matn bo'lib qoldi (limit matn narxida) OK")

    print("\nguest reply: barcha tekshiruvlar o'tdi (11/11).")


# ═══════════════════════════════════════════════════════════════════
#  FLOOD LIMIT (429) — soxta HTTP sessiya bilan
# ═══════════════════════════════════════════════════════════════════

class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    async def json(self, **kwargs):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    """Har chaqiruvda `replies` ro'yxatidagi navbatdagi javobni beradi;
    ro'yxat tugasa oxirgisini takrorlaydi."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.timeouts = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        self.timeouts.append(timeout)
        payload = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(payload, Exception):
            raise payload
        return FakeResponse(payload)


FLOOD = {"ok": False, "error_code": 429, "description": "Too Many Requests",
         "parameters": {"retry_after": 30}}
OK = {"ok": True, "result": {}}


async def flood_tests():
    guest.BOT_TOKEN = guest.BOT_TOKEN or "test-token"
    slept = []

    async def fake_sleep(sec):
        slept.append(sec)

    real_sleep = asyncio.sleep
    asyncio.sleep = fake_sleep

    try:
        # ═══════════════════════════════════════════════════════════
        # 12) YAKUNIY JAVOB FLOOD'DAN KEYIN HAM YETIB BORADI
        #     Javob tayyor — uni yo'qotgandan ko'ra kutgan afzal.
        # ═══════════════════════════════════════════════════════════
        session = FakeSession([FLOOD, OK])
        guest._get_http_session = lambda: _ready(session)
        ok, _ = await _edit_guest_inline_message("iid", "javob", wait_on_flood=True)
        assert ok, "flood'dan keyin javob YO'QOLDI — aynan shu xato edi"
        assert slept and slept[0] <= guest._GUEST_FLOOD_MAX_WAIT, slept
        print(f"[12] 429 dan keyin {slept[0]:.0f}s kutib javob yetkazildi OK")

        # ── 13) Flood'da ikkinchi format sinalmaydi (yana bir 429 bermaslik)
        session = FakeSession([FLOOD])
        guest._get_http_session = lambda: _ready(session)
        ok, flood = await _edit_guest_inline_message("iid", "status")
        assert not ok and flood == 30, (ok, flood)
        assert len(session.calls) == 1, (
            f"flood paytida {len(session.calls)} ta so'rov — cheklovni "
            f"yomonlashtiradi, bittasi yetarli")
        print("[13] flood paytida ortiqcha so'rov yuborilmadi OK")

        # ── 14) Oddiy rad etishda esa zaxira format SINALADI ────────
        session = FakeSession([{"ok": False, "description": "can't parse"}, OK])
        guest._get_http_session = lambda: _ready(session)
        ok, _ = await _edit_guest_inline_message("iid", "javob")
        assert ok and len(session.calls) == 2, (ok, len(session.calls))
        assert "text" in session.calls[1], "zaxira oddiy matn formati bo'lishi kerak"
        print("[14] rich rad etilsa oddiy matnga tushdi OK")

        # ── 14a) YAKUNIY JAVOB rich=True bilan to'liq bezakdan o'tadi
        # ⚠️ Ilgari guruhda build_rich_markdown() UMUMAN chaqirilmasdi:
        # jadval, xarita, premium emoji ishlamasdi, `[batafsil: ...]`
        # kabi ICHKI belgilar esa xom matn bo'lib ekranga chiqardi —
        # model ularni prompt bo'yicha baribir yozadi.
        session = FakeSession([OK])
        guest._get_http_session = lambda: _ready(session)
        await _edit_guest_inline_message(
            "iid", "[batafsil: Tarixi] ichi [/batafsil]", rich=True)
        boy = session.calls[0]["rich_message"]["markdown"]
        assert "<details><summary>Tarixi</summary>" in boy, boy
        assert "batafsil" not in boy.replace("<details>", ""), boy
        print("[14a] guruhda ham to'liq bezak ishlaydi OK")

        # ── 14b) Zaxira oddiy yo'lda belgi YO'QOLADI, ma'lumot QOLADI
        session = FakeSession([{"ok": False, "description": "can't parse"}, OK])
        guest._get_http_session = lambda: _ready(session)
        await _edit_guest_inline_message(
            "iid", "Joy [xarita:41.3,69.2,14] shu yerda", rich=True)
        oddiy = session.calls[1]["text"]
        assert "xarita" not in oddiy and "shu yerda" in oddiy, oddiy
        print("[14b] zaxira yo'lda ichki belgi xom qolmadi OK")

        # ── 14c) STATUS animatsiyasi bezakdan o'TMAYDI
        # U har 4 soniyada qayta yuboriladi — har bir qo'shimcha bezak
        # rad etilish ehtimolini bekorga oshirardi.
        session = FakeSession([OK])
        guest._get_http_session = lambda: _ready(session)
        await _edit_guest_inline_message("iid", "**Qidiryapman** 🔍")
        assert "tg://emoji" not in session.calls[0]["rich_message"]["markdown"]
        print("[14c] status animatsiyasi bezaksiz qoldi OK")

        # ── 14d) RASM guruh javobiga ham tushadi ────────────────
        # Ilgari guest yo'lida `images_out=None` edi: prompt "rasm
        # yubora olaman" deb va'da qilardi, model chaqirardi, javobiga
        # JIMLIK olardi va uni "topilmadi" deb tushunib qayta-qayta
        # qidirardi — kontekst portlashi.
        rasm = [{"url": "https://x.uz/a.jpg", "title": "A", "source": "x.uz"}]
        session = FakeSession([OK])
        guest._get_http_session = lambda: _ready(session)
        await _edit_guest_inline_message("iid", "Mana rasm [rasm:1]",
                                         rich=True, images=rasm)
        boy = session.calls[0]["rich_message"]["markdown"]
        assert "https://x.uz/a.jpg" in boy and "[rasm:1]" not in boy, boy
        print("[14d] rasm belgisi haqiqiy media blokka aylandi OK")

        # ⚠️ Telegram rasmli xabarni YARATISHDAN OLDIN har bir havolani
        # manba saytdan o'zi yuklab oladi — umumiy 10s sessiya bunga
        # yetmaydi. Shaxsiy chatda aynan shu xato bo'lgan.
        assert session.timeouts[0] is not None, "rasmli xabar 10s bilan ketdi"
        assert session.timeouts[0].total >= 60, session.timeouts[0].total
        print("[14e] rasmli xabarga alohida vaqt chegarasi berildi OK")

        # ── 14f) TIMEOUT'da IKKINCHI FORMAT YUBORILMAYDI ────────
        # Timeout — bu "rad etildi" EMAS: xabar yetib borgan bo'lishi
        # mumkin. Ikkinchi formatni yuborsak, foydalanuvchi bitta
        # javobni ikki marta ko'radi (biri rasmli, biri rasmsiz).
        session = FakeSession([asyncio.TimeoutError()])
        guest._get_http_session = lambda: _ready(session)
        ok, _ = await _edit_guest_inline_message("iid", "Rasm [rasm:1]",
                                                 rich=True, images=rasm)
        assert not ok, "timeout muvaffaqiyat deb hisoblandi"
        assert len(session.calls) == 1, (
            f"timeout'dan keyin {len(session.calls)} ta so'rov — "
            f"javob IKKI MARTA yetib borishi mumkin")
        print("[14f] timeout'da ikkinchi format yuborilmadi OK")

        # ── 14g) Zaxira oddiy matnda [rasm:N] XOM qolmaydi ──────
        session = FakeSession([{"ok": False, "description": "can't parse"}, OK])
        guest._get_http_session = lambda: _ready(session)
        await _edit_guest_inline_message("iid", "Mana [rasm:1] rasm",
                                         rich=True, images=rasm)
        oddiy = session.calls[1]["text"]
        assert "[rasm" not in oddiy and "rasm" in oddiy, oddiy
        print("[14g] zaxira matnda rasm belgisi xom qolmadi OK")
    finally:
        asyncio.sleep = real_sleep

    # ═══════════════════════════════════════════════════════════════
    # 15) ANIMATSIYA FLOOD'DA DARHOL TO'XTAYDI
    #     Aks holda u tahrirlash budjetini yeb, yakuniy javobni
    #     yuborishga imkon qoldirmaydi.
    # ═══════════════════════════════════════════════════════════════
    calls = []

    async def flooding_edit(text):
        calls.append(text)
        return True          # True = "to'xta"

    stop = asyncio.Event()
    await asyncio.wait_for(
        _run_guest_status_animator(flooding_edit, "text", stop, interval=0.01),
        timeout=2,
    )
    assert len(calls) == 1, f"animatsiya to'xtamadi, {len(calls)} marta chaqirdi"
    print("[15] flood signalida animatsiya darhol to'xtadi OK")

    # ── 16) Oddiy holatda esa animatsiya davom etadi ────────────────
    calls2 = []

    async def normal_edit(text):
        calls2.append(text)
        if len(calls2) >= 3:
            stop2.set()
        return False

    stop2 = asyncio.Event()
    await asyncio.wait_for(
        _run_guest_status_animator(normal_edit, "text", stop2, interval=0.01),
        timeout=2,
    )
    assert len(calls2) >= 3, calls2
    print("[16] oddiy holatda animatsiya ishlashda davom etdi OK")

    print("\nflood himoyasi: barcha tekshiruvlar o'tdi (12/12).")


async def _ready(value):
    return value


if __name__ == "__main__":
    main()
    asyncio.run(flood_tests())
