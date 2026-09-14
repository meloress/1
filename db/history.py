"""Suhbat tarixi — PostgreSQL + RAM kesh.

⚠️ NEGA SQLite EMAS (bu fayl ilgari aiosqlite ishlatardi):
Railway'da konteyner fayl tizimi HAR DEPLOYDA tozalanadi. Ya'ni har bir
deploy barcha foydalanuvchilar uchun suhbat kontekstini nolga tushirardi —
foydalanuvchi tomonidan bu "bot meni unutdi" deb ko'rinadi. Bu ayniqsa Pro
foydalanuvchini tez yo'qotadi, chunki u aynan eslab qolish uchun to'lagan.

Postgres allaqachon ulangan va 150 xabar × foydalanuvchi u uchun hech narsa,
shuning uchun alohida Volume ham kerak emas — bitta kamroq harakatlanuvchi
qism.
"""
import asyncio
import logging
from typing import List, Dict

from db import database

logger = logging.getLogger(__name__)

# --------------------------------------------------
# KONFIGURATSIYA
# --------------------------------------------------
try:
    from core.config import (SYSTEM_PROMPT, CONTEXT_WINDOW, CONTEXT_WINDOW_PRO,
                             HISTORY_SUMMARY_BATCH, HISTORY_HARD_LIMIT)
except ImportError:
    SYSTEM_PROMPT = "Siz foydali yordamchisiz."
    CONTEXT_WINDOW = 12
    CONTEXT_WINDOW_PRO = 24
    HISTORY_SUMMARY_BATCH = 20
    HISTORY_HARD_LIMIT = 200

# SAQLASH chegarasi — hamma uchun eng katta oyna bo'yicha. O'QISH chegarasi
# esa chaqiruvchi beradigan `limit` (tarifga qarab). Ikkovini ajratmasak,
# Pro'ning uzun xotirasi jimgina ishlamay qolardi: kesh va baza baribir
# 50 tadan keyingisini o'chirib tashlagan bo'lardi.
_STORE_LIMIT = max(CONTEXT_WINDOW, CONTEXT_WINDOW_PRO)

_cache: Dict[int, List[Dict]] = {}

# Xulosa yozish bitta chat uchun bir vaqtda BITTA marta ishlasin. Ikkita
# xabar ketma-ket kelsa, ikkala vazifa ham o'sha 20 ta qatorni o'qib,
# ikkitasi ham xulosaga qo'shardi — natijada takror ma'lumot va ikki
# barobar chaqiruv. (core/memory.py dagi debounce bilan bir xil naqsh.)
_summary_locks: Dict[int, asyncio.Lock] = {}
_summary_cache: Dict[int, str] = {}


async def _pool():
    """Umumiy asyncpg hovuzi. `database` MODULI import qilinadi (undagi
    `pool` nomi emas) — aks holda create_db_pool() dan keyin bu yerda
    eski None qiymat qolib ketardi."""
    if database.pool is None:
        await database.create_db_pool()
    return database.pool


# --------------------------------------------------
# DB INITSIALIZATSIYA — main.py da bir marta chaqiriladi
# --------------------------------------------------
async def init_db():
    """Jadval va indeksni yaratadi (agar yo'q bo'lsa)."""
    pool = await _pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id         BIGSERIAL PRIMARY KEY,
                chat_id    BIGINT NOT NULL,
                role       TEXT   NOT NULL,
                content    TEXT   NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_chat "
            "ON chat_messages (chat_id, id)"
        )
        # Oynadan chiqqan xabarlarning siqilgan shakli — har chatga bitta
        # qator. Ilgari u qism shunchaki o'chirilardi.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_summaries (
                chat_id    BIGINT PRIMARY KEY,
                summary    TEXT   NOT NULL,
                covered    INT    NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)


