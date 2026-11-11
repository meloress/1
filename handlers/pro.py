"""Pro tarif: Telegram Stars orqali sotib olish, sovg'a, referal, promokod.

ASOSIY PRINSIP: "pul olindi, lekin foydalanuvchi hech narsa olmadi va hech
kim bilmay qoldi" holati BO'LMASLIGI kerak. Shuning uchun:

  * grant_paid_pro() to'lov yozuvini va tarifni BITTA tranzaksiyada beradi;
  * har qanday xato yo'lida foydalanuvchi chek raqamini oladi va admin
    darhol xabardor qilinadi;
  * takroriy successful_payment update'i charge_id UNIQUE cheklovida
    to'xtaydi, kodda emas.

REGISTRATSIYA: to'lov handlerlari main.py'da dp.message'ga TO'G'RIDAN-TO'G'RI
yoziladi — sabab main.py'dagi izohda.
"""
import asyncio
import html
import os
import re
import time
from datetime import datetime, timedelta, timezone
from html import escape as html_escape

from aiogram.types import (
    Message, CallbackQuery, PreCheckoutQuery, LabeledPrice,
    InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton,
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
)
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError

from core.loader import bot, logger
from core.config import (
    PRO_PLANS, PRO_PLANS_BY_DAYS, PRO_PAYLOAD_VERSION, daily_limit,
    MESSAGE_COST_TEXT, MESSAGE_COST_PHOTO, MESSAGE_COST_VOICE, MESSAGE_COST_DOCUMENT,
    REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS, REFERRAL_MAX_REWARDS,
    CUSTOM_EMOJI, emoji_id, MESSAGE_EFFECTS, BTN_PRIMARY, BTN_SUCCESS, BTN_DANGER,
    BTN_LINK, KARTA_NARX, ADMIN_USERNAME, TIMEZONE,
    OBUNA_DAVR, OBUNA_KUN, OBUNA_NARX, CONTEXT_WINDOW_PRO, DOCUMENT_MAX_SIZE_PRO,
)

# Xotira va'dasi — raqamlar oynaning O'ZIDAN. Ilgari to'lov oynasida
# «2× xotira», /pro ekranida «3×» turardi, haqiqati esa 80/30 ≈ 2,7×.
XOTIRA = f"{CONTEXT_WINDOW_PRO} xabarlik xotira"
from db import database
from services import menu as menu_module

# main.py ishga tushganda to'ldiriladi (deep-link havolalar uchun kerak).
BOT_USERNAME: str = ""

# main.py get_me() dan to'ldiradi. Inline rejim @BotFather'da /setinline
# bilan YOQILADI — kod uni o'zi yoqa olmaydi. Yoqilmagan bo'lsa ulashish
# tugmasi eski (matnli) usulga tushadi, ya'ni hech narsa buzilmaydi.
INLINE_ENABLED: bool = False


# ═══════════════════════════════════════════════════════════════════
#  0. KO'RINISH: PREMIUM EMOJI, RANGLI TUGMALAR, XAVFSIZ YUBORISH
# ═══════════════════════════════════════════════════════════════════

def pe(name: str, fallback: str) -> str:
    """Premium (animatsion) emoji — mavjud bo'lmasa oddiy emoji qoladi.

    <tg-emoji> tegi ichidagi belgi Telegram Premium'i YO'Q foydalanuvchida
    ham ko'rinadi (u oddiy emoji sifatida tushadi), shuning uchun bu
    hech kimga xizmatni buzmaydi.
    """
    eid = emoji_id(name)
    if not eid:
        return fallback
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


def btn(text: str, callback_data: str, *, style: str | None = None,
        icon: str | None = None, url: str | None = None,
        disabled: bool = False) -> InlineKeyboardButton:
    """Rangli/ikonkali tugma quruvchi.

    style faqat 'primary' | 'success' | 'danger' bo'lishi mumkin — boshqa
    qiymat Telegram tomonidan rad etiladi va BUTUN xabar yuborilmaydi
    (empirik tekshirilgan, core/config.py izohiga qarang). Ayniqsa
    BTN_LINK ("link") bu yerga TUSHMASLIGI kerak — u faqat rich xabar
    ichidagi <tg-button> uchun.

    disabled=True (Bot API 10.3) — tugma ko'rinadi, lekin bosilmaydi.
    ⚠️ `disabled` amalning O'ZI hisoblanadi: Telegram "tugma turini
    belgilaydigan maydonlardan ANIQ BITTASI bo'lsin" deb talab qiladi,
    shuning uchun callback_data/url ATAYLAB qo'shilmaydi.
    """
    kwargs = {"text": text}
    if disabled:
        kwargs["disabled"] = {}
    elif url:
        kwargs["url"] = url
    else:
        kwargs["callback_data"] = callback_data
    if style:
        kwargs["style"] = style
    if icon and emoji_id(icon):
        kwargs["icon_custom_emoji_id"] = emoji_id(icon)
    return InlineKeyboardButton(**kwargs)


ADMIN_IZOH = "\n\n<i>💬 Savol yoki muammo bo'lsa — pastdagi tugma orqali adminga yozing.</i>"


def admin_tugmasi() -> list[InlineKeyboardButton]:
    """Klaviatura QATORI: bosganda adminning shaxsiy chati ochiladi."""
    return [btn("💬 Admin bilan bog'lanish", "", url=f"https://t.me/{ADMIN_USERNAME}")]


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[admin_tugmasi()])


BAN_MATNI = ("🚫 <b>Siz botdan foydalanish huquqidan mahrum qilingansiz.</b>\n\n"
             "<i>Xato deb o'ylasangiz — pastdagi tugma orqali adminga yozing.</i>")


# ═══════════════════════════════════════════════════════════════════
#  RICH XABAR ICHIDAGI TUGMALAR (Bot API 10.3)
# ═══════════════════════════════════════════════════════════════════
# Oddiy klaviaturadan farqi: bu tugmalar xabar MATNINING ichida turadi,
# ya'ni javobning kerakli joyiga qo'yish mumkin. Rich markdown ixtiyoriy
# HTML qabul qiladi, shuning uchun qo'shimcha parser kerak emas.
_RICH_BTN_ATTRS = {
    "url": "url", "callback_data": "data", "copy_text": "text",
    "switch_inline_query": "query", "switch_inline_query_current_chat": "query",
}


def _attr_value(raw) -> str:
    """Atribut qiymatini HTML atributiga XAVFSIZ joylaydi.

    ⚠️ QATOR AJRATUVCHI ALOHIDA: `html.escape()` uni tegmasdan qoldiradi,
    Telegram parseri esa atribut ichidagi XOM `\\n` ni ko'rib tegni o'sha
    yerda uzadi — natijada `<tg-button ...>` foydalanuvchiga xom matn
    bo'lib chiqadi (jonli nosozlik: ko'p qatorli kod uchun "Nusxa olish"
    tugmasi shunday buzilgan edi).
    `&#10;` esa parser uchun oddiy belgi, nusxa olinganda haqiqiy qator
    ajratuvchiga qaytadi — ya'ni kod ishlaydigan holda ko'chiriladi.
    """
    text = str(raw).replace("\r\n", "\n").replace("\r", "\n")
    return (html_escape(text, quote=True)
            .replace("\n", "&#10;")
            .replace("\t", "&#9;"))


def rich_button(label: str, *, type: str = "callback_data",
                style: str | None = None, **value) -> str:
    """Bitta <tg-button>. `value` — turga mos yagona qiymat.

    ⚠️ Birinchi parametr ATAYLAB `label`, `text` emas: `copy_text`
    turining o'z qiymati ham `text=` deb ataladi va ikkalasi to'qnashardi.

    Misollar:
        rich_button("Pro", type="callback_data", data="pro:open", style=BTN_SUCCESS)
        rich_button("Nusxa olish", type="copy_text", text="ABC123")
        rich_button("Tugagan", type="disabled")

    ⚠️ Matn HTML sifatida yoziladi — qochirish (escape) SHART, aks holda
    javobdagi `<` yoki `&` butun xabarni rad ettiradi.
    """
    attrs = [f'type="{html_escape(type, quote=True)}"']
    if style:
        attrs.append(f'style="{html_escape(style, quote=True)}"')
    attr_name = _RICH_BTN_ATTRS.get(type)
    if attr_name:
        raw = value.get(attr_name) or value.get("value") or ""
        attrs.append(f'{attr_name}="{_attr_value(raw)}"')
    # Yorliqda ham qator ajratuvchi bo'lmasin — u tugmani ikki qatorga
    # bo'lmaydi, shunchaki maketni buzadi.
    return (f"<tg-button {' '.join(attrs)}>"
            f"{html_escape(' '.join(str(label).split()))}</tg-button>")


def rich_button_row(buttons: list[str], align: str = "center") -> str:
    """<tg-button-row> — bir qatorda 1-8 tugma.

    ⚠️ 8 tadan ortiq tugma Telegram tomonidan rad etiladi (butun xabar
    bilan birga), shuning uchun bu yerda kesib qo'yiladi.
    """
    buttons = [b for b in buttons if b][:8]
    if not buttons:
        return ""
    if align not in ("left", "center", "right"):
        align = "center"
    return f'<tg-button-row align="{align}">{"".join(buttons)}</tg-button-row>'


def _downgrade_kb(kb: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup | None:
    """Klaviaturadan bezak maydonlarini olib tashlaydi (fallback uchun)."""
    if kb is None:
        return None

    # ⚠️ switch_inline_query ham KO'CHIRILADI: u tushib qolsa tugmada
    # birorta ham amal maydoni qolmaydi va Telegram BUTUN klaviaturani
    # rad etadi — ya'ni "chekinish" xabarni yo'q qilardi.
    #
    # ⚠️ `disabled` (10.3) ham AYNAN SHU sababdan ko'chiriladi: u tugma
    # turini belgilaydigan yagona maydon. Tashlab yuborilsa, o'chirilgan
    # tugma "amalsiz" bo'lib qolib, butun klaviaturani rad ettirardi.
    def _copy(b: InlineKeyboardButton) -> InlineKeyboardButton:
        kwargs = {
            "text": b.text,
            "callback_data": b.callback_data,
            "url": b.url,
            "switch_inline_query": b.switch_inline_query,
        }
        # aiogram 3.31 dan boshlab `disabled` — haqiqiy maydon, undan
        # oldin esa faqat extra edi; ikkalasi ham tekshiriladi.
        disabled = getattr(b, "disabled", None) or (b.model_extra or {}).get("disabled")
        if disabled is not None:
            kwargs = {"text": b.text, "disabled": disabled}
        return InlineKeyboardButton(**kwargs)

    rows = [[_copy(b) for b in row] for row in kb.inline_keyboard]
    # force_reply — bezak emas, oqimning bir qismi (foydalanuvchi javob
    # yozishi kutilyapti), shuning uchun chekinishda ham saqlanadi.
    extra = {}
    if getattr(kb, "force_reply", None) or (kb.model_extra or {}).get("force_reply"):
        extra["force_reply"] = True
    return InlineKeyboardMarkup(inline_keyboard=rows, **extra)


_TAG_RE = re.compile(r"<[^>]+>")


async def send_rich(target, text: str, kb: InlineKeyboardMarkup | None = None,
                    effect: str | None = None, **extra):
    """Bezakli xabar yuboradi va HAR QANDAY holatda yetkazib beradi.

    Bezaklar (effekt, tugma ranglari, premium emoji) — "bo'lsa yaxshi",
    lekin ular tufayli xabar UMUMAN yetib bormasligi qabul qilinmaydi:
    to'lov tasdig'i yoki limit xabari yo'qolsa, bu foydalanuvchi uchun
    haqiqiy muammo. Shuning uchun progressiv chekinish:

        1) to'liq bezak bilan
        2) effektsiz    (effekt faqat shaxsiy chatda ishlaydi)
        3) rangsiz      (eski mijoz/API bezak maydonlarini bilmasa)
        4) HTML'siz     (oxirgi chora — tekis matn)

    `extra` — qo'shimcha yuborish parametrlari (masalan guruh uchun
    `ephemeral_message_parameters`). ⚠️ Ular ham bezak hisoblanadi:
    butun zanjir qo'shimcha BILAN bir marta, keyin BUTUNLAY USIZ yana
    bir marta o'tiladi. Aks holda API qo'shimchani bilmasa (eski server),
    xabar hech qachon yetib bormasdi.
    """
    attempts = [
        {"parse_mode": "HTML", "reply_markup": kb, "message_effect_id": effect},
        {"parse_mode": "HTML", "reply_markup": kb},
        {"parse_mode": "HTML", "reply_markup": _downgrade_kb(kb)},
        {"reply_markup": _downgrade_kb(kb)},
    ]
    plain = _TAG_RE.sub("", text)
    rounds = [extra, {}] if extra else [{}]
    for round_extra in rounds:
        for i, kwargs in enumerate(attempts):
            if effect is None and i == 0:
                continue                  # effekt yo'q — birinchi urinish ortiqcha
            try:
                return await target.answer(plain if "parse_mode" not in kwargs else text,
                                           **kwargs, **round_extra)
            except Exception as exc:
                logger.debug(f"[Pro] yuborish urinishi {i + 1} "
                             f"(extra={bool(round_extra)}) muvaffaqiyatsiz: {exc}")
    logger.error("[Pro] xabar HECH QANDAY ko'rinishda yuborilmadi")


# ═══════════════════════════════════════════════════════════════════
#  1. INVOICE PAYLOAD
# ═══════════════════════════════════════════════════════════════════
# Format: "pro:<versiya>:<kun>:<oluvchi_id>"
#
# Telegram payload uchun 128 bayt beradi — bizga yetadi va ortadi.
# Versiya bor: narxlar yoki format o'zgarsa, foydalanuvchi telefonida
# osilib qolgan eski invoice pre_checkout'da tushunarli sabab bilan rad
# etiladi (jim qolib noto'g'ri tarif bermaydi).

def build_payload(days: int, beneficiary_id: int) -> str:
    return f"pro:{PRO_PAYLOAD_VERSION}:{days}:{beneficiary_id}"


def parse_payload(payload: str) -> tuple[int, int] | None:
    """(kun, oluvchi_id) yoki None.

    ATAYLAB SOF FUNKSIYA — bazaga ham, tarmoqqa ham tegmaydi. Telegram
    pre_checkout javobiga atigi 10 SONIYA beradi va javob kelmasa to'lov
    o'zi bekor bo'ladi; shuning uchun majburiy ish faqat satrni bo'lish
    bo'lishi kerak.
    """
    try:
        tag, version, days_raw, beneficiary_raw = payload.split(":")
    except (ValueError, AttributeError):
        return None
    if tag != "pro" or version != PRO_PAYLOAD_VERSION:
        return None
    try:
        days, beneficiary = int(days_raw), int(beneficiary_raw)
    except ValueError:
        return None
    if days not in PRO_PLANS_BY_DAYS or beneficiary <= 0:
        return None
    return days, beneficiary


# Oylik obuna: "prosub:<versiya>:<foydalanuvchi>:<narx>". Narx payload
# ICHIDA: har oylik yangilanish o'sha (obuna bo'lgan paytdagi) narxda
# keladi — keyin OBUNA_NARX o'zgarsa ham eski obunachining to'lovi
# «narx mos emas» deb rad etilmasin. Payloadni faqat bot yasaydi
# (createInvoiceLink), ya'ni narxni foydalanuvchi tanlay olmaydi.
def build_obuna_payload(user_id: int, stars: int) -> str:
    return f"prosub:{PRO_PAYLOAD_VERSION}:{user_id}:{stars}"


def parse_obuna_payload(payload: str) -> tuple[int, int] | None:
    """(foydalanuvchi_id, narx) yoki None. parse_payload kabi SOF."""
    try:
        tag, version, uid_raw, stars_raw = payload.split(":")
        uid, stars = int(uid_raw), int(stars_raw)
    except (ValueError, AttributeError):
        return None
    if tag != "prosub" or version != PRO_PAYLOAD_VERSION:
        return None
    # 10 000 — Telegram'ning obuna narxi chegarasi.
    if uid <= 0 or not 1 <= stars <= 10000:
        return None
    return uid, stars


def vaqt_html(dt: datetime, fmt: str = "d") -> str:
    """Bot API 9.5 `date_time`: Telegram sanani har kimga O'Z vaqt
    mintaqasi va tilida ko'rsatadi; ichidagi matn — eski mijozlar uchun.
    `fmt="t"` — faqat soat («14:32»)."""
    shakl = "%H:%M" if fmt == "t" else "%d.%m.%Y"
    return (f'<tg-time unix="{int(dt.timestamp())}" format="{fmt}">'
            f'{dt.astimezone(TIMEZONE).strftime(shakl)}</tg-time>')


# ═══════════════════════════════════════════════════════════════════
#  2. KLAVIATURALAR VA MATNLAR
# ═══════════════════════════════════════════════════════════════════

def _buy_buttons(beneficiary_id: int | None = None,
                 obuna: bool = False) -> list[list[InlineKeyboardButton]]:
    """Narx tugmalari — 2 ustunli panjara, eng foydalisi yashil rangda.

    beneficiary_id — sovg'a uchun (o'ziga bo'lsa None).
    obuna — tepada «har oy avtomatik» qatori. Sovg'ada HECH QACHON: obuna
    to'lovchining o'z balansidan har oy yechiladi.
    """
    if obuna and beneficiary_id is None:
        return [[btn(f"♻️ Har oy avtomatik · {OBUNA_NARX} ⭐", "pro:obuna",
                     style=BTN_SUCCESS)]] + _buy_buttons()
    suffix = f":{beneficiary_id}" if beneficiary_id else ""
    # Kun boshiga eng arzon tarif "tavsiya etilgan" sifatida ajratiladi —
    # bu ro'yxatdan HISOBLANADI, qo'lda belgilanmaydi, shuning uchun narx
    # o'zgarsa urg'u ham o'zi to'g'ri joyga ko'chadi.
    best = min(PRO_PLANS, key=lambda p: p[1] / p[0])[0]
    buttons = []
    for days, stars, title, badge in PRO_PLANS:
        label = f"{title} · {stars} ⭐"
        if badge:
            label += f"  {badge}"
        buttons.append(btn(
            label, f"pro:buy:{days}{suffix}",
            style=BTN_SUCCESS if days == best else BTN_PRIMARY,
        ))
    # Ikkitadan qatorlarga bo'lamiz — 4 ta tugma bir ustunda cho'zilib
    # ketgandan ko'ra ixcham panjara chiroyliroq va taqqoslash osonroq.
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)]


