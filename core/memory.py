import time
import asyncio
from typing import Dict, Any, List

FAILED_REQUEST_TTL   = 3600
USER_ACTION_TTL      = 86400
ONGOING_TTL          = 120
CLEANUP_INTERVAL     = 300
# Xavfsizlik to'ri: taymer biror sababdan ishlamay qolsa. ⚠️ 30s dan
# oshirildi: bufer endi NAVBAT sifatida ham ishlatiladi (busy_handler),
# ya'ni javob generatsiyasi tugaguncha — bir necha daqiqagacha — taymersiz
# turishi mumkin. 30s da tozalash aynan navbatdagi xabarni yo'qotardi.
TEXT_MERGE_BUFFER_TTL = 600

failed_requests:      Dict[int, Dict[str, Any]] = {}
ongoing_requests:     Dict[int, float]           = {}
user_last_action_ts:  Dict[int, float]           = {}

# --------------------------------------------------
# TEXT MERGE BUFFER
# --------------------------------------------------
# Telegram uzun xabarni (>4096 belgi) bir necha qismga bo'lib yuboradi.
# Bu bufer o'sha qismlarni chat_id bo'yicha yig'ib turadi va ular BITTA
# so'rov sifatida qayta ishlanishini ta'minlaydi (handlers/messages.py
# ichidagi handle_text / _process_merged_text bilan birga ishlaydi).
#
# Struktura (har bir chat_id uchun):
# {
#     "parts":      List[str]       — kelgan xabar qismlari, tartib bilan
#     "last_message": aiogram.types.Message — javob shu xabarga bog'lanadi
#     "timer_task": asyncio.Task    — "davomi kelmasa, qayta ishla" taymeri
#     "created_at": float           — birinchi qism kelgan vaqt (TTL uchun)
# }
text_merge_buffers: Dict[int, Dict[str, Any]] = {}
text_merge_locks:   Dict[int, asyncio.Lock]    = {}


# Shu suhbatda ALLAQACHON yuborilgan rasm havolalari (chat_id -> URL'lar).
#
# ⚠️ NEGA KERAK: foydalanuvchi «tuning qilingani-chi?» deb qayta-qayta
# so'raganda bot har safar O'SHA to'rt rasmni qaytarardi. Sabab qidiruvda
# edi, lekin ikkinchi qatlam ham shart: qidiruv baribir o'sha natijani
# bersa, kamida TAKRORLAMASIN — yangi rasm topilmasa rostini aytgani
# yaxshiroq.
#
# RAM'da: bu suhbat davomidagi holat, bazaga yozishga arzimaydi.
# /new bilan va chegaradan oshganda tozalanadi.
SENT_IMAGES_KEEP = 24
sent_image_urls: Dict[int, List[str]] = {}


def remember_sent_images(chat_id: int, images: List[dict]) -> None:
    """Yuborilgan rasm havolalarini eslab qoladi."""
    if not images:
        return
    ro_yxat = sent_image_urls.setdefault(chat_id, [])
    for img in images:
        url = (img or {}).get("url")
        if url and url not in ro_yxat:
            ro_yxat.append(url)
    if len(ro_yxat) > SENT_IMAGES_KEEP:
        del ro_yxat[:-SENT_IMAGES_KEEP]


def recent_sent_images(chat_id: int) -> set:
    """Qidiruvdan chiqarib tashlanadigan havolalar."""
    return set(sent_image_urls.get(chat_id) or ())


def forget_sent_images(chat_id: int) -> None:
    """/new — suhbat tozalansa rasm tarixi ham tozalanadi."""
    sent_image_urls.pop(chat_id, None)


# --------------------------------------------------
# OXIRGI JOYLASHUV (chat_id -> (lat, lon, vaqt))
# --------------------------------------------------
# Foydalanuvchi yuborgan lokatsiya. `find_nearby` tooli AYNAN shu
# yozuv borligiga qarab biriktiriladi — ya'ni oddiy suhbatda tool
# sxemasi umuman yuborilmaydi va bironta token sarflanmaydi.
#
# ⚠️ TTL QISQA (30 daqiqa) va bu ATAYLAB: odam mashinada ketyapti,
# yarim soatdan keyin u allaqachon boshqa joyda bo'ladi. Eskirgan
# koordinata bo'yicha «eng yaqin zapravka» aytish — noto'g'ri javobni
# ishonch bilan aytish, ya'ni umuman javob bermaslikdan yomonroq.
#
# RAM'da: rasm tarixi bilan bir xil sabab — bu suhbat holati, bazaga
# yozishga arzimaydi va qayta ishga tushganda eskirgani ham yaxshi.
LOCATION_TTL = 1800
last_locations: Dict[int, tuple] = {}


