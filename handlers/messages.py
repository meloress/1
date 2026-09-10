import asyncio
import time
import os
import re
import json
import base64
import html as html_lib

import aiohttp
from aiogram import Router
from aiogram.types import (
    Message, FSInputFile, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from core.config import (
    BOT_TOKEN, CONTEXT_WINDOW,
    TEXT_MERGE_WAIT, TEXT_MERGE_MAX_PARTS,
    TEXT_MERGE_MAX_CHARS, MAX_TEXT_LENGTH, STREAM_IDLE_TIMEOUT,
    DAILY_FREE_LIMIT, MESSAGE_COST_TEXT, MESSAGE_COST_PHOTO,
    MESSAGE_COST_DOCUMENT, MESSAGE_COST_VOICE, PLAN_LIMITS, CUSTOM_EMOJI,
    message_cost, pick_reasoning_effort,
    DOCUMENT_MAX_SIZE_FREE, DOCUMENT_MAX_SIZE_PRO, document_max_size,
)
from core.loader import logger, bot
from aiogram.filters import CommandObject
from db.database import (
    save_user, log_user_activity, is_admin, is_superadmin,
    check_and_consume_quota, refund_quota, is_banned, has_started,
)
from handlers import pro as pro_module
from services import menu as menu_module
from services.file_task_quota import DailyQuota
from core.keyboards import admin_keyboard
from handlers.helpers import process_daily_pin, notify_watchers, send_error_with_retry
from core.memory import (get_text_merge_lock, text_merge_buffers,
                         clear_text_merge_buffer, forget_sent_images,
                         remember_location, forget_location)
from services.ai import (
    safe_update_history, get_gpt_reply,
    speech_to_text_smart, text_to_speech_smart,
    get_vision_reply, extract_text_from_document,
    clear_chat_history, safe_get_chat_history,
    build_rich_markdown, embed_images, strip_image_tokens, strip_rich_tokens,
    strip_custom_emoji, code_fences_to_html, strip_internal_names,
)

router = Router()
chat_last_interaction = {}

SESSION_TIMEOUT = 86400


# --------------------------------------------------
# FON VAZIFALARI (foydalanuvchi savolidan AI javobigacha
# bo'lgan kritik yo'lni bloklamasligi uchun)
# --------------------------------------------------
def _fire_and_forget(coro, *, label: str = "background_task") -> asyncio.Task:
    """Coroutine'ni fon vazifasi sifatida ishga tushiradi.

    Statistika/loglash kabi foydalanuvchini kutdirmasligi kerak bo'lgan
    ishlarni asosiy (AI javobigacha bo'lgan) oqimdan butunlay ajratadi
    va tasodifiy xatolik "Task exception was never retrieved"
    ogohlantirishiga olib kelmasligi uchun xatoni shu yerda ushlaydi.
    """
    async def _runner():
        try:
            await coro
        except Exception as e:
            logger.debug(f"[{label}] fon vazifasida xatolik: {e}")

    return asyncio.create_task(_runner())


def track_user_activity(user_id: int, username: str | None, event: str) -> None:
    """save_user + log_user_activity'ni parallel, bloklamaydigan tarzda bajaradi."""
    _fire_and_forget(save_user(user_id, username), label="save_user")
    _fire_and_forget(log_user_activity(user_id, username, event), label="log_user_activity")
    # Referal bonusi aynan shu yerda hisobga olinadi — /start da emas.
    # Sabab: /start bosish soxta akkaunt uchun bepul, HAQIQIY savol berish
    # esa yo'q. maybe_qualify_referral() ichida RAM keshi bor, shuning
    # uchun bu har xabarda DB so'roviga aylanmaydi.
    if event.endswith("_message"):
        _fire_and_forget(pro_module.maybe_qualify_referral(user_id), label="referral_qualify")


# --------------------------------------------------
# FSM STATE (Spamning oldini olish uchun)
# --------------------------------------------------
class GeneratingState(StatesGroup):
    generating = State()

@router.message(GeneratingState.generating)
async def busy_handler(message: Message):
    """Javob ketayotganda kelgan xabar — NAVBATGA, tashlanmaydi.

    ⚠️ Ilgari bu yerda faqat "Iltimos kuting" javobi bor edi va xabarning
    O'ZI YO'QOLARDI — foydalanuvchi uni qo'lda qayta yozishga majbur
    bo'lardi. Endi matn o'sha text-merge buferiga qo'yiladi;
    `_process_merged_text()` tugaganda buferda qolganini o'zi ishga
    tushiradi (finally blokiga qarang).

    Navbatga FAQAT oddiy matn tushadi:
      * buyruq (`/pro`, `/new`) — AI so'rovi emas, uni GPT'ga yuborish
        xato bo'lardi;
      * rasm/hujjat/ovoz — o'z quvuri bor, buferga sig'maydi.
    Ikkalasi ham eski xatti-harakatda qoladi: kutishni so'raymiz.
    """
    matn = (message.text or "").strip()
    if matn and not matn.startswith("/"):
        chat_id = message.chat.id
        async with get_text_merge_lock(chat_id):
            buf = text_merge_buffers.get(chat_id)
            if buf is None:
                buf = {"parts": [], "last_message": message,
                       "timer_task": None, "created_at": time.time()}
                text_merge_buffers[chat_id] = buf
            if len(buf["parts"]) >= TEXT_MERGE_MAX_PARTS:
                javob = ("⚠️ Navbat to'ldi — avvalgi savollarga javob "
                         "berib bo'lgach qayta yozing.")
            else:
                buf["parts"].append(matn)
                buf["last_message"] = message
                buf["created_at"] = time.time()
                javob = ("⏳ Navbatga oldim — avvalgi javob tugagach "
                         "javob beraman.")
        try:
            await message.answer(javob, **ephemeral_params(message))
        except Exception:
            pass
        return

    # Guruhda bu xabar FAQAT so'rov egasiga ko'rinadi (Bot API 10.3) —
    # qolganlar uchun bu shovqin, bot esa "spam qilyapti" bo'lib ko'rinadi.
    try:
        await message.answer("Iltimos kuting, javob generatsiya qilinmoqda...",
                             **ephemeral_params(message))
    except Exception:
        # Ephemeral qo'llab-quvvatlanmasa ham ogohlantirish yetib borsin.
        await message.answer("Iltimos kuting, javob generatsiya qilinmoqda...")


# --------------------------------------------------
# RICH MESSAGE / STREAMING YORDAMCHILARI
# --------------------------------------------------

# OPTIMIZATSIYA: avval har bir so'rov uchun YANGI aiohttp.ClientSession
# ochilar edi (yangi TCP + TLS handshake har safar!). Bu "thinking"
# animatsiyasi paytida sekundiga bir necha marta takrorlanadi, ya'ni
# foydalanuvchi savol berib AI javobini kutayotgan har bir soniyada
# keraksiz tarmoq lag'i qo'shib turgan. Endi bitta doimiy, ulanishlarni
# qayta ishlatadigan (keep-alive) sessiya ishlatiladi.
_http_session: aiohttp.ClientSession | None = None
_http_session_lock = asyncio.Lock()


async def _get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        async with _http_session_lock:
            if _http_session is None or _http_session.closed:
                connector = aiohttp.TCPConnector(
                    limit=100,
                    limit_per_host=30,
                    ttl_dns_cache=300,
                    keepalive_timeout=75,
                )
                # "Thinking" draftlari va streaming push'lari yengil,
                # tez-tez yuboriladigan so'rovlar — 30s kutish shart emas,
                # muammo bo'lsa tezroq fallback rejimga o'tishimiz kerak.
                timeout = aiohttp.ClientTimeout(total=10, connect=5)
                _http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return _http_session


async def close_http_session() -> None:
    """Bot to'xtaganda chaqirish uchun (resurslarni to'g'ri tozalash)."""
    global _http_session
    if _http_session is not None and not _http_session.closed:
        await _http_session.close()
        _http_session = None


# Telegram javobi kelmaganda NIMA bo'lgani noma'lum — xabar yetib borgan
# ham bo'lishi mumkin. Bu farq hal qiluvchi: "rad etildi" da qayta urinsa
# bo'ladi, "noma'lum" da esa QAYTA URINISH TAKROR XABAR yaratadi.
OUTCOME_REJECTED = "rejected"     # Telegram aniq rad etdi (ok:false / 4xx)
OUTCOME_UNKNOWN = "unknown"       # timeout yoki tarmoq uzildi


async def _telegram_api_request(method: str, payload: dict, *,
                                outcome: list | None = None,
                                timeout: float | None = None):
    """Telegram API'ga JSON so'rov.

    `outcome` berilsa — muvaffaqiyatsizlik SABABI shu ro'yxatga yoziladi
    (OUTCOME_REJECTED / OUTCOME_UNKNOWN). Chaqiruvchi shunga qarab qayta
    urinish xavfsizmi yoki yo'qligini hal qiladi.

    `timeout` — umumiy sessiya chegarasini (10s) bosib o'tadi. Rasm
    havolasi bor rich xabarda SHART: Telegram xabarni yaratishdan oldin
    har bir rasmni O'ZI manba saytdan yuklab oladi va bu 10 soniyadan
    oson oshadi.
    """
    if not BOT_TOKEN:
        if outcome is not None:
            outcome.append(OUTCOME_UNKNOWN)
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    kwargs = {"json": payload}
    if timeout is not None:
        kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout, connect=5)
    try:
        session = await _get_http_session()
        async with session.post(url, **kwargs) as resp:
            data = await resp.json(content_type=None)
            if resp.status == 200 and data.get("ok"):
                return data.get("result")
            # Telegram javob berdi va rad etdi — xabar YARATILMAGAN,
            # ya'ni boshqa ko'rinishda qayta urinish xavfsiz.
            logger.debug(f"Telegram API {method} failed: {data}")
            if outcome is not None:
                outcome.append(OUTCOME_REJECTED)
            return None
    except Exception as e:
        logger.debug(f"Telegram API {method} exception: {e}")
        if outcome is not None:
            outcome.append(OUTCOME_UNKNOWN)
        return None


async def _telegram_api_multipart(method: str, payload: dict, files: dict):
    """Xuddi _telegram_api_request, lekin YANGI FAYL yuklash bilan.

    Rich xabarga hali `file_id` ga ega bo'lmagan faylni qo'yishning
    yagona yo'li — multipart/form-data. JSON so'rovi bunga yaramaydi,
    shuning uchun alohida funksiya (oddiy yo'lni murakkablashtirmaslik
    uchun ataylab ajratilgan).

    `files`: {"attach_nomi": (fayl_nomi, baytlar)}.
    """
    if not BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        form = aiohttp.FormData()
        for key, value in payload.items():
            # Ichma-ich obyektlar multipart'da JSON satr sifatida ketadi.
            form.add_field(key, value if isinstance(value, str) else json.dumps(value))
        for name, (filename, content) in files.items():
            form.add_field(name, content, filename=filename,
                           content_type="application/octet-stream")

        session = await _get_http_session()
        async with session.post(url, data=form) as resp:
            data = await resp.json(content_type=None)
            if resp.status == 200 and data.get("ok"):
                return data.get("result")
            logger.debug(f"Telegram API {method} (multipart) failed: {data}")
            return None
    except Exception as e:
        logger.debug(f"Telegram API {method} (multipart) exception: {e}")
        return None


def _balance_markdown_fences(text: str) -> str:
    if text.count("```") % 2 != 0:
        return text + "\n```"
    return text


# ⚠️ IKKI XIL CHEGARA, chunki ikki xil xabar turi:
#
#   oddiy xabar (sendMessage)  — 4096 belgi
#   boy xabar  (rich message)  — 32768 belgi (Bot API 10.3)
#
# Ikkalasida ham zaxira qoldiriladi: build_rich_markdown() matnga
# <tg-math>/<tg-time>/<table> kabi teglar qo'shib uzunlikni oshiradi.
#
# NEGA MUHIM: har bir bo'linish — xavf (kod bloki yopilib qayta ochiladi,
# markdown havolasi kesilishi mumkin). Rich yo'lda 9000 belgilik javob
# ilgari UCHTA xabarga bo'linardi, endi bittada ketadi.
MAX_RICH_CHARS = 30000
MAX_PLAIN_CHARS = 4000

# Rasm havolasi bor rich xabar uchun alohida chegara. Umumiy sessiya
# chegarasi 10s — u yengil, tez-tez yuboriladigan draftlar uchun to'g'ri,
# lekin media bor xabarda Telegram manba saytlardan rasmlarni yuklab
# olguncha kutish kerak. 10s da uzilib, "yiqildi" deb qayta yuborish
# aynan TAKROR XABAR nosozligini keltirib chiqargan edi.
RICH_MEDIA_TIMEOUT = 60.0


_MD_LINK_RE = re.compile(r"\[[^\]\n]*\]\([^)\s]*\)?")
# Izoh (footnote): `[^1]` — havola, `[^1]: ...` — ta'rif. Ta'rif qator
# boshida turadi, shuning uchun havola naqshi `:` ni istisno qiladi.
_FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:", re.M)


def _safe_cut(text: str, cut: int, limit: int) -> int:
    """Kesish nuqtasini JUFT konstruktsiyaning o'rtasidan chiqaradi.

    Jonli nosozlik: manbalar ro'yxati aynan `[OLX Uzbekistan](https://...)`
    ning ichida bo'lingan va foydalanuvchi bitta xabarda `• [OLX`, keyingi
    xabarda `Uzbekistan](https://...)` degan buzuq matnni ko'rgan.
    Havola ikkiga bo'linsa, ikkala bo'lakda ham u havola bo'lmay qoladi.

    Izoh ham xuddi shunday juftlik, faqat yarmlari bir-biridan uzoqda:
    `[^1]` matn ichida turadi, `[^1]: ...` ta'rifi esa javob OXIRIDA.
    Bo'linish ularni ikki xabarga ajratsa, havola HECH QAYERGA olib
    bormaydi — shuning uchun kesish nuqtasi butun juftlikdan OLDINGA
    suriladi.

    ⚠️ `text` — qolgan matnning HAMMASI, `rest[:limit]` emas: ta'rif
    chegaradan keyinroqda bo'lishi mumkin va aks holda ko'rinmasdi.
    """
    for m in _MD_LINK_RE.finditer(text):
        if m.start() > cut:
            break
        if m.start() < cut < m.end():
            # Havoladan OLDIN kesamiz; joy qolmasa — o'zgartirmaymiz
            # (uzun havola bitta bo'lakka sig'masligi mumkin).
            return m.start() if m.start() > limit // 4 else cut

    defs = {m.group(1): m.start() for m in _FOOTNOTE_DEF_RE.finditer(text)}
    if defs:
        for m in _FOOTNOTE_REF_RE.finditer(text):
            if m.start() >= cut:
                break
            # Ta'rif kesimdan keyinda — havolani ham keyingi bo'lakka
            # o'tkazamiz. Joy qolmasa (juftlik bo'lak boshidayoq
            # boshlansa) tegilmaydi, aks holda bo'lak har safar
            # kichrayib, bo'lish cheksiz siklga aylanardi.
            d = defs.get(m.group(1))
            if d is not None and d >= cut:
                # Havolaning O'ZIDAN emas, undan oldingi bo'sh joydan
                # kesamiz — aks holda «da'vo[^1]» so'zning o'rtasidan
                # ajralib, birinchi xabar «Muhim da'vo» bilan tugardi.
                start = text.rfind(" ", 0, m.start()) + 1
                if start > limit // 4:
                    return start
    return cut


