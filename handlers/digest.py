"""Kunlik daydjest (Pro): foydalanuvchi tanlagan soatda tanlagan mavzular
bo'yicha qisqa xulosa yuboriladi.

Bu Telegram'ga XOS imkoniyat — veb-chatbot sizga o'zi yozolmaydi.

Alohida fayl, chunki handlers/messages.py allaqachon 1400 qatordan oshgan
va bu feature u bilan `_dm_or_deactivate` dan boshqa hech narsa bo'lishmaydi.
"""
import asyncio
from datetime import datetime, timezone

from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from html import escape as html_escape

from core.loader import logger
from db import database
from handlers.helpers import _dm_or_deactivate
from handlers.helpers import _mavzular
from handlers.messages import _send_rich_message, _thread_key
from handlers.pro import btn, send_rich, BTN_PRIMARY, BTN_SUCCESS, BTN_DANGER
from services.ai import (get_gpt_reply, build_rich_markdown, strip_image_tokens,
                         strip_internal_names)

# Kunning HAMMA soati tanlanadi va bir nechtasi birga bo'lishi mumkin.
# Ilgari 6 ta "mazmunli" soat bor edi va bittasigina saqlanardi.
DIGEST_HOURS = tuple(range(24))
_HOURS_PER_ROW = 6
# Mavzular yozilib, soat hali tanlanmagan holat uchun.
_DEFAULT_HOUR = 8

_MAX_TOPICS_LEN = 200

# Mavzu yozilmagan obuna ham ISHLAYDI. Mavzu so'rovi FSM'da (RAM) kutadi va
# har deploy uni o'chiradi — ilgari bunday obuna «✅ Faol» ko'rinib, daydjest
# esa hech qachon kelmasdi (SQL mavzusizlarni o'tkazib yuborardi).
_STANDART_MAVZU = "O'zbekiston va dunyodagi eng muhim yangiliklar"

# ⚠️ Kuniga ko'pi bilan shuncha daydjest. Har biri internet qidiruvli
# to'liq javob (~15k token); «Barcha soatlar» bitta odamga kuniga 24 ta,
# ya'ni bepul grantning ~15% ini berardi — va 24 xabarda bir xil yangilik.
_MAX_HOURS = 4

# 10 daqiqa. sleep(3600) bo'lsa 08:00 so'ragan odam 08:57 da olishi
# mumkin edi — so'rov bitta indeksli UPDATE, arzon.
_DIGEST_TICK = 600


class DigestStates(StatesGroup):
    waiting_for_topics = State()


_INTRO = (
    "⏰ <b>KUNLIK DAYDJEST</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "<blockquote>Har kuni siz tanlagan soatda, siz tanlagan mavzular "
    "bo'yicha qisqa xulosa yuboraman — internetdan tekshirib.</blockquote>\n\n"
)

_PRO_ONLY = (
    "⏰ <b>Kunlik daydjest — Pro imkoniyati</b>\n\n"
    "<blockquote>Har kuni belgilangan soatda sizni qiziqtirgan mavzular "
    "bo'yicha tayyor xulosa keladi: yangiliklar, kurslar, sport — "
    "nimani so'rasangiz.</blockquote>"
)


