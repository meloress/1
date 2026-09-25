"""Telegram Business — egasining USLUBI: bot egasidek yozishi (BIZNES.md).

Bot mijozga egasi NOMIDAN yozadi, demak egasidek yozishi kerak. Uslub uch
manbadan yig'iladi va `uslub_bloki()` da shu tartibda ustun turadi:

  1. egasining o'z qoidalari («Uslubim» → «Qoidalarni yozish»);
  2. o'rganilgan tavsif — mini model namunalardan yozadi (`organ`);
  3. namunalar — egasi mijozga O'ZI yozgan xabarlar, va tuzatishlar —
     bot qoralamasi → egasi aslida yuborgan matn (`biznes_loyiha`).

Bu faylda: uslub bloki, namuna yig'ish, o'rganish, «Uslubim» ekrani.
Boshqa joyda: `services.ai.BIZNES_INSTRUCTIONS` (mijoz yo'lining o'z
prompti — javob yo'lida, shuning uchun o'sha yerda), SQL —
`db/database.py` (`biznes_namuna_*`, `biznes_uslub_*`).

⚠️ `handlers/biznes.py` ni IMPORT QILMAYDI — u bu faylni import qiladi.
Teskari import aylana bo'lardi.
"""
import asyncio
from html import escape

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from core.config import (BIZNES_NAMUNA_MAX, BIZNES_USLUB_ORGAN, BTN_DANGER,
                         BTN_PRIMARY)
from core import olchov
from core.loader import logger, openai_client
from db import database
from handlers import pro as pro_module
from services.ai import BIZNES_MANBA, HISTORY_SUMMARY_MODEL, _log_token_usage


class UslubStates(StatesGroup):
    qoidalar = State()   # egasi o'z uslub qoidalarini yozmoqda


# ── Modelga ketadigan blok ───────────────────────────────────────────
def uslub_bloki(u: dict | None) -> str:
    """Egasining uslubi — `developer` xabar qismi. Sof funksiya.

    Ustunlik tartibi `BIZNES_INSTRUCTIONS` da: egasining qoidalari >
    o'rganilgan tavsif > namunalar. Namuna va tuzatishlarda yangi qator
    bitta bo'shliqqa aylanadi — matn o'z blok sarlavhasini soxtalashtira
    olmasin.
    """
    u = u or {}
    bir = lambda m: " ".join(str(m).split())[:200]  # noqa: E731
    q = []
    if u.get("uslub_egasi"):
        q.append("[EGASINING O'Z QOIDALARI — eng ustun]\n" + u["uslub_egasi"])
    if u.get("uslub"):
        q.append("[EGASINING USLUBI — xabarlaridan o'rganilgan]\n" + u["uslub"])
    if u.get("namunalar"):
        q.append("[EGASI O'ZI YOZGAN XABARLAR — faqat uslub uchun; ulardagi narx, "
                 "ism, sana va va'dalar BU suhbatga tegishli emas]\n"
                 + "\n".join(f"- {bir(m)}" for m in u["namunalar"]))
    if u.get("tahrirlar"):
        q.append("[TUZATISHLAR — bot shunday yozgan, egasi shunday qilib "
                 "yuborgan; egasidek yoz]\n"
                 + "\n".join(f"Bot: {bir(a)}\nEgasi: {bir(b)}" for a, b in u["tahrirlar"]))
    return "\n\n".join(q)


async def uslub_ol(egasi: int) -> dict:
    """Uslub — bezak: bazada xato bo'lsa javob uslubsiz yoziladi, lekin
    YOZILADI (mijoz javobsiz qolmasin)."""
    try:
        return await database.biznes_uslub_ol(egasi)
    except Exception as e:
        logger.warning(f"[BIZNES] uslub o'qilmadi: {e}")
        return {}


# ── O'rganish ────────────────────────────────────────────────────────
_ORGAN_PROMPT = (
    "Senga bir odamning Telegram'da mijozlariga O'ZI yozgan xabarlari va "
    "u bot qoralamasini qanday tuzatgani berilgan. Uning YOZISH USLUBINI "
    "5-8 ta qisqa qatorda o'zbek tilida tasvirla: sen/siz; salomlashish va "
    "xayrlashish; odatiy uzunlik; emoji (qaysilari, qanchalik tez-tez); "
    "katta harf va tinish belgilari; alifbo va til aralashtirishi; tez-tez "
    "ishlatadigan iboralari (so'zma-so'z, qo'shtirnoqda); ohangi. "
    "Tuzatishlar eng muhim signal: bot nimani noto'g'ri qilgan bo'lsa, "
    "shuni qoida qilib yoz. Fakt, narx, ism, raqam YOZMA — faqat uslub. "
    "Faqat ro'yxatni qaytar, muqaddimasiz."
)