def pro_keyboard_for(plan_type: str) -> InlineKeyboardMarkup:
    """/profile ostidagi klaviatura — tarifga qarab.

    ⚠️ Promokod va referal tugmalari BU YERDA YO'Q — ular ATAYLAB ommaviy
    emas. Bepul olish yo'llari faqat admin yuborgan xabar orqali ochiladi
    (handlers/admin.py → 🎁 Bepul Pro), aks holda hamma bepul kutib
    o'tirardi va hech kim sotib olmasdi.
    """
    if plan_type == 'free':
        rows = [
            [btn("💎 Pro tarifga o'tish", "pro:open", style=BTN_SUCCESS)],
            [btn("🎁 Do'stga sovg'a qilish", "pro:gift")],
        ]
    elif plan_type == 'pro':
        rows = [
            [btn("➕ Muddatni uzaytirish", "pro:open", style=BTN_PRIMARY)],
            [btn("🎁 Sovg'a qilish", "pro:gift")],
        ]
    else:
        # Muddatsiz tarif — sotib olishning ma'nosi yo'q.
        rows = [[btn("🎁 Do'stga sovg'a qilish", "pro:gift", style=BTN_PRIMARY)]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _perks_block() -> str:
    """Pro imkoniyatlari — blockquote ichida (chap tomonda rangli chiziq).

    Raqamlar PLAN_LIMITS dan HISOBLANADI: limitni o'zgartirsangiz reklama
    matni ham o'zi to'g'rilanadi va yolg'on va'da paydo bo'lmaydi.
    """
    # Bir imkoniyat — bir qator (ilgari 7 ta imkoniyat 14 qator olardi va
    # /research, vazifalar, /kunlik, Business umuman ko'rinmasdi).
    # To'liq ro'yxat izohi bilan — /help → Pro (handlers/capabilities.py).
    pro_pts, free_pts = daily_limit('pro', 'points'), daily_limit('free', 'points') or 1
    return (
        "<blockquote>"
        f"⚡️ <b>{f'{pro_pts:,}'.replace(',', ' ')} ball</b>/kun — bepuldan {pro_pts // free_pts}× ko'p\n"
        f"{pe('document', '📄')} <b>{daily_limit('pro', 'files')} ta fayl</b>/kun, "
        f"{DOCUMENT_MAX_SIZE_PRO // (1024 * 1024)} MB gacha hujjat\n"
        f"{pe('photo', '🖼')} <b>{daily_limit('pro', 'images')} ta rasm</b>/kun — chizish va tahrirlash\n"
        f"🔎 <b>/research</b> — 10+ manbali PDF hisobot\n"
        f"⏰ <b>Takroriy eslatma va vazifalar</b> — «har kuni 9 da kursni yubor»\n"
        f"📰 <b>/kunlik</b> — o'z mavzularingizda daydjest\n"
        f"💼 <b>Telegram Business</b> — mijozlaringizga javob beraman\n"
        f"🧠 Chuqur fikrlash · {XOTIRA} · {pe('voice', '🎙')} tabiiy ovoz"
        "</blockquote>"
    )


def _daily_table() -> str:
    """Kunlik hisobda "bepul → Pro" taqqoslashi, premium emoji bilan."""
    pro_pts = daily_limit('pro', 'points')
    rows = [
        (pe('text', '✉️'), "Matnli savol", MESSAGE_COST_TEXT),
        (pe('photo', '🖼'), "Rasm tahlili", MESSAGE_COST_PHOTO),
        (pe('voice', '🎤'), "Ovozli xabar", MESSAGE_COST_VOICE),
        (pe('document', '📄'), "Hujjat tahlili", MESSAGE_COST_DOCUMENT),
    ]
    lines = [
        f"{icon} {name} — <s>{(daily_limit('free', 'points') or 0) // cost}</s> → <b>{pro_pts // cost} ta</b>"
        for icon, name, cost in rows
    ]
    return "<blockquote expandable>" + "\n".join(lines) + "</blockquote>"


def _display_name(profile: dict, user_id: int) -> str:
    """@username yoki ID. get_full_user_profile() username o'rniga
    "Mavjud emas" qaytarishi mumkin — shuni ham hisobga oladi."""
    username = profile.get("username")
    if username and username != "Mavjud emas":
        return f"@{username}"
    return f"<code>{user_id}</code>"


def _days_left(premium_until) -> int:
    if premium_until is None:
        return 0
    return max(0, (premium_until - datetime.now(timezone.utc)).days)


async def _obuna(user_id: int) -> dict | None:
    """Obuna holati; baza javob bermasa None — ekran obunasiz chiziladi."""
    try:
        return await database.pro_obuna_ol(user_id)
    except Exception as exc:
        logger.warning(f"[Pro] obuna holati o'qilmadi (user={user_id}): {exc}")
        return None


def _obuna_faol(ob: dict | None) -> bool:
    return bool(ob) and ob.get("holat") == "faol"


async def _render_pro_screen(user_id: int, ixcham: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    """Pro ekrani; ochiq karta to'lovi bo'lsa — tepasida uning holati.
    `ixcham` — vidjet izohi (`pro_ekranini_yubor`): jadval va halqa kartada."""
    text, kb = await _pro_ekrani(user_id, ixcham)
    try:
        r = await database.karta_faol_sorov(user_id, KARTA_CHEK_OYNA)
    except Exception as e:
        logger.warning(f"[Karta] ochiq to'lov o'qilmadi (user={user_id}): {e}")
        r = None
    if r:
        blok, tugma = karta_holat_matni(r)
        text = blok + text
        if tugma:
            kb = InlineKeyboardMarkup(inline_keyboard=[tugma] + kb.inline_keyboard)
    return text, kb


async def _pro_ekrani(user_id: int, ixcham: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    ob = await _obuna(user_id)
    profile = await database.get_full_user_profile(user_id)
    plan_type = (profile or {}).get('plan_type') or 'free'
    premium_until = (profile or {}).get('premium_until')
    # Muddati o'tgan, watcher hali tushirmagan — «FAOL · 0 kun» emas, sotuv ekrani.
    if plan_type != 'free' and premium_until is not None \
            and premium_until < datetime.now(timezone.utc):
        plan_type = 'free'
    karta_bor = bool(await _karta())
    # Ixcham (karta izohi): ajratuvchi chiziq va «👇 … tanlang» satri YO'Q.
    # Jonli (iPhone, 2026-11-11): karta tariflar ekraniga o'tganda izoh eskicha
    # «To'lov usulini tanlang» deb qolardi (izoh almashmaydi), chiziq esa
    # telefonda karta ostida uzun to'siq bo'lib turardi.
    chiziq = "" if ixcham else "━━━━━━━━━━━━━━━━━━━━\n"

    # Muddatsiz tarif — sotib olishning ma'nosi yo'q va uni toza qo'llash
    # ham mumkin emas, shuning uchun narx tugmalari umuman ko'rsatilmaydi.
    if plan_type != 'free' and premium_until is None:
        text = (
            "💎 <b>SIZDA MUDDATSIZ TARIF</b>\n"
            f"{chiziq}\n"
            "<blockquote>Hech qanday kunlik cheklov qo'llanilmaydi.\n"
            "Sotib olishning hojati yo'q — bemalol foydalanavering 🙌</blockquote>"
        )
        return text, InlineKeyboardMarkup(inline_keyboard=[
            [btn("🎁 Do'stga sovg'a qilish", "pro:gift", style=BTN_PRIMARY)],
            [btn("✖️ Yopish", "pro:close", style=BTN_DANGER)],
        ])

    if plan_type != 'free' and _obuna_faol(ob):
        # Obuna o'zi uzayadi: «uzaytiring» va narx tugmalari ikkinchi
        # to'lovga undardi — o'rniga keyingi yechish sanasi va o'chirish.
        keyingi = (f"Keyingi to'lov: <b>{vaqt_html(ob['keyingi'])}</b> · {ob['narx']} ⭐\n"
                   if ob.get("keyingi") else "")
        text = (
            f"💎 <b>PRO TARIFINGIZ FAOL</b>\n"
            f"{chiziq}\n"
            + ("" if ixcham else f"{_progress_ring(_days_left(premium_until), obuna=True)}\n\n")
            + f"<blockquote>♻️ <b>Oylik obuna yoqilgan</b> — Pro har oy o'zi uzayadi.\n"
            f"{keyingi}"
            f"O'chirsangiz, to'langan muddat oxirigacha ishlaydi.</blockquote>"
        )
        return text, InlineKeyboardMarkup(inline_keyboard=[
            [btn("🎁 Do'stga sovg'a qilish", "pro:gift")],
            [btn("🔕 Avtomatik to'lovni o'chirish", "pro:obuna_bekor")],
            [btn("✖️ Yopish", "pro:close", style=BTN_DANGER)],
        ])

    if plan_type != 'free':
        days_left = _days_left(premium_until)
        header = (
            f"💎 <b>PRO TARIFINGIZ FAOL</b>\n"
            f"{chiziq}\n"
            + ("" if ixcham else f"{_progress_ring(days_left)}\n\n")
            + f"<blockquote>♻️ Muddatni istalgan vaqtda uzaytirishingiz mumkin.\n"
            f"Yangi kunlar qolganiga <b>qo'shiladi</b> — yonib ketmaydi.</blockquote>"
            + ("" if ixcham else "\n\n👇 <b>Uzaytirish:</b>")
        )
        extra = [[btn("🎁 Do'stga sovg'a qilish", "pro:gift")]]
    else:
        header = (
            f"💎 <b>PRO TARIF</b>\n"
            f"{chiziq}\n"
            # Ixcham (vidjet izohi): taqqoslash kartada; imkoniyatlar yig'iq
            # holda shu yerda qoladi — vidjetni bilmaydigan ilova uchun.
            + (_perks_block().replace("<blockquote>", "<blockquote expandable>", 1)
               if ixcham else
               f"{_perks_block()}\n"
               f"📊 <b>Kunlik hisobda</b>  <i>(ochish uchun bosing)</i>\n"
               f"{_daily_table()}\n"
               + (f"⭐️ <b>Telegram Stars</b> yoki 💳 <b>karta orqali</b> so'mda to'lash mumkin.\n\n"
                  f"👇 <b>To'lov usulini tanlang:</b>" if karta_bor else
                  f"⭐️ To'lov <b>Telegram Stars</b> orqali — "
                  f"bank kartasi kerak emas, bir bosishda.\n\n"
                  f"👇 <b>Muddatni tanlang:</b>"))
        )
        # ⚠️ Promokod/referal tugmalari ATAYLAB yo'q — pro_keyboard_for()
        # izohiga qarang.
        extra = [[btn("🎁 Do'stga sovg'a qilish", "pro:gift")]]

    # Karta bor — avval usul (Stars | Karta), muddat ichkarida; yo'q bo'lsa
    # bitta tanlovli menyu ma'nosiz, Stars muddatlari darrov chiqadi.
    tolov = ([[btn("⭐️ Stars orqali", "pro:stars", style=BTN_PRIMARY)],
              [btn("💳 Karta orqali (so'mda)", "pro:kartalar", style=BTN_PRIMARY)]]
             if karta_bor else _buy_buttons(obuna=True))
    rows = tolov + extra + [[btn("✖️ Yopish", "pro:close", style=BTN_DANGER)]]
    return header, InlineKeyboardMarkup(inline_keyboard=rows)


_ORQAGA = [btn("⬅️ Orqaga", "pro:usul")]


async def _tugmalarni_almashtir(query: CallbackQuery, kb: InlineKeyboardMarkup,
                                matn: str) -> None:
    """Pro ekranining matni qoladi, faqat tugmalar almashadi. Tahrirlab
    bo'lmasa (xabar o'chgan va h.k.) — yangi xabar."""
    try:
        await query.message.edit_reply_markup(reply_markup=kb)
    except Exception as e:
        if "not modified" in str(e):      # ikki marta bosildi — tugmalar joyida
            return
        await query.message.answer(matn, parse_mode="HTML", reply_markup=kb)


_RING_SCALE = 30    # bir oy — chiziqchaning to'liq uzunligi


def _progress_ring(days_left: int, obuna: bool = False) -> str:
    """Qolgan muddatni vizual chiziqcha bilan ko'rsatadi.

    Mos yozuvlar nuqtasi — BIR OY, eng uzun tarif emas. Aks holda yillik
    tarif olgan odamga 43 kun qolganda deyarli bo'sh chiziqcha ko'rinib,
    "tugab qolibdi" degan noto'g'ri taassurot berardi. Bir oydan ko'p
    qolgan bo'lsa chiziqcha to'la — bu haqiqatan ham "xotirjam" holat.
    """
    filled = max(1, min(10, round(min(days_left, _RING_SCALE) / _RING_SCALE * 10)))
    bar = "█" * filled + "░" * (10 - filled)
    if obuna:
        warn = ""            # o'zi uzayadi — «tugayapti» yolg'on bo'lardi
    elif days_left <= 3:
        warn = "\n\n⚠️ <b>Muddat tugayapti — hozir uzaytiring!</b>"
    elif days_left <= 7:
        warn = "\n\n🔔 Bir haftadan kam qoldi."
    else:
        warn = ""
    return f"<code>{bar}</code>\n⏳ Qolgan muddat: <b>{days_left} kun</b>{warn}"


# ═══════════════════════════════════════════════════════════════════
#  3. FOYDALANUVCHI HANDLERLARI
# ═══════════════════════════════════════════════════════════════════

def _son(x) -> str:
    """None — cheksiz, 0 — tarifda yo'q."""
    return "∞" if x is None else "—" if not x else f"{x:,}".replace(",", " ")


def pro_qatorlari() -> list:
    """Kartadagi bepul/Pro taqqoslash — `_perks_block()` va `_daily_table()`
    bilan BITTA manba (PLAN_LIMITS): limit o'zgarsa karta ham o'zgaradi.
    "Savol" va "rasm tahlili" — o'sha ballga necha marta (`_daily_table`)."""
    def har(tarif, narx):
        ball = daily_limit(tarif, 'points')
        return None if ball is None else ball // narx
    q = [["⚡", "Ball / kun", _son(daily_limit('free', 'points')), _son(daily_limit('pro', 'points'))],
         ["💬", "Matnli savol", _son(har('free', MESSAGE_COST_TEXT)), _son(har('pro', MESSAGE_COST_TEXT))],
         ["📸", "Rasm tahlili", _son(har('free', MESSAGE_COST_PHOTO)), _son(har('pro', MESSAGE_COST_PHOTO))]]
    for belgi, nom, kalit in (("📄", "Fayl yaratish", "files"), ("🎨", "Rasm chizish", "images"),
                              ("🔬", "Tadqiqot (PDF)", "research")):
        q.append([belgi, nom, _son(daily_limit('free', kalit)), _son(daily_limit('pro', kalit))])
    # Kod Pro'ga bog'lagan imkoniyatlar: takroriy eslatma (_run_reminder_task),
    # /kunlik (digest._pro_faol), Business (biznes).
    return q + [["⏰", "Takroriy eslatma", "—", "✓"], ["📰", "/kunlik", "—", "✓"],
                ["💼", "Business", "—", "✓"]]


def tarif_plitkalari(tur: str) -> list:
    """Kartadagi tarif plitkalari: [nom, narx, izoh, chegirma, eng foydali, kun].
    Plitka BOSILADI: kun — `pro:buy:<kun>` / `pro:karta:<kun>` (ostidagi tugmaning o'zi).
    `tur` — "s" Stars yoki "k" karta (so'm). Ostidagi TUGMALAR bilan bitta
    manba: `PRO_PLANS` / `KARTA_NARX`, eng foydalisi `_buy_buttons()` dagi
    qoida (kun boshiga eng arzon) — karta tugmadan boshqa narsa demasin."""
    best = min(PRO_PLANS, key=lambda p: p[1] / p[0])[0]
    out = []
    for days, stars, title, badge in PRO_PLANS:
        narx = stars if tur == "s" else KARTA_NARX[days]
        birlik = " ⭐" if tur == "s" else " so'm"
        izoh = f"{days} kun"
        if days != 30:
            # Bo'linmas bo'shliq: tor telefonda «20 / 833 so'm» bo'lib uzilmasin.
            oyiga = f"{som(round(narx * 30 / days))}{birlik}".replace(" ", " ")
            izoh += f" · oyiga ≈ {oyiga}"
        out.append([title, som(narx) + birlik, izoh, badge, 1 if days == best else 0, days])
    return out


def _sana(dt) -> str:
    return f"{dt.astimezone(database.TASHKENT_TZ):%d.%m.%Y}"


async def pro_kartasi(user_id: int, ekran: str = "") -> dict:
    """Pro kartasining holati — `_pro_ekrani()` dagi tarif qoidasining o'zi:
    muddati o'tgan Pro — bepul, muddatsiz — "m", obuna — keyingi to'lov.
    `ekran`: "" asosiy, "s" Stars / "k" karta tariflari (services/vidjet.py —
    kalitlar). Obunani o'chirish tasdig'i — faqat xabar ostidagi tugmalarda:
    kartada asosiy ekran qoladi (alohida ekran 4 KB ga sig'madi)."""
    profile = await database.get_full_user_profile(user_id) or {}
    plan_type = profile.get('plan_type') or 'free'
    muddat = profile.get('premium_until')
    if plan_type != 'free' and muddat is not None and muddat < datetime.now(timezone.utc):
        plan_type = 'free'
    h = "f" if plan_type == 'free' else "m" if muddat is None else "p"
    # "kb" — karta sozlangan: kartada «💳 Karta» tugmasi (xabar ostidagi kabi).
    kb = {"kb": 1} if await _karta() else {}
    if ekran == "s":
        d = {"e": "s", "h": h, "t": tarif_plitkalari("s"), **kb}
        # Obuna qatori — `_buy_buttons(obuna=...)` bilan bir xil shart.
        if not _obuna_faol(await _obuna(user_id)):
            d["ob"] = OBUNA_NARX
        return d
    if ekran == "k":
        return {"e": "k", "h": h, "t": tarif_plitkalari("k"), **kb}
    d = {"r": pro_qatorlari(), **kb}
    if h != "p":
        return {**d, "h": h}
    d.update(h="p", k=_days_left(muddat), n=_sana(muddat))
    ob = await _obuna(user_id)
    if _obuna_faol(ob):
        d["o"] = 1
        if ob.get("keyingi"):
            d["n"] = _sana(ob["keyingi"])
    return d


async def _pro_ekrani_almashtir(query: CallbackQuery, user_id: int, ekran: str) -> None:
    """Tugmalar almashgach — Pro kartasi ham o'sha ekranga (o'sha xabarda).
    Xabar karta bo'lmasa (eski matnli ekran) — hech narsa. Xato tugma
    ishini buzmaydi: tugmalar allaqachon almashgan."""
    from handlers.messages import vidjet_xabari
    if vidjet_xabari(query.message) is None:
        return
    try:
        await _pro_holatini_yoz(query, await pro_kartasi(user_id, ekran))
    except Exception as e:
        logger.info(f"[Pro] karta ekrani almashmadi (user={user_id}): {e}")


async def _pro_holatini_yoz(query: CallbackQuery, holat: dict) -> None:
    """Berilgan holatni shu xabardagi Pro kartasiga yozadi (karta bo'lmasa —
    hech narsa). Hech qachon ko'tarilmaydi."""
    from handlers.messages import vidjet_holatini_yoz
    from services import vidjet
    try:
        await vidjet_holatini_yoz(query.message, vidjet.pro_holati(holat))
    except Exception as e:
        logger.info(f"[Pro] karta holati yozilmadi: {e}")


def _korinadigan(matn: str) -> int:
    """Telegram izoh chegarasini teglar va entity'larsiz sanaydi."""
    return len(html.unescape(re.sub(r"<[^>]+>", "", matn)))


async def _pro_vidjeti(message: Message, user_id: int, ekran: str = "",
                      kb: InlineKeyboardMarkup | None = None) -> int | bool:
    """Shaxsiy chatda Pro ekrani — karta vidjeti, izohi ixcham matn,
    tugmalari O'SHA (to'lov yo'li o'zgarmaydi). `ekran`/`kb` — darhol
    muddatlar ekrani (karta bekor qilingach, invoice'dan «Orqaga»). Qaytadi:
    xabar id'si / True (timeout — yetgan bo'lishi mumkin, takror yo'q).
    False — chaqiruvchi oddiy ekranni yuboradi: rad etilgan premium emoji
    ham shu yerda `send_rich` ning pasaytirish zinasiga tushadi."""
    from handlers.messages import OUTCOME_UNKNOWN, _telegram_api_request, _thread_key, xabar_id
    from services import vidjet
    text, asosiy = await _render_pro_screen(user_id, ixcham=True)
    if _korinadigan(text) > vidjet.CAPTION_MAX:
        return False
    # `allow_queries` — kartadagi plitka va tugmalar bosiladi (`profile.vidjet_amali`).
    payload = {"chat_id": message.chat.id, "html": vidjet.pro_html(), "allow_queries": True,
               "chat_data": vidjet.pro_holati(await pro_kartasi(user_id, ekran)),
               "caption": text, "parse_mode": "HTML", "show_caption_above_media": False,
               "reply_markup": (kb or asosiy).model_dump(exclude_none=True)}
    if tid := _thread_key(message):
        payload["message_thread_id"] = tid
    outcome: list = []
    if (r := await _telegram_api_request("sendWidget", payload, outcome=outcome)) is not None:
        return xabar_id(r) or True
    return OUTCOME_UNKNOWN in outcome


async def pro_ekranini_yubor(message: Message, user_id: int, ekran: str = "",
                             kb: InlineKeyboardMarkup | None = None) -> None:
    """/pro, «💎 Pro tarifga o'tish», /start pro — bitta yo'l. Karta faqat
    shaxsiy chatda (production'da vidjet boshqa joyda yo'q); har qanday
    xatoda — oddiy matnli ekran: bezak sotuvni hech qachon to'xtatmasin.
    Chatdagi oldingi ekran (eski Pro, profil...) o'chadi — `ekran_almashtir`."""
    from handlers.messages import ekran_almashtir
    if getattr(getattr(message, "chat", None), "type", None) == "private":
        try:
            if (n := await _pro_vidjeti(message, user_id, ekran, kb)):
                await ekran_almashtir(message.chat.id, n)
                return
        except Exception as e:
            logger.warning(f"[Pro] karta yuborilmadi (user={user_id}): {e}")
    text, asosiy = await _render_pro_screen(user_id)
    if ekran == "k":
        text = karta_tariflar_matni()
    m = await send_rich(message, text, kb or asosiy)
    await ekran_almashtir(getattr(getattr(message, "chat", None), "id", 0) or 0, m)


async def handle_pro(message: Message, state: FSMContext):
    await state.clear()
    await pro_ekranini_yubor(message, message.from_user.id)


async def _send_invoice(chat_id: int, days: int, beneficiary_id: int,
                        is_gift: bool = False):
    """Stars invoice. «⬅️ Orqaga» — muddatlar ekraniga (invoice o'chadi):
    to'lamay qaytgan odamning chatida osilib qolgan invoice qolmaydi.
    ⚠️ To'lov tugmasi BIRINCHI turishi shart (Bot API)."""
    stars, title, _ = PRO_PLANS_BY_DAYS[days]
    prefix = "🎁 Pro sovg'a" if is_gift else "Pro tarif"
    return await bot.send_invoice(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐️ {stars} Stars to'lash", pay=True)],
            [btn("⬅️ Orqaga", f"pro:orqa:{beneficiary_id}" if is_gift else "pro:orqa")]]),
        chat_id=chat_id,
        title=f"{prefix} — {title}",
        description=(
            f"{daily_limit('pro', 'points')} ball/kun · "
            f"{daily_limit('pro', 'files')} fayl/kun · "
            f"chuqur fikrlash · {XOTIRA}"
        ),
        payload=build_payload(days, beneficiary_id),
        # Stars uchun provider_token BO'SH SATR bo'lishi shart (None emas),
        # currency esa aynan "XTR".
        provider_token="",
        currency="XTR",
        # ⚠️ XTR'da amount — bu stars soni, ×100 EMAS.
        prices=[LabeledPrice(label=f"Pro {title}", amount=stars)],
    )


# ═══════════════════════════════════════════════════════════════════
#  4. TO'LOV OQIMI
# ═══════════════════════════════════════════════════════════════════

def tolov_shartlari(payload: str) -> tuple[int, int, int, bool] | None:
    """(kun, oluvchi, kutilgan narx, obunami) — bir martalik xarid ham, oylik
    obuna ham. pre_checkout va successful_payment BIR XIL shartni o'qisin."""
    ob = parse_obuna_payload(payload)
    if ob:
        return OBUNA_KUN, ob[0], ob[1], True
    parsed = parse_payload(payload)
    if parsed is None:
        return None
    days, beneficiary = parsed
    return days, beneficiary, PRO_PLANS_BY_DAYS[days][0], False


async def handle_pre_checkout(query: PreCheckoutQuery):
    """Telegram'ning oxirgi so'rovi: "shu to'lovni qabul qilamizmi?"

    ⏱ 10 soniya ichida JAVOB BERILISHI SHART, aks holda to'lov bekor
    bo'ladi. Shuning uchun majburiy ish faqat sof payload tekshiruvi;
    bazaga murojaat qat'iy timeout ichida va FAIL-OPEN.
    """
    shart = tolov_shartlari(query.invoice_payload or "")
    if shart is None:
        await query.answer(
            ok=False,
            error_message="To'lov ma'lumoti eskirgan. /pro dan qayta boshlang.",
        )
        return

    days, beneficiary, stars, obuna = shart
    if obuna and query.from_user.id != beneficiary:
        # Obuna to'lovchining O'Z balansidan har oy yechiladi — boshqaning
        # obuna havolasini ochgan odam unga yashirin oylik to'lovchi bo'lmasin.
        await query.answer(ok=False, error_message="Bu obuna havolasi sizniki emas. /pro dan oching.")
        return
    if query.total_amount != stars:
        # Telefonda osilib qolgan eski invoice, narx esa o'zgargan.
        await query.answer(
            ok=False,
            error_message="Narx yangilandi. /pro dan qayta boshlang.",
        )
        return

    # Ban tekshiruvi — TO'LOVCHI va OLUVCHI ikkalasi ham. To'lovchi
    # banlangan bo'lsa, u pul to'lab ham botdan foydalana olmaydi; oluvchi
    # banlangan bo'lsa, sovg'a bekorga ketadi. Ikkalasi ham keyin refund
    # talab qiladigan holat, shuning uchun shu yerda to'xtatamiz.
    #
    # FAIL-OPEN: baza 3 soniyada javob bermasa to'lovni RAD ETMAYMIZ —
    # mijozni yo'qotgandan ko'ra qabul qilib, kerak bo'lsa keyin
    # refundStarPayment qilgan afzal (bu ataylab qabul qilingan qaror).
    payer = query.from_user.id
    to_check = {payer, beneficiary}
    try:
        banned = await asyncio.wait_for(
            asyncio.gather(*(database.is_banned(uid) for uid in to_check)),
            timeout=3.0)
        if any(banned):
            await query.answer(
                ok=False,
                error_message=f"Hisob bloklangan. Admin bilan bog'laning: @{ADMIN_USERNAME}",
            )
            return
    except Exception as exc:
        logger.warning(f"[Pro] pre_checkout ban tekshiruvi o'tmadi (fail-open): {exc}")

    await query.answer(ok=True)


async def _alert_admin(payer_id: int, charge_id: str, payload: str,
                       stars: int, problem: str) -> None:
    """To'lov bilan muammo — superadminni darhol xabardor qilamiz.

    Bu xabar YO'QOLMASLIGI muhim: uning ichida qo'lda tiklash uchun kerakli
    hamma narsa bor (kim to'lagan, qancha, qaysi chek).
    """
    text = (
        f"🚨 <b>TO'LOV MUAMMOSI</b>\n\n"
        f"Sabab: <b>{problem}</b>\n"
        f"To'lovchi: <code>{payer_id}</code>\n"
        f"Miqdor: <b>{stars} ⭐</b>\n"
        f"Chek: <code>{charge_id}</code>\n"
        f"Payload: <code>{payload}</code>\n\n"
        f"➡️ Tarifni qo'lda berish: Panel → Foydalanuvchilar → shu ID → Muddatni belgilash"
    )
    try:
        admin_id = await database.get_superadmin_id()
        if admin_id:
            await bot.send_message(admin_id, text, parse_mode="HTML")
            return
    except Exception:
        pass
    # Superadmin topilmasa ham xabar log'da qolsin.
    logger.error(f"[Pro] ADMINGA YETMAGAN OGOHLANTIRISH: {text}")


# ── Kunlik solishtiruv: Telegram'dagi Stars tushumi ↔ `star_payments` ──
# `grant_paid_pro` to'lov va tarifni bitta tranzaksiyada yozadi, lekin u
# YIQILSA (2026-09-25 … 10-30: `str(days)` → DataError) pul Telegram'da,
# bazada esa hech narsa yo'q — va buni besh hafta hech kim sezmadi.
# Bu tekshiruv bazaga emas, TELEGRAM'ning o'z ro'yxatiga qaraydi.
STARS_SOLISHTIR_BOSHI = datetime(2026, 9, 20, tzinfo=timezone.utc)   # birinchi yurish
STARS_SOLISHTIR_ORALIQ = 24 * 3600
_STARS_KUTISH = timedelta(minutes=15)    # endi kelgan to'lov — grant hali yo'lda bo'lishi mumkin
_STARS_SAHIFA_MAX = 50                   # 50 × 100 tranzaksiya — cheksiz sikl bo'lmasin


async def _stars_tushumlar(b, dan: datetime, gacha: datetime) -> list:
    """Bot'ning (dan, gacha] oralig'idagi foydalanuvchi to'lovlari.
    Telegram ro'yxatni ESKIDAN yangiga beradi — oxirigacha varaqlanadi."""
    natija, offset = [], 0
    for _ in range(_STARS_SAHIFA_MAX):
        sahifa = (await b.get_star_transactions(offset=offset, limit=100)).transactions
        for t in sahifa:
            s = t.source
            if (getattr(s, "type", None) == "user"
                    and getattr(s, "transaction_type", None) == "invoice_payment"
                    and dan < t.date <= gacha):
                natija.append(t)
        if len(sahifa) < 100:
            break
        offset += 100
    return natija


async def stars_solishtir() -> int:
    """Pul olingan, lekin `star_payments` da yo'q to'lovlar → superadminga.
    Qaytaradi: topilgan muammoli to'lovlar soni. Oyna `(oxirgi, hozir − 15 daq]`
    va bazada saqlanadi — deploy takroriy xabar ham, bo'shliq ham bermaydi."""
    from handlers import eski_bot
    dan = await database.stars_tekshirildi_ol() or STARS_SOLISHTIR_BOSHI
    gacha = datetime.now(timezone.utc) - _STARS_KUTISH
    botlar = [(bot, BOT_USERNAME or "vexonai")]
    if os.getenv("ESKI_BOT_TOKEN", "").strip():
        if eski_bot._bot is None:
            # Eski bot hali ulanmagan — uning to'lovlarini o'tkazib yubormaslik
            # uchun oyna SURILMAYDI, keyingi safar qayta urinamiz.
            logger.warning("[Stars] eski bot tayyor emas — solishtiruv keyinga")
            return 0
        botlar.append((eski_bot._bot, eski_bot._eski_nom))
    tushum = []
    for b, nom in botlar:
        tushum += [(t, nom) for t in await _stars_tushumlar(b, dan, gacha)]
    bor = await database.star_payments_bor([t.id for t, _ in tushum])
    yoq = [(t, nom) for t, nom in tushum if t.id not in bor]
    for t, nom in yoq:
        await _alert_admin(t.source.user.id, t.id, t.source.invoice_payload or "", t.amount,
                           f"Pro BERILMAGAN (kunlik solishtiruv) · @{nom} · "
                           f"{t.date.astimezone(TIMEZONE):%d.%m.%Y %H:%M}. Pul Telegram'da bor, "
                           f"bazada yo'q — qo'lda bergan bo'lsangiz, e'tibor bermang")
    await database.stars_tekshirildi_yoz(gacha)
    logger.info(f"[Stars] solishtiruv {dan:%d.%m %H:%M} → {gacha:%d.%m %H:%M}: "
                f"{len(tushum)} to'lov, {len(yoq)} tasi bazada yo'q")
    return len(yoq)


async def stars_solishtir_watcher() -> None:
    """main.py fonda. Har soat «24 soat o'tdimi?» — vaqt bazada, ya'ni
    kuniga bir necha deploy jadvalni buzmaydi."""
    await asyncio.sleep(600)      # deploydan keyin baza va eski bot ulansin
    while True:
        try:
            oxirgi = await database.stars_tekshirildi_ol()
            if oxirgi is None or (datetime.now(timezone.utc) - oxirgi).total_seconds() \
                    >= STARS_SOLISHTIR_ORALIQ:
                await stars_solishtir()
        except Exception:
            logger.exception("[Stars] solishtiruv yiqildi")
        await asyncio.sleep(3600)


async def handle_successful_payment(message: Message):
    """To'lov muvaffaqiyatli o'tdi — tarifni beramiz.

    ⚠️ Bu handler main.py'da dp.message'ga TO'G'RIDAN-TO'G'RI yoziladi,
    chunki generating_state_router'dagi busy_handler kontent filtrisiz va
    bu xabarni yutib yuborardi.
    """
    sp = message.successful_payment
    payer = message.from_user.id
    charge_id = sp.telegram_payment_charge_id
    payload = sp.invoice_payload or ""

    shart = tolov_shartlari(payload)
    if shart is not None and shart[3] and shart[1] != payer:
        shart = None         # obuna faqat o'ziga (pre_checkout ham shuni tekshiradi)
    if shart is None:
        # Pul olindi, lekin nima sotganimizni bilmaymiz. JIM QOLMAYMIZ.
        await _alert_admin(payer, charge_id, payload, sp.total_amount, "payload noto'g'ri")
        await _safe_send(message, (
            f"✅ To'lovingiz qabul qilindi.\n"
            f"🧾 Chek: <code>{charge_id}</code>\n\n"
            f"⚙️ Faollashtirish qo'lda bajariladi — admin xabardor qilindi. "
            f"Pulingiz yo'qolmaydi."
        ))
        return

    days, beneficiary, expected_stars, is_obuna = shart

    # ⚠️ CHUQUR HIMOYA: pre_checkout allaqachon tekshirgan, lekin grant —
    # bu pul evaziga xizmat berish nuqtasi, shuning uchun bu yerda ham
    # mustaqil tekshiramiz. Agar biror kun payloadni yasash yoki
    # pre_checkout mantiqi buzilsa, bu yerda to'xtaydi.
    if sp.currency != "XTR" or sp.total_amount != expected_stars:
        logger.error(
            f"[Pro] TO'LOV MOS EMAS: currency={sp.currency!r} "
            f"amount={sp.total_amount} kutilgan={expected_stars} charge={charge_id}")
        await _alert_admin(payer, charge_id, payload, sp.total_amount,
                           f"summa/valyuta mos emas ({sp.currency} {sp.total_amount}, "
                           f"kutilgan XTR {expected_stars})")
        await _safe_send(message, (
            f"✅ To'lovingiz qabul qilindi.\n"
            f"🧾 Chek: <code>{charge_id}</code>\n\n"
            f"⚙️ Tekshiruv talab qilinadi — admin xabardor qilindi. "
            f"Pulingiz yo'qolmaydi."
        ))
        return

    obuna = None
    if is_obuna:
        gacha = (datetime.fromtimestamp(sp.subscription_expiration_date, timezone.utc)
                 if sp.subscription_expiration_date else None)
        yangi = bool(sp.is_first_recurring)
        eski = await _obuna(payer)
        # Ikkinchi parallel obuna (ikki havola ochib ikkalasini to'lagan):
        # Telegram ikkalasini ham har oy yechardi. Bu to'lov o'z 30 kunini
        # beradi, obunaning O'ZI esa pastda o'chiriladi.
        ikkinchi = (yangi and _obuna_faol(eski) and eski["charge_id"] != charge_id
                    and (eski.get("keyingi") is None
                         or eski["keyingi"] > datetime.now(timezone.utc)))
        obuna = {"gacha": gacha, "yangi": yangi, "ikkinchi": ikkinchi}

    try:
        fresh = await database.grant_paid_pro(
            charge_id=charge_id, payer_id=payer, beneficiary_id=beneficiary,
            stars=sp.total_amount, days=days, payload=payload, obuna=obuna,
        )
    except Exception as e:
        logger.exception(f"[Pro] grant_paid_pro muvaffaqiyatsiz (charge={charge_id}): {e}")
        await _alert_admin(payer, charge_id, payload, sp.total_amount, "baza xatosi")
        await _safe_send(message, (
            f"✅ To'lovingiz qabul qilindi.\n"
            f"🧾 Chek: <code>{charge_id}</code>\n\n"
            f"⚙️ Faollashtirishda texnik nosozlik yuz berdi — admin xabardor "
            f"qilindi va tez orada hal qilinadi. <b>Pulingiz yo'qolmaydi.</b>"
        ))
        return

    if not fresh:
        # Telegram update'ni takroran yubordi — foydalanuvchi tasdiqni
        # allaqachon olgan, ikkinchi marta bezovta qilmaymiz.
        logger.info(f"[Pro] takroriy successful_payment e'tiborsiz qoldirildi: {charge_id}")
        return

    # Pro buyruqlarini DARHOL menyuga qo'shamiz — aks holda ular
    # foydalanuvchi keyingi xabarini yozgandagina paydo bo'lardi va yangi
    # sotib olgan odam "nima o'zgardi?" deb qolardi. Sovg'a bo'lsa menyu
    # OLUVCHIga qo'yiladi.
    await menu_module.sync_commands(beneficiary, True)

    if obuna is not None:
        if obuna["ikkinchi"]:
            await _obuna_charge_toxtat(payer, [charge_id])
        await _notify_obuna(message, charge_id, obuna)
        return
    await _notify_purchase(message, payer, beneficiary, days, charge_id)


async def _obuna_charge_toxtat(user_id: int, charge_ids: list) -> bool:
    """Telegram'da avtomatik yechishni o'chiradi (birinchi ishlagan chek bilan).
    ⚠️ Qaytarib yoqib bo'lmaydi: `is_canceled=False` faqat foydalanuvchiga
    «qayta yoqish» huquqini qaytaradi, o'zi yoqmaydi."""
    for cid in dict.fromkeys(c for c in charge_ids if c):
        try:
            await bot.edit_user_star_subscription(
                user_id=user_id, telegram_payment_charge_id=cid, is_canceled=True)
            return True
        except Exception as exc:
            logger.warning(f"[Obuna] o'chirilmadi user={user_id} charge={cid}: {exc}")
    return False


async def obuna_toxtat(user_id: int) -> bool:
    """Faol obunani o'chiradi: foydalanuvchi so'rasa, pul qaytarilsa yoki blok
    bo'lsa (har oy pul olib xizmat bermaslik — qaytarish manbai). Obuna
    bo'lmasa False. Hech qachon ko'tarilmaydi — chaqiruvchining asosiy ishi
    (refund, blok) bu sabab yiqilmasin."""
    try:
        ob = await database.pro_obuna_ol(user_id)
        if not ob or ob["holat"] in ("bekor", "bot_bekor"):
            return False
        ok = await _obuna_charge_toxtat(user_id, [ob["charge_id"], ob["oxirgi_charge"]])
        if ok:
            await database.pro_obuna_holat(user_id, "bot_bekor")
        else:
            await _alert_admin(user_id, ob["charge_id"], "", ob["narx"],
                               "oylik obuna o'chirilmadi — Telegram rad etdi")
        return ok
    except Exception:
        logger.exception(f"[Obuna] obuna_toxtat yiqildi user={user_id}")
        return False


async def _notify_obuna(message: Message, charge_id: str, obuna: dict) -> None:
    """Birinchi to'lov — bayram xabari; har oylik yangilanish — bitta qisqa
    satr (har oy 🎉 bezovta qiladi)."""
    keyingi = (f"Keyingi to'lov: <b>{vaqt_html(obuna['gacha'])}</b> · {OBUNA_NARX} ⭐"
               if obuna.get("gacha") else "")
    if obuna["ikkinchi"]:
        await _safe_send(message, (
            f"✅ To'lov qabul qilindi — Pro'ga <b>+{OBUNA_KUN} kun</b> qo'shildi.\n\n"
            f"Sizda oylik obuna <b>allaqachon bor edi</b>, shuning uchun bu ikkinchisining "
            f"avtomatik to'lovini o'chirdim — har oy ikki marta yechilmaydi.\n"
            f"🧾 Chek: <code>{charge_id}</code>"))
        return
    if not obuna["yangi"]:
        await send_rich(message, (
            f"♻️ <b>Pro obunangiz yangilandi</b> — +{OBUNA_KUN} kun.\n"
            + (f"{keyingi}\n" if keyingi else "")
            + f"<i>O'chirish: /pro</i>"))
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn("👤 Profilimni ko'rish", "pro:profile", style=BTN_PRIMARY)],
        admin_tugmasi(),
    ])
    gacha = f"{obuna['gacha'].astimezone(database.TASHKENT_TZ):%d.%m.%Y}" if obuna.get("gacha") else ""
    if _shaxsiy(message) and await _tabrik_yubor(
            message.chat.id, tabrik_kartasi("o", gacha=gacha),
            f"🎉 <b>OYLIK OBUNA FAOLLASHTIRILDI!</b>\n"
            f"♻️ Har 30 kunda {OBUNA_NARX} ⭐ — o'chirish: /pro\n\n"
            f"🧾 <b>Chek:</b> <code>{charge_id}</code>", kb):
        return
    await send_rich(message, (
        f"🎉 <b>OYLIK OBUNA FAOLLASHTIRILDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>"
        f"♻️ Pro har oy <b>o'zi uzayadi</b> — {OBUNA_NARX} ⭐ Stars balansingizdan.\n"
        + (f"{keyingi}\n" if keyingi else "")
        + f"⚡️ Kunlik ball: <b>{daily_limit('pro', 'points')}</b>\n"
        f"🧠 Chuqur fikrlash va uzun xotira: <b>yoqildi</b>"
        f"</blockquote>\n\n"
        f"🔕 O'chirish istalgan payt: /pro → «Avtomatik to'lovni o'chirish». "
        f"To'langan muddat oxirigacha ishlaydi.\n\n"
        f"🧾 <b>Chek:</b> <code>{charge_id}</code>"
    ), kb=kb, effect=MESSAGE_EFFECTS.get("🎉"))