def remember_location(chat_id: int, lat: float, lon: float) -> None:
    """Foydalanuvchi yuborgan joylashuvni eslab qoladi."""
    last_locations[chat_id] = (float(lat), float(lon), time.time())


def recent_location(chat_id: int):
    """(lat, lon) yoki None — TTL o'tgan bo'lsa None."""
    yozuv = last_locations.get(chat_id)
    if not yozuv:
        return None
    lat, lon, ts = yozuv
    if time.time() - ts > LOCATION_TTL:
        last_locations.pop(chat_id, None)
        return None
    return lat, lon


def forget_location(chat_id: int) -> None:
    """/new — suhbat tozalansa joylashuv ham unutiladi."""
    last_locations.pop(chat_id, None)


def get_text_merge_lock(chat_id: int) -> asyncio.Lock:
    """Har bir chat uchun alohida asyncio.Lock qaytaradi.

    aiogram har bir kelgan update uchun handlerni alohida Task sifatida
    ishga tushiradi, ya'ni bir foydalanuvchidan ketma-ket kelgan 2-3 ta
    xabar handle_text() ichida DEYARLI bir vaqtda (parallel) ishlanishi
    mumkin. Lock shu poyga holatini (race condition) oldini oladi —
    bufer bir vaqtning o'zida faqat bitta coroutine tomonidan
    o'zgartirilishini kafolatlaydi.
    """
    lock = text_merge_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        text_merge_locks[chat_id] = lock
    return lock


def clear_text_merge_buffer(chat_id: int):
    """Chat uchun bufer va taymerni butunlay bekor qiladi (masalan /new
    buyrug'i kelganda yoki muvaffaqiyatli qayta ishlangandan keyin)."""
    buf = text_merge_buffers.pop(chat_id, None)
    if buf:
        timer_task = buf.get("timer_task")
        if timer_task and not timer_task.done():
            timer_task.cancel()

def store_failed_request(chat_id: int, user_id: int, prompt: str,
                         original_text: str, error_message_id: int):
    failed_requests[chat_id] = {
        "user_id":         user_id,
        "prompt":          prompt,
        "original_text":   original_text,
        "attempts_manual": 0,
        "attempts_auto":   0,
        "error_message_id": error_message_id,
        "last_attempt_ts": None,
        "stored_at":       time.time(),   
    }

def clear_failed_request(chat_id: int):
    failed_requests.pop(chat_id, None)
    ongoing_requests.pop(chat_id, None)

def set_ongoing(chat_id: int):
    """bool emas, timestamp saqlaydi — crash bo'lsa ONGOING_TTL dan keyin avtomatik ochiladi."""
    ongoing_requests[chat_id] = time.time()

def is_ongoing(chat_id: int) -> bool:
    """Jarayon ketayotganini tekshiradi. Agar ONGOING_TTL o'tib ketgan bo'lsa — crash deb hisoblab tozalaydi."""
    ts = ongoing_requests.get(chat_id)
    if ts is None:
        return False
    if time.time() - ts > ONGOING_TTL:
        ongoing_requests.pop(chat_id, None)
        return False
    return True

def release_ongoing(chat_id: int):
    ongoing_requests.pop(chat_id, None)

def cleanup_expired():
    """Muddati o'tgan barcha yozuvlarni xotiradan o'chiradi."""
    now = time.time()

    for cid in [c for c, v in failed_requests.items()
                if now - (v.get("stored_at") or now) > FAILED_REQUEST_TTL]:
        failed_requests.pop(cid, None)

    for uid in [u for u, ts in user_last_action_ts.items()
                if now - ts > USER_ACTION_TTL]:
        user_last_action_ts.pop(uid, None)

    for cid in [c for c, ts in ongoing_requests.items()
                if now - ts > ONGOING_TTL]:
        ongoing_requests.pop(cid, None)

    # Xavfsizlik to'ri: agar biror sababdan (masalan kutilmagan xatolik
    # yoki process qayta ishga tushishi) timer_task bekor qilinmay
    # qolgan bo'lsa, TTL dan keyin buferni majburan tozalaymiz — aks
    # holda foydalanuvchining xabari abadiy javobsiz qolib ketishi mumkin.
    for cid in [c for c, v in text_merge_buffers.items()
                if now - v.get("created_at", now) > TEXT_MERGE_BUFFER_TTL]:
        clear_text_merge_buffer(cid)

async def start_cleanup_task():
    """main.py da bir marta chaqiriladi. Har CLEANUP_INTERVAL soniyada tozalaydi."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        cleanup_expired()