def _hours_keyboard(selected, *, locked: bool = False) -> InlineKeyboardMarkup:
    """Soat tugmalari — bosilgani qo'shiladi, qayta bosilsa olib tashlanadi.

    Tanlanganlari yashil. 24 ta tugma 6 tadan qatorlarga bo'linadi, ya'ni
    klaviatura 4 qator — ekranda bemalol sig'adi.

    `locked=True` (bepul tarif) — panjara ko'rinadi, lekin bosilmaydi
    (Bot API 10.3: `disabled`). Sabab: "Pro imkoniyati" degan quruq matn
    nima yo'qotilayotganini ko'rsatmaydi, ko'rinib turgan panjara esa
    ko'rsatadi. Bosilmagani uchun soxta va'da ham bermaydi.
    """
    chosen = set(selected or ())
    rows, row = [], []
    for h in DIGEST_HOURS:
        faol = h in chosen
        row.append(btn(f"✅{h:02d}" if faol else f"{h:02d}",
                       f"dg:h:{h}", style=BTN_SUCCESS if faol else None,
                       disabled=locked))
        if len(row) == _HOURS_PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if locked:
        rows.append([btn("💎 Pro tarif", "pro:open", style=BTN_SUCCESS)])
        rows.append([btn("✖️ Yopish", "dg:close", style=BTN_DANGER)])
    elif chosen:
        rows.append([btn("✏️ Mavzularni o'zgartirish", "dg:topics", style=BTN_PRIMARY),
                     btn("🧹 Tozalash", "dg:clear")])
        rows.append([btn("🔕 Daydjestni to'xtatish", "dg:off", style=BTN_DANGER)])
    else:
        rows.append([btn("✖️ Yopish", "dg:close", style=BTN_DANGER)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyingi_vaqt(hours, hozir: datetime) -> str:
    """Birinchi daydjest qachon: "bugun 20:00" / "ertaga 08:00". Sof.

    Joriy soat "yuborilgan" deb belgilanadi (`set_digest`), shuning uchun
    faqat KEYINGI soatlar bugunga sanaladi. Ilgari "keyingi belgilangan
    soatda" deyilardi — joriy soatni tanlagan odam bugun kutib, hech narsa
    olmay, "ishlamayapti" derdi.
    """
    hours = sorted(hours or ())
    if not hours:
        return "—"
    bugun = [h for h in hours if h > hozir.hour]
    return f"bugun {bugun[0]:02d}:00" if bugun else f"ertaga {hours[0]:02d}:00"


def _hozir() -> datetime:
    return datetime.now(database.TASHKENT_TZ)


def _mavzu_label(topics) -> str:
    return (html_escape(topics) if topics else
            "<i>yozilmagan — umumiy yangiliklar keladi</i> (✏️ bilan o'zgartiring)")


def _hours_label(hours) -> str:
    """[7, 12] -> "07:00, 12:00" """
    return ", ".join(f"{h:02d}:00" for h in hours) or "—"


def _user_hours(profile) -> list[int]:
    """Profildan tanlangan soatlar. Eski digest_hour ham hisobga olinadi."""
    raw = (profile or {}).get("digest_hours")
    if raw:
        return database.parse_digest_hours(raw)
    eski = (profile or {}).get("digest_hour")
    return database.parse_digest_hours([eski] if eski is not None else [])


def _pro_faol(profile) -> bool:
    """`take_due_digests()` SQL shartining o'zi: tarif 'free' emas VA muddati
    o'tmagan. Ilgari ekran faqat tarifni tekshirardi — muddati o'tgan Pro
    soat tanlab, mavzu yozib, keyin hech narsa olmasdi."""
    if (profile or {}).get("plan_type", "free") in (None, "free"):
        return False
    muddat = profile.get("premium_until")
    return muddat is None or muddat > datetime.now(timezone.utc)


async def _profile_or_none(user_id: int):
    try:
        return await database.get_full_user_profile(user_id)
    except Exception as e:
        logger.error(f"[Daydjest] profil o'qishda xatolik: {e}")
        return None


async def _ekran(target, profile) -> None:
    """/kunlik ekrani — `/kunlik` va «⚙️ Soatlar» tugmasi IKKALASI shu yerdan.
    Ilgari tugma o'z qisqa matnini chizardi (mavzusiz, muddati o'tganda ham
    «✅ Faol»)."""
    if not _pro_faol(profile):
        # Panjara o'chirilgan holda ko'rsatiladi — foydalanuvchi nimadan
        # mahrumligini KO'RADI, lekin bosa olmaydi.
        await send_rich(target, _PRO_ONLY, _hours_keyboard(None, locked=True))
        return

    hours = _user_hours(profile)
    if hours:
        status = (f"✅ <b>Faol:</b> har kuni <b>{_hours_label(hours)}</b>\n"
                  f"📌 <b>Mavzular:</b> {_mavzu_label(profile.get('digest_topics'))}\n"
                  f"📨 <b>Keyingisi:</b> {keyingi_vaqt(hours, _hozir())}\n\n"
                  f"<i>Soatni bosib qo'shasiz, qayta bosib olib tashlaysiz.</i>")
    else:
        status = ("🔕 Hozircha o'chirilgan.\n\n"
                  f"<i>Kerakli soatlarni bosing — {_MAX_HOURS} tagacha "
                  "(Toshkent vaqti).</i>")
    await send_rich(target, _INTRO + status, _hours_keyboard(hours))


async def handle_digest(message: Message, state: FSMContext):
    """/kunlik — obunani sozlash ekrani."""
    await state.clear()
    profile = await _profile_or_none(message.from_user.id)
    if profile is None:
        await message.answer("⚠️ Profilingiz topilmadi. /start buyrug'ini bering.")
        return
    await _ekran(message, profile)


async def handle_digest_callback(query: CallbackQuery, state: FSMContext):
    parts = (query.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    user_id = query.from_user.id

    if action == "close":
        # «✖️ Bekor qilish» mavzu so'rovida ham shu: holatdan CHIQISH kerak,
        # aks holda keyingi har qanday gap mavzu bo'lib saqlanardi.
        if await state.get_state() == DigestStates.waiting_for_topics.state:
            await state.clear()
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if action == "off":
        await query.answer("🔕 Daydjest to'xtatildi.", show_alert=True)
        try:
            await database.set_digest(user_id, None)
        except Exception as e:
            logger.error(f"[Daydjest] o'chirishda xatolik: {e}")
            return
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if action == "topics":
        await query.answer()
        await _ask_topics(query.message, state)
        return

    if action == "menu":
        # Soat ekranini QAYTA ochadi — daydjest ostidagi va sozlash
        # tugmalaridan shu yerga qaytiladi.
        await query.answer()
        profile = await _profile_or_none(user_id)
        if profile is not None:
            await _ekran(query.message, profile)
        return

    if action in ("h", "all", "clear"):
        profile = await _profile_or_none(user_id)
        if profile is None or not _pro_faol(profile):
            await query.answer("💎 Bu Pro imkoniyati.", show_alert=True)
            return

        hours = set(_user_hours(profile))
        if action == "all":
            # Eski xabarlardagi tugma — endi yo'q (`_MAX_HOURS` izohi).
            await query.answer(f"Kuniga ko'pi bilan {_MAX_HOURS} ta soat tanlanadi.",
                               show_alert=True)
            return
        elif action == "clear":
            hours = set()
            javob = "🧹 Tozalandi"
        else:
            # ⚠️ Soat MIJOZDAN keladi (callback_data). O'zgartirilgan mijoz
            # istalgan qiymat yubora oladi, shuning uchun qat'iy tekshiruv.
            if len(parts) != 3:
                await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
                return
            try:
                hour = int(parts[2])
            except ValueError:
                await query.answer("❌ Noto'g'ri so'rov.", show_alert=True)
                return
            if hour not in DIGEST_HOURS:
                await query.answer("❌ Bu soat mavjud emas.", show_alert=True)
                return
            if hour in hours:
                hours.discard(hour)
                javob = f"➖ {hour:02d}:00 olib tashlandi"
            elif len(hours) >= _MAX_HOURS:
                await query.answer(f"Kuniga ko'pi bilan {_MAX_HOURS} ta soat — "
                                   "avval birini olib tashlang.", show_alert=True)
                return
            else:
                hours.add(hour)
                javob = f"✅ {hour:02d}:00 qo'shildi"

        try:
            # Mavzu (topic) — tugma bosilgan joy: daydjest o'sha yerga keladi.
            await database.set_digest(user_id, sorted(hours),
                                      thread_id=_thread_key(query.message))
        except Exception as e:
            logger.error(f"[Daydjest] saqlashda xatolik: {e}")
            await query.answer("❗ Texnik nosozlik.", show_alert=True)
            return

        if hours and action == "h" and javob.startswith("✅"):
            javob += f" · birinchisi {keyingi_vaqt(hours, _hozir())}"
        await query.answer(javob)
        if hours and not profile.get("digest_topics"):
            await _ask_topics(query.message, state)
            return
        try:
            await query.message.edit_reply_markup(
                reply_markup=_hours_keyboard(sorted(hours)))
        except Exception:
            pass
        return

    await query.answer()


async def _ask_topics(target, state: FSMContext) -> None:
    await state.set_state(DigestStates.waiting_for_topics)
    await send_rich(target, (
        "📌 <b>Qaysi mavzular qiziqtiradi?</b>\n\n"
        "Bitta xabarda yozing.\n\n"
        "<blockquote>Masalan: <i>O'zbekistondagi yangiliklar, dollar kursi, "
        "IT sohasidagi o'zgarishlar</i></blockquote>\n\n"
        "<i>Yozmasangiz ham daydjest keladi — umumiy yangiliklar bo'yicha.</i>"
    # force_reply — foydalanuvchidan matn kutilyapti, kiritish maydoni
    # o'zi ochilsin (handlers/pro.py:_CANCEL_KB bilan bir xil sabab).
    ), InlineKeyboardMarkup(
        inline_keyboard=[[btn("✖️ Bekor qilish", "dg:close", style=BTN_DANGER)]],
        force_reply=True))


async def process_digest_topics(message: Message, state: FSMContext):
    """FSM: mavzular matni. Buyruq yozilsa holatdan chiqamiz."""
    text = (message.text or "").strip()

    # Buyruq — bu mavzu emas, foydalanuvchi boshqa narsa qilmoqchi.
    # (handlers/pro.py dagi _cancelled_by_command bilan bir xil sabab.)
    if text.startswith("/"):
        await state.clear()
        await message.answer("↩️ Bekor qilindi.")
        return

    if not text:
        await message.answer("❗️ Mavzularni matn bilan yozing.")
        return

    await state.clear()
    topics = text[:_MAX_TOPICS_LEN]
    try:
        profile = await _profile_or_none(message.from_user.id)
        hours = _user_hours(profile) or [_DEFAULT_HOUR]
        await database.set_digest(message.from_user.id, hours, topics,
                                  thread_id=_thread_key(message))
    except Exception as e:
        logger.error(f"[Daydjest] mavzularni saqlashda xatolik: {e}")
        await message.answer("⚠️ Texnik nosozlik. Birozdan keyin urinib ko'ring.")
        return

    await send_rich(message, (
        f"✅ <b>Daydjest sozlandi!</b>\n\n"
        f"<blockquote>⏰ Har kuni: <b>{_hours_label(hours)}</b>\n"
        f"📌 Mavzular: {html_escape(topics)}</blockquote>\n\n"
        f"📨 Birinchisi: <b>{keyingi_vaqt(hours, _hozir())}</b> (Toshkent vaqti)"
    ), InlineKeyboardMarkup(inline_keyboard=[
        [btn("⚙️ Soatlarni o'zgartirish", "dg:menu", style=BTN_PRIMARY)],
        [btn("🔕 Daydjestni to'xtatish", "dg:off", style=BTN_DANGER)]]))


_DIGEST_HEADER = "⏰ <b>KUNLIK DAYDJEST</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
# Markdown yo'li uchun — u yerda <b> emas, ** ishlatiladi.
_DIGEST_HEADER_MD = "⏰ **KUNLIK DAYDJEST**\n\n"


def _digest_keyboard() -> InlineKeyboardMarkup:
    # To'xtatish tugmasi HAR daydjest ostida — foydalanuvchi aynan shu
    # yerda, xabarni o'qib turib qaror qiladi.
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("⚙️ Soatlar", "dg:menu", style=BTN_PRIMARY),
         btn("🔕 To'xtatish", "dg:off", style=BTN_DANGER)]])