_OBUNA_HOLAT = {"canceled": "bekor", "active": "faol", "failed": "xato"}


async def handle_obuna_ozgardi(event) -> None:
    """`Update.subscription` (Bot API 10.2): foydalanuvchi obunani Telegram
    sozlamalarida o'chirdi / qayta yoqdi, yoki yechish o'tmadi."""
    ob = parse_obuna_payload(event.invoice_payload or "")
    holat = _OBUNA_HOLAT.get(event.state)
    if ob is None or holat is None:
        logger.warning(f"[Obuna] noma'lum o'zgarish: {event.state} {event.invoice_payload!r}")
        return
    uid = event.user.id
    try:
        await database.pro_obuna_holat(uid, holat)
    except Exception:
        logger.exception(f"[Obuna] holat yozilmadi user={uid} {holat}")
    gacha = ""
    try:
        until = (await database.get_full_user_profile(uid) or {}).get("premium_until")
        if until:
            gacha = f" Pro <b>{vaqt_html(until)}</b> gacha ishlaydi."
    except Exception:
        pass
    matn = {
        "bekor": f"🔕 <b>Oylik obuna o'chirildi.</b>{gacha}\nQayta yoqish: /pro",
        "faol": "🔔 <b>Oylik obuna qayta yoqildi</b> — Pro har oy o'zi uzayadi.",
        "xato": (f"⚠️ <b>Obuna to'lovi o'tmadi</b> — Stars balansida yetarli yulduz "
                 f"bo'lmagan bo'lishi mumkin.{gacha}\nDavom ettirish: /pro"),
    }[holat]
    try:
        await bot.send_message(uid, matn, parse_mode="HTML")
    except Exception as exc:
        logger.info(f"[Obuna] xabar yetmadi user={uid}: {exc}")


