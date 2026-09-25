"""Suhbat tarixi — PostgreSQL + RAM kesh.

⚠️ NEGA SQLite EMAS (bu fayl ilgari aiosqlite ishlatardi):
Railway'da konteyner fayl tizimi HAR DEPLOYDA tozalanadi. Ya'ni har bir
deploy barcha foydalanuvchilar uchun suhbat kontekstini nolga tushirardi —
foydalanuvchi tomonidan bu "bot meni unutdi" deb ko'rinadi. Bu ayniqsa Pro
foydalanuvchini tez yo'qotadi, chunki u aynan eslab qolish uchun to'lagan.

Postgres allaqachon ulangan va 150 xabar × foydalanuvchi u uchun hech narsa,
shuning uchun alohida Volume ham kerak emas — bitta kamroq harakatlanuvchi
qism.

⚠️ KALIT `chat_id` EMAS, `(chat_id, thread_id)`:
Telegram shaxsiy chatda ham "mavzu" (topic) ochishga ruxsat beradi va har
bir mavzu — AYRIM SUHBAT. Shuning uchun tarix, xulosa va kesh ikkalasi
bo'yicha kalitlanadi. `thread_id = 0` — mavzusiz chat, ya'ni topic rejimi
o'chiq bo'lgandagi bugungi xatti-harakat. Barcha funksiyalarda u
STANDART qiymat, shuning uchun eski chaqiruvlar o'zgarishsiz ishlaydi.
"""
import asyncio
import logging
from typing import List, Dict, Optional, Tuple

from db import database

logger = logging.getLogger(__name__)

# --------------------------------------------------
# KONFIGURATSIYA
# --------------------------------------------------
try:
    from core.config import (SYSTEM_PROMPT, CONTEXT_WINDOW, CONTEXT_WINDOW_PRO,
                             HISTORY_SUMMARY_BATCH, HISTORY_HARD_LIMIT,
                             HISTORY_LONG_WARN_AT)
except ImportError:
    SYSTEM_PROMPT = "Siz foydali yordamchisiz."
    CONTEXT_WINDOW = 12
    CONTEXT_WINDOW_PRO = 24
    HISTORY_SUMMARY_BATCH = 20
    HISTORY_HARD_LIMIT = 200
    HISTORY_LONG_WARN_AT = 120

# SAQLASH chegarasi — hamma uchun eng katta oyna bo'yicha. O'QISH chegarasi
# esa chaqiruvchi beradigan `limit` (tarifga qarab). Ikkovini ajratmasak,
# Pro'ning uzun xotirasi jimgina ishlamay qolardi: kesh va baza baribir
# 50 tadan keyingisini o'chirib tashlagan bo'lardi.
_STORE_LIMIT = max(CONTEXT_WINDOW, CONTEXT_WINDOW_PRO)

# Kalit — (chat_id, thread_id) juftligi. Faqat chat_id bo'lsa bitta
# chatdagi ikki mavzu bir-birining tarixini ustiga yozardi.
Key = Tuple[int, int]

_cache: Dict[Key, List[Dict]] = {}

# Xulosa yozish bitta suhbat uchun bir vaqtda BITTA marta ishlasin. Ikkita
# xabar ketma-ket kelsa, ikkala vazifa ham o'sha 20 ta qatorni o'qib,
# ikkitasi ham xulosaga qo'shardi — natijada takror ma'lumot va ikki
# barobar chaqiruv. (core/memory.py dagi debounce bilan bir xil naqsh.)
_summary_locks: Dict[Key, asyncio.Lock] = {}
_summary_cache: Dict[Key, str] = {}