async def _send_digest(user_id: int, body: str, thread_id: int = 0) -> None:
    """Daydjestni ODDIY JAVOB bilan bir xil yo'ldan yuboradi.

    Ilgari matn `parse_mode="HTML"` bilan ketardi, model esa Markdown
    yozadi — natijada foydalanuvchi xom `**qalin**` va `[matn](havola)`
    ko'rardi. Endi oddiy savol javobi qaysi yo'ldan ketsa, daydjest ham
    o'shandan ketadi (build_rich_markdown + sendRichMessage).

    Zaxira: rich yo'l ishlamasa eski HTML yo'li. U bloklagan
    foydalanuvchini is_active=FALSE qilishni ham o'z zimmasiga oladi.

    `thread_id` — /kunlik sozlangan mavzu (topic); o'chirilgan bo'lsa
    mavzusiz qayta (eslatmalar bilan bir xil: `_mavzular`).
    """
    kb = _digest_keyboard()
    try:
        rich = build_rich_markdown(_DIGEST_HEADER_MD + body)
        for mavzu in _mavzular(thread_id):
            if await _send_rich_message(user_id, markdown=rich, reply_markup=kb,
                                        message_thread_id=mavzu) is not None:
                return
    except Exception as e:
        logger.warning(f"[Daydjest] rich yuborilmadi (user={user_id}): {e}")
    await _dm_or_deactivate(user_id, _DIGEST_HEADER + html_escape(body), kb,
                            thread_id=thread_id)