async def _notify_purchase(message: Message, payer: int, beneficiary: int,
                           days: int, charge_id: str) -> None:
    """Xarid tasdig'i. Grant ALLAQACHON commit bo'lgan — bu yerdagi hech
    qanday xato tarifni bekor qilmaydi."""
    _, title, _ = PRO_PLANS_BY_DAYS[days]

    if beneficiary == payer:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [btn("👤 Profilimni ko'rish", "pro:profile", style=BTN_PRIMARY)],
            [btn("🎁 Do'stga ham sovg'a qilish", "pro:gift")],
            admin_tugmasi(),
        ])
        # Shaxsiy chatda — bayram kartasi; chek raqami izohda (adminga shu kerak).
        if _shaxsiy(message) and await _tabrik_yubor(
                message.chat.id,
                tabrik_kartasi("p", title=title, days=days, gacha=await _tugash_sanasi(payer)),
                f"🎉 <b>PRO TARIF FAOLLASHTIRILDI!</b>\n"
                f"📦 Muddat: <b>{title}</b> ({days} kun)\n\n"
                f"🧾 <b>Chek:</b> <code>{charge_id}</code>\n"
                f"<i>Muammo bo'lsa shu raqamni adminga yuboring.</i>", kb):
            return
        # 🎉 effekt — Telegram'ning animatsion nishonlash effekti. Faqat
        # shaxsiy chatda ishlaydi; send_rich() aks holda effektsiz yuboradi.
        await send_rich(message, (
            f"🎉 <b>PRO TARIF FAOLLASHTIRILDI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<blockquote>"
            f"📦 Muddat: <b>{title}</b> ({days} kun)\n"
            f"⚡️ Kunlik ball: <b>{daily_limit('pro', 'points')}</b>\n"
            f"{pe('document', '📄')} Kunlik fayl: <b>{daily_limit('pro', 'files')} ta</b>\n"
            f"🧠 Chuqur fikrlash: <b>yoqildi</b>\n"
            f"💬 Uzun xotira: <b>yoqildi</b>"
            f"</blockquote>\n\n"
            f"🧾 <b>Chek:</b> <code>{charge_id}</code>\n"
            f"<i>Muammo bo'lsa shu raqamni adminga yuboring.</i>\n\n"
            f"Rahmat! Bemalol foydalanavering 🙌"
        ), kb=kb, effect=MESSAGE_EFFECTS.get("🎉"))
        return

    # ── Sovg'a ──
    recipient_name = f"<code>{beneficiary}</code>"
    oddiy_nom = str(beneficiary)     # kartada — oddiy matn (textContent)
    try:
        target = await database.get_full_user_profile(beneficiary)
        if target:
            recipient_name = _display_name(target, beneficiary)
            u = target.get("username")
            if u and u != "Mavjud emas":
                oddiy_nom = f"@{u}"
    except Exception:
        pass

    giver = f"@{message.from_user.username}" if message.from_user.username else "Do'stingiz"
    # Oluvchiga — sovg'a kartasi; yetmasa (bloklagan, rad) — oldingi matn.
    delivered = await _tabrik_yubor(
        beneficiary, tabrik_kartasi("g", title=title, kim=giver),
        f"🎁 <b>Sizga Pro sovg'a qilindi!</b>\n{giver} — Pro {title} ({days} kun)",
        InlineKeyboardMarkup(inline_keyboard=[
            [btn("👤 Profilimni ko'rish", "pro:profile", style=BTN_PRIMARY)]]))
    if not delivered:
        delivered = await _sovga_matni(beneficiary, giver, title, days)

    note = "" if delivered else (
        "\n\n⚠️ Unga xabar yetkazib bo'lmadi (botni bloklagan bo'lishi mumkin), "
        "lekin tarif <b>berildi</b>."
    )
    # Yuboruvchiga — o'sha karta «yuborildi» ko'rinishida; chek izohda.
    izoh = (f"🎁 <b>SOVG'A YUBORILDI!</b>\n👤 Kimga: {recipient_name}\n"
            f"📦 Muddat: <b>{title}</b> ({days} kun)\n\n"
            f"🧾 <b>Chek:</b> <code>{charge_id}</code>{note}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn("🎁 Yana sovg'a qilish", "pro:gift", style=BTN_PRIMARY)]])
    if _shaxsiy(message) and await _tabrik_yubor(
            message.chat.id, tabrik_kartasi(
                "y", title=title, days=days, kim=oddiy_nom,
                eslatma="" if delivered else "⚠️ Unga xabar yetmadi, lekin tarif berildi"),
            izoh, kb):
        return
    await send_rich(message, (
        f"🎁 <b>SOVG'A YUBORILDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>"
        f"👤 Kimga: {recipient_name}\n"
        f"📦 Muddat: <b>{title}</b> ({days} kun)"
        f"</blockquote>\n\n"
        f"🧾 <b>Chek:</b> <code>{charge_id}</code>{note}"
    ), kb=kb, effect=MESSAGE_EFFECTS.get("🎉"))


async def _sovga_matni(beneficiary: int, giver: str, title: str, days: int) -> bool:
    """Sovg'a oluvchiga oddiy matn (karta yetmaganda). Qaytadi: yetdimi."""
    try:
        await bot.send_message(beneficiary, (
            f"🎁 <b>SIZGA SOVG'A!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{giver} sizga <b>Pro tarif</b> sovg'a qildi.\n\n"
            f"<blockquote>"
            f"📦 Muddat: <b>{title}</b> ({days} kun)\n"
            f"⚡️ Kunlik ball: <b>{daily_limit('pro', 'points')}</b>\n"
            f"{pe('document', '📄')} Kunlik fayl: <b>{daily_limit('pro', 'files')} ta</b>"
            f"</blockquote>"
        ), parse_mode="HTML",
            message_effect_id=MESSAGE_EFFECTS.get("🎉"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [btn("👤 Profilimni ko'rish", "pro:profile", style=BTN_PRIMARY)]]))
        return True
    except Exception as exc:
        # Effekt yoki klaviatura sabab bo'lishi mumkin — soddaroq holda takror.
        try:
            await bot.send_message(beneficiary, (
                f"🎁 <b>Sizga Pro tarif sovg'a qilindi!</b>\n\n"
                f"📦 Muddat: <b>{title}</b> ({days} kun)\n"
                f"👤 Holatni ko'rish: /profile"
            ), parse_mode="HTML")
            return True
        except Exception:
            logger.warning(f"[Pro] sovg'a xabari yetmadi (user={beneficiary}): {exc}")
            return False


async def _safe_send(message: Message, text: str) -> None:
    """Faqat to'lov MUAMMOSI xabarlari — shuning uchun doim admin tugmasi bilan."""
    text += ADMIN_IZOH
    try:
        await message.answer(text, parse_mode="HTML", reply_markup=admin_kb())
    except Exception:
        try:
            await message.answer(re.sub(r"</?[a-z]+>", "", text), reply_markup=admin_kb())
        except Exception as e:
            logger.error(f"[Pro] xabar yuborilmadi: {e}")


# ═══════════════════════════════════════════════════════════════════
#  4b. KARTA ORQALI TO'LOV (so'mda, 2026-10-30)
# ═══════════════════════════════════════════════════════════════════
# Telegram pulni ko'rmaydi — kafolat superadminning O'Z ko'zi: chek
# rasmi hech qachon o'zi Pro bermaydi (tahrirlangan skrinshot — eng ko'p
# firibgarlik). Superadmin bank ilovasida noyob summani (25 047) topib,
# chek ostidagi tugmani bosadi. Sovg'a ham (2026-11-11): `oluvchi` ustuni,
# Pro tasdiqda o'shanga; to'lov, chek va qaror — to'lovchi bilan. Promo — yo'q.

class KartaStates(StatesGroup):
    chek = State()


# Chek kutish holati shuncha yashaydi: undan keyin kelgan rasm — chek emas,
# oddiy savol (AI'ga o'tadi). Holat RAM'da — deploy uni o'chiradi, shuning
# uchun so'rov xabarida «📎 Chekni yuborish» tugmasi turadi.
KARTA_CHEK_OYNA = 3 * 3600
# Karta raqamini olib, shuncha vaqt chek yubormaganga bir marta eslatma;
# oyna tugaganda esa «vaqt tugadi, to'lagan bo'lsangiz — adminga» (`karta_watcher`).
KARTA_ESLATMA = 30 * 60
# Va'da: tez, lekin kafolat 24 soat — superadmin kechasi uxlaydi.
KARTA_VADA = "odatda bir necha soat ichida (eng ko'pi 24 soat)"

_RAD_SABAB = {
    "kelmadi": "to'lov kartaga kelib tushmadi",
    "summa": "o'tkazilgan summa so'ralgan summaga mos emas",
    "chek": "yuborilgan fayl to'lov cheki emas yoki o'qib bo'lmaydi",
}


def som(n: int) -> str:
    return f"{n:,}".replace(",", " ")


async def _karta() -> tuple | None:
    """(raqam, egasi) — panelda superadmin qo'ygan karta. Bezak: baza xatosi
    /pro ekranini yiqitmasin — karta tugmasi shunchaki ko'rinmaydi."""
    try:
        return await database.karta_ol()
    except Exception as e:
        logger.warning(f"[Karta] sozlama o'qilmadi: {e}")
        return None


def karta_korinishi(raqam: str) -> str:
    return " ".join(raqam[i:i + 4] for i in range(0, len(raqam), 4))


def karta_tariflar_matni() -> str:
    return ("💳 <b>Karta orqali to'lov</b>\n\n"
            "Muddatni tanlang — keyingi qadamda karta raqami va aniq summa chiqadi. "
            f"To'lagach chekni shu yerga yuborasiz — Pro <b>{KARTA_VADA}</b> yoqiladi.")


def _karta_tariflar_kb(oluvchi: int | None = None) -> InlineKeyboardMarkup:
    """Karta muddatlari. `oluvchi` — sovg'a: tugmalar `pro:karta:<kun>:<id>`,
    «Orqaga» esa sovg'aning Stars ekraniga."""
    # Yorliq — Stars jadvalidagi (narx nisbati bir xil, test_karta_tolov.py).
    suffix = f":{oluvchi}" if oluvchi else ""
    orqaga = [btn("⬅️ Orqaga", f"pro:stars:{oluvchi}")] if oluvchi else _ORQAGA
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn(f"{title} · {som(KARTA_NARX[days])} so'm" + (f"  {badge}" if badge else ""),
             f"pro:karta:{days}{suffix}", style=BTN_PRIMARY)]
        for days, _, title, badge in PRO_PLANS
    ] + [orqaga])


async def _sovga_kb(oluvchi: int) -> InlineKeyboardMarkup:
    """Sovg'a muddatlari: Stars narxlari (obunasiz — u to'lovchining o'z
    balansidan har oy yechilardi) + karta bo'lsa «Karta orqali» + bekor."""
    karta = ([[btn("💳 Karta orqali (so'mda)", f"pro:kartalar:{oluvchi}", style=BTN_PRIMARY)]]
             if await _karta() else [])
    return InlineKeyboardMarkup(inline_keyboard=(
        _buy_buttons(oluvchi) + karta
        + [[InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="pro:close")]]))


async def _oluvchi_nomi(oluvchi: int) -> str:
    """Kartada ko'rinadigan oddiy nom: @username yoki ID (textContent)."""
    try:
        p = await database.get_full_user_profile(oluvchi)
    except Exception:
        p = None
    u = (p or {}).get("username")
    return f"@{u}" if u and u != "Mavjud emas" else str(oluvchi)


async def _sovga_oluvchisi(query: CallbackQuery, parts: list, joy: int) -> int | None:
    """`pro:<amal>:...:<oluvchi>` dagi oluvchi — TO'LIQ tekshirilgan (`validate_recipient`).
    ⚠️ callback_data mijozdan keladi: yasalgan id bilan yetkazib bo'lmaydigan
    sovg'a sotilmasin. None — xato aytilgan (alert)."""
    try:
        oluvchi = int(parts[joy])
    except (IndexError, ValueError):
        await query.answer("Tugma eskirgan. /gift dan qayta boshlang.", show_alert=True)
        return None
    ok, xato = await validate_recipient(query.from_user.id, oluvchi)
    if not ok:
        await query.answer(re.sub(r"<[^>]+>", "", xato)[:190], show_alert=True)
        return None
    return oluvchi


def karta_sorov_matni(days: int, summa: int, raqam: str, egasi: str,
                      lid: int | None = None) -> str:
    """Sof — testda. `lid` — foydalanuvchiga ko'rinadigan to'lov raqami:
    adminga yozganda «qaysi to'lov?» degan savol tug'ilmasin."""
    _, title, _ = PRO_PLANS_BY_DAYS[days]
    return (
        f"💳 <b>Karta orqali to'lov — Pro {title}</b>\n"
        + (f"🆔 To'lov <b>#{lid}</b> · ⏱ {KARTA_CHEK_OYNA // 3600} soat amal qiladi\n" if lid else "")
        + "\n"
        f"1️⃣ Shu kartaga o'tkazing:\n<code>{karta_korinishi(raqam)}</code>\n"
        + (f"👤 {html_escape(egasi)}\n" if egasi else "")
        + f"\n2️⃣ <b>Aynan shu summani</b> yuboring:\n<b><code>{som(summa)}</code> so'm</b>\n"
        f"<i>Oxiridagi {summa - KARTA_NARX[days]} so'm — to'lovingizni tanib olishimiz uchun.</i>\n\n"
        "3️⃣ To'lagach, <b>chek rasmini</b> (skrinshot) yoki PDF'ini shu chatga yuboring.\n\n"
        f"⏳ Chekni tekshirib, Pro'ni <b>{KARTA_VADA}</b> yoqamiz — natija shu yerga keladi."
    )


