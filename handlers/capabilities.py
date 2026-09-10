"""«Nima qila olaman?» — imkoniyatlar ekrani.

NEGA KERAK: bot nima qila olishi FAQAT /start salomlashuvida yozilgan edi.
Uni odam bir marta — hali botni sinamagan, birinchi kuni — o'qiydi va
unutadi. Natijada eng qimmat imkoniyatlar (PPTX yasash, Excel tahrirlash,
ovozli javob) ishlatilmay yotardi: foydalanuvchi botni oddiy chat deb
o'ylardi.

Ekran UCHTA joydan ochiladi va shu bilan uchta muammoni yopadi:
  1. /help buyrug'i        — menyuda doim turadi (kashf qilinmaslik)
  2. /start ostidagi tugma — birinchi kundan
  3. AVTOMATIK             — foydalanuvchi qo'llab-quvvatlanmagan narsa
     (video, stiker, audio) yuborganda. Ilgari bunda bot MUTLAQO jim
     qolardi va bu "bot buzildi" deb qabul qilinardi.

Har bo'limda nusxa olinadigan MISOL bor (<code> ichida — Telegram'da
bosilsa nusxalanadi). Ro'yxatni o'qish emas, birinchi muvaffaqiyatli
natijani ko'rish ishonch tug'diradi.
"""

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from core.config import (
    BTN_PRIMARY, BTN_SUCCESS, CONTEXT_WINDOW, CONTEXT_WINDOW_PRO,
    DOCUMENT_MAX_SIZE_FREE, DOCUMENT_MAX_SIZE_PRO, PLAN_LIMITS,
)
from core.loader import logger
from handlers import pro as pro_module

# Raqamlar core/config.py dan olinadi — bu yerda takrorlansa, tarif
# o'zgarganda ekran jimgina yolg'on ko'rsata boshlardi.
_MB_FREE = DOCUMENT_MAX_SIZE_FREE // (1024 * 1024)
_MB_PRO = DOCUMENT_MAX_SIZE_PRO // (1024 * 1024)
_PRO = PLAN_LIMITS["pro"]
_FREE = PLAN_LIMITS["free"]