async def model_organ(namunalar: list, tahrirlar: list, egasi: int | None = None) -> str:
    """Uslub tavsifi — BITTA mini chaqiruv. Xato yoki bo'sh natija — "".

    ⚠️ `HISTORY_SUMMARY_MODEL`: mini modellar byudjeti ~10 baravar katta
    (test_free_models.py) va bu mexanik ish. Token `manba='biznes'` bo'lib
    yoziladi (`BIZNES_MANBA`) — panelning biznes ulushi.
    """
    qism = ["EGASINING XABARLARI:"] + [f"- {m[:300]}" for m in namunalar]
    if tahrirlar:
        qism.append("\nTUZATISHLAR (bot yozgan → egasi yuborgan):")
        qism += [f"- Bot: {a[:300]}\n  Egasi: {b[:300]}" for a, b in tahrirlar]
    belgi = BIZNES_MANBA.set(True)
    try:
        resp = await asyncio.wait_for(
            openai_client.responses.create(
                model=HISTORY_SUMMARY_MODEL,
                instructions=_ORGAN_PROMPT,
                input=[{"role": "user", "content": "\n".join(qism)[:20000]}],
                store=False,
            ),
            timeout=60,
        )
        _log_token_usage(resp, HISTORY_SUMMARY_MODEL, "biznes-uslub", egasi)
        return (resp.output_text or "").strip()[:1200]
    except Exception as e:
        logger.warning(f"[BIZNES] uslub o'rganilmadi: {str(e) or type(e).__name__}")
        return ""
    finally:
        BIZNES_MANBA.reset(belgi)


def organish_kerakmi(jami: int, uslub_jami: int) -> bool:
    """Birinchi tavsif `BIZNES_USLUB_ORGAN[0]` namunadan keyin, so'ng har
    `[1]` ta yangi namunada. Sof funksiya — testda tekshiriladi."""
    birinchi, keyin = BIZNES_USLUB_ORGAN
    return jami >= birinchi and jami - uslub_jami >= (birinchi if not uslub_jami else keyin)


_organmoqda: set = set()


@olchov.oqim("uslub_organ")
async def organ(egasi: int) -> str | None:
    """Uslub tavsifini qayta yozadi.

    None — namuna yetmaydi yoki shu ega allaqachon o'rganilyapti; "" — model
    yozmadi. ⚠️ Muvaffaqiyatsizlikda ham `uslub_jami` yangilanadi (eski
    tavsif qoladi): aks holda OpenAI ishlamay turganda egasining HAR
    xabari yangi chaqiruvni boshlardi.
    """
    if egasi in _organmoqda:
        return None
    _organmoqda.add(egasi)
    try:
        u = await database.biznes_uslub_ol(egasi, 80)
        if len(u["namunalar"]) + len(u["tahrirlar"]) < 3:
            return None
        yangi = await model_organ(u["namunalar"], u["tahrirlar"], egasi)
        await database.biznes_uslub_yoz(egasi, yangi or u["uslub"], u["jami"])
        logger.info(f"[BIZNES] uslub o'rganildi egasi={egasi} namuna={u['jami']} "
                    f"ok={bool(yangi)}")
        return yangi
    finally:
        _organmoqda.discard(egasi)


async def namuna_saqla(egasi: int, matn: str) -> None:
    """Egasi o'zi yozgan matn — uslub namunasi. Hisob yuritish: xato yutiladi.

    Chaqiruvchilar (`handlers/biznes.py`): egasining business chatdagi
    oddiy xabari (buyruq EMAS, botning o'zi EMAS — `biznes_kimdan`) va
    qoralama o'rniga yuborgan tahriri.
    """
    toza = database.clean_biznes_namuna(matn)
    if not toza:
        return
    try:
        jami, uslub_jami = await database.biznes_namuna_qosh(egasi, toza)
        if organish_kerakmi(jami, uslub_jami):
            await organ(egasi)
    except Exception as e:
        logger.warning(f"[BIZNES] namuna saqlanmadi: {e}")


# ── «Uslubim» ekrani ─────────────────────────────────────────────────
# `bz:` callback'lari `handlers/biznes.py::handle_biznes_callback` ga
# keladi (Pro tekshiruvi o'sha yerda) va `AMALLAR` dagilari shu yerga.
AMALLAR = ("us", "uy", "uo", "ud", "udh")