def _karta_sorov_kb(lid: int, summa: int, raqam: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Karta raqami", copy_text=CopyTextButton(text=raqam)),
         InlineKeyboardButton(text="📋 Summa", copy_text=CopyTextButton(text=str(summa)))],
        [btn("📎 Chekni yuborish", f"pro:chek:{lid}", style=BTN_SUCCESS)],
        admin_tugmasi(),
        [btn("✖️ Bekor qilish", f"pro:kb:{lid}", style=BTN_DANGER)],
    ])


def _karta_admin_kb(lid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("✅ Tasdiqlash — pul keldi", f"pro:kt:{lid}", style=BTN_SUCCESS)],
        [btn("❌ Pul kelmadi", f"pro:kr:{lid}:kelmadi"),
         btn("❌ Summa boshqa", f"pro:kr:{lid}:summa")],
        [btn("❌ Chek emas", f"pro:kr:{lid}:chek")],
    ])


def karta_admin_matni(r: dict, ism: str, username: str | None) -> str:
    """Superadminga chek osti matni. Sof — testda."""
    _, title, _ = PRO_PLANS_BY_DAYS[r["days"]]
    return (
        f"💳 <b>Karta to'lovi #{r['id']}</b>\n\n"
        f"👤 {html_escape(ism)}" + (f" (@{html_escape(username)})" if username else "")
        + f" · <code>{r['user_id']}</code>\n"
        f"💎 Pro {title}\n"
        + (f"🎁 Sovg'a — Pro shu odamga: <code>{r['oluvchi']}</code>\n" if r.get("oluvchi") else "")
        + f"💰 Kutilgan summa: <b>{som(r['summa'])} so'm</b>\n"
        f"💳 Karta: ···· {r['karta'][-4:]}\n"
        + (f"\n⚠️ <b>Bu chek oldin #{r['takror']} so'rovda ham yuborilgan!</b>\n"
           if r.get("takror") else "")
        + "\nBank ilovangizda <b>aynan shu summa</b> kelganini tekshiring."
    )


async def _chek_kut(state: FSMContext, lid: int) -> None:
    await state.set_state(KartaStates.chek)
    await state.update_data(karta_id=lid, karta_t=time.time())


async def process_karta_chek_bazadan(message: Message, state: FSMContext) -> None:
    """FSM holati YO'Q (deploy uni o'chirgan), lekin bazada chek kutayotgan
    so'rov bor — rasm chek. Yo'q bo'lsa (yoki baza javob bermasa) —
    odatdagidek AI'ga: oddiy rasm savoli bu tekshiruv uchun buzilmasin."""
    try:
        lid = await database.karta_chek_kutilmoqda(message.from_user.id, KARTA_CHEK_OYNA)
    except Exception as e:
        logger.warning(f"[Karta] kutilayotgan chek tekshirilmadi: {e}")
        lid = None
    if not lid:
        raise SkipHandler()
    logger.info(f"[Karta] chek #{lid} FSM'siz tanildi (deploy holatni o'chirgan)")
    await _chek_kut(state, lid)
    await process_karta_chek(message, state)


async def process_karta_chek(message: Message, state: FSMContext) -> None:
    """FSM: chek rasmi yoki fayli. main.py'da AI handlerlaridan OLDIN, faqat
    F.photo | F.document — matn yozsa savol odatdagidek AI'ga ketadi."""
    data = await state.get_data()
    lid = data.get("karta_id")
    if not lid or time.time() - data.get("karta_t", 0) > KARTA_CHEK_OYNA:
        # Eskirgan holat: bu rasm chek emas, oddiy savol — keyingi handlerga.
        await state.clear()
        raise SkipHandler()
    if message.photo:
        f, turi = message.photo[-1], "photo"
    else:
        f, turi = message.document, "document"
    # Albomning ikkinchi rasmi chek emas — birinchisi bilan holat tugaydi.
    await state.clear()
    r = await database.karta_chek_yoz(lid, message.from_user.id, f.file_id, turi,
                                      f.file_unique_id)
    if not r:
        # Oyna shu daqiqada yopilgan (`karta_watcher`) — pul ketgan bo'lishi
        # mumkin, ya'ni «qayta boshlang» yetmaydi: chek adminga borsin.
        await message.answer(
            "⌛️ Bu to'lov so'rovi yopilgan.\n\nPul o'tkazgan bo'lsangiz — shu chekni pastdagi "
            "tugma orqali adminga yuboring, tekshirib Pro'ni yoqamiz. Yangi to'lov: /pro",
            reply_markup=admin_kb())
        return
    nima = "sovg'ani yetkazamiz" if r.get("oluvchi") else "Pro'ni yoqamiz"
    m = await message.answer(f"✅ <b>Chek qabul qilindi</b> (to'lov #{lid}).\n\nTekshirib, "
                             f"{KARTA_VADA} {nima} — natija shu yerga keladi." + ADMIN_IZOH,
                             parse_mode="HTML", reply_markup=admin_kb())
    await _tolov_xabari(lid, getattr(m, "message_id", None))
    logger.info(f"[Karta] chek #{lid} user={message.from_user.id} summa={r['summa']}")
    u = message.from_user
    matn = karta_admin_matni(r, u.full_name, u.username)
    try:
        admin_id = await database.get_superadmin_id()
        if not admin_id:
            raise RuntimeError("superadmin yo'q")
        yubor = bot.send_photo if turi == "photo" else bot.send_document
        try:
            await yubor(admin_id, r["chek_file"], caption=matn, parse_mode="HTML",
                        reply_markup=_karta_admin_kb(lid))
        except Exception as e:
            # Fayl ketmasa ham qaror tugmalari yetib borsin — pul yo'qolmasin.
            logger.warning(f"[Karta] chek fayli adminga ketmadi #{lid}: {e}")
            await bot.send_message(admin_id, matn + "\n\n<i>(chek fayli yuborilmadi)</i>",
                                   parse_mode="HTML", reply_markup=_karta_admin_kb(lid))
    except Exception:
        logger.exception(f"[Karta] ADMINGA YETMAGAN CHEK #{lid} user={u.id} summa={r['summa']}")


async def _karta_callback(query: CallbackQuery, state: FSMContext, parts: list) -> None:
    """pro:kartalar | karta:<kun> | chek:<id> | kb:<id> — foydalanuvchi;
    pro:kt:<id> | kr:<id>:<sabab> — faqat superadmin."""
    action, uid = parts[1], query.from_user.id
    if action == "kartalar":
        # `pro:kartalar:<oluvchi>` — sovg'a; oluvchi har safar qayta tekshiriladi.
        oluvchi = None
        if len(parts) > 2:
            oluvchi = await _sovga_oluvchisi(query, parts, 2)
            if oluvchi is None:
                return
        await query.answer()
        if not await _karta():
            await query.message.answer("Karta orqali to'lov hozircha yo'q — Stars bilan to'lang: /pro")
            return
        await _tugmalarni_almashtir(query, _karta_tariflar_kb(oluvchi), karta_tariflar_matni())
        if oluvchi:
            await _pro_holatini_yoz(query, {"e": "k", "gf": await _oluvchi_nomi(oluvchi),
                                            "t": tarif_plitkalari("k"), "rid": oluvchi})
        else:
            await _pro_ekrani_almashtir(query, uid, "k")
        return
    try:
        son = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("Tugma eskirgan. /pro dan qayta boshlang.", show_alert=True)
        return

    if action == "karta":
        # ⚠️ callback_data — mijoz ma'lumoti: kun katalogdan, narx serverdan,
        # oluvchi (`pro:karta:<kun>:<id>`, sovg'a) — `validate_recipient` dan.
        karta = await _karta()
        if son not in KARTA_NARX or not karta:
            await query.answer("Bu tarif endi mavjud emas. /pro dan qayta boshlang.", show_alert=True)
            return
        oluvchi = None
        if len(parts) > 3:
            oluvchi = await _sovga_oluvchisi(query, parts, 3)
            if oluvchi is None:
                return
        raqam, egasi = karta
        try:
            if await database.is_banned(uid):
                await query.answer("🚫 Hisob bloklangan.", show_alert=True)
                return
        except Exception as exc:
            logger.warning(f"[Karta] ban tekshiruvi o'tmadi: {exc}")
        await query.answer()
        # Har so'rov qaysi kartani ko'rganini eslaydi: karta panelda almashsa,
        # eskisiga to'langan chekda superadmin o'sha kartaning oxirini ko'radi.
        s = await database.karta_sorov_yarat(uid, son, KARTA_NARX[son], raqam, oluvchi)
        nom = await _oluvchi_nomi(oluvchi) if oluvchi else ""
        # ⚠️ Chek kutish holati kartadan MUSTAQIL: yuborishda nima bo'lsa ham yoqiladi.
        try:
            mid = await _tolov_ekrani(query.message, son, s["summa"], raqam, egasi, s["id"], nom)
        finally:
            await _chek_kut(state, s["id"])
        await _tolov_xabari(s["id"], mid)
        # Muddatlar ekrani to'lov kartasi bilan almashadi («✖️ Bekor» uni qaytaradi).
        # Matnli xabar (vaqti tugagani haqidagi) qoladi — unda «adminga yozing» bor.
        from handlers.messages import ekranni_ochir, vidjet_xabari
        if vidjet_xabari(query.message) is not None:
            await ekranni_ochir(query.message.chat.id, query.message.message_id)
        await ekranni_ochir(query.message.chat.id)
        logger.info(f"[Karta] so'rov #{s['id']} user={uid} kun={son} summa={s['summa']}"
                    + (f" sovg'a→{oluvchi}" if oluvchi else ""))
        return

    if action == "chek":
        r = await database.karta_sorov_ol(son, uid)
        if not r or r["holat"] not in ("kutmoqda", "tekshirilmoqda", "rad"):
            await query.answer("Bu to'lov so'rovi endi faol emas — /pro", show_alert=True)
            return
        await _chek_kut(state, son)
        # Alohida xabar emas — oyna (kartada — xabarcha): chatga ortiqcha qator qo'shmaydi.
        await query.answer("📎 Chek rasmini (skrinshot) yoki PDF faylini shu chatga yuboring.",
                           show_alert=True)
        return

    if action == "kb":
        bekor = await database.karta_bekor(son, uid)
        if await state.get_state() == KartaStates.chek.state:
            await state.clear()
        # Bekor bo'lmadi — chek yuborilgan YOKI vaqti tugagan; ikkalasida ham
        # bu so'rov foydalanuvchining qo'lida emas.
        await query.answer("✖️ Bekor qilindi" if bekor else "Bu so'rov endi ochiq emas")
        if bekor:
            await _tolovni_yangidan(query, son, uid)
        return

    if action == "qayta":
        # Vaqti tugagan / bekor qilingan to'lovdagi «💳 Yangi to'lov» (sovg'ada
        # «🎁 Qaytadan»): o'sha xabar o'chadi, muddatlar YANGI xabar bo'lib.
        # ⚠️ Avval `pro:kartalar` edi — u to'lov kartasining O'ZIGA Pro holatini
        # yozib, kartani buzardi.
        await query.answer()
        await _tolovni_yangidan(query, son, uid)
        return

    # ── Superadmin qarori ──
    if not await database.is_superadmin(uid):
        await query.answer("Faqat bosh admin tasdiqlaydi.", show_alert=True)
        return
    if action == "kt":
        r = await database.karta_tasdiqla(son, uid)
        sabab = None
    else:
        sabab = _RAD_SABAB.get(parts[3] if len(parts) > 3 else "")
        if not sabab:
            await query.answer("Tugma eskirgan.", show_alert=True)
            return
        r = await database.karta_rad(son, uid, sabab)
    if r is None:
        await query.answer("Bu to'lov allaqachon hal qilingan.", show_alert=True)
        return
    izoh = f"#{son} · {som(r['summa'])} so'm · {r['days']} kun"
    if sabab is None:
        await database.log_admin_action(uid, "karta_tasdiq", r["user_id"], izoh)
    else:
        await database.log_admin_action(uid, "karta_rad", r["user_id"], f"{izoh} · {sabab}")
    logger.info(f"[Karta] {'tasdiq' if sabab is None else 'rad'} {izoh} user={r['user_id']}")
    belgi = "✅ TASDIQLANDI" if sabab is None else f"❌ RAD ETILDI — {sabab}"
    try:
        await query.message.edit_caption(caption=f"{query.message.html_text}\n\n<b>{belgi}</b>",
                                         parse_mode="HTML", reply_markup=None)
    except Exception:
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    oluvchi = r.get("oluvchi")
    if sabab is None:
        try:
            # Pro kimda bo'lsa (sovg'a — oluvchida), menyu o'shanga.
            await menu_module.sync_commands(oluvchi or r["user_id"], True)
        except Exception as e:
            logger.warning(f"[Karta] menyu yangilanmadi: {e}")
        if oluvchi:
            yetdi = await _karta_sovga_xabarlari(r)
            if yetdi:
                await _tolov_xabarlarini_ochir(son, r["user_id"])
            await query.answer("✅ Tasdiqlandi" if yetdi else
                               "Bajarildi, lekin to'lovchiga xabar yetmadi.", show_alert=not yetdi)
            return
        gacha = await _tugash_sanasi(r["user_id"])
        matn, kb = (f"🎉 <b>Pro faollashdi!</b>\n\nTo'lovingiz ({som(r['summa'])} so'm) "
                    f"tasdiqlandi." + (f" Pro <b>{gacha}</b> gacha faol." if gacha else "")
                    + " Rahmat!"), None
    else:
        matn = (f"❌ <b>To'lov tasdiqlanmadi</b>\n\nSabab: {sabab}.\n\n"
                "Pul o'tkazgan bo'lsangiz, to'g'ri chekni yuboring — qayta tekshiramiz."
                + ADMIN_IZOH)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [btn("📎 Chekni qayta yuborish", f"pro:chek:{son}", style=BTN_PRIMARY)],
            admin_tugmasi()])
    try:
        # Tasdiq — bayram kartasi (foydalanuvchining shaxsiy chati), yetmasa — matn.
        if not (sabab is None and await _tabrik_yubor(
                r["user_id"], tabrik_kartasi("k", gacha=gacha), matn, None)):
            await bot.send_message(r["user_id"], matn, parse_mode="HTML", reply_markup=kb)
        if sabab is None:
            # Natija yetdi — karta, «chek qabul qilindi», eslatma endi ortiqcha.
            # Rad etilganda QOLADI: odam chekni qayta yuboradi (karta tugmasi bilan).
            await _tolov_xabarlarini_ochir(son, r["user_id"])
        await query.answer("✅ Tasdiqlandi" if sabab is None else "Rad etildi")
    except Exception as e:
        logger.warning(f"[Karta] foydalanuvchiga xabar ketmadi #{son}: {e}")
        await query.answer("Bajarildi, lekin foydalanuvchiga xabar yetmadi (botni bloklagan bo'lishi mumkin).",
                           show_alert=True)