# "Bu suhbat uzayib ketdi" ogohlantirishi — bir marta beriladi. Fon
# vazifasi (`_compress_old`) uni shu yerga qo'yadi, handler esa javobni
# yuborgandan keyin `take_long_warning()` bilan olib ketadi. Shu tarzda
# ogohlantirish uchun QO'SHIMCHA SO'ROV kerak emas: `covered` allaqachon
# siqish paytida o'qiladi.
_long_warn: set = set()


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
        # Oynadan chiqqan xabarlarning siqilgan shakli — har suhbatga
        # bitta qator. Ilgari u qism shunchaki o'chirilardi.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_summaries (
                chat_id    BIGINT PRIMARY KEY,
                summary    TEXT   NOT NULL,
                covered    INT    NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # ── MAVZU (topic) MIGRATSIYASI ───────────────────────────────
        # Mavjud qatorlar 0 oladi, ya'ni ular "mavzusiz suhbat" bo'lib
        # qoladi — hech kim hech narsa yo'qotmaydi.
        await conn.execute("ALTER TABLE chat_messages "
                           "ADD COLUMN IF NOT EXISTS thread_id BIGINT NOT NULL DEFAULT 0")
        await conn.execute("ALTER TABLE chat_summaries "
                           "ADD COLUMN IF NOT EXISTS thread_id BIGINT NOT NULL DEFAULT 0")

        # ⚠️ chat_summaries ning PRIMARY KEY'i `chat_id` edi. `ON CONFLICT
        # (chat_id, thread_id)` ishlashi uchun u JUFTLIKKA aylanishi shart,
        # aks holda bir chatdagi ikkinchi mavzu birinchisining xulosasini
        # ustiga yozardi. init_db() har ishga tushishda chaqirilgani uchun
        # bu blok idempotent: kalit allaqachon 2 ustunli bo'lsa tegilmaydi.
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_index i
                    JOIN pg_class c ON c.oid = i.indrelid
                    WHERE c.relname = 'chat_summaries'
                      AND i.indisprimary AND i.indnatts = 2
                ) THEN
                    ALTER TABLE chat_summaries DROP CONSTRAINT IF EXISTS chat_summaries_pkey;
                    ALTER TABLE chat_summaries ADD PRIMARY KEY (chat_id, thread_id);
                END IF;
            END $$;
        """)

        # Indeks ham juftlik bo'yicha — aks holda har o'qishda bitta
        # chatning BARCHA mavzulari skanerlanardi.
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_thread "
            "ON chat_messages (chat_id, thread_id, id)"
        )
        # Eski bir ustunli indeks endi keraksiz — yangisi uning o'rnini
        # to'liq bosadi (chat_id prefiks bo'lib qolyapti).
        await conn.execute("DROP INDEX IF EXISTS idx_chat_messages_chat")


# --------------------------------------------------
# XABAR QO'SHISH
# --------------------------------------------------
async def update_chat_history(chat_id: int, content: str, role: str = "user",
                              thread_id: int = 0) -> int:
    """Xabarni keshga va bazaga yozadi, eskisini qirqadi.

    Shu suhbatdagi JAMI qator sonini qaytaradi. Son baribir hisoblanardi
    (qirqish chegaralari uchun), chaqiruvchi esa undan «bu suhbatning
    boshimi?» degan savolga javob oladi — mavzuga nom qo'yish aynan
    shunga qarab ishlaydi. Qo'shimcha so'rov yo'q.
    """
    key = (chat_id, thread_id)
    if key not in _cache:
        _cache[key] = await _load_from_db(chat_id, thread_id=thread_id)

    _cache[key].append({"role": role, "content": content})

    if len(_cache[key]) > _STORE_LIMIT:
        _cache[key] = _cache[key][-_STORE_LIMIT:]

    pool = await _pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_messages (chat_id, thread_id, role, content) "
            "VALUES ($1, $2, $3, $4)",
            chat_id, thread_id, role, content,
        )
        jami = await conn.fetchval(
            "SELECT COUNT(*) FROM chat_messages "
            "WHERE chat_id = $1 AND thread_id = $2", chat_id, thread_id)

    # ⛔️ OXIRGI HIMOYA. Xulosa yozish uzoq vaqt ishlamay qolsa (model
    # yo'q, kvota tugagan) jadval cheksiz o'smasin. Bu yerda eski
    # xatti-harakat qaytadi: eskisi xulosasiz o'chadi. Ma'lumot
    # yo'qoladi, lekin faqat allaqachon buzilgan holatda.
    if jami > HISTORY_HARD_LIMIT:
        logger.warning(
            f"[XOTIRA] chat={chat_id} mavzu={thread_id}: {jami} qator — "
            f"qattiq chegaradan oshdi, xulosasiz qirqilmoqda "
            f"(xulosa yozuvchi ishlamayaptimi?)")
        await _hard_trim(chat_id, thread_id)
        return jami

    # Siqish faqat to'plam yig'ilganda: 81-chi xabardan boshlab HAR
    # safar model chaqirilsa, bu bitta xabarning narxini ikki barobar
    # qilardi. Fon vazifasi — foydalanuvchi javobini kutib turmasin.
    if jami >= _STORE_LIMIT + HISTORY_SUMMARY_BATCH:
        asyncio.create_task(_compress_old(chat_id, thread_id))

    return jami


async def _hard_trim(chat_id: int, thread_id: int = 0) -> None:
    """Xulosasiz qirqish — eski xatti-harakat, faqat zaxira yo'l sifatida."""
    pool = await _pool()
    async with pool.acquire() as conn:
        # `id <` shakli ataylab: (chat_id, thread_id, id) indeksidan
        # to'g'ridan-to'g'ri foydalanadi, NOT IN esa har safar butun
        # ro'yxatni qayta o'qirdi.
        await conn.execute("""
            DELETE FROM chat_messages
            WHERE chat_id = $1 AND thread_id = $2 AND id < (
                SELECT MIN(id) FROM (
                    SELECT id FROM chat_messages
                    WHERE chat_id = $1 AND thread_id = $2
                    ORDER BY id DESC LIMIT $3
                ) AS keep
            )
        """, chat_id, thread_id, _STORE_LIMIT)