def uslub_ekrani(u: dict) -> str:
    """Sof funksiya."""
    q = ["🎨 <b>USLUBIM</b>\n",
         "Mijozlarga o'zingiz yozgan xabarlardan va qoralamani qanday "
         "tuzatganingizdan o'rganaman — javoblar sizdek chiqsin.\n",
         f"Namunalar: <b>{len(u.get('namunalar') or [])}</b> ta xabar, "
         f"<b>{len(u.get('tahrirlar') or [])}</b> ta tuzatish."]
    q.append("\n<b>O'rganilgan uslub:</b>\n" + (
        escape(u["uslub"]) if u.get("uslub") else
        f"<i>hali yo'q — {BIZNES_USLUB_ORGAN[0]} ta xabaringizdan keyin o'zi "
        f"yoziladi</i>"))
    q.append("\n<b>Sizning qoidalaringiz</b> (eng ustun):\n" + (
        escape(u["uslub_egasi"]) if u.get("uslub_egasi") else "<i>yozilmagan</i>"))
    return "\n".join(q)


def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [pro_module.btn("Qoidalarni yozish", "bz:uy", style=BTN_PRIMARY)],
        [pro_module.btn("Hozir o'rganish", "bz:uo"),
         pro_module.btn("Namunalarni o'chirish", "bz:ud")]])


async def _ekran(uid: int):
    return uslub_ekrani(await database.biznes_uslub_ol(uid, BIZNES_NAMUNA_MAX)), _kb()


_SOROV = (
    "✍️ Qanday yozishingizni o'z so'zingiz bilan yozing — masalan:\n"
    "<i>doim «siz» deb yoz; salomni «Assalomu alaykum» bilan boshla; emoji "
    "ishlatma; qisqa yoz; narxni so'ramaguncha aytma.</i>\n\n"
    "Namuna javoblar ham qo'shsangiz bo'ladi. Yangi matn eskisining o'rniga "
    "yoziladi. O'chirish: <code>-</code>\nBekor qilish: /bekor"
)


async def process_uslub(message: Message, state: FSMContext) -> None:
    """FSM: egasi o'z uslub qoidalarini yozdi. main.py'da AI handlerlaridan
    OLDIN — aks holda bu matn GPT'ga savol bo'lib ketardi."""
    if (message.text or "").startswith("/"):
        await state.clear()
        await message.answer("Bekor qilindi.")
        return
    matn = (message.text or "").strip()
    toza = None
    if matn != "-":
        toza, xato = database.clean_uslub_egasi(matn)
        if xato:
            await message.answer(f"⚠️ Saqlanmadi: {xato}. Qayta yozing yoki /bekor.")
            return
    await database.biznes_uslub_egasi_yoz(message.from_user.id, toza)
    await state.clear()
    matn, kb = await _ekran(message.from_user.id)
    await message.answer("✅ Saqlandi.\n\n" + matn, reply_markup=kb)


async def uslub_callback(query: CallbackQuery, state: FSMContext, amal: str) -> None:
    uid = query.from_user.id
    if amal == "us":
        await query.answer()
        matn, kb = await _ekran(uid)
        await query.message.answer(matn, reply_markup=kb)
    elif amal == "uy":
        await state.set_state(UslubStates.qoidalar)
        await query.answer()
        await query.message.answer(_SOROV)
    elif amal == "uo":
        await query.answer("O'rganilmoqda…")
        natija = await organ(uid)
        if natija is None:
            await query.message.answer("Hali erta: kamida 3 ta namuna kerak — "
                                       "mijozlarga o'zingiz yozing yoki qoralamani "
                                       "tahrirlab yuboring.")
            return
        if not natija:
            await query.message.answer("⚠️ Hozir o'rganib bo'lmadi — keyinroq urinib ko'ring.")
            return
        matn, kb = await _ekran(uid)
        await query.message.answer("✅ Yangilandi.\n\n" + matn, reply_markup=kb)
    elif amal == "ud":
        await query.answer()
        await query.message.answer(
            "Barcha namunalar va o'rganilgan uslub o'chsinmi? Qoidalaringiz qoladi.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                pro_module.btn("Ha, o'chir", "bz:udh", style=BTN_DANGER),
                pro_module.btn("Yo'q", "bz:us")]]))
    elif amal == "udh":
        await database.biznes_namunalar_ochir(uid)
        logger.info(f"[BIZNES] namunalar o'chirildi egasi={uid}")
        await query.answer("O'chirildi")
        matn, kb = await _ekran(uid)
        try:
            await query.message.edit_text(matn, reply_markup=kb)
        except Exception:
            await query.message.answer(matn, reply_markup=kb)