async def _karta_sovga_xabarlari(r: dict) -> bool:
    """Karta orqali sovg'a tasdiqlandi (Pro allaqachon OLUVCHIDA): oluvchiga
    sovg'a kartasi (yetmasa — matn), to'lovchiga «yetkazildi» kartasi (yetmasa —
    matn). Stars sovg'asidagi `_notify_purchase` bilan bir xil xabarlar.
    Qaytadi: to'lovchiga yetdimi."""
    payer, oluvchi, days = r["user_id"], r["oluvchi"], int(r["days"])
    _, title, _ = PRO_PLANS_BY_DAYS[days]
    beruvchi = await _oluvchi_nomi(payer)
    beruvchi = beruvchi if beruvchi.startswith("@") else "Do'stingiz"
    nom = await _oluvchi_nomi(oluvchi)
    yetdi = await _tabrik_yubor(
        oluvchi, tabrik_kartasi("g", title=title, kim=beruvchi),
        f"🎁 <b>Sizga Pro sovg'a qilindi!</b>\n{html_escape(beruvchi)} — Pro {title} ({days} kun)",
        InlineKeyboardMarkup(inline_keyboard=[
            [btn("👤 Profilimni ko'rish", "pro:profile", style=BTN_PRIMARY)]]))
    if not yetdi:
        yetdi = await _sovga_matni(oluvchi, html_escape(beruvchi), title, days)
    eslatma = "" if yetdi else (
        "\n\n⚠️ Unga xabar yetkazib bo'lmadi (botni bloklagan bo'lishi mumkin), "
        "lekin tarif <b>berildi</b>.")
    matn = (f"🎁 <b>Sovg'a yetkazildi!</b>\n\nTo'lovingiz ({som(r['summa'])} so'm) tasdiqlandi — "
            f"{html_escape(nom)} ga Pro {title} ({days} kun).{eslatma}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn("🎁 Yana sovg'a qilish", "pro:gift", style=BTN_PRIMARY)]])
    if await _tabrik_yubor(payer, tabrik_kartasi(
            "y", title=title, days=days, kim=nom,
            eslatma="" if yetdi else "⚠️ Unga xabar yetmadi, lekin tarif berildi"), matn, kb):
        return True
    try:
        await bot.send_message(payer, matn, parse_mode="HTML", reply_markup=kb)
        return True
    except Exception as e:
        logger.warning(f"[Karta] sovg'a to'lovchisiga xabar yetmadi (user={payer}): {e}")
        return False


# ── Brend kartalari: to'lov va bayram (Bot API 10.4 vidjeti) ──────
# Har biri BEZAK: yetmasa (rad, xato) — o'sha eski matnli xabar, tugmalari
# bilan. Pul yo'li (grant, chek, tasdiq) kartadan OLDIN tugagan bo'ladi.

def tolov_kartasi(days: int, summa: int, raqam: str, egasi: str, lid: int,
                  sovga: str = "", yaratilgan: datetime | None = None, holat: str = "k") -> dict:
    """Karta to'lovi kartasining holati (services/vidjet.py — kalitlar).
    Raqamlar `karta_sorov_matni()` dagining o'zi. `sovga` — oluvchi nomi
    (oddiy matn); `yaratilgan` — bazadagi vaqt (oyna undan sanaladi). Sof — testda."""
    _, title, _ = PRO_PLANS_BY_DAYS[days]
    boshi = int(yaratilgan.timestamp()) if yaratilgan else int(time.time())
    d = {"id": lid, "t": title, "n": raqam, "nf": karta_korinishi(raqam),
         "o": egasi or "", "s": summa, "sf": som(summa), "w": summa - KARTA_NARX[days],
         "x": boshi + KARTA_CHEK_OYNA, "h": holat}
    if sovga:
        d["gf"] = sovga
    return d


def tolov_izohi(days: int, summa: int, raqam: str, egasi: str, lid: int,
                sovga: str = "") -> str:
    """Kartaning izohi — vidjetni ko'rsatmaydigan ilova FAQAT shuni ko'radi,
    shuning uchun to'lash uchun kerak narsa (karta, summa, chek) shu yerda ham."""
    _, title, _ = PRO_PLANS_BY_DAYS[days]
    return (f"💳 <b>Karta orqali to'lov — Pro {title}</b> · #{lid}\n"
            + (f"🎁 Sovg'a: {html_escape(sovga)}\n" if sovga else "")
            + f"Karta: <code>{karta_korinishi(raqam)}</code>"
            + (f" · {html_escape(egasi)}" if egasi else "") + "\n"
            f"Summa: <b><code>{som(summa)}</code> so'm</b> — aynan shu summa\n\n"
            "To'lagach, <b>chek rasmini</b> (skrinshot) yoki PDF'ini shu chatga yuboring.")


_TOLOV_HOLAT = {"kutmoqda": "k", "tekshirilmoqda": "t", "rad": "r",
                "tasdiqlandi": "a", "bekor": "b", "eskirdi": "e"}


async def tolov_holati(user_id: int, lid: int) -> dict:
    """"t:<id>" so'roviga javob. `karta_sorov_ol` user_id bilan o'qiydi —
    begona yoki yo'q to'lov {"h": "x"} (karta o'zgarmaydi)."""
    r = await database.karta_sorov_ol(lid, user_id)
    d = {"h": _TOLOV_HOLAT.get((r or {}).get("holat"), "x")}
    if d["h"] == "r":
        d["z"] = r.get("sabab") or ""
    elif d["h"] == "a":
        try:
            # Sovg'a — Pro OLUVCHIDA, sana ham o'shaniki.
            p = await database.get_full_user_profile(r.get("oluvchi") or user_id)
            if p and p.get("premium_until"):
                d["g"] = _sana(p["premium_until"])
        except Exception:
            pass
    return d


async def _tolov_ekrani(target, days: int, summa: int, raqam: str, egasi: str,
                        lid: int, sovga: str = "") -> int | None:
    """Karta raqami va summa: shaxsiy chatda — karta, aks holda yoki rad
    etilsa — oldingi matn. Tugmalar IKKALASIDA bir xil (`_karta_sorov_kb`).
    Qaytadi: xabar id'si (noma'lum — None)."""
    from handlers.messages import xabar_id
    kb = _karta_sorov_kb(lid, summa, raqam)
    if getattr(getattr(target, "chat", None), "type", None) == "private":
        try:
            from handlers.messages import vidjet_yubor
            from services import vidjet
            if (n := await vidjet_yubor(
                    target.chat.id, vidjet.tolov_html(),
                    vidjet.tolov_holati(tolov_kartasi(days, summa, raqam, egasi, lid, sovga)),
                    tolov_izohi(days, summa, raqam, egasi, lid, sovga), kb, sorov=True)):
                return xabar_id(n)
        except Exception as e:
            logger.warning(f"[Karta] to'lov kartasi yuborilmadi #{lid}: {e}")
    return xabar_id(await target.answer(
        (f"🎁 <b>Sovg'a: {html_escape(sovga)}</b>\n" if sovga else "")
        + karta_sorov_matni(days, summa, raqam, egasi, lid),
        parse_mode="HTML", reply_markup=kb))


async def _tolov_xabari(lid: int, mid) -> None:
    """To'lov oqimidagi bot xabarini eslab qoladi (keyin o'chadi). Bezak — jim."""
    if not mid:
        return
    try:
        await database.karta_xabar_qosh(lid, mid)
    except Exception as e:
        logger.info(f"[Karta] xabar id yozilmadi #{lid}: {e}")


async def _tolov_xabarlarini_ochir(lid: int, user_id: int, r: dict | None = None) -> None:
    """To'lovning bot xabarlari (karta, «chek qabul qilindi», eslatma) o'chadi.
    Hech qachon ko'tarilmaydi: natija allaqachon yetgan, bu faqat tozalash."""
    from handlers.messages import ekranni_ochir
    try:
        r = r or await database.karta_sorov_ol(lid, user_id)
        for mid in (r or {}).get("xabarlar") or []:
            await ekranni_ochir(user_id, mid)
    except Exception as e:
        logger.info(f"[Karta] to'lov xabarlari o'chmadi #{lid}: {e}")


async def _tolovni_yangidan(query: CallbackQuery, lid: int, uid: int) -> None:
    """Bekor / vaqti tugagan to'lov: uning xabarlari (bosilgan xabar ham) o'chadi,
    muddatlar ekrani YANGI xabar bo'lib — odam qayerda qolganini yo'qotmaydi.
    Sovg'a bo'lsa — o'sha oluvchiga (yaroqliligi keyingi bosishda tekshiriladi)."""
    from handlers.messages import ekranni_ochir
    r = await database.karta_sorov_ol(lid, uid)
    if r is None:
        await query.message.answer("Bu to'lov so'rovi topilmadi — /pro")
        return
    await _tolov_xabarlarini_ochir(lid, uid, r)
    await ekranni_ochir(query.message.chat.id, query.message.message_id)
    await tarif_ekrani(query.message, uid, "k", r.get("oluvchi"))


def _pro_imkoniyatlari() -> list:
    """Bayram kartasidagi imkoniyatlar — PLAN_LIMITS dan (`_perks_block` bilan
    bitta manba): tarifda yo'q narsa kartada chiqmaydi."""
    l = [["⚡", f"{_son(daily_limit('pro', 'points'))} ball/kun"],
         ["📄", f"{_son(daily_limit('pro', 'files'))} ta fayl/kun"]]
    if daily_limit('pro', 'images') != 0:
        l.append(["🎨", f"{_son(daily_limit('pro', 'images'))} ta rasm/kun"])
    if daily_limit('pro', 'research') != 0:
        l.append(["🔬", "/research — PDF hisobot"])
    return l + [["🧠", "Chuqur fikrlash"], ["💬", XOTIRA[0].upper() + XOTIRA[1:]]]


def tabrik_kartasi(tur: str, *, title: str = "", days: int = 0, gacha: str = "",
                   kim: str = "", eslatma: str = "") -> dict:
    """Bayram kartasining holati. `tur`: p — sotib oldi, o — oylik obuna,
    k — karta to'lovi tasdiqlandi, g — sovg'a oldi, y — sovg'a yubordi.
    `kim` — oddiy matn (kartada textContent). Sof — testda."""
    if tur == "o":
        a, b = "Oylik obuna yoqildi!", "Pro har oy o'zi uzayadi" + (
            f" · keyingi to'lov {gacha}" if gacha else "")
        u = "O'chirish istalgan payt: /pro"
    elif tur == "k":
        a, b = "To'lov tasdiqlandi!", f"Pro {gacha} gacha faol" if gacha else "Pro faollashdi"
        u = "Rahmat! Bemalol foydalanavering 🙌"
    elif tur == "g":
        a, b = "Sizga sovg'a! 🎁", f"{kim} sizga Pro {title} sovg'a qildi"
        u = "Holatni ko'rish: /profile"
    elif tur == "y":
        a, b = "Sovg'a yuborildi! 🎁", f"{kim} — Pro {title} ({days} kun)"
        u = eslatma or "Do'stingizga sovg'a xabari bordi"
    else:
        a = "Pro faollashdi!"
        b = f"{title} ({days} kun)" + (f" · {gacha} gacha" if gacha else "")
        u = "Rahmat! Bemalol foydalanavering 🙌"
    # Kartadagi tugmalar — xabar ostidagilar bilan bir xil callback'lar.
    profil = ["👤 Profilim", "pro:profile", "👤 Profil pastda"]
    sovga = ["🎁 Yana sovg'a" if tur == "y" else "🎁 Do'stga sovg'a", "pro:gift",
             "🎁 Pastda — kimga sovg'a qilishni yozing"]
    k = {"y": [sovga], "g": [profil], "o": [profil]}.get(tur, [profil, sovga])
    return {"a": a, "b": b, "l": _pro_imkoniyatlari(), "u": u, "k": k}


def _shaxsiy(message) -> bool:
    """Shaxsiy chatmi — xato bermaydi (to'lovdan keyingi yo'lda yiqilish
    tasdiq xabarini yo'qotardi)."""
    return getattr(getattr(message, "chat", None), "type", None) == "private"


async def _tabrik_yubor(chat_id: int, holat: dict, izoh: str, kb,
                        effekt: bool = True) -> bool:
    """Bayram kartasi. False — chaqiruvchi oddiy matnni yuboradi. Hech qachon
    ko'tarilmaydi: to'lov allaqachon berilgan, bu faqat tabrik."""
    try:
        from handlers.messages import vidjet_yubor
        from services import vidjet
        return await vidjet_yubor(chat_id, vidjet.tabrik_html(), vidjet.tabrik_holati(holat),
                                  izoh, kb, sorov=True,
                                  effekt=MESSAGE_EFFECTS.get("🎉") if effekt else None)
    except Exception as e:
        logger.warning(f"[Pro] bayram kartasi yuborilmadi (chat={chat_id}): {e}")
        return False


async def _tugash_sanasi(user_id: int) -> str:
    try:
        p = await database.get_full_user_profile(user_id)
        return _sana(p["premium_until"]) if p and p.get("premium_until") else ""
    except Exception:
        return ""


def karta_holat_matni(r: dict) -> tuple[str, list]:
    """/pro tepasidagi «to'lovim qayerda?» bloki va tugmasi. Sof — testda.
    Busiz chek yuborgan odam ikkinchi so'rov ochardi yoki adminga yozardi."""
    lid, summa = r["id"], som(r["summa"])
    if r["holat"] == "tekshirilmoqda":
        vaqt = f", chek {vaqt_html(r['chek_vaqti'], 't')} da" if r.get("chek_vaqti") else ""
        return (f"⏳ <b>To'lovingiz tekshirilmoqda</b> — #{lid} · {summa} so'm{vaqt}.\n"
                f"Pro {KARTA_VADA} yoqiladi, natija shu chatga keladi — qayta to'lash "
                f"shart emas.\n\n"), []
    tugma = [btn("📎 Chekni yuborish", f"pro:chek:{lid}", style=BTN_SUCCESS)]
    if r["holat"] == "rad":
        return (f"❌ <b>To'lov #{lid} tasdiqlanmadi</b> — {html_escape(r.get('sabab') or '')}.\n"
                f"Pul o'tkazgan bo'lsangiz, to'g'ri chekni yuboring.\n\n"), tugma
    tugash = r["yaratilgan"] + timedelta(seconds=KARTA_CHEK_OYNA)
    return (f"💳 <b>Ochiq to'lovingiz bor</b> — #{lid} · {summa} so'm, "
            f"{vaqt_html(tugash, 't')} gacha.\n"
            f"To'lagan bo'lsangiz, chek rasmini shu chatga yuboring.\n\n"), tugma


def karta_eslatma_matni(r: dict) -> str:
    _, title, _ = PRO_PLANS_BY_DAYS[r["days"]]
    tugash = r["yaratilgan"] + timedelta(seconds=KARTA_CHEK_OYNA)
    return (f"⏳ <b>To'lovingiz kutilmoqda</b> — #{r['id']} · Pro {title} · "
            f"<b>{som(r['summa'])} so'm</b>\n\n"
            f"To'lagan bo'lsangiz, <b>chek rasmini</b> shu chatga yuboring.\n"
            f"So'rov {vaqt_html(tugash, 't')} gacha ochiq.")


def karta_tugadi_matni(r: dict) -> str:
    return (f"⌛️ <b>To'lov vaqti tugadi</b> — #{r['id']} · {som(r['summa'])} so'm\n\n"
            f"{KARTA_CHEK_OYNA // 3600} soat ichida chek kelmadi, shuning uchun so'rov yopildi.\n\n"
            f"💳 <b>Pul o'tkazgan bo'lsangiz</b> — xavotir olmang: pastdagi tugma orqali "
            f"adminga chek bilan yozing (to'lov #{r['id']}), tekshirib Pro'ni yoqamiz.\n"
            f"Hali to'lamagan bo'lsangiz — yangi to'lov oching.")


async def karta_watcher() -> None:
    """main.py fonda. Har 5 daqiqada: chek yubormaganga bitta eslatma, oyna
    tugaganda «vaqt tugadi». Holat bazada — deploy xabarni qaytarmaydi ham,
    yo'qotmaydi ham."""
    await asyncio.sleep(90)
    while True:
        try:
            await karta_tekshir()
        except Exception:
            logger.exception("[Karta] watcher yiqildi")
        await asyncio.sleep(300)


async def karta_tekshir() -> None:
    """Watcher'ning bitta aylanishi."""
    r = await database.karta_eslatmalar(KARTA_ESLATMA, KARTA_CHEK_OYNA)
    for x in r["eslat"]:
        await _tolov_xabari(x["id"], await _karta_xabar(x["user_id"], karta_eslatma_matni(x), [
            [btn("📎 Chekni yuborish", f"pro:chek:{x['id']}", style=BTN_SUCCESS)],
            [btn("✖️ Bekor qilish", f"pro:kb:{x['id']}", style=BTN_DANGER)]]))
    for x in r["tugadi"]:
        # Karta va eslatma endi yaroqsiz — o'chadi; ularning o'rniga shu xabar.
        await _tolov_xabarlarini_ochir(x["id"], x["user_id"], x)
        await _karta_xabar(x["user_id"], karta_tugadi_matni(x), [
            admin_tugmasi(),
            [btn("💳 Yangi to'lov", f"pro:qayta:{x['id']}", style=BTN_PRIMARY)]])
    if r["eslat"] or r["tugadi"]:
        logger.info(f"[Karta] eslatma {len(r['eslat'])}, vaqti tugadi {len(r['tugadi'])}")


async def _karta_xabar(uid: int, matn: str, qatorlar: list) -> int | None:
    """Qaytadi: xabar id'si (yetmasa — None)."""
    mid = None
    try:
        m = await bot.send_message(uid, matn, parse_mode="HTML",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=qatorlar))
        mid = getattr(m, "message_id", None)
    except Exception as e:
        # Botni bloklagan — boshqalarga xalal bermasin.
        logger.info(f"[Karta] xabar yetmadi user={uid}: {e}")
    await asyncio.sleep(0.05)
    return mid


# ═══════════════════════════════════════════════════════════════════
#  5. SOVG'A
# ═══════════════════════════════════════════════════════════════════

class GiftStates(StatesGroup):
    waiting_for_recipient = State()


class PromoStates(StatesGroup):
    waiting_for_code = State()


_GIFT_PROMPT = (
    "🎁 <b>PRO TARIFNI SOVG'A QILISH</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Kimga sovg'a qilmoqchisiz?\n\n"
    "<blockquote>"
    "1️⃣ @username yozing\n"
    "2️⃣ yoki ID raqamini yuboring\n"
    "3️⃣ yoki uning xabarini <b>forward</b> qiling"
    "</blockquote>\n\n"
    "❗️ Sovg'a oluvchi avval botga <b>/start</b> bergan bo'lishi kerak — "
    "aks holda unga yetkazib bera olmaymiz."
)

_PROMO_PROMPT = (
    "🎟 <b>PROMOKOD</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Kodni shu yerga yuboring.\n\n"
    "<blockquote><i>Katta-kichik harf farqi yo'q.</i></blockquote>"
)

# force_reply (Bot API 10.3): tugma joyida qoladi, lekin kiritish maydoni
# o'zi ochiladi. Bu ikkala oqim ham foydalanuvchidan MATN kutadi (kimga
# sovg'a / promokod), ilgari esa buni faqat taxmin qilish kerak edi.
# ⚠️ Telegram: klaviatura TAHRIRLANGANDA force_reply qiymati o'zgarmaydi —
# shuning uchun u dastlabki so'rov xabaridayoq qo'yiladi.
_CANCEL_KB = InlineKeyboardMarkup(
    inline_keyboard=[[btn("✖️ Bekor qilish", "pro:open", style=BTN_DANGER)]],
    force_reply=True)


async def _sovga_vidjet_yubor(target, holat: dict, izoh: str, kb) -> bool:
    """Shaxsiy chatda SOVG'A kartasini (berilgan ekranda) yangi xabar qilib
    yuboradi. False — chaqiruvchi oddiy matnni yuboradi; hech qachon ko'tarilmaydi."""
    if getattr(getattr(target, "chat", None), "type", None) != "private":
        return False
    try:
        from handlers.messages import _thread_key, ekran_almashtir, vidjet_yubor
        from services import vidjet
        n = await vidjet_yubor(target.chat.id, vidjet.sovga_html(), vidjet.pro_holati(holat),
                               izoh, kb, sorov=True, thread_id=_thread_key(target))
        if n:
            await ekran_almashtir(target.chat.id, n)
        return bool(n)
    except Exception as e:
        logger.warning(f"[Pro] karta yuborilmadi ({holat.get('e')}): {e}")
        return False


async def _sovga_ekrani(message, oluvchi: int, tur: str = "s",
                        nom_html: str | None = None) -> None:
    """Sovg'a muddatlari YANGI xabar bo'lib: "s" — Stars (+ karta tugmasi),
    "k" — karta narxlari. Oluvchini chaqiruvchi tekshirgan bo'ladi."""
    from handlers.messages import ekran_almashtir
    nom = await _oluvchi_nomi(oluvchi)
    karta = bool(await _karta())
    if tur == "k" and karta:
        kb, matn = _karta_tariflar_kb(oluvchi), "💳 Karta orqali (so'mda) — muddatni tanlang:"
        holat = {"e": "k", "gf": nom, "t": tarif_plitkalari("k"), "rid": oluvchi}
    else:
        kb, matn = await _sovga_kb(oluvchi), "Muddatni tanlang:"
        holat = {"e": "s", "gf": nom, "t": tarif_plitkalari("s"), "rid": oluvchi,
                 **({"kb": 1} if karta else {})}
    izoh = f"🎁 <b>Sovg'a: {nom_html or html_escape(nom)}</b>\n\n{matn}"
    if await _sovga_vidjet_yubor(message, holat, izoh, kb):
        return
    await ekran_almashtir(message.chat.id,
                          await message.answer(izoh, parse_mode="HTML", reply_markup=kb))


async def tarif_ekrani(message, user_id: int, tur: str, oluvchi: int | None = None) -> None:
    """Muddatlar ekrani YANGI xabar bo'lib — eski ekran o'chirilgan joyda:
    karta to'lovi bekor qilingach / vaqti tugagach «Yangi to'lov», invoice'dan
    «Orqaga». `tur`: "s" — Stars, "k" — karta; `oluvchi` — sovg'a."""
    if oluvchi:
        await _sovga_ekrani(message, oluvchi, tur)
        return
    if tur == "k" and await _karta():
        kb = _karta_tariflar_kb()
    else:
        tur, kb = "s", InlineKeyboardMarkup(inline_keyboard=_buy_buttons(
            obuna=not _obuna_faol(await _obuna(user_id))) + [_ORQAGA])
    await pro_ekranini_yubor(message, user_id, tur, kb)


async def _start_gift(target, state: FSMContext) -> None:
    from handlers.messages import ekran_almashtir
    await state.set_state(GiftStates.waiting_for_recipient)
    # Karta — qadamlar; izohda qisqa savol. `force_reply` (_CANCEL_KB) karta
    # bilan rad etilsa — oldingi matnli so'rov, o'sha klaviatura bilan.
    if await _sovga_vidjet_yubor(target, {"e": "g"}, (
            "🎁 <b>Kimga sovg'a qilmoqchisiz?</b>\n"
            "@username, ID raqam yoki uning xabarini forward qiling."), _CANCEL_KB):
        return
    await ekran_almashtir(getattr(getattr(target, "chat", None), "id", 0) or 0,
                          await send_rich(target, _GIFT_PROMPT, _CANCEL_KB))


async def _start_promo(target, state: FSMContext) -> None:
    await state.set_state(PromoStates.waiting_for_code)
    await send_rich(target, _PROMO_PROMPT, _CANCEL_KB)


async def handle_gift(message: Message, state: FSMContext):
    await _start_gift(message, state)