def _split_for_telegram(text: str, limit: int = MAX_PLAIN_CHARS) -> list[str]:
    """Uzun javobni Telegram chegarasiga sig'adigan bo'laklarga bo'ladi.

    ⚠️ NEGA KERAK: MAX_OUTPUT_TOKENS = 16000, ya'ni javob bemalol 15-20 ming
    belgi bo'lishi mumkin. Ilgari bo'lish umuman yo'q edi va bunday javobda
    HAR QANDAY yuborish urinishi rad etilardi — foydalanuvchi animatsiyani
    ko'rib turib, oxirida HECH NARSA olmasdi (botdagi eng yomon nosozlik).

    Kesish joyi ataylab shu tartibda tanlanadi: bo'sh qator → qator → bo'sh
    joy. Hech qaysisi topilmasa (masalan uzun bitta so'z yoki base64) qattiq
    kesiladi. Bo'lak o'rtasida ochiq qolgan kod bloki yopiladi va keyingi
    bo'lakda qayta ochiladi, aks holda qolgan matn butunlay kod bo'lib
    ko'rinardi.
    """
    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut < limit // 2:          # mos chegara yo'q — qattiq kesamiz
            cut = limit
        cut = _safe_cut(rest, cut, limit)
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)

    out: list[str] = []
    open_lang = ""                    # oldingi bo'lakda ochiq qolgan blok tili
    for part in parts:
        if open_lang:
            part = f"```{open_lang}\n{part}"
        if part.count("```") % 2 != 0:
            # Oxirgi ochilgan blokning tili — keyingi bo'lakda tiklanadi.
            open_lang = part.rsplit("```", 1)[1].split("\n", 1)[0].strip()
            part += "\n```"
        else:
            open_lang = ""
        out.append(part)
    return out or [text]


async def _answer_plain(message: Message, text: str):
    """Oddiy xabar yuboradi; Markdown parslanmasa — bezaksiz yuboradi.

    ⚠️ Bu ikkinchi urinish MAJBURIY. Model matnida yolg'iz `*` yoki `_`
    bo'lishi odatiy hol va Telegram bunday xabarni butunlay rad etadi.
    Ilgari bu yerda faqat bitta Markdown urinishi bor edi — u yiqilsa javob
    izsiz yo'qolardi.
    """
    try:
        return await message.answer(text, parse_mode="Markdown")
    except Exception:
        try:
            return await message.answer(text)
        except Exception as e:
            logger.warning(f"[Javob] yuborilmadi (chat={message.chat.id}): {e}")
            return None


def _format_elapsed(elapsed: float) -> str:
    """O'tgan vaqtni foydalanuvchiga ko'rsatish uchun formatlaydi.

    60 soniyagacha — "12s" ko'rinishida, undan keyin — "1:05" (mm:ss)
    ko'rinishida, chunki uzoq kutish holatlarida (masalan chuqur qidiruv
    bir necha bosqichda ishlaganda) faqat soniya sanog'i o'qish qiyin
    bo'lib qoladi.
    """
    total_seconds = max(0, int(elapsed))
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def _rich_message_payload(markdown: str | None = None, html_content: str | None = None) -> dict:
    """InputRichMessage payloadini yasaydi.

    MUHIM: `html` va `markdown` ikkita mustaqil formatlash rejimi.
    tg-thinking/tg-emoji kabi HTML-only teglarni hech qachon `markdown`
    maydoniga qo'shmaslik kerak — parser ularni tushunmay, butun
    xabarni parslashni to'xtatib, natijada oddiy *yulduzcha* belgilari
    ham formatlanmasdan xom holda ko'rinib qoladi (aynan shu xato bor edi).
    """
    rich_message = {"skip_entity_detection": True}
    if html_content is not None:
        rich_message["html"] = html_content
    else:
        rich_message["markdown"] = markdown or ""
    return rich_message


async def _send_rich_draft(
    chat_id: int,
    draft_id: int,
    *,
    markdown: str | None = None,
    html_content: str | None = None,
    message_thread_id=None,
    can_stop: bool = False,
):
    payload = {
        "chat_id": chat_id,
        "draft_id": draft_id,
        "rich_message": _rich_message_payload(markdown, html_content),
    }
    if message_thread_id:
        payload["message_thread_id"] = message_thread_id
    if can_stop:
        # Bot API 10.3: draft ustida "To'xtatish" tugmasi.
        # keep_on_stop — bosilganda yozilib ulgurgan qism darhol
        # o'chib ketmaydi. Hujjat aytadi: qismni BUTUNLAY saqlash uchun
        # baribir yangi xabar yuborish kerak — process_stream_draft()
        # aynan shuni qiladi.
        payload["can_stop"] = True
        payload["keep_on_stop"] = True
    return await _telegram_api_request("sendRichMessageDraft", payload)


def ephemeral_params(message: Message) -> dict:
    """Guruhda — xabarni FAQAT so'rov egasiga ko'rsatish parametrlari.

    Bot API 10.3. Shaxsiy chatda ma'nosi yo'q (u yerda baribir ikki kishi),
    shuning uchun bo'sh dict qaytadi va chaqiruvchi kod o'zgarmaydi.

    NEGA KERAK: limit tugadi, Pro reklamasi, "iltimos kuting" kabi
    xabarlar SHAXSIY, lekin guruhda hammaga ko'rinadi — bu botni
    guruhdan chiqarib yuborishning eng keng tarqalgan sababi.
    """
    if message.chat.type == "private" or message.from_user is None:
        return {}
    return {"ephemeral_message_parameters": {"receiver_user_id": message.from_user.id}}


async def _send_rich_message(
    chat_id: int,
    *,
    markdown: str | None = None,
    html_content: str | None = None,
    message_thread_id=None,
    reply_markup=None,
    outcome: list | None = None,
    timeout: float | None = None,
):
    payload = {
        "chat_id": chat_id,
        "rich_message": _rich_message_payload(markdown, html_content),
    }
    if message_thread_id:
        payload["message_thread_id"] = message_thread_id
    if reply_markup is not None:
        # aiogram modeli -> JSON. exclude_none SHART: bo'sh maydonlar
        # yuborilsa Telegram butun klaviaturani rad etadi.
        payload["reply_markup"] = (
            reply_markup.model_dump(exclude_none=True)
            if hasattr(reply_markup, "model_dump") else reply_markup)
    return await _telegram_api_request("sendRichMessage", payload,
                                       outcome=outcome, timeout=timeout)


# Flood cheklovi kelganda kutiladigan eng uzun vaqt. Undan uzunini
# kutish javobni sekinlashtiradi — bunday holatda oraliq yangilanish
# shunchaki tashlab yuboriladi, YAKUNIY javob baribir alohida ketadi.
EDIT_FLOOD_MAX_WAIT = 5.0


async def _edit_message_fallback(message: Message, text: str):
    """Xabarni tahrirlaydi: Markdown → bezaksiz → (429 bo'lsa) kutib qayta.

    ⚠️ 429 ALOHIDA ushlanadi. Oqim paytida tahrirlash tez-tez ketadi va
    Telegram "flood wait" beradi; ilgari u boshqa xatolar bilan bir xil
    yutilardi, ya'ni o'sha yangilanish JIMGINA yo'qolardi va matn
    ekranda muzlab qolardi.
    """
    for urinish in range(2):
        try:
            return await message.edit_text(text, parse_mode="Markdown")
        except TelegramRetryAfter as e:
            if urinish or e.retry_after > EDIT_FLOOD_MAX_WAIT:
                return None
            await asyncio.sleep(e.retry_after + 0.1)
            continue
        except Exception:
            pass
        try:
            return await message.edit_text(text)
        except TelegramRetryAfter as e:
            if urinish or e.retry_after > EDIT_FLOOD_MAX_WAIT:
                return None
            await asyncio.sleep(e.retry_after + 0.1)
        except Exception:
            return None
    return None


# Telegram bot API'ning hujjat yuborishdagi qattiq chegarasi.
MAX_TELEGRAM_DOCUMENT_SIZE = 50 * 1024 * 1024
# Rasm (photo) chegarasi hujjatnikidan ANCHA past — undan oshgani hujjat
# sifatida yuboriladi, ya'ni baribir yetib boradi, faqat preview'siz.
MAX_TELEGRAM_PHOTO_SIZE = 10 * 1024 * 1024
_PHOTO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


# Bitta rich xabarga sig'adigan natija fayllarining umumiy hajmi. Undan
# oshsa har bir fayl alohida yuboriladi — bitta ulkan multipart so'rovi
# timeout bilan yiqilsa BARCHA fayllar birdan yo'qolardi.
MAX_RICH_BUNDLE_SIZE = 30 * 1024 * 1024


async def _send_output_files_rich(chat_id: int, output_files: list,
                                  message_thread_id=None) -> bool:
    """Bir nechta natija faylini BITTA rich xabarga yig'ib yuboradi.

    Bot API 10.3: rasm `tg://photo?id=`, hujjat esa `tg://document?id=`
    havolasi orqali xabar matnining ichiga joylanadi. Foydalanuvchi 4 ta
    alohida xabar o'rniga bitta tartibli xabar oladi.

    ⚠️ ATAYLAB faqat 2+ fayl uchun: bitta fayl bo'lsa oddiy
    send_document/send_photo allaqachon eng yaxshi ko'rinishni beradi
    (native preview, "Saqlash" tugmasi) va yangi yo'lni sinash uchun
    hech qanday sabab yo'q.

    True — yuborildi; False — chaqiruvchi eski yo'l bilan davom etsin.
    """
    if len(output_files) < 2:
        return False
    total = sum(len(content) for _, content in output_files)
    if total > MAX_RICH_BUNDLE_SIZE:
        return False
    if any(len(content) > MAX_TELEGRAM_DOCUMENT_SIZE for _, content in output_files):
        return False

    media, files, blocks = [], {}, []
    for i, (filename, content) in enumerate(output_files):
        # `id` faqat A-Z a-z 0-9 _ - dan iborat bo'lishi SHART (API talabi),
        # shuning uchun fayl nomi emas, tartib raqami ishlatiladi.
        media_id = f"f{i}"
        is_photo = (filename.lower().endswith(_PHOTO_EXTENSIONS)
                    and len(content) <= MAX_TELEGRAM_PHOTO_SIZE)
        kind = "photo" if is_photo else "document"
        media.append({"id": media_id,
                      "media": {"type": kind, "media": f"attach://{media_id}"}})
        files[media_id] = (filename, content)
        caption = filename.replace('"', "'")
        blocks.append(f'![](tg://{kind}?id={media_id} "{caption}")')

    payload = {
        "chat_id": chat_id,
        "rich_message": {
            "markdown": "\n\n".join(blocks),
            "media": media,
            "skip_entity_detection": True,
        },
    }
    if message_thread_id:
        payload["message_thread_id"] = message_thread_id

    result = await _telegram_api_multipart("sendRichMessage", payload, files)
    if result is None:
        logger.info("[Fayl] rich to'plam rad etildi — fayllar alohida yuboriladi")
        return False

    # To'plam yetib bordi: keyingi so'rov uchun oxirgi fayl eslab qolinadi
    # (alohida yuborish yo'lidagi bilan bir xil mantiq).
    last_name, last_bytes = output_files[-1]
    _remember_file(chat_id, last_bytes, last_name, produced=True)
    logger.info(f"[Fayl] {len(output_files)} ta natija bitta rich xabarda "
                f"yuborildi (chat={chat_id})")
    return True


async def _send_output_files(chat_id: int, output_files: list) -> None:
    """run_python_sandbox yaratgan fayllarni foydalanuvchiga yuboradi.

    Bitta fayldagi xato qolganlarini to'xtatmaydi va jim qolmaydi —
    foydalanuvchi nima bo'lganini biladi.

    ⚠️ Oxirgi muvaffaqiyatli yuborilgan fayl `_remember_file(produced=True)`
    bilan eslab qolinadi. Busiz keyingi so'rov ("nomini ham o'zgartir")
    foydalanuvchining DASTLABKI xom fayliga qaytardi va botning o'z ishi
    yo'qolardi: birinchi tahrir bekor bo'lib, faqat oxirgi so'ralgan
    o'zgarish qolardi. Foydalanuvchi buni "bot eslab qololmayapti" deb
    ko'radi va haq bo'ladi.
    """
    # Avval bitta tartibli rich xabarga urinamiz (2+ fayl bo'lganda).
    # Rad etilsa — pastdagi eski, fayl-ba-fayl yo'l ishlaydi.
    try:
        if await _send_output_files_rich(chat_id, output_files):
            return
    except Exception as e:
        logger.warning(f"[Fayl] rich to'plamda xatolik, alohida yuboriladi: {e}")

    last_sent: tuple[str, bytes] | None = None
    for filename, content in output_files:
        if len(content) > MAX_TELEGRAM_DOCUMENT_SIZE:
            logger.warning(f"Natija fayl juda katta: {filename} ({len(content)} bayt)")
            try:
                await bot.send_message(
                    chat_id,
                    f"⚠️ «{filename}» fayli 50 MB Telegram chegarasidan katta "
                    "bo'lgani uchun yuborib bo'lmadi.",
                )
            except Exception:
                pass
            continue

        # Rasm hujjat sifatida ketsa, chatda ko'rinmaydi — foydalanuvchi
        # uni ochib ko'rishga majbur bo'ladi. send_photo preview beradi.
        # Xato bo'lsa pastdagi hujjat yo'liga tushadi (eski xatti-harakat),
        # ya'ni bu o'zgarish hech narsani yo'qota olmaydi.
        if (filename.lower().endswith(_PHOTO_EXTENSIONS)
                and len(content) <= MAX_TELEGRAM_PHOTO_SIZE):
            try:
                await bot.send_photo(chat_id, BufferedInputFile(content, filename=filename))
                last_sent = (filename, content)
                continue
            except Exception as e:
                logger.warning(f"Rasmni photo sifatida yuborib bo'lmadi ({filename}): {e}")

        try:
            await bot.send_document(chat_id, BufferedInputFile(content, filename=filename))
            last_sent = (filename, content)
        except Exception as e:
            logger.warning(f"Natija faylni yuborib bo'lmadi ({filename}): {e}")
            try:
                await bot.send_message(chat_id, f"⚠️ «{filename}» faylini yuborishda xatolik yuz berdi.")
            except Exception:
                pass

    # Foydalanuvchiga YETIB BORGAN oxirgi fayl keyingi so'rovning boshlang'ich
    # nuqtasi bo'ladi. Yuborilmagan fayl eslab qolinmaydi — aks holda
    # foydalanuvchi ko'rmagan natija ustida ish davom etardi.
    if last_sent is not None:
        _remember_file(chat_id, last_sent[1], last_sent[0], produced=True)
        logger.info(f"[Fayl] natija eslab qolindi: {last_sent[0]} (chat={chat_id})")