# --------------------------------------------------
# XABAR QO'SHISH
# --------------------------------------------------
async def update_chat_history(chat_id: int, content: str, role: str = "user"):
    """Xabarni keshga va bazaga yozadi, eskisini qirqadi."""
    if chat_id not in _cache:
        _cache[chat_id] = await _load_from_db(chat_id)

    _cache[chat_id].append({"role": role, "content": content})

    if len(_cache[chat_id]) > _STORE_LIMIT:
        _cache[chat_id] = _cache[chat_id][-_STORE_LIMIT:]

    pool = await _pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_messages (chat_id, role, content) VALUES ($1, $2, $3)",
            chat_id, role, content,
        )
        jami = await conn.fetchval(
            "SELECT COUNT(*) FROM chat_messages WHERE chat_id = $1", chat_id)

    # ⛔️ OXIRGI HIMOYA. Xulosa yozish uzoq vaqt ishlamay qolsa (model
    # yo'q, kvota tugagan) jadval cheksiz o'smasin. Bu yerda eski
    # xatti-harakat qaytadi: eskisi xulosasiz o'chadi. Ma'lumot
    # yo'qoladi, lekin faqat allaqachon buzilgan holatda.
    if jami > HISTORY_HARD_LIMIT:
        logger.warning(
            f"[XOTIRA] chat={chat_id}: {jami} qator — qattiq chegaradan "
            f"oshdi, xulosasiz qirqilmoqda (xulosa yozuvchi ishlamayaptimi?)")
        await _hard_trim(chat_id)
        return

    # Siqish faqat to'plam yig'ilganda: 81-chi xabardan boshlab HAR
    # safar model chaqirilsa, bu bitta xabarning narxini ikki barobar
    # qilardi. Fon vazifasi — foydalanuvchi javobini kutib turmasin.
    if jami >= _STORE_LIMIT + HISTORY_SUMMARY_BATCH:
        asyncio.create_task(_compress_old(chat_id))


async def _hard_trim(chat_id: int) -> None:
    """Xulosasiz qirqish — eski xatti-harakat, faqat zaxira yo'l sifatida."""
    pool = await _pool()
    async with pool.acquire() as conn:
        # `id <` shakli ataylab: (chat_id, id) indeksidan to'g'ridan-to'g'ri
        # foydalanadi, NOT IN esa har safar butun ro'yxatni qayta o'qirdi.
        await conn.execute("""
            DELETE FROM chat_messages
            WHERE chat_id = $1 AND id < (
                SELECT MIN(id) FROM (
                    SELECT id FROM chat_messages
                    WHERE chat_id = $1 ORDER BY id DESC LIMIT $2
                ) AS keep
            )
        """, chat_id, _STORE_LIMIT)