async def _cancelled_by_command(message: Message, state: FSMContext) -> bool:
    """FSM ichida buyruq yozilsa holatni bo'shatadi.

    Bu handlerlar dp.message'da AI handlerlaridan oldin turadi, shuning
    uchun buyruqni o'tkazib yubormasak foydalanuvchi "kimga sovg'a qilay?"
    holatida qamalib qolardi va /pro ham ishlamasdi.
    """
    text = (message.text or "").strip()
    if not text.startswith("/"):
        return False
    await state.clear()
    if text.split()[0] in ("/pro", "/start"):
        await handle_pro(message, state)
    else:
        await message.answer("↩️ Bekor qilindi.")
    return True


async def validate_recipient(buyer_id: int, recipient_id: int) -> tuple[bool, str]:
    """Sovg'a oluvchi haqiqatan yaroqlimi? (ok, xato_matni)

    ⚠️ XAVFSIZLIK: bu tekshiruv IKKI joyda chaqiriladi — suhbat oqimida VA
    `pro:buy:<kun>:<oluvchi>` callback'ida. Faqat suhbatda qoldirilsa,
    o'zgartirilgan mijoz to'g'ridan-to'g'ri callback yuborib butun
    tekshiruvni chetlab o'tardi va biz yetkazib bera olmaydigan sovg'a
    uchun pul olib qo'ygan bo'lardik.
    """
    if recipient_id == buyer_id:
        return False, ("🙂 O'zingizga sovg'a qilish shart emas — /pro dan "
                       "to'g'ridan-to'g'ri sotib olsangiz bo'ladi.")
    if recipient_id <= 0:
        return False, "❌ Noto'g'ri foydalanuvchi."

    try:
        target = await database.get_full_user_profile(recipient_id)
    except Exception as exc:
        logger.error(f"[Pro] oluvchini tekshirishda xatolik: {exc}")
        return False, "⚠️ Texnik nosozlik. Birozdan keyin urinib ko'ring."

    if not target:
        link = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "bot havolasi"
        return False, (
            f"❌ Bu foydalanuvchi topilmadi.\n\n"
            f"U avval botga <b>/start</b> bergan bo'lishi kerak. "
            f"Unga shu havolani yuboring:\n{link}")
    if target.get("is_banned"):
        return False, "❌ Bu foydalanuvchi bloklangan, unga sovg'a qilib bo'lmaydi."
    if (target.get("plan_type") or 'free') != 'free' and target.get("premium_until") is None:
        return False, ("ℹ️ Bu foydalanuvchida allaqachon <b>muddatsiz</b> tarif "
                       "bor — sovg'a unga hech narsa qo'shmaydi.")
    return True, ""


async def process_gift_recipient(message: Message, state: FSMContext):
    """Sovg'a oluvchini aniqlaydi va TO'LOVDAN OLDIN hamma tekshiruvni qiladi.

    Yetkazib bera olmaydigan sovg'ani sotmaslik — bu oqimning butun mohiyati.
    """
    if await _cancelled_by_command(message, state):
        return

    buyer = message.from_user.id

    # Forward qilingan xabar — eng qulay yo'l. Foydalanuvchining maxfiylik
    # sozlamasi yoqilgan bo'lsa forward_from None bo'ladi (Telegram cheklovi),
    # u holda @username so'raymiz.
    # ⚠️ `forward_origin`, `forward_from` EMAS: Bot API 7.0 dan beri Telegram
    # eski maydonni yubormaydi (aiogram'da qolgan, lekin doim None) — forward
    # yo'li jimgina ishlamay, xabar matni @username deb qidirilardi.
    origin = getattr(message, "forward_origin", None)
    forwarded = getattr(origin, "sender_user", None)
    if forwarded is not None:
        identifier = str(forwarded.id)
    else:
        identifier = (message.text or "").strip()

    if not identifier:
        await message.answer(
            "❌ Tushunarsiz. @username, ID raqam yoki forward qilingan xabar yuboring."
        )
        return

    try:
        # get_user_by_identifier() @username'ni ham, raqamli ID'ni ham
        # qabul qiladi va FAQAT user_id qaytaradi.
        recipient_id = await database.get_user_by_identifier(identifier)
    except Exception as exc:
        logger.error(f"[Pro] sovg'a oluvchini qidirishda xatolik: {exc}")
        await message.answer("⚠️ Texnik nosozlik. Birozdan keyin urinib ko'ring.")
        return

    if not recipient_id:
        await state.clear()
        link = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "bot havolasi"
        await message.answer(
            f"❌ Bu foydalanuvchi topilmadi.\n\n"
            f"U avval botga <b>/start</b> bergan bo'lishi kerak. "
            f"Unga shu havolani yuboring:\n{link}\n\n"
            f"U start bosgach, /pro → 🎁 Sovg'a dan qayta urinib ko'ring.",
            parse_mode="HTML",
        )
        return

    ok, error = await validate_recipient(buyer, recipient_id)
    if not ok:
        await state.clear()
        await message.answer(error, parse_mode="HTML")
        return

    target = await database.get_full_user_profile(recipient_id)
    await state.clear()
    # Stars narxlari + (karta sozlangan bo'lsa) «💳 Karta orqali» — sovg'a ham
    # so'mda (obunasiz: obuna to'lovchining o'z balansidan). «Kimga?» so'rovi
    # shu ekran bilan almashadi (`ekran_almashtir`).
    await _sovga_ekrani(message, recipient_id, "s", _display_name(target or {}, recipient_id))
    # Javob (@username / forward) ham o'chadi: oluvchi endi sarlavhada turibdi.
    if _shaxsiy(message):
        try:
            await message.delete()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
#  6. REFERAL
# ═══════════════════════════════════════════════════════════════════
# ponytail: RAM keshi — qaysi foydalanuvchi uchun "hisobga olish" so'rovi
# allaqachon yuborilganini eslab qoladi. Restartda yo'qoladi va bitta
# ortiqcha UPDATE bo'ladi, xolos: qualify_referral() ning o'zi idempotent,
# shuning uchun bu faqat optimizatsiya. Redis kerak emas.
#
# ⚠️ Chegara SHART: cheksiz o'sadigan to'plam uzoq ishlagan botda xotirani
# yeb, sekin DoS'ga aylanadi. Chegaraga yetganda tozalanadi — eng yomon
# holatda bir nechta ortiqcha UPDATE bo'ladi, boshqa zarari yo'q.
_REFERRAL_CACHE_MAX = 20000
_referral_checked: set[int] = set()


async def register_referral(invited_id: int, raw_referrer: str) -> None:
    """/start ref_<id> — taklifni yozadi (mukofot hali berilmaydi)."""
    try:
        referrer_id = int(raw_referrer)
    except (TypeError, ValueError):
        return
    if referrer_id == invited_id or referrer_id <= 0:
        return          # o'z-o'ziga taklif
    try:
        if not await database.has_started(referrer_id):
            return      # mavjud bo'lmagan taklifchi
        await database.add_referral(invited_id, referrer_id)
    except Exception as e:
        logger.debug(f"[Referal] yozishda xatolik: {e}")


async def maybe_qualify_referral(user_id: int) -> None:
    """Foydalanuvchi HAQIQIY xabar yozdi — taklifni hisobga olamiz va
    yetarli bo'lsa taklifchiga mukofot beramiz.

    Bonus /start da emas, aynan shu yerda beriladi: aks holda soxta
    akkauntlar ochib cheksiz kun yig'ish mumkin bo'lardi.
    """
    if user_id in _referral_checked:
        return
    if len(_referral_checked) >= _REFERRAL_CACHE_MAX:
        _referral_checked.clear()
    _referral_checked.add(user_id)
    try:
        referrer_id = await database.qualify_referral(user_id)
        if referrer_id is None:
            return
        # Shart TAKLIFCHIga qarab olinadi (shaxsiy -> umumiy -> config):
        # bloger uchun qo'yilgan yengil shart uning o'z havolasiga tegishli.
        cfg = await database.get_referral_config(referrer_id)
        rewarded = await database.claim_referral_reward(
            referrer_id, cfg['required'], cfg['reward_days'], cfg['max_rewards'])
        if not rewarded:
            return
        await menu_module.sync_commands(referrer_id, True)
        try:
            await bot.send_message(referrer_id, (
                f"🎉 <b>Referal mukofoti!</b>\n\n"
                f"{cfg['required']} ta do'stingiz botdan foydalana boshladi — "
                f"sizga <b>{cfg['reward_days']} kun Pro</b> qo'shildi.\n\n"
                f"👤 Holatni ko'rish: /profile"
            ), parse_mode="HTML")
        except TelegramForbiddenError:
            await database.deactivate_user(referrer_id)
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"[Referal] hisobga olishda xatolik: {e}")


def _referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}" if BOT_USERNAME else ""


def _share_message(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """DO'STGA boradigan xabar: chiroyli matn + ostida havolali tugma.

    Tugmada `style` ATAYLAB yo'q: bu xabarni bot emas, foydalanuvchi
    yuboradi (inline rejim), rang esa bot imkoniyati — rad etilsa butun
    xabar ketmay qolardi.
    """
    link = _referral_link(user_id)
    text = (
        "🤖 <b>AI yordamchini sinab ko'ring!</b>\n\n"
        "💬 Har qanday savolga javob\n"
        "🌐 Internetdan qidiruv\n"
        "📄 Hujjat va rasm tahlili\n"
        "🎤 Ovozli suhbat\n"
        "📊 Fayllar yaratish va yana ko'plab AI funksiyalar!\n\n"
        "👇 Botga ushbu tugma orqali qo'shiling:"
    )
    # Rang inline natijada ham qabul qilinadi (API'da tekshirilgan), lekin
    # noto'g'ri qiymat BUTUN natijani rad etadi — shuning uchun faqat
    # core/config.py dagi konstanta ishlatiladi, satr yozilmaydi.
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn("🤖ChatGPT-AI", "", style=BTN_PRIMARY, url=link)]])
    return text, kb


def _share_button(user_id: int) -> InlineKeyboardButton:
    """Ulashish tugmasi — inline rejim bo'lsa chiroylisi, bo'lmasa eskisi.

    Inline rejimda foydalanuvchi chat tanlaydi va xabar UNING nomidan,
    tugmasi bilan birga ketadi. t.me/share/url esa faqat TEKIS MATN
    yubora oladi — havola va matn yalang'och ko'rinib turishining sababi
    aynan shu edi, kodning kamchiligi emas.
    """
    if INLINE_ENABLED:
        return InlineKeyboardButton(
            text="📤 Do'stlarga ulashish", switch_inline_query="")
    # Zaxira: hech bo'lmaganda matn to'g'ri kodlansin ("%20" ko'rinmasin).
    from urllib.parse import quote
    link = _referral_link(user_id)
    matn = "Bu AI bot zo'r ekan — o'zbekcha gapiradi, sinab ko'r!"
    return btn("📤 Do'stlarga ulashish", "", style=BTN_SUCCESS,
               url=f"https://t.me/share/url?url={quote(link, safe='')}"
                   f"&text={quote(matn, safe='')}")


async def handle_inline_share(query: InlineQuery) -> None:
    """Inline rejim: "@bot" yozib chat tanlaganda chiqadigan yagona natija.

    ⛔️ INLINE REJIM HOZIR O'CHIQ VA SHUNDAY QOLISHI KERAK — bu handler
    faqat kelajak uchun turibdi.

    ⚠️ BU YERDA YOZILGAN ESKI FARAZ NOTO'G'RI EDI. Ilgari shu izohda
    "ikkalasi yonma-yon yashaydi, biri ikkinchisini almashtirmaydi"
    deb yozilgandi. Jonli sinov (2026-09-10) buni rad etdi: /setinline
    yoqilganda Telegram "@bot savol" ni INLINE SO'ROV deb oladi,
    yuborish tugmasi yo'qoladi va xabar `guest_message` bo'lib UMUMAN
    yuborilmaydi — ekran aylanib turib "x" bilan tugaydi. Pastdagi
    "bo'sh ro'yxat qaytaramiz" hiylasi ham yordam bermaydi: natija
    bo'lmagani xabarni oddiy xabar sifatida yuborishga imkon bermaydi.

    Ya'ni tanlov: CHIROYLI ULASHISH TUGMASI yoki GUEST MODE. Guest Mode
    ancha qimmatliroq, shuning uchun inline o'chiq. Ulashish tugmasi
    zaxira yo'lda (t.me/share/url) baribir ishlaydi — faqat xabar
    tugmasiz, tekis matn bo'ladi.

    Quyidagi mantiq o'zgarishsiz qoldi: agar kimdir inline'ni yoqib
    qo'ysa, kamida referal kartochkasi faqat BO'SH so'rovda chiqadi.
    """
    if (query.query or "").strip():
        try:
            await query.answer([], cache_time=0, is_personal=True)
        except Exception as e:
            logger.debug(f"[Referal] bo'sh inline javob berilmadi: {e}")
        return

    text, kb = _share_message(query.from_user.id)
    try:
        await query.answer(
            [InlineQueryResultArticle(
                id=f"ref{query.from_user.id}",
                title="📤 Do'stga taklif yuborish",
                description="Chiroyli xabar + tugma bilan ketadi",
                input_message_content=InputTextMessageContent(
                    message_text=text, parse_mode="HTML",
                    link_preview_options={"is_disabled": True}),
                reply_markup=kb,
            )],
            cache_time=300,
            # ⚠️ is_personal=True SHART: natija ichida foydalanuvchining
            # SHAXSIY referal havolasi bor. Umumiy kesh bo'lsa Telegram uni
            # boshqa odamga ham berib yuborardi va u begona havolani
            # tarqatib, mukofotni boshqa birov olardi.
            is_personal=True,
        )
    except Exception as e:
        logger.debug(f"[Referal] inline javob berilmadi: {e}")


async def _render_referral(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    try:
        p = await database.get_referral_progress(user_id)
    except Exception:
        p = {'invited': 0, 'qualified': 0, 'rewarded': 0}
    try:
        cfg = await database.get_referral_config(user_id)
    except Exception:
        cfg = {'required': REFERRAL_REQUIRED, 'reward_days': REFERRAL_REWARD_DAYS,
               'claimed': False}
    required, reward_days = cfg['required'], cfg['reward_days']
    claimed = cfg.get('claimed', False)

    toward_next = p['qualified'] - p['rewarded']
    need = max(0, required - toward_next)
    link = _referral_link(user_id) or "(havola tayyorlanmoqda)"

    # Vizual progress: har bir do'st bitta belgi. Raqamdan ko'ra
    # "yana 1 ta qoldi" degan his kuchliroq turtki beradi.
    done = min(required, toward_next)
    dots = "🟢" * done + "⚪️" * (required - done)

    if claimed:
        # Mukofot shu to'lqinda allaqachon olingan. Buni AYTMASAK, odam
        # do'st chaqirib, hech narsa olmay, botni aldayapti deb o'ylardi.
        status = ("✅ Mukofot olingan — keyingi taklif e'lon qilinganda "
                  "yana ochiladi")
    elif need == 0:
        status = "🎉 Mukofot tayyor!"
    else:
        status = f"Yana <b>{need} ta</b> do'st kerak"

    text = (
        f"👥 <b>DO'ST TAKLIF QILING</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>Har <b>{required} ta</b> do'st uchun "
        f"<b>{reward_days} kun Pro</b> — mutlaqo bepul.\n"
        f"Har taklifda <b>bir marta</b>.</blockquote>\n\n"
        f"{dots}  <b>{done}/{required}</b>\n"
        f"{status}\n\n"
        f"📊 <b>Statistikangiz</b>\n"
        f"├ Taklif qilingan: <b>{p['invited']}</b>\n"
        f"├ Faol bo'lgan: <b>{p['qualified']}</b>\n"
        f"└ Olingan mukofot: <b>{p['rewarded'] // required * reward_days} kun</b>\n\n"
        f"🔗 <b>Havolangiz</b> <i>(bosib nusxalang)</i>\n"
        f"<code>{link}</code>\n\n"
        f"<blockquote expandable><i>Do'stingiz havola orqali kirib, "
        f"birinchi savolini berganda hisobga olinadi — shunchaki /start "
        f"bosish yetarli emas. Bu qoida soxta akkauntlarga qarshi.</i></blockquote>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_share_button(user_id)],
        [btn("💎 Pro tarif", "pro:open", style=BTN_PRIMARY)],
        [btn("✖️ Yopish", "pro:close", style=BTN_DANGER)],
    ])
    return text, kb


# ═══════════════════════════════════════════════════════════════════
#  7. PROMOKOD
# ═══════════════════════════════════════════════════════════════════

# ⚠️ XAVFSIZLIK — PROMOKODNI TAXMIN QILISHGA QARSHI.
#
# Kod ikki yo'l bilan kiritiladi: /promo buyrug'i va `pro:code:<KOD>`
# callback'i. Callback_data mijoz tomonidan yuboriladi, ya'ni hujumchi
# tugmani ko'rmasdan ham sekundiga o'nlab kodni sinab ko'ra oladi.
# Cheklovsiz bu "bepul Pro generatori" bo'lardi.
#
# Sirpanuvchi oyna: PROMO_WINDOW soniya ichida PROMO_MAX_TRIES urinish.
# MUVAFFAQIYATSIZ urinishlar sanaladi — to'g'ri kod kiritgan odam
# jazolanmaydi.
PROMO_MAX_TRIES = 5
PROMO_WINDOW = 600           # 10 daqiqa
_promo_tries: dict[int, list[float]] = {}
_PROMO_TRIES_MAX_USERS = 5000     # ponytail: RAM chegarasi, Redis kerak emas


def _promo_rate_limited(user_id: int) -> int:
    """0 — ruxsat; >0 — necha soniya kutish kerak."""
    now = time.time()
    tries = [t for t in _promo_tries.get(user_id, []) if now - t < PROMO_WINDOW]
    _promo_tries[user_id] = tries
    if len(tries) < PROMO_MAX_TRIES:
        return 0
    return int(PROMO_WINDOW - (now - tries[0])) + 1


def _promo_note_failure(user_id: int) -> None:
    if len(_promo_tries) > _PROMO_TRIES_MAX_USERS:
        # Eng eski yozuvlarni tashlab yuboramiz — cheksiz o'sish DoS bo'ladi.
        now = time.time()
        for uid in [u for u, ts in _promo_tries.items()
                    if not ts or now - ts[-1] > PROMO_WINDOW]:
            _promo_tries.pop(uid, None)
    _promo_tries.setdefault(user_id, []).append(time.time())


_PROMO_REASONS = {
    # ATAYLAB umumiy matn: kod bor-yo'qligini oshkor qilmaymiz, aks holda
    # kodlarni taxmin qilib topish osonlashadi.
    'invalid':   "❌ Kod topilmadi yoki muddati o'tgan.",
    'revoked':   "❌ Kod topilmadi yoki muddati o'tgan.",
    'expired':   "❌ Kod topilmadi yoki muddati o'tgan.",
    'exhausted': "❌ Bu kod ishlatilib bo'lingan.",
    'already':   "ℹ️ Siz bu koddan allaqachon foydalangansiz.",
}