STATUS_TEXTS_BY_TYPE: dict[str, list[str]] = {
    "text": [
        "Ma'lumotlar tahlil qilinmoqda",
        "Fikrlar jamlanmoqda",
        "Javob shakllantirilmoqda",
        "Mukammal matn tayyorlanmoqda",
    ],
    "photo": [
        "Rasm tahlil qilinmoqda",
        "Tasvirdagi detallar aniqlanmoqda",
        "Ko'rganlarim tahlil qilinmoqda",
        "Javob shakllantirilmoqda",
    ],
    "document": [
        "Hujjat o'qilmoqda",
        "Matn tahlil qilinmoqda",
        "Muhim joylar ajratilmoqda",
        "Javob shakllantirilmoqda",
    ],
    "voice": [
        "Ovozli xabar tinglanmoqda",
        "Aytganlaringiz tahlil qilinmoqda",
        "Fikrlar jamlanmoqda",
        "Javob shakllantirilmoqda",
    ],
    "search": [
        "Internetdan ma'lumot qidirilmoqda",
        "Manbalar solishtirilmoqda",
        "Eng so'nggi ma'lumotlar tekshirilmoqda",
        "Natijalar tahlil qilinmoqda",
    ],
    # /research — botdagi ENG UZUN amal (2-5 daqiqa). Ilgari u oddiy
    # "search" ro'yxatidan foydalanardi: to'rtta ibora ~10 soniyada bir
    # aylanib, uch daqiqa davomida o'ttiz marta takrorlanardi va ekran
    # qotib qolgandek ko'rinardi. Bu yerda bosqichlar ko'p va ular
    # haqiqiy quvurga mos: reja -> manbalar -> o'qish -> taqqoslash ->
    # xulosa -> hisobot.
    "research": [
        "Tadqiqot rejasi tuzilmoqda",
        "Manbalar qidirilmoqda",
        "Topilgan manbalar o'qilmoqda",
        "Ma'lumotlar solishtirilmoqda",
        "Qarama-qarshi da'volar tekshirilmoqda",
        "Raqamlar va sanalar aniqlanmoqda",
        "Xulosalar shakllantirilmoqda",
        "Hisobot yozilmoqda",
    ],
    "file_task": [
        "Vazifa tahlil qilinmoqda",
        "Kod tayyorlanmoqda",
        "Fayl ustida ishlanmoqda",
        "Natija shakllantirilmoqda",
    ],
    # Rasm yaratish ~20-25 soniya davom etadi — animatsiya bosqichlari
    # foydalanuvchiga jarayon ketayotganini ko'rsatib turadi.
    "image": [
        "Rasm g'oyasi shakllantirilmoqda",
        "Kompozitsiya tanlanmoqda",
        "Ranglar joylanmoqda",
        "Rasm chizilmoqda",
    ],
    "reminder": [
        "Vaqt aniqlanmoqda",
        "Eslatma qo'yilmoqda",
        "Rejaga yozilmoqda",
        "Tasdiqlanmoqda",
    ],
    # Uzoq muddatli xotira. Bu YAGONA status turi bo'lib, foydalanuvchi
    # o'zi so'ramagan ish haqida gapiradi — shuning uchun ohang ham
    # boshqacha: texnik emas, shaxsiy. Nuqtalarni animatsiya o'zi qo'shadi
    # (`{status}{dots}`), shuning uchun matn oxirida "..." YOZILMAYDI.
    "memory": [
        "Sizni eslab qolayapman",
        "Muhim ma'lumot saqlanmoqda",
        "Xotiramga yozib qo'yayapman",
        "Sizni yaxshiroq tanib olyapman",
    ],
}

# ID'lar core/config.py:CUSTOM_EMOJI da — yagona manba, chunki ular
# handlers/pro.py dagi Pro reklamasida ham ishlatiladi.
EMOJI_ID_BY_TYPE: dict[str, str] = {
    **CUSTOM_EMOJI,
    # Fayl vazifasi uchun hujjat emojisi qayta ishlatiladi — alohida premium
    # emoji ID kerak bo'lsa, uni CUSTOM_EMOJI ga qo'shib shu yerga ulang.
    "file_task": CUSTOM_EMOJI["document"],
    "image": CUSTOM_EMOJI["photo"],
    "research": CUSTOM_EMOJI["search"],
}


# --------------------------------------------------
# ⏹ GENERATSIYANI TO'XTATISH (Bot API 10.3)
# --------------------------------------------------
# Foydalanuvchi draft ustidagi "To'xtatish" tugmasini bosganda Telegram
# `stopped_message_generation` update'ini yuboradi — uning ichida faqat
# draft_id bo'ladi. main.py dagi outer middleware shu ID bo'yicha
# tegishli Event'ni ko'taradi, oqim esa darhol uziladi.
#
# ⚠️ ATAYLAB oddiy dict: draft bir necha soniya yashaydi, kalit esa
# `finally` da doim o'chiriladi. Umuman o'chib qolsa ham zarari yo'q —
# Event kichkina obyekt, lekin sizib ketmasligi uchun quyida tozalanadi.
_stop_events: dict[int, asyncio.Event] = {}


def request_stop(draft_id: int) -> bool:
    """Berilgan draft uchun to'xtatish signalini beradi. True — topildi."""
    event = _stop_events.get(draft_id)
    if event is None:
        return False
    event.set()
    return True


async def _next_or_stop(iterator, stop_event: asyncio.Event):
    """Oqimdan keyingi bo'lakni oladi, lekin to'xtatishni ham kutadi.

    NEGA oddiy `async for` YETARLI EMAS: qidiruv yoki fayl vazifasi
    ishlayotgan paytda oqimdan 20-30 soniya davomida HECH QANDAY bo'lak
    kelmasligi mumkin. Oddiy siklda to'xtatish tugmasi shuncha vaqt
    "o'lik" bo'lib turardi — ya'ni eng kerakli paytda ishlamasdi.

    Qaytaradi: (chunk, stopped, finished).

    Oqim STREAM_IDLE_TIMEOUT davomida jim qolsa — `TimeoutError`.
    ⚠️ Bu UMUMIY emas, BO'SH TURISH chegarasi: fayl vazifasi yoki chuqur
    qidiruv paytida bo'lak kelmasdan bir necha daqiqa o'tishi normal,
    umumiy chegara esa aynan o'sha ishlayotgan vazifani o'ldirardi.
    """
    next_task = asyncio.ensure_future(iterator.__anext__())
    stop_task = asyncio.ensure_future(stop_event.wait())
    try:
        done, _ = await asyncio.wait(
            {next_task, stop_task}, return_when=asyncio.FIRST_COMPLETED,
            timeout=STREAM_IDLE_TIMEOUT)
    except asyncio.CancelledError:
        next_task.cancel()
        stop_task.cancel()
        raise

    if not done:
        next_task.cancel()
        stop_task.cancel()
        raise TimeoutError(
            f"oqim {STREAM_IDLE_TIMEOUT:.0f}s davomida jim qoldi")

    if stop_task in done:
        next_task.cancel()
        # Bekor qilingan task'ning natijasini "o'qib" qo'yamiz, aks holda
        # asyncio "Task exception was never retrieved" deb ogohlantiradi.
        try:
            await next_task
        except (asyncio.CancelledError, Exception):
            pass
        return None, True, False

    stop_task.cancel()
    try:
        return next_task.result(), False, False
    except StopAsyncIteration:
        return None, False, True


