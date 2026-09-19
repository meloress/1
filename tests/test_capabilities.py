"""«Nima qila olaman?» ekrani va jimlik o'rniga javob.
Ishga tushirish: python tests/test_capabilities.py

ENG MUHIM TEKSHIRUVLAR:
  4-band — qo'llab-quvvatlanmagan tur (video, stiker, audio) JAVOBSIZ
    qolmasligi. Ilgari bunday xabar uchun handler umuman yo'q edi va bot
    mutlaqo jim qolardi — foydalanuvchi uchun bu "bot o'ldi" degani.
  6-band — tugma stillari FAQAT primary/success/danger bo'lishi. Boshqa
    qiymatni Telegram rad etadi va BUTUN xabar yuborilmaydi, ya'ni ekran
    umuman ochilmaydi (core/config.py izohi).
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio

from handlers import capabilities as cap
from core.config import BTN_PRIMARY, BTN_SUCCESS, BTN_DANGER


class FakeUser:
    def __init__(self, uid=777):
        self.id = uid


class FakeMessage:
    """send_rich() va edit_text() ni kuzatadigan soxta xabar."""
    def __init__(self, edit_ok=True):
        self.edit_ok = edit_ok
        self.from_user = FakeUser()
        self.sent = []      # (matn, klaviatura)
        self.edited = []

    async def answer(self, text, **kwargs):
        self.sent.append((text, kwargs.get("reply_markup")))
        return self

    async def edit_text(self, text, **kwargs):
        if not self.edit_ok:
            raise RuntimeError("message is not modified")
        self.edited.append((text, kwargs.get("reply_markup")))
        return self


class FakeQuery:
    def __init__(self, data, message, is_pro=False):
        self.data = data
        self.message = message
        # ⚠️ Tugmani BOSGAN odam — `message.from_user` emas. Guruhda u
        # botning o'zi bo'lardi va tarif har doim noto'g'ri chiqardi.
        self.from_user = FakeUser()
        self.answered = False

    async def answer(self, *a, **k):
        self.answered = True


def _all_buttons(kb):
    return [b for row in kb.inline_keyboard for b in row]


# Baza yo'q: tarif o'qishni soxtalashtiramiz. `_tarif` ning o'z
# try/except'i ham False qaytarardi, lekin u har chaqiruvda bazaga
# ulanmoqchi bo'lib testni sekinlashtirardi.
_PRO_BAYROQ = {"qiymat": False}


async def _soxta_tarif(_user_id):
    return _PRO_BAYROQ["qiymat"]


cap._tarif = _soxta_tarif


async def main():
    # ── 1) Asosiy ekran: har bo'lim uchun tugma bor ─────────────────
    msg = FakeMessage()
    await cap.handle_help(msg)
    assert len(msg.sent) == 1, msg.sent
    text, kb = msg.sent[0]
    assert "NIMA QILA OLAMAN" in text, text
    keys = {b.callback_data for b in _all_buttons(kb)}
    assert keys == {f"cap:{k}" for k in cap.SECTIONS}, keys
    print(f"[1] /help ekrani {len(keys)} ta bo'lim tugmasi bilan ochildi OK")

    # ── 2) Har bir bo'lim ochiladi va "Orqaga" tugmasi bor ──────────
    for key in cap.SECTIONS:
        m = FakeMessage()
        q = FakeQuery(f"cap:{key}", m)
        await cap.handle_capabilities_callback(q)
        assert q.answered, "callback javobsiz qolsa Telegram'da soat aylanaveradi"
        assert m.edited, f"{key}: ekran tahrirlanishi kerak"
        body, kb = m.edited[0]
        assert cap.SECTIONS[key]["title"] in body, key
        assert "cap:menu" in {b.callback_data for b in _all_buttons(kb)}, (
            f"{key}: 'Orqaga' tugmasi yo'q — foydalanuvchi tuzoqda qoladi")
    print(f"[2] {len(cap.SECTIONS)} ta bo'lim ochildi, hammasida 'Orqaga' bor OK")

    # ── 3) Misollar <code> ichida (bosib nusxalash uchun) ───────────
    with_example = [k for k, s in cap.SECTIONS.items() if s["example"]]
    assert len(with_example) >= 4, with_example
    for key in with_example:
        body = cap._section_text(key, False)
        assert f"<code>{cap.SECTIONS[key]['example']}</code>" in body, key
    print(f"[3] {len(with_example)} ta bo'limda nusxalanadigan misol bor OK")

    # ═══════════════════════════════════════════════════════════════
    # 4) QO'LLAB-QUVVATLANMAGAN TUR JAVOBSIZ QOLMAYDI
    # ═══════════════════════════════════════════════════════════════
    class FakeUnsupported(FakeMessage):
        def __init__(self, kind):
            super().__init__()
            for k in cap._UNSUPPORTED_HINTS:
                setattr(self, k, object() if k == kind else None)

    for kind in cap._UNSUPPORTED_HINTS:
        m = FakeUnsupported(kind)
        await cap.handle_unsupported(m)
        assert m.sent, f"KRITIK: '{kind}' uchun bot JIM qoldi"
        body, kb = m.sent[0]
        assert cap._UNSUPPORTED_HINTS[kind].split()[0] in body, (kind, body[:80])
        assert "cap:menu" in {b.callback_data for b in _all_buttons(kb)}, kind
    print(f"[4] {len(cap._UNSUPPORTED_HINTS)} ta qo'llab-quvvatlanmagan tur "
          f"javobsiz qolmadi OK")

    # ── 5) Noma'lum kalit menyuga tushadi, xatoga emas ──────────────
    # Eski xabardagi tugma bosilishi mumkin — foydalanuvchi aybdor emas.
    m = FakeMessage()
    await cap.handle_capabilities_callback(FakeQuery("cap:allaqachonyoq", m))
    assert m.edited and "NIMA QILA OLAMAN" in m.edited[0][0]
    print("[5] noma'lum bo'lim menyuga qaytardi OK")

    # ═══════════════════════════════════════════════════════════════
    # 6) TUGMA STILLARI — faqat primary/success/danger
    # ═══════════════════════════════════════════════════════════════
    allowed = {BTN_PRIMARY, BTN_SUCCESS, BTN_DANGER, None}
    boards = [cap._menu_keyboard()] + [cap._section_keyboard(k) for k in cap.SECTIONS]
    for kb in boards:
        for b in _all_buttons(kb):
            style = getattr(b, "style", None)
            assert style in allowed, (
                f"KRITIK: '{style}' stili Telegram tomonidan rad etiladi va "
                f"BUTUN xabar yuborilmaydi — ekran umuman ochilmaydi")
    print("[6] barcha tugma stillari Telegram qabul qiladigan qiymatda OK")

    # ── 7) Tahrirlash yiqilsa ham ekran yetib boradi ────────────────
    m = FakeMessage(edit_ok=False)
    await cap.handle_capabilities_callback(FakeQuery("cap:chat", m))
    assert m.sent, "tahrirlash yiqilganda yangi xabar yuborilishi kerak"
    print("[7] tahrirlash yiqilsa zaxira yo'l ishladi OK")

    # ── 8) Menyuda /help bor va u ro'yxatdan o'tgan ─────────────────
    from services.menu import COMMON_COMMANDS
    assert "help" in {c.command for c in COMMON_COMMANDS}, (
        "/help menyuda bo'lmasa, ekranni faqat /start ko'rganlar topadi")
    print("[8] /help buyruqlar menyusida OK")

    # ═══════════════════════════════════════════════════════════════
    # 9) TUGMA IKONKALARI — premium emoji HAQIQIY ID'ga tushishi
    # ═══════════════════════════════════════════════════════════════
    # icon= nomi CUSTOM_EMOJI'da bo'lmasa pro.btn() uni JIMGINA tashlab
    # ketadi: xato chiqmaydi, tugma shunchaki emojisiz qoladi. Shuning
    # uchun bog'lanishni test tekshiradi.
    from core.config import CUSTOM_EMOJI
    menu_buttons = _all_buttons(cap._menu_keyboard()) + [cap.menu_button()]
    for b in menu_buttons:
        eid = getattr(b, "icon_custom_emoji_id", None)
        assert eid, f"'{b.text}' tugmasida premium ikonka yo'q"
        assert eid in CUSTOM_EMOJI.values(), (b.text, eid)
    print(f"[9] {len(menu_buttons)} ta tugmada premium ikonka bor OK")

    # ── 10) Matnda emoji TAKRORLANMAYDI ────────────────────────────
    # Ikonka tugmaning O'ZIGA qo'yiladi; matnda ham emoji qolsa
    # foydalanuvchi ikkita emoji ko'rardi.
    for b in menu_buttons:
        assert not any(ord(ch) > 0x2100 for ch in b.text[:2]), (
            f"'{b.text}' matnida oddiy emoji qolib ketgan — ikonka bilan "
            f"birga ikkita emoji chiqadi")
    print("[10] tugma matnida emoji takrorlanmadi OK")

    # ── 11) Bo'lim sarlavhasi tugma bilan BIR XIL emojida ──────────
    # Manba bitta: SECTIONS[key]["emoji"]. Ajralib ketsa foydalanuvchi
    # tugmada bir emoji, ochilgan ekranda boshqasini ko'rardi.
    for key in cap.SECTIONS:
        eid = CUSTOM_EMOJI.get(cap.SECTIONS[key]["emoji"][0])
        assert eid, f"{key}: emoji kaliti CUSTOM_EMOJI'da yo'q"
        assert eid in cap._section_text(key, False), key
    print("[11] sarlavha va tugma bir xil emojida OK")

    import inspect
    # ═══════════════════════════════════════════════════════════════
    # 12) MODEL IMKONIYATLARNI SHU DICTDAN O'QIYDI
    # ═══════════════════════════════════════════════════════════════
    # Jonli shikoyat: «funksiyalaringni to'liq aytib o't» savoliga model
    # har safar chala ro'yxat berardi — tarjima, kod, matematika, ya'ni
    # har qanday chatbotda bor narsalar. Sababi: model FAQAT o'sha
    # so'rovga biriktirilgan asboblarni ko'radi, /research, /kunlik,
    # guruh rejimi va mavzular esa asbob emas.
    #
    # Yechim ro'yxatni ikkinchi marta yozish EMAS (CLAUDE.md, «Five
    # label maps»: ikki nusxaning biri ALBATTA eskiradi) — model ham,
    # ekran ham AYNAN shu SECTIONS dan o'qiydi.
    import services.ai as ai_module

    matn = cap.model_uchun(False)
    for key, sec in cap.SECTIONS.items():
        assert sec["title"] in matn, f"'{key}' modelga berilmayapti"
    assert "<" not in matn and ">" not in matn, (
        "HTML teglari modelga ketyapti — token yeydi va javobga "
        "sirqib chiqishi mumkin")
    print(f"[12] {len(cap.SECTIONS)} ta bo'lim modelga to'liq beriladi OK")

    # ── 12b) Tarif modelga AYTILADI ────────────────────────────────
    # Aks holda model bepul odamga «rasm chizib beraman» deb va'da
    # berardi — bu va'da bajarilmaydi va shikoyatga aylanadi.
    bepul_matn = cap.model_uchun(False)
    pro_matn = cap.model_uchun(True)
    assert bepul_matn != pro_matn
    assert "ISHLAMAYDI" in bepul_matn, bepul_matn[:300]
    assert "ISHLAMAYDI" not in pro_matn, pro_matn[:300]
    print("[12b] modelga foydalanuvchining tarifi aytiladi OK")

    # ── 12c) Eshik asbobi bor, arzon va ro'yxatdan o'tgan ──────────
    from core.config import INTERNAL_TOOL_NAMES
    eshik = ai_module._IMKONIYAT_TOOL
    assert eshik["name"] == "open_capabilities"
    assert eshik["parameters"]["properties"] == {}, (
        "eshik argumentsiz bo'lishi kerak — har raundda to'lanadi")
    # ⚠️ Nom INTERNAL_TOOL_NAMES da bo'lmasa strip_internal_names() uni
    # tozalamaydi va model asbob nomini foydalanuvchiga aytib qo'yadi.
    assert "open_capabilities" in INTERNAL_TOOL_NAMES
    # Eshik qimmat matndan sezilarli arzon bo'lishi SHART — butun
    # ikki bosqichli naqshning ma'nosi shunda.
    assert len(eshik["description"]) < len(matn) / 3, (
        len(eshik["description"]), len(matn))
    print(f"[12c] eshik argumentsiz, {len(eshik['description'])} belgi "
          f"({len(matn)} belgilik matn o'rniga) OK")

    # ── 12d) Dispatch bo'sh `else` dan YUQORIDA ────────────────────
    # `else` shoxi noma'lum nomni VEB QIDIRUVGA yuboradi — ya'ni eshik
    # pastda qolsa, «nima qila olasan» DuckDuckGo so'roviga aylanardi.
    src = inspect.getsource(ai_module.get_openai_reply)
    assert '"open_capabilities"' in src, "eshik uchun dispatch shoxi yo'q"
    assert src.index('"open_capabilities"') < src.index(
        "            else:\n                search_ran = True"), (
        "eshik bo\'sh `else` dan keyin tursa, chaqiruv veb qidiruvga ketadi")
    # Bir martadan ortiq chaqirilmasin: matn o'zgarmas, ikkinchi chaqiruv
    # bekorga ~2000 token yeydi.
    assert "imkoniyat_rounds < 1" in src, (
        "chegara yo'q — model bir xil matnni qayta-qayta yuklab olishi mumkin")
    print("[12d] eshik `else` dan yuqorida va bir martaga cheklangan OK")

    # ═══════════════════════════════════════════════════════════════
    # 13) EKRAN TARIFNI AYTADI
    # ═══════════════════════════════════════════════════════════════
    # Ilgari ekran tarifni umuman bilmasdi: bepul odam «rasm chizish,
    # eslatmalar» ro'yxatini o'qib O'ZIDA ishlaydi deb o'ylardi.
    bepul = cap._menu_text(False)
    pro = cap._menu_text(True)
    assert bepul != pro, "bosh ekran ikki tarifda bir xil — tarif aytilmagan"
    assert "Bepul" in bepul and "/pro" in bepul, bepul
    assert "Pro" in pro and "/pro" not in pro, pro

    p_bepul = cap._section_text("pro", False)
    p_pro = cap._section_text("pro", True)
    assert "yopiq" in p_bepul, "bepul odamga Pro bo'limi ochiq ko'rinyapti"
    assert "yopiq" not in p_pro and "ochiq" in p_pro, p_pro
    print("[13] ekran tarifga qarab boshqacha gapiradi OK")

    # ── 13b) Har bir bo'lim IKKALA tarifda ham yiqilmasdan chiziladi ─
    # `body`/`note` endi funksiya bo'lishi mumkin — biri unutilsa
    # TypeError faqat jonli chatda chiqardi.
    for key in cap.SECTIONS:
        for flag in (False, True):
            body = cap._section_text(key, flag)
            assert cap.SECTIONS[key]["title"] in body, (key, flag)
    print(f"[13b] {len(cap.SECTIONS)} ta bo'lim ikkala tarifda ham chizildi OK")

    # ── 13c) Bosh ekrandagi raqam ro'yxatdan olinadi ────────────────
    # Qo'lda yozilgan raqam ro'yxat o'zgarganda jimgina yolg'on aytardi.
    assert str(len(cap._PRO_QULF)) in bepul, bepul
    print(f"[13c] «yana {len(cap._PRO_QULF)} ta imkoniyat» raqami "
          f"ro'yxatdan olinadi OK")

    # ═══════════════════════════════════════════════════════════════
    # 14) YANGI BO'LIMLAR — eng ko'p yo'qotilgan imkoniyatlar
    # ═══════════════════════════════════════════════════════════════
    # Bularning hammasi kodda ISHLAYDI, lekin ekranda aytilmagani uchun
    # foydalanuvchilar mavjudligini ham bilmasdi.
    for key, kalit_soz in (("guruh", "@uzchatgptaibot"),
                           ("joy", "Joylashuv"),
                           ("chat", "Mavzular")):
        assert key in cap.SECTIONS, f"'{key}' bo'limi yo'q"
        assert kalit_soz in cap._section_text(key, False), (key, kalit_soz)
    print("[14] guruh rejimi, joylashuv va mavzular ekranda bor OK")

    print("\ncapabilities: barcha tekshiruvlar o'tdi (16/16).")


if __name__ == "__main__":
    asyncio.run(main())
