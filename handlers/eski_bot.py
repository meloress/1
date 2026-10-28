"""Eski bot (@uzchatgptaibot) — faqat yangi botga yo'naltiradi.

Bot @vexonai ga ko'chdi. Eski token `ESKI_BOT_TOKEN` da turadi va shu
jarayonning ichida ALOHIDA Dispatcher bilan polling qiladi: kim nima
qilmasin — matn, rasm, tugma, guruhdagi @eslatma — bitta qat'iy xabar oladi.

Nega alohida Railway service emas: kod 150 qator, bazaga TEGMAYDI, va
yangi botning `getMe` username'ini o'qiydi — bitta jarayonda bu tekin.

⛔️ Ataylab qilinmaydiganlar:
- Business: mijozga HECH NARSA yuborilmaydi. Mijoz egasi bilan
  gaplashyapman deb o'ylaydi; unga «bot to'xtatildi» yozish egasining
  obro'sini to'kadi. Faqat egasiga, bir marta, «yangi botni ulang».
- To'lov: `pre_checkout_query` RAD etiladi. Javobsiz qoldirilsa ham to'lov
  o'tmaydi, lekin odam sababini bilmay qoladi.
- Baza: hech qanday yozuv yo'q. Pro, tarix, limitlar yangi botda — o'sha
  baza, o'sha user_id.
"""
import asyncio
import logging
import time

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound, TelegramRetryAfter
from aiogram.methods import AnswerGuestQuery
from aiogram.types import (
    BotCommandScopeAllPrivateChats, BotCommandScopeChat, BotCommandScopeDefault,
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQueryResultArticle, InputTextMessageContent, MenuButtonDefault, Message,
    PreCheckoutQuery, BusinessConnection,
)

logger = logging.getLogger(__name__)

_LOGO = "assets/vexon_logo.jpg"
_ZAXIRA_NOM = "vexonai"
# Bitta odam albom yoki ketma-ket 5 xabar yuborsa — 5 marta bir xil javob
# emas, bittasi yetadi.
_JIM_SONIYA = 10


def _yangi() -> str:
    """Yangi botning username'i — main.py getMe() dan keyin to'ladi."""
    from handlers import pro as pro_module
    return pro_module.BOT_USERNAME or _ZAXIRA_NOM


def _matn() -> str:
    y = _yangi()
    return (
        "⛔️ <b>Bu bot o'z faoliyatini to'xtatdi.</b>\n\n"
        f"Barcha funksiyalar yangi botga ko'chirildi: <b>@{y}</b>\n\n"
        "✅ Pro obunangiz, limitlaringiz va suhbat tarixingiz o'sha yerda "
        f"saqlangan — @{y} ga o'ting, <b>/start</b> bosing va bemalol "
        "davom eting.\n\n"
        "Bu botda endi hech qanday funksiya ishlamaydi."
    )


def _tugma() -> InlineKeyboardMarkup:
    y = _yangi()
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🚀 @{y} ga o'tish", url=f"https://t.me/{y}")]])


_oxirgi: dict[int, float] = {}       # ponytail: RAM, deploy'da tozalanadi — bu faqat shovqin filtri
_tozalangan: set[int] = set()        # menyusi tozalangan chatlar
_egasiga_aytilgan: set[int] = set()  # Business egalari
_logo_id: str | None = None          # birinchi yuborishdan keyin file_id
_bot: Bot | None = None              # /eski_xabar shu orqali yuboradi
_eski_nom: str = "uzchatgptaibot"    # getMe dan keyin aniq nom


def _elon(ega: bool = False) -> str:
    """Bir martalik tarqatma matni (/eski_xabar). Javob matnidan (`_matn`)
    farqi: bu odam hech narsa so'ramagan — shuning uchun avval NIMA
    o'zgargani, keyin «hech narsa yo'qolmadi», keyin bitta aniq qadam.

    ⚠️ Rasm izohi (caption) 1024 belgi — ega varianti ham sig'ishi shart
    (tests/test_eski_bot.py)."""
    y = _yangi()
    matn = (
        "🚀 <b>Biz yangi manzilga ko'chdik!</b>\n\n"
        f"Bot endi <b>Vexon AI</b> nomi bilan ishlaydi: <b>@{y}</b>\n\n"
        "✅ <b>Hech narsa yo'qolmadi</b> — hammasi o'sha yerda:\n"
        "• Pro obunangiz va uning muddati\n"
        "• Suhbat tarixingiz va bot siz haqingizda eslab qolganlar\n"
        "• Limitlaringiz va sozlamalaringiz\n\n"
        f"⏰ Eslatma va kunlik daydjestlar endi faqat @{y} dan keladi — "
        "u yerda /start bosmaguningizcha ular sizga <b>yetib bormaydi</b>.\n\n"
        "👇 Tugmani bosing va <b>/start</b> — shu bilan tamom.\n"
    )
    if ega:
        matn += (
            "\n💼 <b>Telegram Business:</b> mijozlaringizga avtojavob hozir "
            "<b>to'xtagan</b>. Qayta yoqish: Sozlamalar → Telegram Biznes → "
            f"Chatni avtomatlashtirish → <b>@{y}</b>. Sozlamalaringiz o'zi ko'chadi.\n"
        )
    return matn + f"\n<i>@{_eski_nom} endi savollarga javob bermaydi.</i>"