# Javobda BITTA qisqa kod bloki bo'lsa — "nusxalash" tugmasi qo'yiladi.
# copy_text tugmasi Telegram'da 256 belgi bilan cheklangan, undan uzunini
# yuborish butun xabarni rad ettiradi.
_CODE_FENCE_RE = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)\n```", re.S)
_COPY_TEXT_LIMIT = 256


def _copy_button_html(text: str) -> str:
    """Javobga mos "nusxalash" tugmasi (yoki bo'sh satr).

    ⚠️ Bir nechta kod bloki bo'lsa tugma QO'YILMAYDI: qaysi birini
    nusxalashi noaniq bo'lib qoladi, noaniq tugma esa tugmasizdan yomon.
    """
    blocks = _CODE_FENCE_RE.findall(text)
    if len(blocks) != 1:
        return ""
    snippet = blocks[0][1].strip()
    if not snippet or len(snippet) > _COPY_TEXT_LIMIT:
        return ""
    # Faqat ikonka, yozuvsiz: tugma kod blokining yonida turadi va nima
    # qilishi 📋 dan tushunarli. Yozuv qatorning yarmini egallab, javobni
    # og'irlashtirardi. Butunlay bo'sh yorliq esa MUMKIN EMAS — Telegram
    # tugma matni bo'sh bo'lsa xabarni rad etadi.
    return pro_module.rich_button_row([
        pro_module.rich_button("📋", type="copy_text", text=snippet),
    ], align="right")


# Uzun kod chatda o'qib bo'lmaydi va _split_for_telegram() uni bo'lak
# chegarasida ikkiga kesadi — shuning uchun matndan olinib, FAYL qilib
# yuboriladi. Chegara ~bir ekran.
LONG_CODE_LINES = 30
_CODE_EXT = {
    "python": ".py", "py": ".py", "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts", "html": ".html", "css": ".css",
    "sql": ".sql", "json": ".json", "bash": ".sh", "sh": ".sh",
    "c": ".c", "cpp": ".cpp", "java": ".java", "go": ".go", "php": ".php",
}


def _extract_long_code(text: str) -> tuple[str, list]:
    """Uzun kod bloklarini matndan ajratib oladi.

    Qaytaradi: (kod o'rniga izoh qo'yilgan matn, [(fayl_nomi, baytlar)]).
    Model tarixiga esa ASL matn saqlanadi — aks holda keyingi "shu kodni
    o'zgartir" so'rovida modelda kodning o'zi bo'lmasdi.
    """
    fayllar: list[tuple[str, bytes]] = []

    def one(match):
        lang, kod = match.group(1), match.group(2)
        qator = kod.count("\n") + 1
        if qator <= LONG_CODE_LINES:
            return match.group(0)
        nom = f"kod_{len(fayllar) + 1}{_CODE_EXT.get(lang.lower(), '.txt')}"
        fayllar.append((nom, kod.encode("utf-8")))
        return f"📎 Kod uzun ({qator} qator) — «{nom}» fayli sifatida biriktirdim."

    return _CODE_FENCE_RE.sub(one, text), fayllar


async def process_stream_draft(message: Message, stream_generator, content_type: str = "text",
                               images: list | None = None) -> str:
    """OpenAI oqimini Telegram rich draft va yakuniy rich message ga ulaydi.

    `images` — services/ai.py topib bergan internet rasmlari ro'yxati.
    Model javob matnida [rasm:N] belgisini qoldirgan bo'lsa, u shu yerda
    haqiqiy media blokiga almashtiriladi (bot rasmni yuklab olmaydi —
    havolani Telegram o'zi tortadi).
    """
    full_text = ""
    chunk_buffer = ""
    draft_id = abs(hash((message.chat.id, message.message_id, time.time_ns()))) % 2_147_483_647 or 1
    message_thread_id = getattr(message, "message_thread_id", None)
    # ⚠️ IKKI XIL TALAB, ATAYLAB AJRATILGAN:
    #   * sendRichMessageDraft — Telegram FAQAT shaxsiy chatga ruxsat
    #     beradi ("target private chat"), shuning uchun animatsiya va
    #     to'xtatish tugmasi guruhda yo'q;
    #   * sendRichMessage — guruh/superguruhda ham ishlaydi.
    # Ilgari ikkalasi bitta bayroqda edi va guruhdagi yakuniy javob
    # bezaksiz ketardi — ya'ni jadval, yig'iladigan manbalar va
    # internetdan olingan rasmlar guruhda umuman ko'rinmasdi.
    using_rich_draft = message.chat.type == "private"
    # Draft yo'li HECH BO'LMASA BIR MARTA ishladimi. Bu ikki xil
    # nosozlikni ajratadi: (a) draft umuman qo'llab-quvvatlanmaydi —
    # darhol oddiy xabarga tushish kerak; (b) ishlab turgan draft
    # vaqtincha rad etildi (429 flood wait) — kutib qayta urinish kerak.
    rich_draft_ok = False
    can_send_rich = True
    fallback_message = None
    fallback_used = False      # zaxira xabar yakuniy javob uchun ishlatildimi
    last_push = 0.0

    # Qidiruv boshlanganda GPT-generator "[STATUS]search" chunk yuborishi
    # mumkin — shu payt active_type "search"ga o'tadi va status matni/emoji
    # ham shunga mos almashadi (pastdagi async-for ichida yangilanadi).
    active_type = content_type

    STATUS_INTERVAL = 2.4
    DOT_INTERVAL = 0.5
    RICH_DRAFT_PING_INTERVAL = 0.6
    FALLBACK_PING_INTERVAL = 1.0
    RICH_DRAFT_FAILURE_LIMIT = 2

    # Jonli oqim tezligi. ⚠️ Telegram tahrirlashni qattiq cheklaydi:
    # har bo'lakda yangilash 429 "flood wait" beradi va oqim MUZLAB
    # qoladi. Shuning uchun ikki shart birga: kamida PUSH_MIN_CHARS
    # yangi belgi VA oxirgi yangilanishdan PUSH_INTERVAL soniya.
    # Istisno — BIRINCHI bo'lak: kutish hissi aynan boshida sezilarli,
    # shuning uchun u darhol ekranga chiqadi.
    PUSH_INTERVAL = 1.0
    PUSH_MIN_CHARS = 100

    stop_animation = asyncio.Event()

    def _status_texts() -> list[str]:
        return STATUS_TEXTS_BY_TYPE.get(active_type, STATUS_TEXTS_BY_TYPE["text"])

    def _thinking_html(elapsed: float) -> str:
        status_texts = _status_texts()
        emoji_id = EMOJI_ID_BY_TYPE.get(active_type, EMOJI_ID_BY_TYPE["text"])
        status_index = int(elapsed // STATUS_INTERVAL) % len(status_texts)
        current_status = status_texts[status_index]
        dots = "." * (int(elapsed // DOT_INTERVAL) % 4 + 1)
        safe_status = html_lib.escape(current_status)
        elapsed_label = html_lib.escape(_format_elapsed(elapsed))

        # JAVOB SHU YERDA: <br/> orqali yangi qatorga tushirildi, lekin <tg-thinking> ichida saqlab qolindi.
        # Natijada sekund ham status xabari kabi bir xil xira (grayish/translucent) bo'lib chiqadi.
        return (
            f'<tg-thinking><tg-emoji emoji-id="{emoji_id}">🔄</tg-emoji> '
            f"<b>{safe_status}{dots}</b><br/>"
            f"{elapsed_label}</tg-thinking>"
        )

    async def emoji_animator():
        nonlocal fallback_message, using_rich_draft, rich_draft_ok
        start_ts = time.monotonic()
        rich_draft_failures = 0
        last_fallback_text = None
        while not stop_animation.is_set():
            elapsed = time.monotonic() - start_ts
            wait_time = RICH_DRAFT_PING_INTERVAL

            if using_rich_draft:
                thinking_html = _thinking_html(elapsed)
                try:
                    res = await _send_rich_draft(
                        message.chat.id, draft_id,
                        html_content=thinking_html,
                        message_thread_id=message_thread_id,
                        can_stop=True,
                    )
                    if res is None:
                        rich_draft_failures += 1
                        if rich_draft_failures >= RICH_DRAFT_FAILURE_LIMIT:
                            using_rich_draft = False
                    else:
                        rich_draft_failures = 0
                        rich_draft_ok = True
                except Exception:
                    rich_draft_failures += 1
                    if rich_draft_failures >= RICH_DRAFT_FAILURE_LIMIT:
                        using_rich_draft = False

            if not using_rich_draft:
                status_texts = _status_texts()
                status_index = int(elapsed // STATUS_INTERVAL) % len(status_texts)
                dots = "." * (int(elapsed // DOT_INTERVAL) % 4 + 1)
                elapsed_label = _format_elapsed(elapsed)
                text_to_send_fallback = f"🔄 *{status_texts[status_index]}{dots}*\n{elapsed_label}"
                wait_time = FALLBACK_PING_INTERVAL
                try:
                    if fallback_message is None:
                        fallback_message = await message.answer(text_to_send_fallback, parse_mode="Markdown")
                        last_fallback_text = text_to_send_fallback
                    elif text_to_send_fallback != last_fallback_text:
                        await _edit_message_fallback(fallback_message, text_to_send_fallback)
                        last_fallback_text = text_to_send_fallback
                except TelegramRetryAfter as e:
                    wait_time = e.retry_after + 0.1
                except Exception:
                    pass

            try:
                await asyncio.wait_for(stop_animation.wait(), timeout=wait_time)
            except asyncio.TimeoutError:
                pass

    anim_task = asyncio.create_task(emoji_animator())

    async def push_update(current_text: str, final: bool = False,
                          force: bool = False):
        nonlocal fallback_message, using_rich_draft, last_push
        nonlocal push_failures, rich_draft_ok
        now = time.monotonic()
        if not (final or force) and now - last_push < PUSH_INTERVAL:
            return
        last_push = now

        # Oraliq ko'rinish ham Telegram chegarasiga sig'ishi kerak: uzun
        # javobda har bir push rad etilib, oqim "muzlab" qolardi. Yakuniy
        # matn baribir to'liq, bo'laklarga bo'linib yuboriladi (pastda).
        # ⚠️ [rasm:N], [batafsil: ...], [iqtibos: ...] — MODEL uchun ichki
        # belgilar, foydalanuvchi ularni ko'rmasligi kerak. Yakuniy
        # xabarda ular media blok / <details> / <aside> ga aylanadi,
        # oqim paytida esa xom holda ekranda turib qolardi.
        # strip_internal_names — ichki tool nomlari oqim paytida ham
        # ekranga chiqmasin (core/config.py: INTERNAL_TOOL_NAMES).
        display_text = strip_internal_names(
            strip_rich_tokens(strip_image_tokens(current_text)))
        if not final:
            display_text += " ✍️"

        # ⚠️ Draft — RICH xabar, ya'ni unga 32768 chegarasi tegishli.
        # Zaxira yo'li (oddiy xabarni tahrirlash) esa 4096 da qoladi,
        # shuning uchun kesish bir marta emas, HAR YO'L UCHUN alohida.
        def _fit(limit: int) -> str:
            t = display_text
            if len(t) > limit:
                t = t[:limit - 1] + "…"
            return _balance_markdown_fences(t)

        if using_rich_draft:
            result = await _send_rich_draft(
                message.chat.id, draft_id,
                # Draft ham rich xabar — fence bu yerda ham Web'da
                # "not supported" bo'ladi (code_fences_to_html izohiga q.).
                # ⚠️ _fit() ichida _balance_markdown_fences bor: oqim
                # o'rtasida ochiq qolgan ``` avval yopiladi, keyin
                # <pre> ga o'giriladi — yarim fence buzuq HTML bermaydi.
                markdown=code_fences_to_html(_fit(MAX_RICH_CHARS)),
                message_thread_id=message_thread_id,
                can_stop=True,
            )
            if result is not None:
                push_failures = 0
                rich_draft_ok = True
                return
            # ⚠️ ISHLAB TURGAN draft BITTA rad javobidan keyin
            # tashlanmaydi: eng ko'p uchraydigan sabab — 429 flood wait,
            # ya'ni vaqtinchalik holat. Oldin shu yerda darhol
            # `using_rich_draft = False` turardi va bitta cheklov butun
            # javobni oddiy xabarga tushirib yuborardi.
            # Hech qachon ishlamagan draft esa (rich_draft_ok=False)
            # darhol tashlanadi — kutib turishning ma'nosi yo'q,
            # foydalanuvchi tezroq oddiy kutish xabarini ko'rgani afzal.
            push_failures += 1
            if rich_draft_ok and push_failures < RICH_DRAFT_FAILURE_LIMIT:
                return                      # keyingi bo'lakda qayta urinamiz
            using_rich_draft = False

        safe_markdown = _fit(MAX_PLAIN_CHARS)

        if fallback_message is None:
            if force:
                # ⚠️ MAJBURIY birinchi push uchun YANGI kutish xabari
                # yaratilmaydi. Draft o'lik bo'lsa qisqa javob bitta
                # bo'lakda kelib tugaydi va o'sha xabar darhol
                # o'chiriladi — ekranda ma'nosiz ko'z qisish bo'lardi.
                # Uzun javobda esa animator uni ~1s ichida o'zi yasaydi.
                return
            try:
                fallback_message = await message.answer("⏳ Javob tayyorlanmoqda...")
            except Exception:
                fallback_message = None

        if fallback_message is not None:
            await _edit_message_fallback(fallback_message, safe_markdown)

    # To'xtatish tugmasi shu draft'ga bog'lanadi.
    stop_requested = asyncio.Event()
    _stop_events[draft_id] = stop_requested
    stopped = False
    timed_out = False
    push_failures = 0
    first_push = True
    stream_iter = stream_generator.__aiter__()

    try:
        while True:
            try:
                chunk, was_stopped, finished = await _next_or_stop(
                    stream_iter, stop_requested)
            except TimeoutError as e:
                # Oqim o'lgan. Yozilib ulgurgan qism baribir yuboriladi,
                # hech narsa bo'lmasa — chaqiruvchi xatoni ko'radi.
                timed_out = True
                logger.warning(f"[Timeout] {e} (chat={message.chat.id})")
                break
            if was_stopped:
                stopped = True
                logger.info(f"[Stop] foydalanuvchi generatsiyani to'xtatdi "
                            f"(chat={message.chat.id}, draft={draft_id})")
                break
            if finished:
                break
            if not chunk:
                continue

            if chunk.startswith("[STATUS]"):
                # Kontent emas — bu faqat "band" animatsiyasiga signal.
                # Animatsiya TO'XTATILMAYDI, chunki qidiruv/fayl vazifasi
                # hali davom etyapti (ekran "muzlab qolmasligi" uchun).
                if "file_task" in chunk:
                    active_type = "file_task"
                elif "image" in chunk:
                    active_type = "image"
                elif "reminder" in chunk:
                    active_type = "reminder"
                elif "memory" in chunk:
                    active_type = "memory"
                elif "search" in chunk:
                    # ⚠️ /research O'Z holatini saqlaydi. Uning ichida
                    # o'nlab qidiruv ketadi va har biri statusni umumiy
                    # "qidiruv"ga tushirsa, 2-5 daqiqalik tadqiqot
                    # oddiy savoldan farq qilmay qolardi.
                    if content_type != "research":
                        active_type = "search"
                # ⚠️ ANIMATSIYANI QAYTA YOQAMIZ. Model tool chaqirishdan
                # OLDIN matn yozgan bo'lsa (odatiy hol: "hozir
                # qidiraman..."), animatsiya allaqachon to'xtagan va
                # animator task tugagan bo'ladi. Vazifa esa 20-60
                # soniya davom etadi — ekranda o'sha eskirgan matn
                # (uni [CLEAR_TEXT] baribir tashlaydi) qimirlamay
                # turardi. Qayta yoqilgan animator draftni holat
                # kadri bilan qoplaydi.
                if stop_animation.is_set() and anim_task.done():
                    stop_animation.clear()
                    anim_task = asyncio.create_task(emoji_animator())
                continue

            # [CLEAR_TEXT] — kontent EMAS, boshqaruv signali: shu paytgacha
            # yig'ilgan oraliq matnni tashlab yuborish kerak. Shuning uchun u
            # animatsiyani TO'XTATMASLIGI kerak — aks holda ko'p bosqichli
            # vazifada (masalan fayl ustida ikkinchi marta kod ishlayotganda)
            # ekran bo'sh holatda muzlab qolardi. Animatsiyani faqat haqiqiy
            # matn kelganda to'xtatamiz (pastda).
            if "[CLEAR_TEXT]" in chunk:
                full_text = ""
                chunk_buffer = ""
                # Tooldan keyingi javob noldan boshlanadi — birinchi
                # bo'lagi yana darhol ekranga chiqsin.
                first_push = True
                chunk = chunk.replace("[CLEAR_TEXT]", "")
                if not chunk:
                    continue

            if not stop_animation.is_set():
                stop_animation.set()

            full_text += chunk
            chunk_buffer += chunk
            clean_text = full_text.replace("[NO_BUTTON]", "").strip()

            if len(chunk_buffer) >= PUSH_MIN_CHARS or first_push:
                await push_update(clean_text, force=first_push)
                first_push = False
                chunk_buffer = ""

    finally:
        _stop_events.pop(draft_id, None)
        if stopped:
            # OpenAI oqimini ham yopamiz — aks holda so'rov fonda davom
            # etib, TO'XTATILGAN javob uchun ham token hisoblanardi.
            try:
                await stream_generator.aclose()
            except Exception:
                pass
        stop_animation.set()
        anim_task.cancel()
        try:
            await anim_task
        # ⚠️ asyncio.CancelledError — BaseException, ya'ni `except Exception`
        # UNI TUTMAYDI. Animator aynan shu paytda Telegram'ga so'rov yuborib
        # turgan bo'lsa (tez keladigan qisqa javoblarda odatiy hol), cancel()
        # uni uzib, xato BUTUN handler'dan yuqoriga otilardi: ball yechilgan,
        # javob tayyor, lekin foydalanuvchi HECH NARSA olmasdi. Uni bu yerda
        # yutamiz — animator ataylab to'xtatilgan, bu xato emas.
        except (asyncio.CancelledError, Exception):
            pass

    # ⚠️ Ichki nomlar shu yerda kesiladi — YAKUNIY matndan, ya'ni
    # yuborish, tarix va admin oynasi uchun bir joyda.
    clean_text = strip_internal_names(
        full_text.replace("[NO_BUTTON]", "").strip())
    if timed_out:
        # Bir harf ham kelmagan bo'lsa — chaqiruvchining except bloki
        # toza xato + "Qayta so'rash" tugmasini beradi va ballni
        # qaytaradi. Yarim javob esa yo'qotilmaydi, izoh bilan ketadi.
        if not clean_text:
            raise TimeoutError("javob oqimi jim qoldi")
        clean_text += "\n\n⚠️ _Javob to'liq tugamadi — qayta so'rang._"
    # Tarixga ASL matn (kodi bilan) ketadi, chatga esa fayl + izoh.
    history_text = clean_text
    kod_fayllar: list = []
    if clean_text:
        clean_text, kod_fayllar = _extract_long_code(clean_text)
    if clean_text:
        # Rich xabarga 32768 belgi sig'adi, oddiysiga 4096. Bo'lish
        # qaysi yo'l bilan ketishiga qarab tanlanadi — guruhda ham rich
        # ishlaydi (draft esa yo'q), shuning uchun mezon can_send_rich.
        parts = _split_for_telegram(
            clean_text, MAX_RICH_CHARS if can_send_rich else MAX_PLAIN_CHARS)
        # "Nusxa olish" tugmasi FAQAT javob bitta bo'lakka sig'ganda.
        # Sabab: _split_for_telegram() bo'lak o'rtasida qolgan kod blokini
        # yopib, keyingisida qayta ochadi — ya'ni bo'lingan javobda tugma
        # kodning YARMINI nusxalab, foydalanuvchini chalg'itardi.
        # To'xtatilgan javobda ham tugma yo'q: u tugallanmagan.
        buttons_html = ("" if (stopped or len(parts) != 1)
                        else _copy_button_html(clean_text))

        # Har bir bo'lak uchun pog'onalar:
        #   1) rich xabar — rasm/tugma bilan
        #   2) rich xabar — bezaksiz (rasm havolasi o'lik bo'lsa Telegram
        #      BUTUN xabarni rad etadi; javob bezakdan muhimroq)
        #   3) kutish xabarini tahrirlash (faqat birinchi bo'lak)
        #   4) oddiy yangi xabar
        # Javob "yo'qolib qolishi" uchun to'rttasi ham yiqilishi kerak.
        for idx, part in enumerate(parts):
            base_md = build_rich_markdown(part)
            # ⚠️ ZAXIRA VARIANTIDA PREMIUM EMOJI HAM YO'Q. Matn ichidagi
            # custom emoji bot egasida Telegram Premium bo'lishini talab
            # qiladi; obuna tugasa Telegram BUTUN xabarni rad etadi.
            # Rasm havolasi bilan bir xil tamoyil — javob bezakdan
            # muhimroq.
            plain_md = strip_custom_emoji(strip_image_tokens(base_md))
            rich_md = embed_images(base_md, images or [])
            if buttons_html:
                rich_md += "\n\n" + buttons_html

            if can_send_rich:
                outcome: list = []
                # Bezak = rasm bloki YOKI premium emoji. Ikkalasi ham
                # xabarni rad ettirishi mumkin va ikkalasisiz variant
                # bitta — plain_md.
                bezakli = rich_md != plain_md
                sent = await _send_rich_message(
                    message.chat.id,
                    markdown=rich_md,
                    message_thread_id=message_thread_id,
                    outcome=outcome,
                    # ⚠️ Rasm bo'lsa Telegram xabarni yaratishdan OLDIN har
                    # bir havolani manba saytdan O'ZI yuklab oladi — bu
                    # umumiy 10s chegarasidan oson oshadi.
                    timeout=RICH_MEDIA_TIMEOUT if bezakli else None,
                )
                if sent is not None:
                    continue

                # ⚠️ QAYTA URINISH FAQAT ANIQ RAD ETILGANDA. Timeout yoki
                # uzilishda xabar YETIB BORGAN bo'lishi mumkin — o'shanda
                # ikkinchi marta yuborish foydalanuvchiga BIR XIL javobni
                # ikki marta ko'rsatardi (aynan shu nosozlik kuzatilgan:
                # birinchisi rasmli, ikkinchisi rasmsiz).
                if OUTCOME_UNKNOWN in outcome:
                    logger.warning(
                        "[Rich] javob kelmadi (timeout) — xabar yetib borgan "
                        "bo'lishi mumkin, TAKROR yuborilmaydi")
                    continue

                # Aniq rad etildi: sababi deyarli har doim media havolasi
                # yoki tugma. Ikkalasisiz qayta urinamiz.
                if bezakli:
                    logger.info("[Rich] bezakli xabar rad etildi — "
                                "rasm/emoji/tugmasiz qayta urinilmoqda")
                    plain_outcome: list = []
                    sent = await _send_rich_message(
                        message.chat.id,
                        markdown=plain_md,
                        message_thread_id=message_thread_id,
                        outcome=plain_outcome,
                    )
                    if sent is not None or OUTCOME_UNKNOWN in plain_outcome:
                        continue

            # ⚠️ ZAXIRA YO'LI — ODDIY XABAR, ya'ni 4096 chegarasi. Bo'lak
            # esa rich o'lchamida (30000 gacha) kesilgan: uni QAYTA
            # bo'lmasdan yuborish Telegram tomonidan rad etiladi va javob
            # BUTUNLAY yo'qoladi — rich yo'l allaqachon yiqilgan holat.
            for kichik in _split_for_telegram(
                    strip_rich_tokens(strip_image_tokens(part)),
                    MAX_PLAIN_CHARS):
                if (idx == 0 and fallback_message is not None
                        and not fallback_used):
                    if await _edit_message_fallback(
                            fallback_message, kichik) is not None:
                        fallback_used = True
                        continue

                await _answer_plain(message, kichik)

    # Uzun kod — matndan keyin alohida fayl(lar) bo'lib boradi.
    if kod_fayllar:
        try:
            await _send_output_files(message.chat.id, kod_fayllar)
        except Exception as e:
            logger.warning(f"[Kod fayl] yuborilmadi (chat={message.chat.id}): {e}")

    # "⏳ Javob tayyorlanmoqda..." xabari — bu faqat draft yiqilgandagi
    # ZAXIRA ko'rsatkich. Yakuniy javob boshqa yo'l bilan yetkazilgan
    # bo'lsa (yoki umuman matn bo'lmasa — faqat fayl), u chatda yarim
    # matn va ✍️ belgisi bilan osilib qolardi. O'chirib tashlaymiz.
    if fallback_message is not None and not fallback_used:
        try:
            await bot.delete_message(message.chat.id, fallback_message.message_id)
        except Exception:
            pass

    return history_text