async def _apply_promo(target, user_id: int, code: str) -> None:
    # ⚠️ Tezlik cheklovi HAR QANDAY bazaga borishdan OLDIN — aks holda
    # hujumchi baza yukini oshirib DoS ham qila olardi.
    wait = _promo_rate_limited(user_id)
    if wait:
        await target.answer(
            f"⏳ Juda ko'p urinish. <b>{wait // 60 + 1} daqiqa</b>dan keyin "
            f"qayta urinib ko'ring.",
            parse_mode="HTML")
        return

    code = (code or "").strip()
    # Kod formati qat'iy: faqat harf/raqam/pastki chiziq. Bu SQL uchun emas
    # (so'rovlar parametrlangan), balki keraksiz bazaga borishni to'sish va
    # HTML'ga begona belgi tushmasligi uchun.
    if not code or len(code) > 32 or not code.replace("_", "").isalnum():
        _promo_note_failure(user_id)
        await target.answer("❌ Kod topilmadi yoki muddati o'tgan.")
        return

    try:
        result = await database.redeem_promo(user_id, code)
    except Exception as exc:
        logger.error(f"[Promo] xatolik: {exc}")
        await target.answer("⚠️ Texnik nosozlik. Birozdan keyin urinib ko'ring.")
        return

    if not result['ok']:
        # Faqat MUVAFFAQIYATSIZ urinish sanaladi.
        _promo_note_failure(user_id)
        await send_rich(
            target,
            _PROMO_REASONS.get(result['reason'], _PROMO_REASONS['invalid']),
            InlineKeyboardMarkup(inline_keyboard=[
                [btn("🎟 Boshqa kod kiritish", "pro:promo")],
                [btn("💎 Pro tarif", "pro:open", style=BTN_PRIMARY)],
            ]))
        return

    # To'lov yo'li bilan bir xil: Pro buyruqlari keyingi xabarni kutmasin.
    await menu_module.sync_commands(user_id, True)
    await send_rich(target, (
        f"🎉 <b>PROMOKOD QABUL QILINDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>💎 Sizga <b>{result['days']} kun Pro</b> qo'shildi.\n"
        f"⚡️ Kunlik ball: <b>{daily_limit('pro', 'points')}</b>\n"
        f"{pe('document', '📄')} Kunlik fayl: <b>{daily_limit('pro', 'files')} ta</b>"
        f"</blockquote>"
    ), InlineKeyboardMarkup(inline_keyboard=[
        [btn("👤 Profilimni ko'rish", "pro:profile", style=BTN_PRIMARY)]]),
        effect=MESSAGE_EFFECTS.get("🎉"))


# ═══════════════════════════════════════════════════════════════════
#  7b. ADMIN YUBORADIGAN "BEPUL PRO" XABARLARI
# ═══════════════════════════════════════════════════════════════════
# Bu xabarlar FAQAT admin tanlagan odamga boradi (handlers/admin.py →
# 🎁 Bepul Pro). Ommaviy ekranlarda promokod/referal tugmalari yo'q —
# aks holda hamma bepulini kutib o'tirardi va hech kim sotib olmasdi.

async def send_promo_gift(user_id: int, code: str, days: int,
                          expires_at=None, note: str = "") -> bool:
    """Foydalanuvchiga promokodni chiroyli xabar bilan yuboradi.

    Kod HAM matnda (nusxa olish uchun), HAM bitta bosishda faollashadigan
    tugmada beriladi — qo'lda yozdirish keraksiz ishqalanish.
    """
    deadline = ""
    if expires_at is not None:
        deadline = (f"\n⏰ <b>Amal qilish muddati:</b> "
                    f"{expires_at.strftime('%d.%m.%Y')} gacha")
    extra = f"\n\n<blockquote>{note}</blockquote>" if note else ""

    text = (
        f"🎁 <b>SIZGA MAXSUS SOVG'A</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Siz uchun <b>{days} kunlik Pro</b> tarif ajratildi.{extra}\n\n"
        f"<blockquote>"
        f"⚡️ Kunlik ball: <b>{daily_limit('pro', 'points')}</b> "
        f"<i>(bepulda {daily_limit('free', 'points')})</i>\n"
        f"{pe('document', '📄')} Kunlik fayl: <b>{daily_limit('pro', 'files')} ta</b> "
        f"<i>(bepulda {daily_limit('free', 'files')})</i>\n"
        f"⏰ Takroriy eslatmalar · 🧠 Chuqur fikrlash · 💬 {XOTIRA}"
        f"</blockquote>\n\n"
        f"🎟 <b>Kodingiz:</b> <code>{code}</code>{deadline}\n\n"
        f"👇 Faollashtirish uchun tugmani bosing:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn(f"🎟 {days} kunlik Pro'ni olish", f"pro:code:{code}", style=BTN_SUCCESS)],
    ])
    try:
        await bot.send_message(
            user_id, text, parse_mode="HTML", reply_markup=kb,
            message_effect_id=MESSAGE_EFFECTS.get("🎉"))
        return True
    except Exception as exc:
        logger.warning(f"[Bepul Pro] promokod yetmadi (user={user_id}): {exc}")
        return False


async def send_referral_invite(user_id: int, note: str = "") -> bool:
    """Foydalanuvchiga uning SHAXSIY referal havolasini yuboradi."""
    link = _referral_link(user_id) or None
    if link is None:
        logger.error("[Bepul Pro] BOT_USERNAME yo'q — referal havolasi yasab bo'lmadi")
        return False

    # YANGI TO'LQIN. Har bir taklifda mukofot huquqi qaytadan ochiladi va
    # bitta to'lqinda faqat bir marta beriladi. Bu shu yerda — taklif
    # yuboriladigan HAR QANDAY yo'l shu funksiyadan o'tadi, admin
    # oqimlariga tarqatilsa yangi yo'l qo'shilganda unutilardi.
    try:
        await database.bump_referral_round(user_id)
    except Exception:
        logger.exception(f"[Referal] to'lqin oshirilmadi (user={user_id})")
        return False

    # Shart shu odamning O'ZIGA qarab olinadi — admin unga shaxsiy shart
    # qo'ygan bo'lsa, taklif xabarida ham aynan shu ko'rinishi kerak.
    try:
        cfg = await database.get_referral_config(user_id)
    except Exception:
        cfg = {'required': REFERRAL_REQUIRED, 'reward_days': REFERRAL_REWARD_DAYS}
    required, reward_days = cfg['required'], cfg['reward_days']

    extra = f"\n\n<blockquote>{note}</blockquote>" if note else ""
    text = (
        f"👥 <b>DO'STLARINGIZNI TAKLIF QILING</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Siz uchun maxsus taklif dasturi ochildi.{extra}\n\n"
        f"<blockquote>"
        f"<b>{required} ta</b> do'st taklif qiling — "
        f"<b>{reward_days} kun Pro</b> bepul.\n"
        f"<i>Bu taklif bo'yicha bir marta beriladi.</i>"
        f"</blockquote>\n\n"
        f"🔗 <b>Shaxsiy havolangiz</b> <i>(bosib nusxalang)</i>\n"
        f"<code>{link}</code>\n\n"
        f"<blockquote expandable><i>Do'stingiz havola orqali kirib, "
        f"birinchi savolini berganda hisobga olinadi — shunchaki /start "
        f"bosish yetarli emas.</i></blockquote>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [_share_button(user_id)],
        [btn("📊 Holatimni ko'rish", "pro:ref", style=BTN_PRIMARY)],
    ])
    try:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
        return True
    except Exception as exc:
        logger.warning(f"[Bepul Pro] referal taklifi yetmadi (user={user_id}): {exc}")
        return False


async def handle_promo(message: Message, state: FSMContext, command=None):
    """/promo KOD — yoki argumentsiz bo'lsa kodni so'raydi."""
    args = (command.args if command else None) or ""
    if args.strip():
        await state.clear()
        await _apply_promo(message, message.from_user.id, args)
        return
    await _start_promo(message, state)


async def process_promo_code(message: Message, state: FSMContext):
    if await _cancelled_by_command(message, state):
        return
    await state.clear()
    await _apply_promo(message, message.from_user.id, message.text or "")


# ═══════════════════════════════════════════════════════════════════
#  8. CALLBACK ROUTER
# ═══════════════════════════════════════════════════════════════════

async def _obuna_taklif(query: CallbackQuery, user_id: int) -> None:
    """Obuna havolasi. ⚠️ `send_invoice` obuna qila olmaydi — faqat
    createInvoiceLink (`subscription_period`), ya'ni URL tugma."""
    try:
        if await database.is_banned(user_id):
            await query.message.answer(BAN_MATNI, reply_markup=admin_kb())
            return
    except Exception as exc:
        logger.warning(f"[Obuna] ban tekshiruvi o'tmadi: {exc}")
    if _obuna_faol(await _obuna(user_id)):
        await query.message.answer("♻️ Oylik obunangiz allaqachon yoqilgan — /pro")
        return
    try:
        havola = await bot.create_invoice_link(
            title="Pro — oylik obuna",
            description=(f"Har 30 kunda {OBUNA_NARX} ⭐ · {daily_limit('pro', 'points')} "
                         f"ball/kun · chuqur fikrlash · {XOTIRA}"),
            payload=build_obuna_payload(user_id, OBUNA_NARX),
            provider_token="", currency="XTR",
            prices=[LabeledPrice(label="Pro · 1 oy", amount=OBUNA_NARX)],
            subscription_period=OBUNA_DAVR,
        )
    except Exception as exc:
        logger.error(f"[Obuna] havola yasalmadi: {exc}")
        await query.message.answer(
            "⚠️ <b>Obuna oynasini ochib bo'lmadi.</b>\n\nBirozdan keyin qayta urinib "
            "ko'ring." + ADMIN_IZOH, parse_mode="HTML", reply_markup=admin_kb())
        return
    await send_rich(query.message, (
        f"♻️ <b>PRO — OYLIK OBUNA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote>"
        f"⭐️ Har 30 kunda <b>{OBUNA_NARX} ⭐</b> Stars balansingizdan o'zi yechiladi.\n"
        f"⏳ Pro uzilmaydi — muddatni eslab, qayta sotib olish shart emas.\n"
        f"🔕 Istalgan payt o'chirasiz: /pro yoki Telegram → Sozlamalar → Stars."
        f"</blockquote>"
    ), kb=InlineKeyboardMarkup(inline_keyboard=[
        [btn(f"⭐️ Obuna bo'lish — {OBUNA_NARX} ⭐/oy", "", url=havola, style=BTN_SUCCESS)],
        [btn("✖️ Yopish", "pro:close", style=BTN_DANGER)],
    ]))


async def handle_pro_callback(query: CallbackQuery, state: FSMContext):
    data = query.data or ""
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    user_id = query.from_user.id

    if action == "close":
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if action == "open":
        await query.answer()
        await state.clear()          # sovg'a/promokod holatidan chiqish ham shu tugma
        chat = getattr(query.message, "chat", None)
        if chat is not None and chat.type != "private":
            # Guruhda Pro ekrani butun guruhga chiqardi — tarif, xarid, invoice
            # SHAXSIY ma'lumot. Ekranning keyingi tugmalari ham guruhga
            # yaramaydi (invoice ochiq ketadi, sovg'a/promokod FSM guruhda
            # ochiladi). Shuning uchun guruhda — faqat bosgan odamga
            # (ephemeral, Bot API 10.4) shaxsiy chatga havola.
            from handlers.messages import ephemeral_params   # ⚠️ tsiklik import
            havola = f"https://t.me/{BOT_USERNAME or 'vexonai'}?start=pro"
            await send_rich(query.message,
                            "💎 <b>Pro tarifi</b> — narxlar va to'lov shaxsiy chatda.",
                            InlineKeyboardMarkup(inline_keyboard=[[btn(
                                "💎 Pro'ni ochish", "", url=havola, style=BTN_SUCCESS)]]),
                            **ephemeral_params(query.message, query))
            return
        # Limit xabari ostidagi tugmadan kelinganda o'sha xabarni tahrirlash
        # noto'g'ri bo'lardi (foydalanuvchi limit haqidagi ma'lumotni
        # yo'qotardi) — yangi xabar yuboramiz.
        await pro_ekranini_yubor(query.message, user_id)
        return

    if action == "buy":
        # ⚠️ XAVFSIZLIK: callback_data — MIJOZ yuboradigan ma'lumot. Uni
        # "biz yasagan tugmadan keldi" deb hisoblash mumkin emas: maxsus
        # mijoz istalgan `pro:buy:<kun>:<oluvchi>` ni yuborishi mumkin.
        # Shuning uchun HAR BIR maydon shu yerda qaytadan tekshiriladi.
        await query.answer()
        try:
            days = int(parts[2])
            beneficiary = int(parts[3]) if len(parts) > 3 else user_id
        except (IndexError, ValueError):
            await query.message.answer("⚠️ Tugma eskirgan. /pro dan qayta boshlang.")
            return

        # 1) Muddat — faqat katalogdagi qiymat (narxni o'zi tanlab bo'lmaydi).
        if days not in PRO_PLANS_BY_DAYS:
            await query.message.answer("⚠️ Bu tarif endi mavjud emas. /pro dan qayta boshlang.")
            return

        # 2) Sotib oluvchining o'zi banlanganmi — banlangan odam pul to'lab
        #    ham botdan foydalana olmaydi, ya'ni bu bilib turib qaytariladigan
        #    to'lov bo'lardi. Undan ko'ra sotmagan yaxshi.
        try:
            if await database.is_banned(user_id):
                await query.message.answer(BAN_MATNI, reply_markup=admin_kb())
                return
        except Exception as exc:
            logger.warning(f"[Pro] buy: ban tekshiruvi o'tmadi: {exc}")

        # 3) Sovg'a bo'lsa — oluvchini TO'LIQ tekshiramiz. Suhbat oqimidagi
        #    tekshiruvga tayanish yetarli emas (yuqoridagi izohga qarang).
        if beneficiary != user_id:
            ok, error = await validate_recipient(user_id, beneficiary)
            if not ok:
                await query.message.answer(error, parse_mode="HTML")
                return

        from handlers.messages import ekran_almashtir, ekranni_ochir
        chat_id = query.message.chat.id
        try:
            inv = await _send_invoice(chat_id, days, beneficiary,
                                      is_gift=(beneficiary != user_id))
        except Exception as exc:
            logger.error(f"[Pro] invoice yuborilmadi: {exc}")
            await query.message.answer(
                "⚠️ <b>To'lov oynasini ochib bo'lmadi.</b>\n\nBirozdan keyin qayta urinib "
                "ko'ring." + ADMIN_IZOH, parse_mode="HTML", reply_markup=admin_kb())
            return
        # Muddatlar ekrani invoice bilan almashadi (qaytish — «⬅️ Orqaga»).
        await ekranni_ochir(chat_id, query.message.message_id)
        await ekran_almashtir(chat_id, inv, "invoice")
        return

    if action == "orqa":
        # Invoice'dagi «⬅️ Orqaga» (`pro:orqa[:<oluvchi>]`): invoice o'chadi,
        # Stars muddatlari qaytadan. Oluvchi — mijoz ma'lumoti, qayta tekshiriladi.
        oluvchi = None
        if len(parts) > 2:
            oluvchi = await _sovga_oluvchisi(query, parts, 2)
            if oluvchi is None:
                return
        await query.answer()
        from handlers.messages import ekranni_ochir
        await ekranni_ochir(query.message.chat.id, query.message.message_id)
        await tarif_ekrani(query.message, user_id, "s", oluvchi)
        return

    if action == "stars" and len(parts) > 2:
        # Sovg'aning Stars ekrani (karta muddatlaridan «Orqaga»).
        oluvchi = await _sovga_oluvchisi(query, parts, 2)
        if oluvchi is None:
            return
        await query.answer()
        await _tugmalarni_almashtir(query, await _sovga_kb(oluvchi), "🎁 <b>Muddatni tanlang:</b>")
        await _pro_holatini_yoz(query, {"e": "s", "gf": await _oluvchi_nomi(oluvchi),
                                        "t": tarif_plitkalari("s"), "rid": oluvchi,
                                        **({"kb": 1} if await _karta() else {})})
        return

    if action == "stars":
        await query.answer()
        await _tugmalarni_almashtir(query, InlineKeyboardMarkup(
            inline_keyboard=_buy_buttons(obuna=not _obuna_faol(await _obuna(user_id)))
            + [_ORQAGA]), "⭐️ <b>Muddatni tanlang:</b>")
        await _pro_ekrani_almashtir(query, user_id, "s")
        return

    if action == "obuna":
        await query.answer()
        await _obuna_taklif(query, user_id)
        return

    if action == "obuna_bekor":
        await query.answer()
        if len(parts) < 3 or parts[2] != "ha":
            # Tasdiq — bitta tasodifiy bosish oylik to'lovni o'chirib yubormasin.
            await _tugmalarni_almashtir(query, InlineKeyboardMarkup(inline_keyboard=[
                [btn("🔕 Ha, o'chirilsin", "pro:obuna_bekor:ha", style=BTN_DANGER)],
                [btn("⬅️ Yo'q, qolsin", "pro:usul")],
            ]), "🔕 Avtomatik to'lov o'chirilsinmi?")
            return
        if await obuna_toxtat(user_id):
            until = ((await database.get_full_user_profile(user_id)) or {}).get("premium_until")
            gacha = f" Pro <b>{vaqt_html(until)}</b> gacha ishlaydi." if until else ""
            await send_rich(query.message, (
                f"🔕 <b>Avtomatik to'lov o'chirildi.</b>{gacha}\n\n"
                f"Fikringiz o'zgarsa — /pro dan qayta obuna bo'lasiz."))
        else:
            await _safe_send(query.message, (
                "⚠️ <b>Obunani o'chirib bo'lmadi.</b>\n\nTelegram → Sozlamalar → "
                "Telegram Stars → obunalar bo'limidan o'chirsa ham bo'ladi."))
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if action == "usul":
        await query.answer()
        _, kb = await _render_pro_screen(user_id)
        await _tugmalarni_almashtir(query, kb, "💎 <b>Pro</b> — to'lov usulini tanlang:")
        await _pro_ekrani_almashtir(query, user_id, "")
        return

    if action in ("kartalar", "karta", "chek", "kb", "qayta", "kt", "kr"):
        await _karta_callback(query, state, parts)
        return

    if action == "gift":
        await query.answer()
        await _start_gift(query.message, state)
        return

    if action == "promo":
        await query.answer()
        await _start_promo(query.message, state)
        return

    if action == "code":
        # Admin yuborgan xabardagi "bir bosishda olish" tugmasi.
        # Kod callback_data ichida (max 32 belgi — "pro:code:" bilan
        # birga 41 bayt, Telegram chegarasi 64).
        await query.answer()
        code = data.split(":", 2)[2] if len(parts) > 2 else ""
        # Tugmani darhol olib tashlaymiz: ikki marta bosilsa ikkinchisi
        # "allaqachon ishlatgansiz" degan chalkash javob berardi.
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await _apply_promo(query.message, user_id, code)
        return

    if action == "ref":
        await query.answer()
        text, kb = await _render_referral(user_id)
        await send_rich(query.message, text, kb)
        return

    if action == "profile":
        await query.answer()
        from handlers.profile import handle_profile
        # user_id ni ANIQ uzatamiz: query.message — botning o'z xabari,
        # uning from_user'i bot bo'ladi.
        await handle_profile(query.message, user_id=user_id)
        return

    await query.answer()