async def _compress_old(chat_id: int, thread_id: int = 0) -> None:
    """Oynadan chiqqan eng eski xabarlarni xulosaga qo'shib, o'chiradi.

    ⚠️ TARTIB MUHIM VA U MA'LUMOT YO'QOTMASLIK UCHUN: avval xulosa
    OLINADI, keyin saqlanadi, va FAQAT shundan keyin xom qatorlar
    o'chiriladi. Xulosa chiqmasa — hech narsa o'chirilmaydi va
    xabarlar joyida qoladi (keyingi xabarda qayta uriniladi).

    Teskari tartibda yozilsa, tuzatishning o'zi biz tuzatayotgan
    nosozlikni takrorlardi: suhbat boshi jimgina yo'qolardi.
    """
    key = (chat_id, thread_id)
    lock = _summary_locks.setdefault(key, asyncio.Lock())
    if lock.locked():
        return                      # allaqachon ishlayapti
    async with lock:
        pool = await _pool()
        async with pool.acquire() as conn:
            # Oynadan TASHQARIDAGI eng eski qatorlar.
            rows = await conn.fetch("""
                SELECT id, role, content FROM chat_messages
                WHERE chat_id = $1 AND thread_id = $2 AND id < (
                    SELECT MIN(id) FROM (
                        SELECT id FROM chat_messages
                        WHERE chat_id = $1 AND thread_id = $2
                        ORDER BY id DESC LIMIT $3
                    ) AS keep
                )
                ORDER BY id LIMIT $4
            """, chat_id, thread_id, _STORE_LIMIT, HISTORY_SUMMARY_BATCH)
            if not rows:
                return
            avvalgi = await conn.fetchrow(
                "SELECT summary, covered FROM chat_summaries "
                "WHERE chat_id = $1 AND thread_id = $2", chat_id, thread_id)
        eski = (avvalgi["summary"] if avvalgi else "") or ""
        eski_covered = (avvalgi["covered"] if avvalgi else 0) or 0

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
                    INSERT INTO chat_summaries
                        (chat_id, thread_id, summary, covered, updated_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (chat_id, thread_id) DO UPDATE
                    SET summary = $3,
                        covered = chat_summaries.covered + $4,
                        updated_at = NOW()
                """, chat_id, thread_id, yangi, len(rows))
                await conn.execute(
                    "DELETE FROM chat_messages "
                    "WHERE chat_id = $1 AND thread_id = $2 AND id <= $3",
                    chat_id, thread_id, oxirgi_id)
        _summary_cache[key] = yangi

        # Suhbat uzayib ketdi — chegarani AYNAN SHU siqishda kesib
        # o'tgan bo'lsa bir marta belgilab qo'yamiz. `covered` faqat
        # o'sadi (xom qatorlar soni esa siqilgach qaytib tushadi),
        # shuning uchun "uzun suhbat" o'lchovi aynan shu.
        covered = eski_covered + len(rows)
        if eski_covered < HISTORY_LONG_WARN_AT <= covered:
            _long_warn.add(key)

        logger.info(f"[XOTIRA] chat={chat_id} mavzu={thread_id}: "
                    f"{len(rows)} xabar xulosaga siqildi "
                    f"({len(yangi)} belgi, jami siqilgan {covered})")


def take_long_warning(chat_id: int, thread_id: int = 0) -> bool:
    """«Suhbat uzayib ketdi» ogohlantirishini bir marta beradi.

    RAMdan o'qiydi — javob yuborilgandan keyin har safar chaqiriladi,
    shuning uchun bu yerda baza so'rovi bo'lmasligi SHART.
    """
    key = (chat_id, thread_id)
    if key in _long_warn:
        _long_warn.discard(key)
        return True
    return False


async def get_chat_summary(chat_id: int, thread_id: int = 0) -> str:
    """Oynadan chiqqan qismning siqilgan shakli (bo'lmasa — bo'sh satr)."""
    key = (chat_id, thread_id)
    if key in _summary_cache:
        return _summary_cache[key]
    pool = await _pool()
    async with pool.acquire() as conn:
        matn = await conn.fetchval(
            "SELECT summary FROM chat_summaries "
            "WHERE chat_id = $1 AND thread_id = $2", chat_id, thread_id)
    _summary_cache[key] = matn or ""
    return _summary_cache[key]


# --------------------------------------------------
# TARIX OLISH
# --------------------------------------------------
async def get_chat_history(chat_id: int, limit: int = CONTEXT_WINDOW,
                           thread_id: int = 0) -> List[Dict]:
    """Keshdan yoki bazadan tarixni qaytaradi. system prompt qo'shilmaydi."""
    key = (chat_id, thread_id)
    if key in _cache:
        return _cache[key][-limit:]

    # Keshga HAR DOIM to'liq saqlash oynasi yuklanadi: aks holda free
    # foydalanuvchi Pro'ga o'tganda kesh 50 tada qotib qolar va u
    # to'lagan uzun xotira faqat bot qayta ishga tushgach ochilardi.
    history = await _load_from_db(chat_id, _STORE_LIMIT, thread_id)
    _cache[key] = history
    return history[-limit:]


async def _load_from_db(chat_id: int, limit: int = _STORE_LIMIT,
                        thread_id: int = 0) -> List[Dict]:
    """Bazadan so'nggi `limit` ta xabarni yuklaydi."""
    pool = await _pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content FROM chat_messages
               WHERE chat_id = $1 AND thread_id = $2
               ORDER BY id DESC LIMIT $3""",
            chat_id, thread_id, limit,
        )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# --------------------------------------------------
# TARIXNI TOZALASH
# --------------------------------------------------
async def clear_history(chat_id: int, thread_id: Optional[int] = 0):
    """Kesh va bazadan suhbat tarixini to'liq o'chiradi.

    `thread_id=None` — CHATDAGI BARCHA MAVZULAR. Bu faqat foydalanuvchini
    butunlay tozalash uchun; `/new` esa aynan o'zi bosilgan mavzuni
    o'chiradi, aks holda bitta mavzuni yangilamoqchi bo'lgan odam
    qolganlarini ham yo'qotardi.

    ⚠️ XULOSA HAM O'CHADI. Busiz `/new` foydalanuvchiga YOLG'ON aytgan
    bo'lardi: u "tarix tozalandi" degan xabarni ko'radi, bot esa eski
    suhbatning siqilgan shaklini saqlab qolib, keyingi javobda uni
    ishlatishda davom etardi. O'chirish — o'chirish degani.

    ⛔️ "Barcha mavzular" — faqat foydalanuvchining O'Z suhbatlari
    (`thread_id >= 0`). Manfiy `thread_id` — Telegram Business: `chat_id`
    o'sha odam, lekin suhbat boshqa EGANIKI (`thread_id = -owner_id`).
    Uni o'chirish begona egalarning tarixini o'chirish bo'lardi (AUDIT S3).
    """
    if thread_id is None:
        for d in (_cache, _summary_cache):
            for k in [k for k in d if k[0] == chat_id and k[1] >= 0]:
                d.pop(k, None)
        for k in [k for k in _long_warn if k[0] == chat_id and k[1] >= 0]:
            _long_warn.discard(k)
        shart, args = "chat_id = $1 AND thread_id >= 0", (chat_id,)
    else:
        key = (chat_id, thread_id)
        _cache.pop(key, None)
        _summary_cache.pop(key, None)
        _long_warn.discard(key)
        shart, args = "chat_id = $1 AND thread_id = $2", (chat_id, thread_id)

    pool = await _pool()
    async with pool.acquire() as conn:
        await conn.execute(f"DELETE FROM chat_messages WHERE {shart}", *args)
        await conn.execute(f"DELETE FROM chat_summaries WHERE {shart}", *args)