# --------------------------------------------------
# XOTIRANI AVTOMATIK TOZALASH
# --------------------------------------------------
async def check_and_clear_session(chat_id: int):
    now = time.time()
    last_time = chat_last_interaction.get(chat_id, now)

    if now - last_time > SESSION_TIMEOUT:
        forget_sent_images(chat_id)
        forget_location(chat_id)
        await clear_chat_history(chat_id)
        try:
            msg = await bot.send_message(
                chat_id,
                "🧹 <i>Suhbat xotirasi yangilandi.</i>",
                parse_mode="HTML"
            )
            asyncio.create_task(delete_msg_later(chat_id, msg.message_id, 5))
        except Exception:
            pass

    chat_last_interaction[chat_id] = now


async def delete_msg_later(chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# --------------------------------------------------
# KUNLIK LIMIT (DAILY QUOTA)
# --------------------------------------------------
async def _check_quota(user_id: int, cost: int) -> dict:
    try:
        quota = await check_and_consume_quota(user_id, cost)
    except Exception as e:
        logger.error(f"[Kvota] tekshiruvda xatolik (user={user_id}): {e}")
        return {"allowed": True, "used": 0, "limit": DAILY_FREE_LIMIT, "unlimited": False}

    # Buyruqlar menyusini shu yerda moslaymiz: tarif ALLAQACHON bazadan
    # o'qilgan (qo'shimcha so'rov yo'q) va bu yo'l hamma xabar turidan
    # o'tadi. Tarif tugashi ham aynan check_and_consume_quota() ichida
    # aniqlanadi, ya'ni Pro buyruqlari o'z vaqtida yo'qoladi.
    _fire_and_forget(
        menu_module.sync_commands(user_id, _is_pro(quota)), label="menyu")
    return quota


def _is_pro(quota: dict) -> bool:
    """Pro imkoniyatlari (chuqur fikrlash, 2× xotira) uchun bayroq.

    Tarif check_and_consume_quota() natijasidan olinadi — u allaqachon
    bazadan o'qigan, shuning uchun qo'shimcha so'rov kerak emas. Admin va
    muddatsiz 'premium' ham shu imkoniyatlarni oladi.
    """
    return quota.get("plan", "free") != "free"


async def _refund_quota(user_id: int, cost: int, quota: dict | None = None) -> None:
    """
    Hech qanday haqiqiy AI javobi berilmagan so'rovlar uchun oldin
    yechilgan kvotani qaytaradi.

    MUHIM GUARD: agar `quota["unlimited"]` bo'lsa (admin/superadmin/premium),
    check_and_consume_quota() ularning hisobini umuman o'zgartirmagan edi —
    shuning uchun bu yerda "qaytarish" ularning hisobini haqiqatda hech
    qachon yechilmagan miqdorga kamaytirib yuboradi. Bunday holatda hech
    narsa qilinmaydi.
    """
    if quota is not None and quota.get("unlimited"):
        return
    try:
        await refund_quota(user_id, cost)
    except Exception as e:
        logger.error(f"[Kvota] qaytarishda xatolik (user={user_id}): {e}")


async def _answer_with_pro_button(message: Message, text: str, offer: bool) -> None:
    """Limit xabarini yuboradi; `offer` bo'lsa yoniga "Pro" tugmasini qo'yadi.

    Tugma ATAYLAB shu xabarning o'zida: foydalanuvchi limitga urilgan payt —
    konversiya uchun eng qulay moment, uni /profile ga yuborib yo'qotmaymiz.
    """
    kb = None
    if offer:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [pro_module.btn("💎 Pro tarifga o'tish", "pro:open",
                            style=pro_module.BTN_SUCCESS)],
        ])
    # Guruhda limit/tarif xabari — SHAXSIY ma'lumot: qancha ball qolgani
    # va qaysi tarifda ekani hammaga ko'rinmasligi kerak (Bot API 10.3).
    await pro_module.send_rich(message, text, kb, **ephemeral_params(message))


async def _after_file_task(message: Message, quota_box: list, produced_files: bool) -> None:
    """Fayl vazifasidan keyingi ish: faollikni yozish va limit xabari.

    Limit xabari ATAYLAB modelning o'z so'zlariga tashlab qo'yilmagan:
    model har safar boshqacha ifodalaydi, tarif shartlarini o'zicha o'ylab
    topishi ham mumkin. services/ai.py modelga faqat bitta qisqa uzr jumlasi
    yozishni buyuradi, tafsilotni esa shu yerdan aniq matn bilan beramiz.
    """
    # quota_box'da bir nechta kvota bo'lishi mumkin (fayl va rasm) —
    # bittasi ishlatilib, ikkinchisiga umuman tegilmagan bo'lishi odatiy hol.
    #
    # ⚠️ `charged` tekshiruvi MAJBURIY: agar faqat rasm chizilgan bo'lsa,
    # fayl kvotasi hech qachon yechilmagan bo'ladi va uning qiymatlari
    # boshlang'ich holatda qoladi (limit=0, used=0, plan='free'). O'shanda
    # pastdagi "oxirgi bepul faylingiz" shoxi yolg'on ishga tushib, PRO
    # foydalanuvchiga bepul tarif haqida xabar yozib yuborardi.
    quota = next((q for q in (quota_box or []) if getattr(q, "charged", False)), None)
    if quota is None:
        return

    # Fayl yaratish admin statistikasida ko'rinsin — u eng qimmat amal,
    # lekin ilgari hech qanday faollik turi sifatida yozilmasdi.
    if produced_files and quota.kind == "files":
        track_user_activity(
            message.from_user.id, message.from_user.username, "file_task"
        )

    # Pro foydalanuvchiga Pro sotib olishni taklif qilmaymiz — uning limiti
    # allaqachon eng balandi, xabar faqat holatni tushuntiradi.
    is_free = getattr(quota, "plan", "free") == "free"

    if quota.kind == "images":
        # Rasm BEPULDA UMUMAN YO'Q (limit=0), shuning uchun bepul
        # foydalanuvchi uchun bu "limit tugadi" emas, "bu Pro imkoniyati".
        if quota.limit_hit and quota.limit == 0:
            text = (
                f"🖼 <b>Rasm chizish — Pro imkoniyati</b>\n\n"
                f"<blockquote>Pro tarifda kuniga <b>{PLAN_LIMITS['pro']['images']} ta</b> "
                f"rasm chizib beraman: manzara, logotip, illyustratsiya — "
                f"istagan tasviringizni.</blockquote>\n\n"
                f"💬 Qolgan hamma narsa hozir ham ishlaydi."
            )
        elif quota.limit_hit:
            text = (
                f"🖼 <b>Bugungi rasm limiti tugadi</b> ({quota.limit} ta).\n"
                f"🕛 Ertaga soat <b>00:00</b> da yangilanadi.\n"
                f"💬 Suhbat hozir ham ishlaydi."
            )
        else:
            return
        await _answer_with_pro_button(message, text, offer=is_free)
        return

    if quota.limit_hit and is_free:
        text = (
            f"📄 <b>Bugungi fayl limiti tugadi</b>\n\n"
            f"Bepul tarifda kuniga <b>{quota.limit} ta</b> fayl yaratish "
            f"mumkin va bugungisi ishlatib bo'lindi.\n"
            f"🕛 Yangi limit ertaga soat <b>00:00</b> da avtomatik yangilanadi.\n\n"
            f"💎 <b>Pro</b> tarifda kuniga <b>{PLAN_LIMITS['pro']['files']} ta</b>:\n"
            f"├ 📊 Prezentatsiya — PPTX\n"
            f"├ 📄 Hujjat — PDF, Word\n"
            f"├ 📈 Jadval va diagramma — Excel\n"
            f"└ 🔄 Formatdan formatga o'girish\n\n"
            f"💬 Oddiy savollar hozir ham ishlaydi — bemalol yozavering."
        )
    elif quota.limit_hit:
        text = (
            f"📄 <b>Bugungi fayl limiti tugadi</b> ({quota.limit} ta).\n"
            f"Siz bugun juda faol bo'ldingiz 🙌\n"
            f"🕛 Limit ertaga soat <b>00:00</b> da to'liq yangilanadi.\n"
            f"💬 Oddiy savollar hozir ham ishlaydi."
        )
    elif produced_files and quota.remaining == 0 and is_free:
        # Konversiya uchun eng qulay payt: fayl endigina qo'lida.
        text = (
            f"ℹ️ Bu bugungi <b>oxirgi bepul faylingiz</b> edi.\n"
            f"🕛 Ertaga soat <b>00:00</b> da yana <b>{quota.limit} ta</b> beriladi.\n"
            f"💎 Pro'da kuniga <b>{PLAN_LIMITS['pro']['files']} ta</b>."
        )
    else:
        return

    await _answer_with_pro_button(message, text, offer=is_free)


_FEATURE_LABELS: dict[str, tuple[str, int]] = {
    "text": ("<b>✉️ Matnli xabar</b>", MESSAGE_COST_TEXT),
    "photo": ("<b>🖼 Rasm tahlili</b>", MESSAGE_COST_PHOTO),
    "voice": ("<b>🎤 Ovozli xabar</b>", MESSAGE_COST_VOICE),
    "document": ("<b>📄 Hujjat tahlili</b>", MESSAGE_COST_DOCUMENT),
}


