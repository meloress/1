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
#
# ⚠️ `body` va `note` MATN YOKI FUNKSIYA bo'lishi mumkin. Funksiya bo'lsa
# unga `is_pro` beriladi. Sabab: ilgari ekran tarifni umuman bilmasdi va
# "bepulda 3, Pro'da 20" deb yozardi — bepul odam buni O'ZIDA ishlaydi
# deb o'qirdi, so'rardi, rad javob olardi. Endi ekran FAQAT o'sha odamda
# nima ishlashini aytadi.
SECTIONS: dict[str, dict] = {
    "chat": {
        "button": "Suhbat",
        "emoji": ("chat", "💬"),
        "title": "SUHBAT VA INTERNET QIDIRUVI",
        "body": lambda pro: (
            "Istalgan savolni bering — javob yozilib borayotganini "
            "jonli ko'rasiz.\n\n"
            "Javob bugungi ma'lumotni talab qilsa, o'zim internetdan "
            "qidiraman va manbalarni ko'rsataman: valyuta kursi, "
            "ob-havo, yangiliklar, narxlar.\n\n"
            "🔗 <b>Havola tashlasangiz</b> — o'sha sahifani ochib o'qiyman, "
            "qidiruvga ketmayman. «Shuni qisqartir» desangiz kifoya.\n\n"
            "🗂 <b>Mavzular</b> — bitta chat ichida bir nechta suhbat "
            "yuritsangiz bo'ladi va <b>har biri o'z xotirasida</b> qoladi. "
            "Yangi mavzu ochsangiz, birinchi javobdan keyin unga o'zim "
            "nom qo'yaman.\n\n"
            + (f"Suhbatni eslab qolaman — oxirgi <b>{CONTEXT_WINDOW_PRO}</b> ta "
               "xabar (Pro tarifingizdagi uzaytirilgan xotira). "
               if pro else
               f"Suhbatni eslab qolaman — oxirgi <b>{CONTEXT_WINDOW}</b> ta "
               f"xabar (Pro'da <b>{CONTEXT_WINDOW_PRO}</b> ta). ")
            + "Siz haqingizdagi muhim narsalarni esa doimiy yodda saqlayman."
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
        "note": lambda pro: (
            f"📎 Sizda hajm chegarasi — <b>{_MB_PRO} MB</b>" if pro else
            f"📎 Sizda hajm chegarasi — <b>{_MB_FREE} MB</b> "
            f"(Pro'da {_MB_PRO} MB)"),
    },
    "photo": {
        "button": "Rasm",
        "emoji": ("photo", "📸"),
        "title": "RASM TAHLILI",
        "body": lambda pro: (
            "Rasm yuboring — uni xuddi insondek ko'rib tushuntiraman.\n\n"
            "Chek, skrinshot, dori qutisi, uy vazifasi, xato haqidagi "
            "xabar, qo'lda yozilgan matn — hammasini o'qiy olaman.\n\n"
            "Rasm bilan birga savolingizni izoh qilib yozsangiz, aynan "
            "shunga javob beraman.\n\n"
            + ("🎨 <b>Rasm chizish va tahrirlash</b> ham sizda ochiq — "
               "«chizib ber» yoki rasm yuborib «fonini o'zgartir» "
               "desangiz bo'ladi."
               if pro else
               "🔒 <b>Rasm chizish va tahrirlash</b> — Pro tarifida. "
               "Hozircha faqat tahlil qila olaman.")
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
        "note": lambda pro: (
            f"📅 Sizda kuniga <b>{_PRO['files']} ta</b> fayl" if pro else
            f"📅 Sizda kuniga <b>{_FREE['files']} ta</b> fayl "
            f"(Pro'da {_PRO['files']} ta)"),
    },
    # ⚠️ BU BO'LIM ENG KO'P YO'QOTILGAN IMKONIYAT EDI. Guest rejimi
    # to'liq ishlaydi, lekin ekranda umuman aytilmagani uchun odamlar
    # botni FAQAT shaxsiy chatdagi narsa deb bilishardi.
    "guruh": {
        "button": "Guruhda",
        "emoji": ("chat", "👥"),
        "title": "GURUH VA KANALLARDA",
        # ⚠️ Funksiya sifatida — `BOT_USERNAME` ni main.py getMe() dan
        # KEYIN yozadi, ya'ni import paytida u hali bo'sh. Va bu yerga
        # nom qo'lda yozilsa, bot qayta nomlanganda ekran jimgina
        # yolg'on manzil ko'rsatib turardi.
        "body": lambda pro: (
            "Meni guruhga qo'shish shart emas — istalgan chatda "
            f"<b>@{pro_module.BOT_USERNAME or 'uzchatgptaibot'}</b> deb "
            "yozib, savolingizni qo'shsangiz kifoya. Javob o'sha yerda, "
            "hamma ko'radigan qilib chiqadi.\n\n"
            "Guruhda ham: internetdan qidiraman, rasm topaman, jadval "
            "va tugmalar chiqara olaman, ovozli xabaringizni tushunaman.\n\n"
            "Kim so'raganini ajrataman — xotira va limitlar shaxsiy "
            "chatdagi bilan <b>bitta</b>, ya'ni bu yerda gaplashib, "
            "u yerda davom ettirsangiz bo'ladi."
        ),
        "example": "",
        "note": "📁 Guruhda fayl yasay olmayman — u faqat shaxsiy chatda",
    },
    # ⚠️ BU HAM KO'RINMAS IMKONIYAT edi: lokatsiya yuborilmaguncha
    # `find_nearby` asbobi biriktirilmaydi, ya'ni odam buni so'rab ham
    # ko'rmasdi — so'rashni bilmasdi.
    "joy": {
        "button": "Joylashuv",
        "emoji": ("limits", "📍"),
        "title": "YAQIN ATROFNI TOPISH",
        "body": (
            "Lokatsiyangizni yuboring (📎 → Joylashuv) va nima "
            "kerakligini ayting — haqiqiy xaritadan topib beraman:\n\n"
            "├ ⛽️ zapravka, ⚕️ dorixona, 🏧 bankomat\n"
            "├ 🍽 kafe, 🛒 do'kon, 🏥 shifoxona\n"
            "└ va OpenStreetMap'da belgilangan boshqa hamma narsa\n\n"
            "Har biriga masofasini yozaman, eng yaqin uchtasiga esa "
            "<b>yo'nalish tugmasi</b> qo'yaman — bosasiz, navigator "
            "ochiladi.\n\n"
            "Suhbat ichida kerak bo'lsa <b>xarita</b> ham chizaman."
        ),
        "example": "",
        "note": "⏱ Lokatsiyani 30 daqiqa eslab turaman — keyin qaytadan kerak",
    },
    "pro": {
        "button": "Pro",
        "emoji": ("pro", "💎"),
        "title": "PRO IMKONIYATLARI",
        "body": lambda pro: (
            ("✅ <b>Bularning hammasi sizda ochiq.</b>\n\n" if pro else
             "🔒 <b>Sizda hozir yopiq</b> — tarifingiz Bepul.\n\n")
            + f"├ 🖼 <b>Rasm chizish</b> — kuniga {_PRO['images']} ta\n"
            "├ 🎨 <b>Rasm tahrirlash</b> — yuborgan suratingizni "
            "o'zgartirish\n"
            "├ 🔎 <b>Chuqur tadqiqot</b> — 10+ manba, tayyor PDF hisobot "
            "(/research)\n"
            "├ ⏰ <b>Eslatmalar</b> — «ertaga soat 9 da eslat» desangiz, "
            "o'sha vaqtda o'zim yozaman\n"
            "├ 📰 <b>Kunlik daydjest</b> — tanlagan mavzularingiz bo'yicha "
            "(/kunlik)\n"
            f"├ 🧠 <b>Uzunroq xotira</b> ({CONTEXT_WINDOW_PRO} xabar) va "
            "chuqurroq fikrlash\n"
            "├ 🎙 <b>Tabiiyroq ovoz</b> — ovozli javoblarda\n"
            f"└ 📄 Kuniga {_PRO['files']} ta fayl, {_MB_PRO} MB gacha hujjat"
        ),
        "example": "",
        "note": lambda pro: ("💎 Tarif holati: /profile" if pro else
                             "💎 Tariflar va narxlar: /pro"),
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
            "• Sizning nomingizdan hech kimga xabar yubora olmayman\n"
            "• Javobni o'zim tanlab ovozda yubora olmayman — ovozli javob "
            "faqat siz ovozli xabar yuborganingizda keladi\n\n"
            "Qolgan hamma narsani — bemalol so'rang."
        ),
        "example": "",
        "note": "",
    },
}

# Asosiy ekranda tugmalar shu tartibda, ikkitadan qatorga.
_ROWS = (("chat", "doc"), ("photo", "voice"), ("file", "guruh"),
         ("joy", "pro"), ("limits",))

# Pro'da ochiladigan, bepulda YO'Q imkoniyatlar soni — bosh ekrandagi
# bitta qator uchun. Qo'lda emas, `pro` bo'limidagi qulflangan
# imkoniyatlar ro'yxatidan olinadi, aks holda ro'yxat o'zgarganda bu
# raqam jimgina yolg'on aytib turardi.
_PRO_QULF = ("rasm chizish", "rasm tahrirlash", "chuqur tadqiqot",
             "eslatmalar", "kunlik daydjest")


def _menu_text(is_pro: bool) -> str:
    """Bosh ekran. Tarif qatori ATAYLAB birinchi ekranda.

    Ilgari ekran tarifni umuman aytmasdi, ya'ni bepul odam ro'yxatni
    o'qib "hammasi menda bor" deb o'ylardi va ishlamagan narsani
    so'rardi. Eng ko'p shikoyat shundan chiqqan.
    """
    tarif = ("💎 Tarifingiz: <b>Pro</b> — hamma imkoniyat ochiq."
             if is_pro else
             f"Tarifingiz: <b>Bepul</b> · Pro'da yana {len(_PRO_QULF)} ta "
             "imkoniyat ochiladi → /pro")
    return (
        "🎯 <b>MEN NIMA QILA OLAMAN</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{tarif}\n\n"
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


def _matn(qiymat, is_pro: bool) -> str:
    """`body`/`note` matn ham, funksiya ham bo'lishi mumkin."""
    return qiymat(is_pro) if callable(qiymat) else qiymat


def _section_text(key: str, is_pro: bool) -> str:
    s = SECTIONS[key]
    emoji = pro_module.pe(*s["emoji"])
    parts = [f"{emoji} <b>{s['title']}</b>\n━━━━━━━━━━━━━━━━━━━━\n",
             _matn(s["body"], is_pro)]
    if s["example"]:
        parts.append(
            "\n<b>Sinab ko'ring</b> — bosib nusxalang:\n"
            f"<code>{s['example']}</code>"
        )
    izoh = _matn(s["note"], is_pro)
    if izoh:
        parts.append(f"\n{izoh}")
    return "\n".join(parts)


# ── «Nima qila olasan?» — tabiiy savolni tanish ─────────────────────
# ⚠️ NEGA KOD, MODEL EMAS. Bu savol ilgari AI ga ketardi va javob HAR
# SAFAR boshqacha, har safar chala chiqardi: model faqat o'sha so'rovga
# biriktirilgan ASBOBLARNI ko'radi (`_capability_manifest`), ya'ni
# /research, /kunlik, guruh rejimi, mavzular va hatto tarif haqida
# umuman bilmaydi. Bo'shliqni "har qanday chatbotda bor" ro'yxati bilan
# to'ldirardi — foydalanuvchi eng qimmat imkoniyatlarni bilmay qolardi.
#
# Bu yo'l HECH QANDAY AI tokeni sarflamaydi va javob doim to'liq.
# Naqsh o'tkazib yuborsa — eski xatti-harakat qoladi, ya'ni yomonlashmaydi.
_SAVOL_MAX = 120          # undan uzuni — savol emas, ish topshirig'i

_SAVOL_IBORALARI = (
    # ⚠️ IBORALAR ATAYLAB ANIQ, bitta so'z emas. «imkoniyatlaring» ni
    # yolg'iz qo'ysak, «imkoniyatlaringdan foydalanib menga prezentatsiya
    # yasab ber» ham tanilardi — ya'ni ish bajarilmay, o'rniga yordam
    # ekrani chiqardi. Shuning uchun `-ni` shakli olingan (`-dan` emas)
    # va fe'llar to'liq yozilgan.
    # o'zbekcha
    "nima qila ola", "nimalar qila ola", "nima ish qila ola",
    "qila olishingni", "qila olishingizni",
    "funksiyalaringni", "imkoniyatlaringni",
    "funksiyalaring nima", "imkoniyatlaring nima",
    "barcha funksiya", "hamma funksiya", "barcha imkoniyat",
    "hamma imkoniyat", "qanday funksiya", "qanaqa funksiya",
    "qanday imkoniyat", "qanaqa imkoniyat",
    "nimalarni bilasan", "nima bila olasan", "qanday yordam bera",
    # ruscha
    "что ты умеешь", "что умеешь", "твои возможности",
    "что ты можешь", "что можешь", "какие функции",
    # inglizcha
    "what can you do", "your capabilities", "your features",
    "what do you do", "list your functions", "all your functions",
)

# Bir xil ko'rinadigan, lekin turli kodli apostroflar — o'zbek matnida
# hammasi uchraydi va biri bilan yozilgan naqsh boshqasini topmaydi.
_APOSTROF = str.maketrans({"‘": "'", "’": "'",
                           "ʻ": "'", "ʼ": "'", "`": "'"})


def imkoniyat_savolimi(matn: str) -> bool:
    """Bu xabar «nima qila olasan?» savolimi?

    Uzunlik chegarasi MUHIM: «imkoniyatlaringdan foydalanib menga PDF
    yasab ber» — bu savol emas, topshiriq, va uni ekran bilan javob
    berish ishni BAJARMASLIK bo'lardi.
    """
    if not matn:
        return False
    t = matn.translate(_APOSTROF).lower().strip()
    if len(t) > _SAVOL_MAX:
        return False
    return any(ibora in t for ibora in _SAVOL_IBORALARI)


def menu_button():
    """/start ostiga qo'yiladigan tugma (handlers/messages.py ishlatadi)."""
    return pro_module.btn("Nima qila olaman?", "cap:menu",
                          style=BTN_PRIMARY, icon="capabilities")


async def _tarif(user_id: int) -> bool:
    """Ekran uchun tarif. Baza javob bermasa — bepul deb ko'rsatamiz.

    ⚠️ Xato bo'lganda FALSE ATAYLAB: "Pro'da ochiladi" deb ko'rsatish eng
    yomoni "sizda ochiq" deb aldab qo'yishdan afzal. Va bu ekran hech
    qanday darvoza emas — haqiqiy tekshiruv baribir har bir imkoniyatning
    o'z joyida qoladi.
    """
    try:
        from db import database
        return await database.pro_tarifmi(user_id)
    except Exception as exc:
        logger.debug(f"[Imkoniyatlar] tarif o'qilmadi: {exc}")
        return False


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
    """/help — imkoniyatlar ekrani.

    Bu yerga `/help` dan tashqari TABIIY SAVOL ham keladi («nima qila
    olasan?»). Sabab handlers/messages.py da yozilgan: ilgari bunday
    savol modelga ketardi, model esa faqat biriktirilgan ASBOBLARNI
    ko'rgani uchun /research, /kunlik, guruh rejimi va mavzular haqida
    umuman bilmasdi — bo'shliqni "har qanday chatbot" ro'yxati bilan
    to'ldirardi.
    """
    await _show(message, _menu_text(await _tarif(message.from_user.id)),
                _menu_keyboard(), edit=False)


async def handle_capabilities_callback(query: CallbackQuery) -> None:
    """cap:menu va cap:<bo'lim> tugmalari."""
    await query.answer()
    key = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
    # ⚠️ Tarif tugmani BOSGAN odamniki, xabar egasiniki emas: guruhda
    # ekran boshqa odamga ham ko'rinadi va `query.message.from_user`
    # BOTNING o'zi bo'lardi.
    is_pro = await _tarif(query.from_user.id)

    if key == "menu" or key not in SECTIONS:
        # ⚠️ Noma'lum kalit menyuga tushadi, xato xabariga EMAS: callback
        # eski xabardan ham kelishi mumkin (bot yangilangan, tugma esa
        # chatda qolgan) va bunda foydalanuvchi aybdor emas.
        await _show(query.message, _menu_text(is_pro), _menu_keyboard(), edit=True)
        return

    await _show(query.message, _section_text(key, is_pro),
                _section_keyboard(key), edit=True)


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