def tayyormi() -> bool:
    return _bot is not None


async def _rasmli(bot: Bot, chat_id: int, matn: str) -> None:
    """Logo + matn + tugma. Rasm o'tmasa — matnning o'zi. Bloklagan odam
    (Forbidden) xatosi CHAQIRUVCHIGA chiqadi: tarqatma uni sanaydi."""
    global _logo_id
    try:
        if _logo_id is None:
            with open(_LOGO, "rb") as f:
                rasm = BufferedInputFile(f.read(), filename="vexon_ai.jpg")
        else:
            rasm = _logo_id
        m = await bot.send_photo(chat_id, rasm, caption=matn, reply_markup=_tugma())
        _logo_id = m.photo[-1].file_id
    except (TelegramForbiddenError, TelegramRetryAfter):
        raise
    except Exception as e:
        # Rasm o'tmasa ham xabar yetib borishi shart — asosiysi manzil.
        logger.warning(f"[Eski bot] rasm yuborilmadi: {e}")
        await bot.send_message(chat_id, matn, reply_markup=_tugma())


async def namuna(chat_id: int) -> None:
    """Adminning o'ziga ikkala variant — odamlar aynan nimani ko'rishi."""
    await _rasmli(_bot, chat_id, _elon())
    await _rasmli(_bot, chat_id, _elon(ega=True))


async def tarqat(oddiy: list[int], egalar: list[int], progress=None) -> dict:
    """Hammaga bir marta. Bazaga tegmaydi — ro'yxat chaqiruvchidan keladi.

    Sekundiga ~20 ta (Telegram chegarasi ~30): 429 kelsa aytilgan vaqt
    kutiladi va o'sha odamga qayta yuboriladi."""
    egalar_set = set(egalar)
    hammasi = list(dict.fromkeys(list(egalar) + list(oddiy)))   # takrorsiz, egalar oldin
    natija = {"yuborildi": 0, "bloklagan": 0, "xato": 0, "jami": len(hammasi)}
    for i, uid in enumerate(hammasi, 1):
        for _ in range(3):
            try:
                await _rasmli(_bot, uid, _elon(ega=uid in egalar_set))
                natija["yuborildi"] += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 0.5)
            except (TelegramForbiddenError, TelegramNotFound):
                natija["bloklagan"] += 1
                break
            except Exception as e:
                natija["xato"] += 1
                logger.warning(f"[Eski bot] tarqatma: {uid} ga yetmadi: {e}")
                break
        else:
            natija["xato"] += 1
        if progress and i % 200 == 0:
            await progress(i, len(hammasi))
        await asyncio.sleep(0.05)
    return natija


async def _menyuni_tozala(bot: Bot, chat_id: int) -> None:
    """Pro foydalanuvchida chatga bog'langan /kunlik, /research menyusi va
    admin'da panel tugmasi qolgan — ular endi hech narsa qilmaydi."""
    if chat_id in _tozalangan:
        return
    _tozalangan.add(chat_id)
    for chaqiruv in (bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=chat_id)),
                     bot.set_chat_menu_button(chat_id=chat_id, menu_button=MenuButtonDefault())):
        try:
            await chaqiruv
        except Exception:
            pass


async def _yubor(bot: Bot, chat_id: int) -> None:
    hozir = time.monotonic()
    if hozir - _oxirgi.get(chat_id, 0) < _JIM_SONIYA:
        return
    _oxirgi[chat_id] = hozir
    await _menyuni_tozala(bot, chat_id)
    try:
        await _rasmli(bot, chat_id, _matn())
    except Exception as e:
        logger.warning(f"[Eski bot] xabar yuborilmadi (chat={chat_id}): {e}")