async def _send_limit_reached_message(message: Message, quota: dict, feature: str | None = None):
    if quota.get("banned"):
        try:
            # Guruhda bloklanganini butun guruhga e'lon qilish shart emas.
            await message.answer("🚫 Siz botdan foydalanish huquqidan mahrum qilingansiz.",
                                 **ephemeral_params(message))
        except Exception:
            try:
                await message.answer("🚫 Siz botdan foydalanish huquqidan mahrum qilingansiz.")
            except Exception:
                pass
        return

    used = quota.get("used", quota.get("limit", 0))
    limit = quota.get("limit", 0)
    remaining = max(0, limit - used)
    is_free = quota.get("plan", "free") == "free"

    feature_label = _FEATURE_LABELS.get(feature, (None, None))[0] if feature else None

    affordable = [
        (label, remaining // cost)
        for key, (label, cost) in _FEATURE_LABELS.items()
        if key != feature
    ]
    has_any_affordable = remaining > 0 and any(count > 0 for _, count in affordable)

    if not has_any_affordable and not is_free:
        # Pro/premium limitiga urilish juda kam uchraydi — bu yerda upsell
        # o'rinsiz, aybdorlik hissi ham keraksiz.
        text = (
            f"⏳ <b>Bugungi limitingiz tugadi</b> ({used}/{limit} ball).\n"
            f"Siz bugun juda faol bo'ldingiz 🙌\n"
            f"🕛 Limit ertaga soat <b>00:00</b> da to'liq yangilanadi."
        )
    elif not has_any_affordable:
        text = (
            f"⏳ <b>Bugungi bepul limitingiz tugadi</b> ({used}/{limit} ball).\n"
            f"🕛 Yangi limit ertaga soat <b>00:00</b> da avtomatik yangilanadi.\n\n"
            f"💎 <b>Pro</b> tarifda kuniga "
            f"<b>{PLAN_LIMITS['pro']['points']} ball</b> — {PLAN_LIMITS['pro']['points'] // limit if limit else 10}× ko'p."
        )
    else:
        lines = "\n".join(f"├ {label}: {count} ta" for label, count in affordable)
        feature_part = f" <b>{feature_label}</b> uchun" if feature_label else ""
        text = (
            f"❌{feature_part} AI Creditlaringiz yetarli emas.\n"
            f"💰 <b>Qolgan Creditlar:</b> {remaining}\n\n"
            f"<b>Hali ham foydalanishingiz mumkin:</b>\n{lines}\n\n"
            f"🕛 Creditlar ertaga soat <b>00:00</b> da avtomatik yangilanadi."
        )

    await _answer_with_pro_button(message, text, offer=is_free)


# --------------------------------------------------
# 1. START VA COMMAND HANDLERS
# --------------------------------------------------
# DIQQAT: bu funksiyalar `@router...` bilan bezatilmagan ataylab — ular
# main.py'da `general_router.message.register(...)` orqali, tegishli
# (non_admin_predicate va h.k.) filtrlar bilan qo'lda ro'yxatdan o'tkaziladi.
# `router` bu yerda FAQAT `GeneratingState` spam-guard (busy_handler) uchun
# ishlatiladi — agar bu funksiyalarga ham `@router...` qo'shilsa, main.py
# `router`ni include qilganda ular filtrsiz (masalan admin uchun ham)
# qayta ro'yxatdan o'tib, general_router'dagi to'g'ri filtrlangan versiyani
# hech qachon ishga tushirmay qo'yadi.
def _greeting_text(*, premium: bool) -> str:
    """/start salomlashuvi. premium=False — zaxira, oddiy emoji bilan.

    Emoji nomlari core/config.py: CUSTOM_EMOJI dan olinadi. Nom xato
    yozilsa pe() jimgina oddiy emojiga tushadi, shuning uchun nomlar
    tests/test_greeting.py da tekshiriladi.
    """
    e = (lambda name, fb: pro_module.pe(name, fb)) if premium else (lambda name, fb: fb)
    return (
        f"{e('wave', '👋')} <b>Keling tanishib olaylik!</b>\n\n"
        f"{e('bot', '🤖')} Men sizning AI yordamchingizman. "
        f"Quyidagilarni qila olaman:\n"
        f"➤ Savollaringizga javob beraman "
        f"(Internetdan ham qidiraman {e('search', '🌐')})\n"
        f"➤ {e('file', '📄')} <b>Hujjatlar (PDF/Word/Excel/TXT)</b> yuborsangiz, "
        f"o'qib tahlil qilaman!\n"
        f"➤ {e('photo', '📸')} <b>Rasm</b> yuborsangiz — uni xuddi insondek "
        f"ko'rib tushuntiraman!\n"
        f"➤ {e('voice', '🎙')} <b>Ovozli xabar</b> yuborsangiz — "
        f"<b>ovozli javob</b> qaytaraman!\n"
        f"➤ {e('tools', '🛠')} <b>Fayl yaratib beraman</b> — PPTX, PDF, Word, Excel\n\n"
        f"{e('broom', '🧹')} Agar suhbatni noldan boshlamoqchi bo'lsangiz "
        f"/new buyrug'ini bering.\n\n"
        f"{e('write', '✍️')} Savolingizni yozing, rasm, hujjat yoki ovoz "
        f"yuboring. Boshladikmi?"
    )


async def handle_start(message: Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    user_id = message.from_user.id

    # ⚠️ TARTIB MUHIM: track_user_activity() ichida save_user() fon
    # vazifasi sifatida ishga tushadi va foydalanuvchini bazaga YOZADI.
    # "Bu foydalanuvchi yangimi?" tekshiruvi undan KEYIN qo'yilsa, referal
    # goh ishlab, goh ishlamay qoladi (race condition).
    is_new_user = False
    try:
        is_new_user = not await has_started(user_id)
    except Exception:
        pass

    track_user_activity(user_id, message.from_user.username, "start")

    # Referal deep-link: t.me/<bot>?start=ref_<taklif_qilgan_id>
    # Mukofot bu yerda EMAS, foydalanuvchi birinchi haqiqiy savolini
    # berganda beriladi (pro.maybe_qualify_referral) — soxta akkauntlar
    # ochib kun yig'ishning oldini oladi.
    start_payload = (command.args or "") if command else ""
    if is_new_user and start_payload.startswith("ref_"):
        _fire_and_forget(
            pro_module.register_referral(user_id, start_payload[4:]), label="referral")

    try:
        if await is_banned(message.from_user.id):
            await message.answer("🚫 Siz botdan foydalanish huquqidan mahrum qilingansiz.")
            return
    except Exception:
        pass

    try:
        admin_flag = await is_admin(message.from_user.id)
        super_flag = await is_superadmin(message.from_user.id)
        if admin_flag or super_flag:
            await message.answer("👋 <b>Admin panelga xush kelibsiz!</b>", reply_markup=admin_keyboard)
            return
    except Exception:
        pass

    # Salomlashuv ostidagi tugma imkoniyatlar ekranini ochadi. Ro'yxatni
    # o'qigan odam odatda "xo'sh, endi nima yozay?" degan joyda to'xtaydi —
    # tugma aynan shu bo'shliqni yopadi va tayyor misollarga olib boradi.
    from handlers.capabilities import menu_button      # ⚠️ tsiklik import
    kb = InlineKeyboardMarkup(inline_keyboard=[[menu_button()]])

    try:
        await message.answer(_greeting_text(premium=True), reply_markup=kb)
    except TelegramBadRequest as exc:
        # Premium emoji Telegram tomonidan rad etilsa BUTUN xabar
        # yuborilmaydi va yangi foydalanuvchi hech narsa ko'rmaydi — bu
        # botdagi eng yomon nosozlik. Shuning uchun oddiy emojili
        # variantga tushamiz (qalin matn saqlanadi).
        logger.warning(f"[/start] premium emoji rad etildi: {exc}")
        # ⚠️ Klaviatura ham SODDALASHTIRILADI. Rad etilgan narsa matndagi
        # <tg-emoji> bo'lishi shart emas — tugmadagi icon_custom_emoji_id
        # ham xuddi shu xatoni beradi. Eski kb bilan qayta urinish o'sha
        # holatda yana yiqilib, tugmani BUTUNLAY yo'qotardi.
        plain_kb = pro_module._downgrade_kb(kb)
        try:
            await message.answer(_greeting_text(premium=False), reply_markup=plain_kb)
        except TelegramBadRequest:
            # Tugma ham rad etilsa (masalan `style` maydonini bilmaydigan
            # eski mijoz) — salomlashuvning O'ZI baribir yetib borsin.
            await message.answer(_greeting_text(premium=False))


# --------------------------------------------------
# 2. TEXT HANDLER (Web Search)
# --------------------------------------------------
# --------------------------------------------------
# YUBORILGAN FAYLNI ESLAB QOLISH
#
# Telegram'da UZATILGAN (forward) faylga izoh (caption) yozib bo'lmaydi.
# Shuning uchun foydalanuvchi odatda avval faylni, keyin ALOHIDA xabar
# qilib ko'rsatmani yuboradi ("bu yerdagi 31.12.99 ni 0 qil"). Ilgari bu
# ikki xabar mustaqil ishlanardi: fayl ko'rsatmasiz kelib qisqacha
# mazmun olardi, ko'rsatma esa faylsiz kelib "qaysi fayl?" bo'lib qolardi.
#
# Ikki bosqichli yechim:
#   1) Izohsiz fayl kelsa, javob berishdan oldin _INSTRUCTION_WAIT soniya
#      ko'rsatma kutiladi — odatdagi holat shu yerda hal bo'ladi.
#   2) Fayl yana _PENDING_FILE_TTL davomida eslab qolinadi, shuning uchun
#      keyinroq yozilgan ("endi buni PDF qilib ber") so'rovga ham o'sha
#      fayl avtomatik biriktiriladi.
# --------------------------------------------------
_PENDING_FILE_TTL = 10 * 60    # keyingi matnli xabarlarga biriktirish oynasi
_INSTRUCTION_WAIT = 12.0       # izohsiz fayldan keyin ko'rsatmani kutish
_PENDING_FILE_MAX = 30         # ponytail: RAM chegarasi, kerak bo'lsa Redis'ga ko'chiriladi
# Eslab qolingan fayl FAQAT davomiy so'rovga biriktiriladi. Davomi doim
# qisqa bo'ladi ("endi PDF qil", "sarlavhani o'zgartir"); uzun xabar esa
# to'liq YANGI topshiriq (tayyor prezentatsiya spetsifikatsiyasi va h.k.).
# Uzun so'rovga eski faylni biriktirish real nosozlikka olib kelgan edi:
# model "bu sen yaratgan fayl, davom ettir" izohini o'qib, yangi hujjat
# yasash o'rniga eskisini tekshirish bilan barcha raundlarni sarflab,
# oxirida foydalanuvchiga faylsiz, xom matnli javob yozib qo'ygan.
_PENDING_FOLLOWUP_MAX_CHARS = 400
_pending_files: dict[int, dict] = {}


def _prune_pending_files() -> None:
    now = time.time()
    for cid in [c for c, r in _pending_files.items()
                if now - r.get("ts", 0) > _PENDING_FILE_TTL]:
        _pending_files.pop(cid, None)
    while len(_pending_files) > _PENDING_FILE_MAX:
        oldest = min(_pending_files, key=lambda c: _pending_files[c].get("ts", 0))
        _pending_files.pop(oldest, None)


def clear_pending_file(chat_id: int) -> None:
    _pending_files.pop(chat_id, None)


def _get_pending_file(chat_id: int) -> dict | None:
    _prune_pending_files()
    rec = _pending_files.get(chat_id)
    return rec if rec and rec.get("bytes") else None


def _remember_file(chat_id: int, file_bytes: bytes, file_name: str,
                   *, produced: bool = False) -> None:
    """`produced=True` — faylni BOT yaratgan (foydalanuvchi yuklagan emas).

    Bu farq muhim: davomiy so'rov ("nomini ham o'zgartir") botning OXIRGI
    natijasi ustiga qo'yilishi kerak, dastlabki xom fayl ustiga emas.
    """
    _prune_pending_files()
    rec = _pending_files.setdefault(chat_id, {})
    rec.update({"ts": time.time(), "bytes": file_bytes, "name": file_name,
                "produced": produced})


def _pending_for_request(chat_id: int, text: str) -> dict | None:
    """Shu so'rovga eslab qolingan fayl biriktiriladimi?"""
    if len(text) > _PENDING_FOLLOWUP_MAX_CHARS:
        return None
    return _get_pending_file(chat_id)


def _capture_instruction(chat_id: int, text: str) -> bool:
    """Fayl ko'rsatma kutayotgan bo'lsa, matnni unga uzatadi.

    True qaytsa — bu xabar fayl bilan BIRGA ishlanadi, shuning uchun
    handle_text uni alohida so'rov sifatida ishlamasligi kerak.
    """
    rec = _pending_files.get(chat_id)
    event = rec.get("event") if rec else None
    if event is None or event.is_set():
        return False
    rec["instruction"] = text
    event.set()
    return True


async def _wait_for_instruction(chat_id: int) -> str | None:
    rec = _pending_files.get(chat_id)
    event = rec.get("event") if rec else None
    if event is None:
        return None
    try:
        await asyncio.wait_for(event.wait(), _INSTRUCTION_WAIT)
    except asyncio.TimeoutError:
        return None
    finally:
        rec.pop("event", None)
    return rec.pop("instruction", None)


def pending_file_note(file_name: str, *, earlier: bool = False,
                      produced: bool = False) -> str:
    """Modelga faylning sandbox ichida MAVJUDLIGINI aniq aytadigan izoh.

    Busiz model ko'rgan narsasi (matn ko'rinishi yoki uning yo'qligi)
    asosida "menga faylning o'zi emas, matni yuborilgan" deb xulosa
    qilib, tahrirlashdan bosh tortadi.
    """
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "bin"
    if produced:
        # ⚠️ Modelga bu faylni O'ZI yaratganini aytish SHART. Aks holda u
        # xuddi yangi xom fayl kelgandek ishlaydi va oldingi tahrirlarni
        # bekor qilib, faqat oxirgi so'ralgan o'zgarishni qo'yib beradi —
        # foydalanuvchi uchun bu "bot esidan chiqardi" bo'lib ko'rinadi.
        return (
            f"[FAYL BIRIKTIRILGAN] Bu — SEN oxirgi marta yaratib bergan "
            f"«{file_name}» fayli. Foydalanuvchi shu natijani DAVOM "
            f"ETTIRMOQCHI: undagi barcha oldingi o'zgarishlar saqlanib "
            f"qolishi shart, yangi so'rov ularning USTIGA qo'yiladi. Fayl "
            f"run_python_sandbox tool'i ichida `input.{ext}` yo'lida XOM "
            f"HOLDA turibdi. Ishni noldan boshlamang va faylni qayta "
            f"so'ramang."
        )
    qachon = "avval " if earlier else ""
    return (
        f"[FAYL BIRIKTIRILGAN] Foydalanuvchi {qachon}«{file_name}» faylini "
        f"yubordi. Fayl run_python_sandbox tool'i ichida `input.{ext}` "
        f"yo'lida XOM HOLDA mavjud — uni o'qish, tahrirlash yoki boshqa "
        f"formatga o'girish uchun o'sha tool'ni ishlating. Faylni qayta "
        f"so'ramang."
    )


async def handle_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text_str = message.text.strip()

    if text_str.lower() in ["/new", "/clear", "yangi suhbat"]:
        clear_text_merge_buffer(chat_id)
        clear_pending_file(chat_id)
        forget_sent_images(chat_id)
        forget_location(chat_id)
        await clear_chat_history(chat_id)
        chat_last_interaction[chat_id] = time.time()
        await message.answer("🧹 Xotira tozalandi! Mutlaqo yangi mavzuda suhbatlashishimiz mumkin.")
        return

    track_user_activity(user_id, message.from_user.username, "text_message")
    asyncio.create_task(process_daily_pin(message))

    # Hozirgina izohsiz fayl kelgan bo'lsa, bu xabar — o'sha fayl uchun
    # ko'rsatma. Uni handle_document kutib turibdi, shu yerda to'xtaymiz.
    if _capture_instruction(chat_id, message.text):
        notify_watchers(user_id, message.from_user.username, "in", text=message.text)
        logger.info(f"[Hujjat] ko'rsatma alohida xabardan olindi: chat={chat_id}")
        return

    await _queue_for_ai(chat_id, message, message.text, state)


async def _queue_for_ai(chat_id: int, message: Message, text: str,
                        state: FSMContext) -> None:
    """Matnni debounce buferiga qo'shadi va taymerni qayta boshlaydi.

    handle_text VA handle_location ikkalasi ham shu yerdan o'tadi.
    Joylashuv uchun bu ATAYLAB: aks holda u alohida yo'l bo'lib,
    kvota, navbat, oqim va TARIX undan chetlab o'tardi.
    """
    lock = get_text_merge_lock(chat_id)
    async with lock:
        buf = text_merge_buffers.get(chat_id)
        if buf is None:
            buf = {"parts": [], "last_message": message, "timer_task": None, "created_at": time.time()}
            text_merge_buffers[chat_id] = buf

        old_timer = buf.get("timer_task")
        if old_timer and not old_timer.done():
            old_timer.cancel()

        buf["parts"].append(text)
        buf["last_message"] = message

        total_len = sum(len(p) for p in buf["parts"])
        safety_limit_hit = len(buf["parts"]) >= TEXT_MERGE_MAX_PARTS or total_len >= TEXT_MERGE_MAX_CHARS

        # Chegaraga urilgan bufer darhol ketadi, qolgan hamma holatda
        # taymer QAYTA BOSHLANADI (core/config.py: TEXT_MERGE_WAIT izohi).
        delay = 0.0 if safety_limit_hit else TEXT_MERGE_WAIT

        buf["timer_task"] = asyncio.create_task(_schedule_merged_processing(chat_id, delay, state))


async def _schedule_merged_processing(chat_id: int, delay: float, state: FSMContext):
    try:
        if delay > 0:
            await asyncio.sleep(delay)

        lock = get_text_merge_lock(chat_id)
        async with lock:
            buf = text_merge_buffers.pop(chat_id, None)

        if not buf:
            return

        await _process_merged_text(chat_id, buf, state)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[Text Merge Error] {e}")


async def _process_merged_text(chat_id: int, buf: dict, state: FSMContext):
    parts = buf.get("parts") or []
    last_message: Message = buf.get("last_message")
    if not parts or last_message is None:
        return

    # ⚠️ Qator ajratuvchi bilan: bo'laklar IKKI xil sababdan kelishi
    # mumkin — Telegram 4096 belgida bo'lib yuborgan BITTA matn, yoki
    # foydalanuvchi ketma-ket yozgan ALOHIDA xabarlar. Ikkinchisida
    # bo'sh satr bilan yopishtirish so'zlarni bir-biriga qo'shib
    # yuborardi ("...tugadimi" + "yo'q" → "tugadimiyo'q").
    merged_text = parts[0] if len(parts) == 1 else "\n".join(parts)
    notify_watchers(last_message.from_user.id, last_message.from_user.username, "in", text=merged_text)

    if len(parts) > 1:
        logger.info(
            f"[Text Merge] chat={chat_id}: {len(parts)} ta bo'lingan xabar "
            f"{len(merged_text)} belgili bitta so'rovga birlashtirildi."
        )

    if len(merged_text) > MAX_TEXT_LENGTH:
        try:
            await bot.send_message(
                chat_id,
                f"📏 Matn juda uzun: {len(merged_text)} belgi "
                f"(chegara — {MAX_TEXT_LENGTH}).\n\n"
                "Iltimos, savolni qisqartiring yoki matnni <b>fayl</b> "
                "qilib yuboring — faylni to'liq o'qiy olaman.")
        except Exception:
            pass
        return

    user_id = last_message.from_user.id
    # Matn murakkabligiga qarab reasoning darajasi (va shunga mos narx) tanlanadi —
    # "salom" arzon (past effort), matematik/kod savoli qimmatroq (chuqurroq effort).
    text_effort = pick_reasoning_effort(merged_text)
    text_cost = message_cost("text", text_effort)
    quota = await _check_quota(user_id, text_cost)
    if not quota["allowed"]:
        await _send_limit_reached_message(last_message, quota, feature="text")
        return

    await check_and_clear_session(chat_id)
    await state.set_state(GeneratingState.generating)

    try:
        # ⚠️ YOUTUBE XULOSASI OLIB TASHLANDI (ataylab, tiklamang).
        # Bu yerda youtube.com havolasini ushlab, subtitrlarni yuklaydigan
        # alohida yo'l bor edi. YouTube bulut provayderlarining IP'larini
        # bloklaydi (RequestBlocked), ya'ni kod mahalliy kompyuterda
        # ishlab, serverda HAR SAFAR yiqilardi. Uni faqat pullik
        # residential proksi tiklaydi. Ishlamaydigan va'da ishlamaydigan
        # funksiyadan yomonroq bo'lgani uchun /start ro'yxatidan ham
        # olib tashlandi. Qaytarish kerak bo'lsa: proksi oling, keyin
        # youtube-transcript-api'ni requirements'ga qaytaring.
        # ══════════════════════════════════════════════════════════════
        # MUHIM TUZATISH (kontekst/xotira yo'qolish bug'i):
        #
        # Avvalgi versiyada foydalanuvchi xabari AI'dan javob olishdan
        # OLDIN saqlanardi. Natijada get_openai_reply() (services/ai.py)
        # tarixni DB'dan o'qiganda o'sha SO'NGGI xabarni (masalan "Hop")
        # allaqachon tarix ichida topib olardi va keyin uni YANA bir
        # marta — bu safar CONCISE_INSTRUCTION kabi
        # katta formatlash instruksiyasi bilan o'ralgan holda — messages
        # ro'yxatiga qo'shardi. Bu ikkita oqibatga olib kelardi:
        #   1) Ketma-ket ikkita "user" turi (orasida "assistant" yo'q) —
        #      modelning tabiiy suhbat oqimini buzadi.
        #   2) Qisqa javoblarda ("Hop", "Ha", "Davom et") asosiy matn
        #      formatlash qoidalari ichida "ko'milib" qolib, model buni
        #      oldingi mavzuning davomi emas, mustaqil yangi so'rov deb
        #      qabul qilardi.
        #
        # Tuzatish: (a) CONCISE_INSTRUCTION bu yerda
        # umuman qo'shilmaydi — ular services/ai.py'da SYSTEM promptga
        # allaqachon qo'shiladi, shuning uchun takrorlash shart emas;
        # (b) foydalanuvchi xabari tarixga FAQAT AI javobi muvaffaqiyatli
        # qaytgandan KEYIN, assistant javobi bilan BIRGALIKDA yoziladi —
        # shu bilan get_openai_reply() chaqirilgan paytda tarix hali
        # joriy xabarni o'z ichiga olmaydi va u faqat BIR MARTA, toza
        # holda "user" turi sifatida qo'shiladi.
        # ══════════════════════════════════════════════════════════════
        # Yaqinda fayl yuborilgan bo'lsa, uni shu so'rovga ham biriktiramiz —
        # "endi buni PDF qilib ber" kabi davomiy so'rovlar shu bilan ishlaydi.
        pending = _pending_for_request(chat_id, merged_text)
        prompt_text, file_kwargs = merged_text, {}
        if pending:
            note = pending_file_note(pending['name'], earlier=True,
                                     produced=pending.get('produced', False))
            prompt_text = (f"{note}"
                           f"\n\nFoydalanuvchi so'rovi: {merged_text}")
            file_kwargs = {"input_file_bytes": pending["bytes"],
                           "input_filename": pending["name"]}
            pending["ts"] = time.time()   # ketma-ket so'rovlar uchun oynani uzaytiramiz

        output_files: list = []
        file_quota_box: list = []
        images: list = []
        stream_gen = get_gpt_reply(chat_id, prompt_text, user_id=user_id,
                                   output_files=output_files,
                                   file_quota_out=file_quota_box,
                                   images_out=images,
                                   is_pro=_is_pro(quota),
                                   tg_name=last_message.from_user.full_name,
                                   **file_kwargs)
        full_reply = await process_stream_draft(last_message, stream_gen, images=images)

        if output_files:
            await _send_output_files(chat_id, output_files)
        await _after_file_task(last_message, file_quota_box, bool(output_files))

        # ⚠️ HECH NARSA YETKAZILMAGAN bo'lsa ball qaytariladi. Bu holat
        # ilgari jimgina o'tib ketardi (xato ham otilmaydi, javob ham
        # yo'q — ball esa yechilgan). Endi u aniq yopildi va bu ayni
        # paytda "To'xtatish" tugmasining ham to'g'ri xatti-harakati:
        # foydalanuvchi bir harf ham ko'rmasdan to'xtatsa, pul olinmaydi.
        if not full_reply and not output_files:
            await _refund_quota(user_id, text_cost, quota)

        if full_reply:
            notify_watchers(user_id, last_message.from_user.username, "out", text=full_reply)
            try:
                await safe_update_history(chat_id, merged_text, role="user")
                await safe_update_history(chat_id, full_reply, role="assistant",
                                          images=images)
            except Exception as e:
                logger.warning(f"[Tarix saqlash xatosi - matn] chat={chat_id}: {e}")

    except Exception as e:
        logger.error(f"[Text Error] {e}")
        try:
            await send_error_with_retry(
                chat_id=chat_id, message_id=last_message.message_id,
                user_id=user_id, prompt=merged_text,
                reason=("⏳ Javob juda uzoq cho'zildi."
                        if isinstance(e, TimeoutError) else None),
                kind="timeout" if isinstance(e, TimeoutError) else "matn",
            )
        except Exception:
            pass
        await _refund_quota(user_id, text_cost, quota)
    finally:
        # ⚠️ TARTIB MUHIM: avval holat tozalanadi, keyin navbat ishga
        # tushadi. Aks holda navbatdagi xabar o'zi qo'ygan
        # GeneratingState ichida qolib, busy_handler uni yana navbatga
        # qo'yardi — cheksiz aylanish.
        await state.clear()
        # busy_handler javob ketayotganda kelgan xabarlarni shu buferga
        # yig'adi. Taymeri yo'q, ya'ni uni shu yerda uyg'otish kerak.
        if (text_merge_buffers.get(chat_id) or {}).get("parts"):
            logger.info(f"[Navbat] chat={chat_id}: kutib turgan xabar(lar) "
                        f"qayta ishlanmoqda")
            asyncio.create_task(
                _schedule_merged_processing(chat_id, 0.0, state))


# --------------------------------------------------
# 2b. CHUQUR TADQIQOT (/research — faqat Pro)
# --------------------------------------------------
_RESEARCH_MIN_LEN = 8

_RESEARCH_HINT = (
    "🔎 <b>CHUQUR TADQIQOT</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "<blockquote>Bitta savol bo'yicha 10+ manbani qidiraman, "
    "solishtiraman va tayyor <b>PDF hisobot</b> qilib beraman.</blockquote>\n\n"
    "Shunday yozing:\n"
    "<code>/research O'zbekistonda elektromobil bozori 2026</code>\n\n"
    "<i>Bir necha daqiqa vaqt oladi — javob kelguncha kutib turing.</i>"
)


def _research_limit_text(quota) -> str:
    """Limit 0 bo'lsa — bu 'Pro imkoniyati', aks holda 'bugungisi tugadi'."""
    if quota.limit == 0:
        return (
            "🔎 <b>Chuqur tadqiqot — Pro imkoniyati</b>\n\n"
            "<blockquote>Pro tarifda kuniga "
            f"<b>{PLAN_LIMITS['pro']['research']} ta</b> chuqur tadqiqot: "
            "10+ manba, taqqoslash va tayyor PDF hisobot.</blockquote>\n\n"
            "💬 Oddiy savollar hozir ham ishlaydi."
        )
    return (
        f"🔎 <b>Bugungi tadqiqot limiti tugadi</b> ({quota.limit} ta).\n"
        f"🕛 Ertaga soat <b>00:00</b> da yangilanadi.\n"
        f"💬 Oddiy savollar hozir ham ishlaydi."
    )


async def handle_research(message: Message, state: FSMContext,
                          command: CommandObject = None):
    """/research <savol> — ko'p bosqichli qidiruv + xulosa + PDF hisobot.

    BALL YECHILMAYDI — o'z kunlik sanog'i bor. Sabab fayl limitidagi bilan
    bir xil: tadqiqot eng qimmat amal, ballardan yechilsa bitta tadqiqotdan
    keyin foydalanuvchi oddiy savol ham berolmay qolardi.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    topic = ((command.args if command else None) or "").strip()

    if len(topic) < _RESEARCH_MIN_LEN:
        await pro_module.send_rich(message, _RESEARCH_HINT)
        return

    quota = DailyQuota(user_id, "research")
    if not await quota.ensure_charged():
        if quota.limit_hit:
            await _answer_with_pro_button(
                message, _research_limit_text(quota), offer=(quota.limit == 0))
        else:
            await message.answer("🚫 Siz botdan foydalanish huquqidan mahrum qilingansiz.")
        return

    track_user_activity(user_id, message.from_user.username, "research")
    notify_watchers(user_id, message.from_user.username, "in", text=f"/research {topic}")
    await check_and_clear_session(chat_id)
    await state.set_state(GeneratingState.generating)

    output_files: list = []
    images: list = []
    try:
        stream_gen = get_gpt_reply(
            chat_id, f"Chuqur tadqiqot mavzusi: {topic[:1000]}",
            # user_id=None ATAYLAB: fayl sanog'i yechilmasin. Tadqiqot
            # sanog'i butun amal (qidiruvlar + hisobot + PDF) uchun
            # allaqachon to'langan, ikki marta yechish adolatsiz bo'lardi.
            user_id=None,
            output_files=output_files,
            images_out=images,
            is_pro=True,
            research=True,
        )
        full_reply = await process_stream_draft(message, stream_gen,
                                                content_type="research", images=images)

        if output_files:
            await _send_output_files(chat_id, output_files)

        if full_reply:
            quota.mark_success()
            notify_watchers(user_id, message.from_user.username, "out", text=full_reply)
            try:
                await safe_update_history(chat_id, f"[Tadqiqot]: {topic}", role="user")
                await safe_update_history(chat_id, full_reply, role="assistant",
                                          images=images)
            except Exception as e:
                logger.warning(f"[Tarix saqlash xatosi - tadqiqot] chat={chat_id}: {e}")
    except Exception as e:
        logger.error(f"[Research Error] {e}")
        await message.answer(
            "❌ Tadqiqot yakunlanmadi. Sanog'ingiz qaytarildi — "
            "birozdan keyin qayta urinib ko'ring."
        )
    finally:
        # Muvaffaqiyat bo'lmagan bo'lsa sanoqni o'zi qaytaradi.
        await quota.refund_if_unused()
        await state.clear()


# --------------------------------------------------
# 3. PHOTO HANDLER (Vision)
# --------------------------------------------------
async def handle_photo(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id

    track_user_activity(user_id, message.from_user.username, "photo_message")
    notify_watchers(user_id, message.from_user.username, "in", copy_chat_id=chat_id, copy_message_id=message.message_id)
    asyncio.create_task(process_daily_pin(message))

    await check_and_clear_session(chat_id)

    quota = await _check_quota(user_id, MESSAGE_COST_PHOTO)
    if not quota["allowed"]:
        await _send_limit_reached_message(message, quota, feature="photo")
        return

    await state.set_state(GeneratingState.generating)

    try:
        await bot.send_chat_action(chat_id, "upload_photo")
    except Exception:
        pass

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        from io import BytesIO
        result = BytesIO()
        await bot.download_file(file.file_path, result)
        image_bytes = result.getvalue()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        caption = message.caption if message.caption else "Bu rasmda nimalar borligini to'liq tushuntirib ber."

        # CONCISE_INSTRUCTION bu yerga qo'shilmaydi —
        # get_vision_reply() ularni SYSTEM promptga o'zi qo'shadi (services/ai.py).
        # Tarix esa javob muvaffaqiyatli olingandan keyin, birgalikda saqlanadi.
        stream_gen = get_vision_reply(chat_id, base64_image, caption,
                                      is_pro=_is_pro(quota), user_id=user_id,
                                      tg_name=message.from_user.full_name)
        full_reply = await process_stream_draft(message, stream_gen, content_type="photo")

        if full_reply:
            notify_watchers(user_id, message.from_user.username, "out", text=full_reply)
            try:
                await safe_update_history(chat_id, f"[Rasm yuborildi]: {caption}", role="user")
                # Vision yo'lida internetdan rasm qidirilmaydi (get_vision_reply
                # bir raundli va unda qidiruv tooli yo'q) — `images` ham yo'q.
                await safe_update_history(chat_id, full_reply, role="assistant")
            except Exception as e:
                logger.warning(f"[Tarix saqlash xatosi - rasm] chat={chat_id}: {e}")

    except Exception as e:
        logger.error(f"Rasm xatosi: {str(e)}")
        await message.answer("❌ Rasm tahlilida xatolik yuz berdi.")
        await _refund_quota(user_id, MESSAGE_COST_PHOTO, quota)
    finally:
        await state.clear()


# --------------------------------------------------
# 4. DOCUMENT HANDLER (ALL FILES)
# --------------------------------------------------
async def handle_document(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id
    document = message.document
    file_name = document.file_name if document.file_name else "fayl"

    track_user_activity(user_id, message.from_user.username, "document_message")
    notify_watchers(user_id, message.from_user.username, "in", copy_chat_id=chat_id, copy_message_id=message.message_id)
    asyncio.create_task(process_daily_pin(message))

    await check_and_clear_session(chat_id)

    # Qattiq shift — tarifdan qat'i nazar: Telegram Bot API 20 MB dan
    # kattasini yuklab olishga umuman ruxsat bermaydi.
    if (document.file_size or 0) > DOCUMENT_MAX_SIZE_PRO:
        await message.answer(
            f"⚠️ Fayl juda katta. Telegram botlarga eng ko'pi "
            f"<b>{DOCUMENT_MAX_SIZE_PRO // (1024 * 1024)} MB</b> gacha ruxsat beradi."
        )
        return

    quota = await _check_quota(user_id, MESSAGE_COST_DOCUMENT)
    if not quota["allowed"]:
        await _send_limit_reached_message(message, quota, feature="document")
        return

    # Tarif chegarasi kvotadan KEYIN tekshiriladi — plan aynan shu natijadan
    # keladi, ya'ni qo'shimcha DB so'rovi kerak emas. Fayl rad etilsa ball
    # qaytariladi: hech qanday AI javobi berilmadi.
    size_cap = document_max_size(quota.get("plan"))
    if (document.file_size or 0) > size_cap:
        await _refund_quota(user_id, MESSAGE_COST_DOCUMENT, quota)
        mb = size_cap // (1024 * 1024)
        free_plan = not _is_pro(quota)
        text = (f"⚠️ Fayl hajmi <b>{mb} MB</b> dan katta.\n\n"
                f"<blockquote>Pro tarifda "
                f"<b>{DOCUMENT_MAX_SIZE_PRO // (1024 * 1024)} MB</b> gacha "
                f"yuborish mumkin — skanerlangan PDF, prezentatsiya va katta "
                f"Excel odatda shu oraliqda.</blockquote>"
                if free_plan else
                f"⚠️ Fayl hajmi <b>{mb} MB</b> dan katta.")
        await _answer_with_pro_button(message, text, offer=free_plan)
        return

    # Izohsiz fayl — ko'rsatma keyingi xabarda kelishi mumkin. Buni
    # YUKLAB OLISHDAN OLDIN belgilab qo'yamiz, aks holda yuklash paytida
    # kelgan xabar alohida so'rov bo'lib ketadi. GeneratingState ham
    # hozircha o'rnatilmaydi — u busy_handler'ni yoqib, aynan o'sha
    # ko'rsatmani "iltimos kuting" javobi bilan yutib yuborardi.
    if not message.caption:
        _pending_files[chat_id] = {"ts": time.time(), "event": asyncio.Event()}

    try:
        await bot.send_chat_action(chat_id, "upload_document")
    except Exception:
        pass

    prompt = None
    try:
        file = await bot.get_file(document.file_id)
        from io import BytesIO
        result = BytesIO()
        await bot.download_file(file.file_path, result)
        file_bytes = result.getvalue()

        extracted = extract_text_from_document(file_bytes, file_name)
        if asyncio.iscoroutine(extracted):
            extracted_text = await extracted
        else:
            extracted_text = extracted

        _remember_file(chat_id, file_bytes, file_name)

        caption = message.caption
        if not caption:
            caption = await _wait_for_instruction(chat_id)
        if not caption:
            caption = "Shu hujjatning qisqacha mazmunini yozib ber."

        await state.set_state(GeneratingState.generating)

        # MUHIM: matnni ajratib bo'lmasa ham TO'XTAMAYMIZ. Binar formatlarda
        # matn o'qilmasligi mumkin, LEKIN run_python_sandbox tool'i faylning
        # XOM BAYTLARI bilan ishlaydi va uni openpyxl/pandas orqali to'g'ri
        # ocha oladi.
        unreadable = (
            not extracted_text
            or extracted_text.startswith("[XATOLIK]")
            or extracted_text.startswith("[BINARY]")
        )
        if unreadable:
            logger.info(f"[Hujjat] matn ajratilmadi ({file_name}) — sandbox'ga tayanamiz")

        file_note = pending_file_note(file_name)

        if unreadable:
            body = (
                f"{file_note}\n\n"
                "Bu format matn sifatida o'qilmadi (binar fayl), shuning uchun "
                "mazmunini ko'rish uchun ham tool'dan foydalaning."
            )
        else:
            body = f"{file_note}\n\nFayl mazmunidan namuna:\n{extracted_text}"

        # CONCISE_INSTRUCTION bu yerga qo'shilmaydi —
        # get_openai_reply() ularni SYSTEM promptga o'zi qo'shadi (services/ai.py).
        prompt = f"{body}\n\nFoydalanuvchi so'rovi: {caption}"
        output_files: list = []
        file_quota_box: list = []
        images: list = []
        stream_gen = get_gpt_reply(
            chat_id, prompt,
            user_id=user_id,
            input_file_bytes=file_bytes,
            input_filename=file_name,
            output_files=output_files,
            file_quota_out=file_quota_box,
            images_out=images,
            is_pro=_is_pro(quota),
            tg_name=message.from_user.full_name,
        )
        full_reply = await process_stream_draft(message, stream_gen,
                                                content_type="document", images=images)

        if output_files:
            await _send_output_files(chat_id, output_files)
        await _after_file_task(message, file_quota_box, bool(output_files))

        # Hech narsa yetkazilmadi — ball qaytariladi (to'xtatish tugmasi
        # bosilgan yoki model bo'sh javob qaytargan holat).
        if not full_reply and not output_files:
            await _refund_quota(user_id, MESSAGE_COST_DOCUMENT, quota)

        if full_reply:
            notify_watchers(user_id, message.from_user.username, "out", text=full_reply)
            try:
                await safe_update_history(chat_id, f"[Fayl yuborildi: {file_name}]: {caption}", role="user")
                await safe_update_history(chat_id, full_reply, role="assistant",
                                          images=images)
            except Exception as e:
                logger.warning(f"[Tarix saqlash xatosi - hujjat] chat={chat_id}: {e}")

    except Exception as e:
        logger.error(f"Hujjat xatosi: {str(e)}")
        if prompt:
            try:
                await send_error_with_retry(
                    chat_id=chat_id, message_id=message.message_id,
                    user_id=user_id, prompt=prompt,
                )
            except Exception:
                pass
        else:
            await message.answer("❌ Hujjatni o'qishda xatolik yuz berdi.")
        await _refund_quota(user_id, MESSAGE_COST_DOCUMENT, quota)
    finally:
        # Osilib qolgan "ko'rsatma kutilmoqda" bayrog'i keyingi xabarlarni
        # javobsiz yutib yuborardi — har qanday holatda tozalaymiz.
        _pending_files.get(chat_id, {}).pop("event", None)
        await state.clear()


# --------------------------------------------------
# 5. VOICE HANDLER
# --------------------------------------------------
# --------------------------------------------------
# JOYLASHUV
# --------------------------------------------------
# Model tarixda AYNAN shuni ko'radi. Koordinata ATAYLAB yozilmaydi:
# u tarixda qolib, keyingi kunlarda «eng yaqin» savoliga ESKIRGAN joy
# bo'yicha javob berilishiga olib kelardi. Haqiqiy koordinata faqat
# RAM'dagi 30 daqiqalik yozuvdan olinadi (core/memory.py).
_LOCATION_NOTE = "📍 Joriy joylashuvimni yubordim."

# Ilgari lokatsiya "qo'llab-quvvatlanmagan tur" edi va bot unga
# «Joylashuv bilan ishlay olmayman» kartochkasi bilan javob berardi —
# model esa xuddi shu suhbatda «lokatsiyangizni yuborsangiz eng yaqin
# zapravkani topaman» deb VA'DA bergan bo'lardi. Ikkalasi ham tuzatildi:
# bu handler koordinatani eslab qoladi, `_capability_manifest()` esa
# joylashuv YO'Q paytda modelga uni so'rashni aytadi.
#
# ⚠️ BU YERDA AI CHAQIRILMAYDI. Lokatsiyaning o'zi savol emas — odam
# uni yuborib, keyin nima kerakligini yozadi. Shu bosqichda modelga
# so'rov yuborish bir raundni bekorga sarflardi.
async def handle_location(message: Message, state: FSMContext):
    chat_id = message.chat.id
    loc = message.location
    if loc is None:
        return
    track_user_activity(message.from_user.id,
                        message.from_user.username, "location_message")
    await check_and_clear_session(chat_id)
    remember_location(chat_id, loc.latitude, loc.longitude)
    chat_last_interaction[chat_id] = time.time()
    # ⚠️ JOYLASHUV SUHBATGA XABAR BO'LIB KIRADI, tayyor kartochka bilan
    # javob berilmaydi. Avval shunday edi va u JONLI XATO berdi: kartochka
    # tarixga tushmaydi, ya'ni model uchun ko'rinmas. Model ekranda
    # «lokatsiyangizni yuboring» degan o'z gapini, keyin «Zapravka» degan
    # javobni ko'rardi — joylashuv KELGANI haqida hech qanday belgi yo'q —
    # va yana «lokatsiyangizni yuboring» derdi. Cheksiz aylanma.
    #
    # Endi u oddiy matn yo'lidan o'tadi: kvota, navbat, oqim va tarix —
    # hammasi bir xil. Foyda ikkitomonlama: 1.5 soniyalik birlashtirish
    # oynasi tufayli «joylashuv + darhol yozilgan 'zapravka'» BITTA
    # so'rovga qo'shiladi, ya'ni javob ham bitta raundda keladi.
    await _queue_for_ai(chat_id, message, _LOCATION_NOTE, state)


async def handle_voice(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id

    track_user_activity(user_id, message.from_user.username, "voice_message")
    notify_watchers(user_id, message.from_user.username, "in", copy_chat_id=chat_id, copy_message_id=message.message_id)
    asyncio.create_task(process_daily_pin(message))

    await check_and_clear_session(chat_id)

    quota = await _check_quota(user_id, MESSAGE_COST_VOICE)
    if not quota["allowed"]:
        await _send_limit_reached_message(message, quota, feature="voice")
        return

    await state.set_state(GeneratingState.generating)

    voice_path = None
    generated_audio = None
    user_text = None

    try:
        await bot.send_chat_action(chat_id, "typing")
    except Exception:
        pass

    try:
        voice = message.voice
        file_id = voice.file_id
        file = await bot.get_file(file_id)
        voice_path = f"voice_{file_id}.ogg"
        await bot.download_file(file.file_path, voice_path)

        # Pro'da OpenAI transkripsiyasi (aniqroq), aks holda bepul yo'l.
        user_text = await speech_to_text_smart(voice_path, is_pro=_is_pro(quota))

        if not user_text:
            await message.answer("🤷‍♂️ Ovozni tushunib bo'lmadi.")
            await _refund_quota(user_id, MESSAGE_COST_VOICE, quota)
            return

        await message.reply(f"🗣 <b>Siz:</b> \"{user_text}\"", parse_mode="HTML")

        # CONCISE_INSTRUCTION bu yerga qo'shilmaydi —
        # get_openai_reply() ularni SYSTEM promptga o'zi qo'shadi (services/ai.py).
        output_files: list = []
        file_quota_box: list = []
        images: list = []
        stream_gen = get_gpt_reply(chat_id, user_text, user_id=user_id,
                                   output_files=output_files,
                                   file_quota_out=file_quota_box,
                                   images_out=images,
                                   is_pro=_is_pro(quota),
                                   tg_name=message.from_user.full_name)
        full_reply_text = await process_stream_draft(message, stream_gen,
                                                     content_type="voice", images=images)

        if output_files:
            await _send_output_files(chat_id, output_files)
        await _after_file_task(message, file_quota_box, bool(output_files))

        # Javob umuman chiqmadi — ovoz ham sintez qilinmaydi, ball
        # qaytariladi va shu yerda to'xtaymiz (bo'sh matnni TTS'ga
        # yuborish faqat keraksiz xato beradi).
        if not full_reply_text and not output_files:
            await _refund_quota(user_id, MESSAGE_COST_VOICE, quota)
            return

        if full_reply_text:
            notify_watchers(user_id, message.from_user.username, "out", text=full_reply_text)
            try:
                await safe_update_history(chat_id, user_text, role="user")
                await safe_update_history(chat_id, full_reply_text, role="assistant",
                                          images=images)
            except Exception as e:
                logger.warning(f"[Tarix saqlash xatosi - ovoz] chat={chat_id}: {e}")

        try:
            await bot.send_chat_action(chat_id, "record_voice")
        except Exception:
            pass

        audio_filename = f"reply_{chat_id}_{int(time.time())}.mp3"
        generated_audio = await text_to_speech_smart(
            full_reply_text, audio_filename, is_pro=_is_pro(quota))

        if generated_audio and os.path.exists(generated_audio):
            input_file = FSInputFile(generated_audio)
            await message.answer_voice(input_file)

    except Exception as e:
        logger.error(f"Voice error: {e}")
        if user_text:
            try:
                await send_error_with_retry(
                    chat_id=chat_id, message_id=message.message_id,
                    user_id=user_id, prompt=user_text,
                )
            except Exception:
                pass
        else:
            await message.answer("❌ Xatolik yuz berdi.")
        await _refund_quota(user_id, MESSAGE_COST_VOICE, quota)
    finally:
        try:
            if voice_path and os.path.exists(voice_path):
                os.remove(voice_path)
        except Exception as cleanup_err:
            logger.debug(f"voice_path tozalashda xatolik: {cleanup_err}")

        try:
            if generated_audio and os.path.exists(generated_audio):
                os.remove(generated_audio)
        except Exception as cleanup_err:
            logger.debug(f"generated_audio tozalashda xatolik: {cleanup_err}")

        await state.clear()