# (kalit, tugma matni, emoji nomi, sarlavha, tavsif, misol, izoh)
# `emoji` — core/config.py: CUSTOM_EMOJI kaliti; topilmasa pe() jimgina
# oddiy emojiga tushadi.
SECTIONS: dict[str, dict] = {
    "chat": {
        "button": "Suhbat",
        "emoji": ("chat", "💬"),
        "title": "SUHBAT VA INTERNET QIDIRUVI",
        "body": (
            "Istalgan savolni bering — javob yozilib borayotganini "
            "jonli ko'rasiz.\n\n"
            "Javob bugungi ma'lumotni talab qilsa, o'zim internetdan "
            "qidiraman va manbalarni ko'rsataman: valyuta kursi, "
            "ob-havo, yangiliklar, narxlar.\n\n"
            f"Suhbatni eslab qolaman — oxirgi <b>{CONTEXT_WINDOW}</b> ta "
            f"xabar (Pro'da <b>{CONTEXT_WINDOW_PRO}</b> ta). Siz haqingizdagi "
            "muhim narsalarni esa doimiy yodda saqlayman."
        ),
        "example": "Bugun dollar kursi qancha va oxirgi bir oyda qanday o'zgargan?",
        "note": "🧹 Suhbatni noldan boshlash: /new",
    },
    "doc": {
        "button": "Hujjat",
        "emoji": ("file", "📄"),
        "title": "HUJJAT TAHLILI",
        "body": (
            "PDF, Word, Excel, PowerPoint yoki matnli fayl yuboring — "
            "o'qib chiqaman, xulosa qilaman, savollaringizga javob beraman.\n\n"
            "Izohsiz yuborsangiz ko'rsatmangizni kutaman — faylni tashlab, "
            "keyingi xabarda nima qilishimni yozsangiz bo'ladi."
        ),
        "example": "Shu shartnomadagi asosiy majburiyatlarni jadval qilib ber",
        "note": f"📎 Hajmi: bepulda {_MB_FREE} MB, Pro'da {_MB_PRO} MB gacha",
    },
    "photo": {
        "button": "Rasm",
        "emoji": ("photo", "📸"),
        "title": "RASM TAHLILI",
        "body": (
            "Rasm yuboring — uni xuddi insondek ko'rib tushuntiraman.\n\n"
            "Chek, skrinshot, dori qutisi, uy vazifasi, xato haqidagi "
            "xabar, qo'lda yozilgan matn — hammasini o'qiy olaman.\n\n"
            "Rasm bilan birga savolingizni izoh qilib yozsangiz, aynan "
            "shunga javob beraman."
        ),
        "example": "Bu chekdagi eng qimmat uchta mahsulotni ayt",
        "note": "",
    },
    "voice": {
        "button": "Ovoz",
        "emoji": ("voice", "🎙"),
        "title": "OVOZLI XABAR",
        "body": (
            "Yozishga vaqt yo'qmi — gapiring. Ovozli xabaringizni "
            "tushunaman va <b>ovozda javob qaytaraman</b>.\n\n"
            "O'zbek, rus va ingliz tilini taniyman: qaysi tilda "
            "gapirsangiz, javob ham o'sha tilda va o'sha til ona "
            "tili bo'lgan ovozda keladi."
        ),
        "example": "",
        "note": "🎧 Javob matn va ovoz — ikkalasi ham keladi",
    },
    "file": {
        "button": "Fayl yaratish",
        "emoji": ("build", "🛠"),
        "title": "FAYL YARATISH VA TAHRIRLASH",
        "body": (
            "Tayyor fayl yasab beraman — chatga biriktirilgan holda "
            "keladi, hech qayerdan yuklab olish shart emas:\n\n"
            "├ 📊 Taqdimot — <b>PPTX</b>\n"
            "├ 📄 Hujjat — <b>PDF</b>, <b>Word</b>\n"
            "├ 📈 Jadval va diagramma — <b>Excel</b>\n"
            "└ 🔄 Formatdan formatga o'girish\n\n"
            "Mavjud faylni ham tahrirlay olaman: Excel'ni yuboring va "
            "nimani o'zgartirishni ayting — <b>formatini buzmasdan</b> "
            "tuzatib qaytaraman."
        ),
        "example": "Toshkent haqida 7 slaydlik chiroyli prezentatsiya yasab ber",
        "note": (f"📅 Kuniga: bepulda {_FREE['files']} ta, "
                 f"Pro'da {_PRO['files']} ta"),
    },
    "pro": {
        "button": "Pro",
        "emoji": ("pro", "💎"),
        "title": "PRO IMKONIYATLARI",
        "body": (
            f"├ 🖼 <b>Rasm chizish</b> — kuniga {_PRO['images']} ta\n"
            f"├ 🔎 <b>Chuqur tadqiqot</b> — 10+ manba, tayyor PDF hisobot "
            f"(/research)\n"
            "├ ⏰ <b>Eslatmalar</b> — «ertaga soat 9 da eslat» desangiz, "
            "o'sha vaqtda o'zim yozaman\n"
            "├ 📰 <b>Kunlik daydjest</b> — tanlagan mavzularingiz bo'yicha "
            "(/kunlik)\n"
            f"├ 🧠 <b>3× uzun xotira</b> va chuqurroq fikrlash\n"
            f"└ 📄 Kuniga {_PRO['files']} ta fayl, {_MB_PRO} MB gacha hujjat"
        ),
        "example": "",
        "note": "💎 Tariflar va narxlar: /pro",
    },
    # ⚠️ BU BO'LIM ATAYLAB BOR. G'alati tuyulishi mumkin, lekin ishonchni
    # eng kuchli oshiradigan qism aynan shu: chegarasini o'zi aytadigan
    # botning qolgan gapiga ishonsa bo'ladi. YouTube xulosasi olib
    # tashlangandan keyin bu ayniqsa muhim — odamlar hali ham havola
    # tashlab ko'radi va sababini bilmasa botni ayblaydi.
    "limits": {
        "button": "Chegaralarim",
        "emoji": ("limits", "🚫"),
        "title": "NIMALARNI QILA OLMAYMAN",
        "body": (
            "Halol aytganim ma'qul — vaqtingizni behuda sarflamang:\n\n"
            "• <b>Video ko'ra olmayman</b> — video, videoxabar va GIF "
            "mazmunini tahlil qila olmayman\n"
            "• <b>YouTube videolarini o'qiy olmayman</b> — havola "
            "tashlasangiz ham foydasi yo'q\n"
            "• <b>Musiqa va audio fayllarni</b> tinglay olmayman "
            "(ovozli xabar esa ishlaydi)\n"
            "• <b>Internetdan fayl yuklab</b> bera olmayman\n"
            "• Sizning nomingizdan hech kimga xabar yubora olmayman\n\n"
            "Qolgan hamma narsani — bemalol so'rang."
        ),
        "example": "",
        "note": "",
    },
}