async def _build_digest(topics: str) -> str:
    """Daydjest matnini oddiy tool sikli orqali tayyorlaydi.

    chat_id=0 ATAYLAB: (a) foydalanuvchining suhbat tarixi daydjestni
    buzmasin, (b) daydjest uning tarixiga yozilib, ertangi savollariga
    ta'sir qilmasin. `output_files` berilmaydi → sandbox o'chiq, arzon.
    """
    prompt = (
        f"Bugungi sana bo'yicha shu mavzular yuzasidan qisqa kunlik "
        f"daydjest tayyorla: {topics}\n\n"
        f"internet_search bilan tekshir. Format: har mavzu uchun 1-2 gap, "
        f"eng ko'pi 6 punkt, oxirida manbalar. 1200 belgidan oshmasin."
    )
    parts: list[str] = []
    async for chunk in get_gpt_reply(0, prompt, is_pro=True):
        if not chunk or chunk.startswith("[STATUS]"):
            continue
        if "[CLEAR_TEXT]" in chunk:
            parts.clear()
            chunk = chunk.replace("[CLEAR_TEXT]", "")
        if chunk:
            parts.append(chunk)
    # Oddiy javob yo'lidagi ikki himoya: vosita nomlari sizmasin, rasmlar
    # esa bu yerda yuborilmaydi — `[rasm:N]` xom matn bo'lib qolmasin.
    return strip_image_tokens(strip_internal_names("".join(parts))).strip()