async def _compress_old(chat_id: int) -> None:
    """Oynadan chiqqan eng eski xabarlarni xulosaga qo'shib, o'chiradi.

    ⚠️ TARTIB MUHIM VA U MA'LUMOT YO'QOTMASLIK UCHUN: avval xulosa
    OLINADI, keyin saqlanadi, va FAQAT shundan keyin xom qatorlar
    o'chiriladi. Xulosa chiqmasa — hech narsa o'chirilmaydi va
    xabarlar joyida qoladi (keyingi xabarda qayta uriniladi).

    Teskari tartibda yozilsa, tuzatishning o'zi biz tuzatayotgan
    nosozlikni takrorlardi: suhbat boshi jimgina yo'qolardi.
    """
    lock = _summary_locks.setdefault(chat_id, asyncio.Lock())
    if lock.locked():
        return                      # allaqachon ishlayapti
    async with lock:
        pool = await _pool()
        async with pool.acquire() as conn:
            # Oynadan TASHQARIDAGI eng eski qatorlar.
            rows = await conn.fetch("""
                SELECT id, role, content FROM chat_messages
                WHERE chat_id = $1 AND id < (
                    SELECT MIN(id) FROM (
                        SELECT id FROM chat_messages
                        WHERE chat_id = $1 ORDER BY id DESC LIMIT $2
                    ) AS keep
                )
                ORDER BY id LIMIT $3
            """, chat_id, _STORE_LIMIT, HISTORY_SUMMARY_BATCH)
            if not rows:
                return
            eski = await conn.fetchval(
                "SELECT summary FROM chat_summaries WHERE chat_id = $1",
                chat_id) or ""

        # ⚠️ Kech import: services.ai ning o'zi db.history dan o'qiydi,
        # modul boshida import qilinsa halqa hosil bo'lardi.
        from services.ai import summarize_history_chunk
        yangi = await summarize_history_chunk(
            eski, [{"role": r["role"], "content": r["content"]} for r in rows])

        if not yangi:
            # Xulosa chiqmadi — XABARLAR QOLADI. Keyingi xabarda qayta
            # uriniladi, qattiq chegara esa cheksiz o'sishdan saqlaydi.
            return

        oxirgi_id = rows[-1]["id"]
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO chat_summaries (chat_id, summary, covered, updated_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (chat_id) DO UPDATE
                    SET summary = $2,
                        covered = chat_summaries.covered + $3,
                        updated_at = NOW()
                """, chat_id, yangi, len(rows))
                await conn.execute(
                    "DELETE FROM chat_messages WHERE chat_id = $1 AND id <= $2",
                    chat_id, oxirgi_id)
        _summary_cache[chat_id] = yangi
        logger.info(f"[XOTIRA] chat={chat_id}: {len(rows)} xabar xulosaga "
                    f"siqildi ({len(yangi)} belgi)")


async def get_chat_summary(chat_id: int) -> str:
    """Oynadan chiqqan qismning siqilgan shakli (bo'lmasa — bo'sh satr)."""
    if chat_id in _summary_cache:
        return _summary_cache[chat_id]
    pool = await _pool()
    async with pool.acquire() as conn:
        matn = await conn.fetchval(
            "SELECT summary FROM chat_summaries WHERE chat_id = $1", chat_id)
    _summary_cache[chat_id] = matn or ""
    return _summary_cache[chat_id]


# --------------------------------------------------
# TARIX OLISH
# --------------------------------------------------
async def get_chat_history(chat_id: int, limit: int = CONTEXT_WINDOW) -> List[Dict]:
    """Keshdan yoki bazadan tarixni qaytaradi. system prompt qo'shilmaydi."""
    if chat_id in _cache:
        return _cache[chat_id][-limit:]

    # Keshga HAR DOIM to'liq saqlash oynasi yuklanadi: aks holda free
    # foydalanuvchi Pro'ga o'tganda kesh 50 tada qotib qolar va u
    # to'lagan uzun xotira faqat bot qayta ishga tushgach ochilardi.
    history = await _load_from_db(chat_id, _STORE_LIMIT)
    _cache[chat_id] = history
    return history[-limit:]


async def _load_from_db(chat_id: int, limit: int = _STORE_LIMIT) -> List[Dict]:
    """Bazadan so'nggi `limit` ta xabarni yuklaydi."""
    pool = await _pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content FROM chat_messages
               WHERE chat_id = $1
               ORDER BY id DESC LIMIT $2""",
            chat_id, limit,
        )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# --------------------------------------------------
# TARIXNI TOZALASH
# --------------------------------------------------
async def clear_history(chat_id: int):
    """Kesh va bazadan chat tarixini to'liq o'chiradi.

    ⚠️ XULOSA HAM O'CHADI. Busiz `/new` foydalanuvchiga YOLG'ON aytgan
    bo'lardi: u "tarix tozalandi" degan xabarni ko'radi, bot esa eski
    suhbatning siqilgan shaklini saqlab qolib, keyingi javobda uni
    ishlatishda davom etardi. O'chirish — o'chirish degani.
    """
    _cache.pop(chat_id, None)
    _summary_cache.pop(chat_id, None)
    pool = await _pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM chat_messages WHERE chat_id = $1", chat_id)
        await conn.execute("DELETE FROM chat_summaries WHERE chat_id = $1", chat_id)


async def clear_user_history(chat_id: int):
    await clear_history(chat_id)