# Asosiy ekranda tugmalar shu tartibda, ikkitadan qatorga.
_ROWS = (("chat", "doc"), ("photo", "voice"), ("file", "pro"), ("limits",))

_MENU_TEXT = (
    "🎯 <b>MEN NIMA QILA OLAMAN</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "<blockquote>Har bir bo'limda tayyor misol bor — bosib nusxalang va "
    "menga yuboring. Eng tez yo'l shu.</blockquote>\n\n"
    "Qaysi biri qiziq?"
)


def _menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for row in _ROWS:
        rows.append([
            # icon= premium (animatsion) emoji tugmaning O'ZIGA qo'yadi.
            # Manba bitta — SECTIONS[key]["emoji"], ya'ni bo'lim sarlavhasi
            # bilan tugma har doim bir xil emojini ko'rsatadi.
            pro_module.btn(SECTIONS[key]["button"], f"cap:{key}",
                           style=BTN_PRIMARY if key != "pro" else BTN_SUCCESS,
                           icon=SECTIONS[key]["emoji"][0])
            for key in row
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _section_keyboard(key: str) -> InlineKeyboardMarkup:
    rows = [[pro_module.btn("⬅️ Orqaga", "cap:menu")]]  # ikonkasiz — bu navigatsiya
    # Pro bo'limidan to'g'ridan-to'g'ri sotib olish ekraniga — konversiya
    # uchun eng qulay payt aynan shu yerda.
    if key == "pro":
        rows.insert(0, [pro_module.btn("Pro tarifga o'tish", "pro:open",
                                       style=BTN_SUCCESS, icon="pro")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _section_text(key: str) -> str:
    s = SECTIONS[key]
    emoji = pro_module.pe(*s["emoji"])
    parts = [f"{emoji} <b>{s['title']}</b>\n━━━━━━━━━━━━━━━━━━━━\n", s["body"]]
    if s["example"]:
        parts.append(
            "\n<b>Sinab ko'ring</b> — bosib nusxalang:\n"
            f"<code>{s['example']}</code>"
        )
    if s["note"]:
        parts.append(f"\n{s['note']}")
    return "\n".join(parts)


def menu_button():
    """/start ostiga qo'yiladigan tugma (handlers/messages.py ishlatadi)."""
    return pro_module.btn("Nima qila olaman?", "cap:menu",
                          style=BTN_PRIMARY, icon="capabilities")


async def _show(target: Message, text: str, kb: InlineKeyboardMarkup,
                *, edit: bool) -> None:
    """Ekranni ko'rsatadi: iloji bo'lsa joyida tahrirlab, aks holda yangi
    xabar bilan. Tahrirlash chatni xabarlarga to'ldirmaydi, lekin u
    yiqilsa (eski xabar, o'chirilgan xabar) ekran YO'QOLMASLIGI kerak —
    shuning uchun zaxira sifatida send_rich() ishlatiladi, u o'z navbatida
    bezaklarni bosqichma-bosqich tashlab bo'lsa ham yetkazadi."""
    if edit:
        try:
            await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
            return
        except Exception as exc:
            logger.debug(f"[Imkoniyatlar] tahrirlash yiqildi: {exc}")
    await pro_module.send_rich(target, text, kb)


async def handle_help(message: Message) -> None:
    """/help — imkoniyatlar ekrani."""
    await _show(message, _MENU_TEXT, _menu_keyboard(), edit=False)


async def handle_capabilities_callback(query: CallbackQuery) -> None:
    """cap:menu va cap:<bo'lim> tugmalari."""
    await query.answer()
    key = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""

    if key == "menu" or key not in SECTIONS:
        # ⚠️ Noma'lum kalit menyuga tushadi, xato xabariga EMAS: callback
        # eski xabardan ham kelishi mumkin (bot yangilangan, tugma esa
        # chatda qolgan) va bunda foydalanuvchi aybdor emas.
        await _show(query.message, _MENU_TEXT, _menu_keyboard(), edit=True)
        return

    await _show(query.message, _section_text(key), _section_keyboard(key), edit=True)


# ═══════════════════════════════════════════════════════════════════
#  QO'LLAB-QUVVATLANMAGAN KONTENT — JIMLIK O'RNIGA
# ═══════════════════════════════════════════════════════════════════
# Ilgari bu turdagi xabarlar uchun HECH QANDAY handler yo'q edi: odam
# video yuboradi, bot mutlaqo jim qoladi. Foydalanuvchi uchun bu "bot
# o'ldi" degani. Endi nosozlikka o'xshagan lahza kashfiyot lahzasiga
# aylanadi — nima qila olmasligimni aytib, nima qila olishimni ko'rsatamiz.
_UNSUPPORTED_HINTS = {
    "video": "Videoni ko'ra olmayman",
    "video_note": "Videoxabarni ko'ra olmayman",
    "animation": "GIF ichidagi harakatni ko'ra olmayman",
    "audio": "Musiqa va audio fayllarni tinglay olmayman",
    "sticker": "Stikerni tushunmadim",
    "contact": "Kontakt bilan ishlay olmayman",
    "poll": "So'rovnoma bilan ishlay olmayman",
}

_UNSUPPORTED_EXTRA = {
    "video": "Videodagi gapni tushunishim uchun uni <b>ovozli xabar</b> "
             "qilib yuboring yoki kadrni <b>rasm</b> qilib tashlang.",
    "video_note": "Aytmoqchi bo'lganingizni <b>ovozli xabar</b> qilib "
                  "yuboring — tinglayman va ovozda javob beraman.",
    "animation": "Kadrni <b>rasm</b> qilib yuborsangiz, uni tahlil qilaman.",
    "audio": "Gapni <b>ovozli xabar</b> (mikrofon tugmasi) qilib yuborsangiz "
             "tushunaman.",
    "sticker": "Nimani nazarda tutganingizni yozib yuboring 🙂",
}


def _content_kind(message: Message) -> str:
    for kind in _UNSUPPORTED_HINTS:
        if getattr(message, kind, None) is not None:
            return kind
    return ""


async def handle_unsupported(message: Message) -> None:
    """Qo'llab-quvvatlanmagan tur — qisqa, iliq javob + imkoniyatlar tugmasi."""
    kind = _content_kind(message)
    hint = _UNSUPPORTED_HINTS.get(kind, "Bu turdagi xabarni tushunmadim")
    extra = _UNSUPPORTED_EXTRA.get(kind, "")

    text = f"🤔 <b>{hint}.</b>\n\n"
    if extra:
        text += f"{extra}\n\n"
    text += ("Lekin men matn, rasm, hujjat va ovoz bilan ishlayman — "
             "hamda tayyor fayl yasab beraman.")

    kb = InlineKeyboardMarkup(inline_keyboard=[[menu_button()]])
    await pro_module.send_rich(message, text, kb)