async def _bitta_daydjest(row: dict, sem: asyncio.Semaphore) -> None:
    """Bitta foydalanuvchi. Xato SHU YERDA ushlanadi: ilgari bir kishining
    yuborish xatosi butun tsiklni to'xtatardi, qolganlar esa bazada
    allaqachon "yuborildi" edi — o'sha kuni hech narsa olmasdi."""
    uid = row["user_id"]
    async with sem:
        try:
            body = await _build_digest(row.get("digest_topics") or _STANDART_MAVZU)
            if not body:
                # Ilgari jim edi: sanoq "yuborildi", foydalanuvchi esa hech narsa olmasdi.
                logger.warning(f"[Daydjest] bo'sh javob (user={uid})")
                return
            await _send_digest(uid, body, row.get("digest_thread_id") or 0)
            logger.info(f"[Daydjest] yuborildi (user={uid})")
        except Exception as e:
            # Sanoq allaqachon "yuborildi" deb belgilangan — ertaga qayta
            # uriniladi. Ataylab: soat bo'yi qayta urinib bezovta qilmaymiz.
            logger.error(f"[Daydjest] tayyorlab bo'lmadi (user={uid}): "
                         f"{type(e).__name__}: {e}")


# Bir vaqtda nechta daydjest tayyorlanadi. Ketma-ket bo'lsa 08:00 dagi
# o'ninchi odam ~8 daqiqa kutardi (har biri qidiruvli to'liq javob); ko'p
# bo'lsa OpenAI TPM chegarasi. ponytail: doimiy son, navbat kerak bo'lsa — keyin.
_PARALLEL = 3


async def daily_digest_watcher():
    """premium_expiry_watcher() bilan bir xil naqsh — while + sleep, cron yo'q."""
    while True:
        await asyncio.sleep(_DIGEST_TICK)
        try:
            due = await database.take_due_digests()
            if due:
                logger.info(f"[Daydjest] {len(due)} ta foydalanuvchiga tayyorlanmoqda")
                sem = asyncio.Semaphore(_PARALLEL)
                await asyncio.gather(*(_bitta_daydjest(dict(r), sem) for r in due))
        except Exception as e:
            logger.error(f"[Daydjest] fon vazifasida xatolik: {e}")