async def _egasiga(bot: Bot, owner_id: int, owner_chat: int) -> None:
    if owner_id in _egasiga_aytilgan:
        return
    _egasiga_aytilgan.add(owner_id)
    y = _yangi()
    try:
        await bot.send_message(
            owner_chat,
            "⛔️ <b>Bu bot to'xtatildi va mijozlaringizga endi javob bermaydi.</b>\n\n"
            "Mijozlaringizga hech narsa yuborilmadi. Avtojavobni davom ettirish "
            "uchun: Telegram → Sozlamalar → Telegram Biznes → Chatni "
            f"avtomatlashtirish → bu botni o'chirib, <b>@{y}</b> ni ulang.",
            reply_markup=_tugma())
    except Exception as e:
        logger.warning(f"[Eski bot] Business egasiga yetmadi (owner={owner_id}): {e}")


def _dispatcher() -> Dispatcher:
    dp = Dispatcher()

    @dp.message(F.chat.type == "private")
    async def xabar(message: Message, bot: Bot):
        await _yubor(bot, message.chat.id)

    @dp.callback_query()
    async def tugma(query: CallbackQuery, bot: Bot):
        try:
            await query.answer(f"Bot to'xtatildi. Yangi bot: @{_yangi()}", show_alert=True)
        except Exception:
            pass
        await _yubor(bot, query.from_user.id)

    @dp.guest_message()
    async def mehmon(message: Message, bot: Bot):
        y = _yangi()
        try:
            await bot(AnswerGuestQuery(
                guest_query_id=message.guest_query_id,
                result=InlineQueryResultArticle(
                    id=str(message.guest_query_id), title="Bot ko'chdi",
                    input_message_content=InputTextMessageContent(
                        message_text=f"⛔️ Bu bot to'xtatildi. Endi @{y} deb yozing — "
                                     "barcha funksiyalar o'sha yerda."))))
        except Exception as e:
            logger.warning(f"[Eski bot] guest javobi o'tmadi: {e}")

    @dp.business_connection()
    async def ulanish(conn: BusinessConnection, bot: Bot):
        if conn.is_enabled:
            await _egasiga(bot, conn.user.id, conn.user_chat_id)

    @dp.business_message()
    async def biznes(message: Message, bot: Bot):
        # Mijozga — hech narsa. Faqat egasini bir marta ogohlantiramiz.
        if message.business_connection_id is None:
            return
        try:
            conn = await bot.get_business_connection(message.business_connection_id)
        except Exception:
            return
        await _egasiga(bot, conn.user.id, conn.user_chat_id)

    @dp.pre_checkout_query()
    async def tolov(query: PreCheckoutQuery, bot: Bot):
        await query.answer(ok=False, error_message=(
            f"Bu bot to'xtatildi — to'lov qabul qilinmaydi. Pro'ni @{_yangi()} "
            "botida oling."))

    return dp


async def _profilni_yangila(bot: Bot) -> None:
    """Chatlar ro'yxatida va bo'sh chatda ko'rinadigan narsalar."""
    y = _yangi()
    for chaqiruv in (
        bot.delete_my_commands(scope=BotCommandScopeDefault()),
        bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats()),
        bot.set_chat_menu_button(menu_button=MenuButtonDefault()),
        bot.set_my_short_description(f"⛔️ Bot to'xtatildi. Yangi bot: @{y}"),
        bot.set_my_description(
            f"⛔️ Bu bot o'z faoliyatini to'xtatdi. Barcha funksiyalar @{y} ga "
            "ko'chirildi — Pro obunangiz va tarixingiz o'sha yerda saqlangan."),
    ):
        try:
            await chaqiruv
        except Exception as e:
            logger.warning(f"[Eski bot] profil sozlamasi o'tmadi: {e}")
    # Ism — chatlar ro'yxatida har kuni ko'rinadigan yagona joy. Telegram
    # set_my_name'ni tez-tez chaqirishni cheklaydi, shuning uchun faqat farq
    # bo'lsa yoziladi (har deploy'da emas).
    nom = f"⛔️ Ko'chdik → @{y}"
    try:
        if (await bot.get_my_name()).name != nom:
            await bot.set_my_name(nom)
    except Exception as e:
        logger.warning(f"[Eski bot] ism o'zgarmadi: {e}")


async def ishga_tushir(token: str) -> None:
    """main.py fonda chaqiradi. Hech qachon yiqilmaydi — asosiy bot
    eski botning muammosi tufayli to'xtamasligi shart."""
    global _bot, _eski_nom
    try:
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
        me = await bot.get_me()
        _bot, _eski_nom = bot, me.username or _eski_nom
        logger.info(f"[Eski bot] @{me.username} → @{_yangi()} ga yo'naltiradi")
        await _profilni_yangila(bot)
        dp = _dispatcher()
        # handle_signals=False: SIGINT/SIGTERM asosiy dispatcher'niki.
        await dp.start_polling(bot, handle_signals=False,
                               allowed_updates=dp.resolve_used_update_types())
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("[Eski bot] ishga tushmadi — asosiy bot davom etadi")
