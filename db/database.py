import os
import asyncio
import json
import time
import logging
import re
from functools import wraps

import asyncpg
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from core.config import (
    GPT_MODEL_DISPLAY_NAME, DAILY_FREE_LIMIT, DAILY_FILE_LIMIT_FREE,
    plan_limits, daily_limit, DAILY_COUNTERS,
    MAX_ACTIVE_REMINDERS, REMINDER_MAX_LEN, REMINDER_REPEATS,
    REMINDER_MAX_AHEAD_DAYS,
    REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS, REFERRAL_MAX_REWARDS,
    INACTIVE_STEPS, ACTIVITY_TYPES,
    BIZNES_BILIM_MAX, BIZNES_REJIMLAR, BIZNES_LOYIHA_TTL_SOAT,
    BIZNES_NAMUNA_MAX, BIZNES_NAMUNA_KORSAT, BIZNES_TAHRIR_KORSAT,
    BIZNES_USLUB_MAX,
)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

logger = logging.getLogger(__name__)

pool: Optional[asyncpg.pool.Pool] = None
_pool_lock = asyncio.Lock()

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

# Kuzatuv (watch) keshi — asosiy xabar oqimidan har xabarda sinxron
# tekshiriladi, shuning uchun DB so'rovisiz, oddiy dict/set qarash bo'lishi
# shart (load_watch_cache() orqali ishga tushganda to'ldiriladi).
_watch_group_id: Optional[int] = None
_watched_user_ids: set = set()

# Ba'zi provayderlar (Neon, Supabase, Railway va h.k.) uzoq turgan ulanishni
# serverning o'zi kutilmaganda yopib qo'yishi mumkin. asyncpg pool'i buni
# oldindan bilmaydi va "o'lik" ulanishni keyingi so'rovga berib yuborishi
# mumkin — natijada ConnectionDoesNotExistError / InterfaceError chiqadi.
# Shu turdagi xatolarni retry qilish uchun ro'yxat:
_RETRYABLE_DB_ERRORS = (
    asyncpg.PostgresConnectionError,   # ConnectionDoesNotExistError va shunga o'xshashlar shundan meros oladi
    asyncpg.InterfaceError,            # "connection is closed" va shunga o'xshash holatlar
    ConnectionResetError,
    OSError,
)


def with_db_retry(retries: int = 2, delay: float = 0.5):
    """
    DB funksiyasini ulanish xatosi (yuqoridagi _RETRYABLE_DB_ERRORS) yuz
    berganda avtomatik qayta chaqiradigan dekorator.

    Nega ishlaydi: xato chiqqan "o'lik" ulanishni asyncpg pool o'zi
    tashlab yuboradi (qayta pool'ga qaytarmaydi), shuning uchun keyingi
    urinishda pool.acquire() yangi, sog'lom ulanish beradi.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except _RETRYABLE_DB_ERRORS as e:
                    last_err = e
                    logger.warning(
                        f"DB ulanish xatosi ({func.__name__}), {attempt + 1}-urinish: {e}"
                    )
                    if attempt < retries:
                        await asyncio.sleep(delay * (attempt + 1))
            raise last_err
        return wrapper
    return decorator


async def _indeks_yarat(conn, nom: str, ifoda: str) -> None:
    """Indeksni JADVALNI QULFLAMASDAN quradi (`CONCURRENTLY`).

    ⚠️ `CONCURRENTLY` tranzaksiya blokida ISHLAMAYDI. asyncpg'da
    `conn.execute(sql)` ARGUMENTSIZ chaqirilsa oddiy so'rov protokoli
    ishlaydi va tranzaksiya ochilmaydi — shuning uchun bu yerda hech
    qachon parametr berilmaydi va `nom`/`ifoda` faqat shu fayldagi
    o'zgarmas matnlar bo'ladi. Parametr qo'shilsa asyncpg tayyorlangan
    so'rovga o'tadi va Postgres "cannot run inside a transaction block"
    beradi.

    ⛔️ Yiqilgan `CONCURRENTLY` jadvalda YAROQSIZ (invalid) indeks
    qoldiradi, `IF NOT EXISTS` esa uni "bor" deb o'tkazib yuboradi —
    ya'ni indeks abadiy yaroqsiz qoladi va hech narsa aytmaydi. Shuning
    uchun avval yaroqsizi qidiriladi va tashlanadi.

    Xato JIM YUTILMAYDI: indeks bo'lmasa bot ishlaydi, faqat sekin —
    bu ogohlantirish, ishga tushishni to'xtatadigan sabab emas.
    """
    try:
        yaroqsiz = await conn.fetchval(
            '''SELECT TRUE FROM pg_class c
                 JOIN pg_index i ON i.indexrelid = c.oid
                WHERE c.relname = $1 AND NOT i.indisvalid''', nom)
        if yaroqsiz:
            logger.warning(f"[indeks] {nom} yaroqsiz edi — qayta quriladi")
            await conn.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {nom}")
        await conn.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {nom} ON {ifoda}")
    except Exception as e:
        logger.warning(f"[indeks] {nom} qurilmadi: {e}")
        return
    logger.info(f"[indeks] {nom} tayyor")


# Qulfsiz quriladigan indekslar: (nomi, jadval va ustunlar).
#
# ⚠️ Uchalasi ham YOZILADIGAN jadval ustida: `user_history` ga har model
# raundida, `error_log` ga har foydalanuvchi xatosida, `admin_audit` ga
# har admin amalida. Oddiy `CREATE INDEX` ularni qurish davomida
# qulflaydi, ya'ni deploy paytida yozib bo'lmaydigan oyna paydo bo'lardi.
_INDEKSLAR = (
    # `token_stats::eng_qimmat` `created_at` bo'yicha filtrlab, `user_id`
    # bo'yicha guruhlaydi — bitta ustunli indeks faqat filtrni qoplaydi.
    ("idx_user_history_kun_user", "user_history (created_at, user_id)"),
    ("idx_error_log_kun", "error_log (created_at)"),
    ("idx_admin_audit_vaqt", "admin_audit (action_time)"),
    # Javobsiz chat kuzatuvchisi (REJA.md 4.2) har 5 daqiqada faqat
    # business tarixini (`thread_id < 0`) so'nggi soatlar bo'yicha o'qiydi.
    # Qisman indeks: oddiy DM tarixi unga umuman kirmaydi.
    ("idx_chat_messages_biznes",
     "chat_messages (created_at) WHERE thread_id < 0"),
    # «Chatlar» ekrani va ertalabki hisobot egasining business tarixini
    # `thread_id = -owner` bo'yicha o'qiydi. Mavjud `(chat_id, thread_id, id)`
    # thread bo'yicha BOSHLANMAYDI — `chat_messages` (HAMMA foydalanuvchining
    # DM tarixi) to'liq skanerlanardi (AUDIT 6.2.1). ⚠️ So'rovlarda
    # `AND thread_id < 0` ATAYLAB: parametrli `thread_id = $1` dan planner
    # qisman indeks shartini isbotlay olmaydi.
    ("idx_chat_messages_biznes_thread",
     "chat_messages (thread_id, id) WHERE thread_id < 0"),
    # `biznes_loyiha` da PK'dan boshqa indeks yo'q edi (AUDIT 6.2.2): har
    # egasi xabarida `eskirt` va har tanlovda kutayotganini qidirish.
    ("idx_biznes_loyiha_kutmoqda",
     "biznes_loyiha (owner_id, chat_id) WHERE holat = 'kutmoqda'"),
    ("idx_biznes_loyiha_egasi", "biznes_loyiha (owner_id, id)"),
)


async def indekslarni_qur() -> None:
    """Qulfsiz indekslar — FON VAZIFASI, ishga tushishni kutkazmaydi.

    ⛔️ `CONCURRENTLY` jadvalni skanerlab chiqadi, ya'ni katta jadvalda
    u SONIYALAB davom etadi. `main()` ichida `await` qilinsa bot ham,
    panel ham shuncha vaqt ishga tushmay turardi — indeks esa tezlik
    uchun, ishlashi uchun emas. Indekssiz bot darhol ishlaydi, faqat
    sekinroq; kutib turgan bot esa umuman ishlamaydi.

    Shuning uchun `main.py` buni `asyncio.create_task()` bilan
    chaqiradi va natija faqat LOGGA yoziladi — `[indeks] … tayyor`
    yoki `[indeks] … qurilmadi: …`.
    """
    global pool
    if pool is None:
        await create_db_pool()
    try:
        async with pool.acquire() as conn:
            for nom, ifoda in _INDEKSLAR:
                await _indeks_yarat(conn, nom, ifoda)
    except Exception as e:
        # Butun vazifa yiqilsa ham bot ishlayveradi — bu fon ishi.
        logger.warning(f"[indeks] qurish vazifasi yiqildi: {e}")


async def create_db_pool():
    """Create and return a global asyncpg pool (if not created yet)."""
    global pool
    if pool is None:
        async with _pool_lock:
            if pool is None:
                if not DATABASE_URL:
                    raise RuntimeError("DATABASE_URL is not set in environment")
                pool = await asyncpg.create_pool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=10,
                    # Ulanishlar uzoq bo'sh turmasin — provayder o'zi yopib
                    # qo'yishidan oldin pool ularni proaktiv yangilaydi.
                    max_inactive_connection_lifetime=60,
                    # Bitta so'rov cheksiz "osilib" qolmasligi uchun.
                    command_timeout=30,
                )
    return pool

async def close_db_pool():
    """Close the global pool (use on shutdown)."""
    global pool
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass
        pool = None

@with_db_retry()
async def create_users_table():
    """
    Create required tables if they do not exist.
    Uses TIMESTAMPTZ for timezone-aware timestamps.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(100),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_seen TIMESTAMPTZ,
                is_active BOOLEAN DEFAULT TRUE
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(100),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS admin_audit (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT,
                action VARCHAR(100),
                target_user_id BIGINT,
                details TEXT,
                action_time TIMESTAMPTZ DEFAULT NOW()
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_activity (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                username VARCHAR(100),
                activity_time TIMESTAMPTZ DEFAULT NOW(),
                activity_type VARCHAR(50)
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS superadmins (
                user_id BIGINT PRIMARY KEY
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                id INT PRIMARY KEY DEFAULT 1,
                maintenance_active BOOLEAN DEFAULT FALSE,
                maintenance_message TEXT,
                CHECK (id = 1)
            );
        ''')
        await conn.execute('''
            INSERT INTO bot_settings (id) VALUES (1)
            ON CONFLICT (id) DO NOTHING
        ''')
        # Referal shartlari admin panelidan boshqariladi. NULL = core/config.py
        # dagi qiymat ishlatiladi, ya'ni sozlanmagan bot ham eski xatti-harakatda
        # qoladi va migratsiya kerak emas.
        await conn.execute('''
            ALTER TABLE bot_settings
                ADD COLUMN IF NOT EXISTS referral_required INT,
                ADD COLUMN IF NOT EXISTS referral_reward_days INT
        ''')
        # Kunlik limitlar admin panelidan sozlanadi. NULL = core/config.py
        # dagi PLAN_LIMITS ishlatiladi, ya'ni sozlanmagan bot eski
        # xatti-harakatda qoladi va migratsiya kerak emas.
        await conn.execute('''
            ALTER TABLE bot_settings
                ADD COLUMN IF NOT EXISTS limit_overrides JSONB
        ''')
        # Xatolar jurnali. Ilgari xato FAQAT Railway logida qolardi —
        # ya'ni admin bot buzilganini foydalanuvchi aytgandan keyin
        # bilardi. Jadval ataylab kichik: eng eskilari `log_error()`
        # ichida o'chiriladi.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS error_log (
                id BIGSERIAL PRIMARY KEY,
                kind VARCHAR(50) NOT NULL,
                message TEXT NOT NULL,
                user_id BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        ''')
        # Rejalashtirilgan tarqatma. Oluvchilar ro'yxati SAQLANMAYDI —
        # faqat segment: yuborish vaqtida auditoriya yangi bo'lishi
        # kerak (oradan bir kun o'tsa ro'yxat eskiradi).
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
                id BIGSERIAL PRIMARY KEY,
                admin_id BIGINT NOT NULL,
                src_chat_id BIGINT NOT NULL,
                src_message_id BIGINT NOT NULL,
                buttons JSONB,
                segment VARCHAR(20) NOT NULL DEFAULT 'all',
                run_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                sent_at TIMESTAMPTZ
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS watch_settings (
                id INT PRIMARY KEY DEFAULT 1,
                group_id BIGINT,
                CHECK (id = 1)
            );
        ''')
        await conn.execute('''
            INSERT INTO watch_settings (id) VALUES (1)
            ON CONFLICT (id) DO NOTHING
        ''')
        # Kuzatuv guruhiga yozib bo'lmayotgani PANELDA ko'rinsin.
        #
        # ⚠️ NEGA KERAK: ogohlantirish yuborilmasa kod faqat
        # `logger.warning` yozardi — ya'ni «bot yiqildi» xabari
        # yetmagani Railway logida qolardi, va u yerga bot yiqilganda
        # qaraladi. Xabar ketmadi, tizim esa «ketdi» deb hisoblardi.
        #
        # Uchalasi NULL bo'lishi mumkin = hali hech narsa yiqilmagan,
        # ya'ni migratsiya kerak emas va sozlanmagan bot eski
        # xatti-harakatda qoladi.
        await conn.execute('''
            ALTER TABLE watch_settings
                ADD COLUMN IF NOT EXISTS oxirgi_xato_vaqt TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS oxirgi_xato_sabab TEXT,
                ADD COLUMN IF NOT EXISTS oxirgi_ok_vaqt TIMESTAMPTZ
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT,
                added_at TIMESTAMPTZ DEFAULT NOW()
            );
        ''')

        # ── TO'LOVLAR (Telegram Stars) ──────────────────────────────
        # charge_id UNIQUE — takroriy grant'dan himoyaning BUTUN mexanizmi.
        # Telegram bitta successful_payment update'ini bir necha marta
        # yuborishi mumkin; ON CONFLICT DO NOTHING tufayli ikkinchisi
        # hech narsa qilmaydi va Pro ikki marta berilmaydi.
        #
        # payer_id va beneficiary_id ALOHIDA: sovg'a qilinganda to'lovchi
        # va Pro oluvchi har xil odam bo'ladi. Refund HAR DOIM payer_id ga
        # qilinadi — Telegram pulni o'shanga qaytaradi.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS star_payments (
                id SERIAL PRIMARY KEY,
                charge_id TEXT UNIQUE NOT NULL,
                payer_id BIGINT NOT NULL,
                beneficiary_id BIGINT NOT NULL,
                stars INT NOT NULL,
                plan VARCHAR(20) NOT NULL DEFAULT 'pro',
                days INT NOT NULL,
                payload TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                refunded_at TIMESTAMPTZ,
                refunded_by BIGINT
            );
        ''')

        # ── REFERAL ─────────────────────────────────────────────────
        # invited_id PRIMARY KEY — bir odam FAQAT bir marta taklif qilinadi.
        # Qayta-taklif suiiste'moli shu bitta cheklov bilan yopiladi,
        # dasturiy tekshiruv kerak emas.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                invited_id BIGINT PRIMARY KEY,
                referrer_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                qualified_at TIMESTAMPTZ,
                rewarded_at TIMESTAMPTZ
            );
        ''')

        # ── PROMOKODLAR ─────────────────────────────────────────────
        # promo_redemptions PRIMARY KEY (code, user_id) — "bir foydalanuvchi
        # bir marta" qoidasi cheklov sifatida, race condition imkonsiz.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promo_codes (
                code VARCHAR(32) PRIMARY KEY,
                days INT NOT NULL,
                plan VARCHAR(20) NOT NULL DEFAULT 'pro',
                max_uses INT NOT NULL DEFAULT 1,
                used_count INT NOT NULL DEFAULT 0,
                expires_at TIMESTAMPTZ,
                created_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                revoked BOOLEAN DEFAULT FALSE
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promo_redemptions (
                code VARCHAR(32) REFERENCES promo_codes(code) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                redeemed_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (code, user_id)
            );
        ''')
        # Uzoq muddatli xotira — foydalanuvchi haqidagi doimiy faktlar.
        # Suhbat tarixi (db/history.py) 60 xabardan keyin JISMONAN o'chadi,
        # shuning uchun "ismim Aziz" u yerda saqlanib qololmaydi. Bu jadval
        # esa modelning O'ZI tanlab yozgan faktlarini abadiy saqlaydi.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_memories (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            );
        ''')

        # Eslatmalar va rejalashtirilgan vazifalar (Pro).
        # `chat_id` ATAYLAB yo'q: eslatma DOIM shaxsiy chatga boradi.
        # Guruhda yaratilgan eslatma o'sha guruhga tushsa, foydalanuvchining
        # shaxsiy ishi begonalarga ko'rinardi.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                text TEXT NOT NULL,
                run_at TIMESTAMPTZ NOT NULL,
                repeat TEXT NOT NULL DEFAULT 'once',
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_sent_at TIMESTAMPTZ
            );
        ''')

        # Telegram Business ulanishlari (REJA.md 0.5). Har `business_message`
        # ulanishni o'qiydi — shuning uchun RAM keshdan (`_biznes_kesh`),
        # jadval esa deploy'dan keyin keshni tiklash uchun.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS biznes_ulanish (
                conn_id     TEXT PRIMARY KEY,
                owner_id    BIGINT NOT NULL,
                owner_chat  BIGINT NOT NULL,
                yoqilgan    BOOLEAN NOT NULL,
                huquqlar    JSONB NOT NULL,
                rejim       TEXT NOT NULL DEFAULT 'buyruq',
                yangilangan TIMESTAMP NOT NULL DEFAULT NOW()
            );
        ''')
        # Egasining biznes bilimi (REJA.md 2-bosqich) — har mijoz so'rovida
        # `developer` xabar bo'lib ketadi, `instructions`'ga HECH QACHON.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS biznes_profil (
                owner_id    BIGINT PRIMARY KEY,
                bilim       TEXT NOT NULL,
                yangilangan TIMESTAMP NOT NULL DEFAULT NOW()
            );
        ''')
        # "Yordamchi" rejimi loyihalari. RAM'da emas: `callback_data` 64
        # bayt, loyiha matni sig'maydi, va deploy tugmani o'lik qilmasin.
        # holat: kutmoqda → yuborilmoqda → yuborildi | tahrirlandi;
        #        yoki bekor | eskirgan. `tahrirlandi` va `yuborildi`
        #        nisbati — 3-bosqichga o'tish mezoni (REJA.md).
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS biznes_loyiha (
                id          BIGSERIAL PRIMARY KEY,
                owner_id    BIGINT NOT NULL,
                conn_id     TEXT NOT NULL,
                chat_id     BIGINT NOT NULL,
                mijoz_matni TEXT NOT NULL,
                loyiha      TEXT NOT NULL,
                yakuniy     TEXT,
                holat       TEXT NOT NULL DEFAULT 'kutmoqda',
                yaratilgan  TIMESTAMP NOT NULL DEFAULT NOW()
            );
        ''')
        # Egasining uslubi (5-bosqich). `uslub` — mini model yozgan tavsif,
        # `uslub_egasi` — egasining o'z qoidalari (ustun turadi).
        # `namuna_jami` faqat o'sadi (jadval kesiladi, sanoq esa yo'q) —
        # qayta o'rganish vaqti `uslub_jami` bilan farqidan aniqlanadi.
        await conn.execute('''
            ALTER TABLE biznes_profil
                ADD COLUMN IF NOT EXISTS uslub       TEXT,
                ADD COLUMN IF NOT EXISTS uslub_egasi TEXT,
                ADD COLUMN IF NOT EXISTS namuna_jami INT NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS uslub_jami  INT NOT NULL DEFAULT 0
        ''')
        # Egasining bot DM'idagi «💼 Biznes» mavzusi. Mavzular yoqilgan
        # shaxsiy chatda `message_thread_id` siz xabar HAR SAFAR yangi mavzu
        # ochardi (jonli ko'rilgan) — hamma Business xabari shu bittasiga.
        await conn.execute(
            "ALTER TABLE biznes_profil ADD COLUMN IF NOT EXISTS dm_mavzu BIGINT")
        # `[tanlov:]` — egasiga tugma bilan beriladigan tayyor javoblar.
        await conn.execute(
            "ALTER TABLE biznes_loyiha ADD COLUMN IF NOT EXISTS variantlar JSONB")
        # Dublikat update himoyasi (AUDIT 7.1): deploy paytida eski jarayon
        # update'ni olib, offsetni tasdiqlamay o'lsa, yangisi uni qayta oladi —
        # avtomat ikki marta javob berardi. RAM qayta ishga tushishdan
        # omon qolmaydi, shuning uchun bazada. Kunlik `biznes_tozala()` kesadi.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS biznes_korilgan (
                owner_id   BIGINT NOT NULL,
                chat_id    BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                vaqt       TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (owner_id, chat_id, message_id)
            );
        ''')
        # Pauza SABABI: 'egasi' (egasi o'zi yozdi — suhbat uning qo'lida) yoki
        # 'uzatish' (bot savolni egasiga uzatdi — suhbatdosh javob kutyapti).
        # Faqat 'uzatish' da suhbatdoshga bir marta "bandman" va egasiga eslatma.
        await conn.execute('''
            ALTER TABLE biznes_chat
                ADD COLUMN IF NOT EXISTS pauza_sababi   TEXT,
                ADD COLUMN IF NOT EXISTS band_yuborildi BOOLEAN NOT NULL DEFAULT FALSE
        ''')
        # Avtomat javob oxiridagi «🤖 avtojavob» belgisi (standart — yoqilgan).
        await conn.execute(
            "ALTER TABLE biznes_ulanish ADD COLUMN IF NOT EXISTS "
            "avto_belgi BOOLEAN NOT NULL DEFAULT TRUE")
        # Egasi mijozga O'ZI yozgan xabarlar — uslub namunalari. Chat tarixi
        # (`chat_messages`) yetmaydi: u yerda `assistant` — egasi ham, bot
        # uning nomidan yuborgani ham, ya'ni bot o'zidan o'rganib qolardi.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS biznes_namuna (
                id         BIGSERIAL PRIMARY KEY,
                owner_id   BIGINT NOT NULL,
                matn       TEXT NOT NULL,
                yaratilgan TIMESTAMP NOT NULL DEFAULT NOW()
            );
        ''')
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_biznes_namuna_egasi "
            "ON biznes_namuna (owner_id, id DESC)")
        # Avtomat rejim: ish vaqti (NULL = doim) — egasi darajasida.
        await conn.execute(
            "ALTER TABLE biznes_ulanish ADD COLUMN IF NOT EXISTS ish_vaqti TEXT")
        # Ertalabki hisobot (4.1) yuborilgan kun — qayta ishga tushishda
        # ikkinchi marta ketmasin (`biznes_hisobot_band` atomik egallaydi).
        await conn.execute(
            "ALTER TABLE biznes_ulanish ADD COLUMN IF NOT EXISTS hisobot_sana DATE")
        # Mijozlar kartotekasi (4.3). `tg_ism`/`username` — Telegram
        # bergani (ishonchli), `ism`/`telefon`/`qiziqish` — MODEL yozgani
        # (ishonchsiz, `clean_mijoz_maydon()` dan o'tadi).
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS biznes_mijoz (
                owner_id  BIGINT NOT NULL,
                chat_id   BIGINT NOT NULL,
                tg_ism    TEXT,
                username  TEXT,
                ism       TEXT,
                telefon   TEXT,
                qiziqish  TEXT,
                oxirgi    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (owner_id, chat_id)
            );
        ''')
        # Chat bo'yicha holat: egasi o'chirgan chat va pauza (uzatishdan
        # yoki egasi o'zi yozgandan keyin). RAM'da EMAS: deploy pauzani
        # o'chirib yuborsa, bot egasi qo'lga olgan suhbatga qaytib kirardi.
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS biznes_chat (
                owner_id    BIGINT NOT NULL,
                chat_id     BIGINT NOT NULL,
                ochirilgan  BOOLEAN NOT NULL DEFAULT FALSE,
                pauza_gacha TIMESTAMPTZ,
                PRIMARY KEY (owner_id, chat_id)
            );
        ''')

        # Eski, ishlatib bo'lingan eslatmalarni tozalash. Ilgari ular
        # active=FALSE bo'lib jadvalda qolib ketardi; endi yuborilgach
        # o'chiriladi, shuning uchun bu faqat eskilarini yig'ishtiradi.
        try:
            await conn.execute(
                'DELETE FROM scheduled_tasks WHERE active = FALSE')
        except Exception:
            logger.exception("eski eslatmalar tozalanmadi")

        try:
            # Qisman indeks: watcher har 60 soniyada FAQAT faol va muddati
            # kelganlarini so'raydi, o'chirilgan eskilari indeksga umuman
            # kirmaydi.
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scheduled_due "
                "ON scheduled_tasks (run_at) WHERE active;")
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_scheduled_user "
                "ON scheduled_tasks (user_id) WHERE active;")
            # `updated_at` keyinroq qo'shildi. Modelga sana ko'rsatiladi, va
            # tuzatilgan fakt eski sana bilan tursa model unga kamroq
            # ishonadi — shuning uchun yangilanish vaqti alohida yoziladi.
            await conn.execute(
                "ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories(user_id, id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_star_payments_payer ON star_payments(payer_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_star_payments_created ON star_payments(created_at);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_time ON user_activity(activity_time);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_user ON user_activity(user_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
        except Exception:
            pass

        # ⚠️ `CONCURRENTLY` indekslari BU YERDA EMAS — `indekslarni_qur()`
        # da, fon vazifasida. Izohini o'sha yerdan o'qing.


@with_db_retry()
async def save_user(user_id: int, username: Optional[str] = None) -> None:
    """
    Save or update user. If username is None, keep existing username.
    Always update last_seen to NOW() and set is_active = TRUE.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, username, last_seen)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET
                username = COALESCE(EXCLUDED.username, users.username),
                last_seen = NOW(),
                is_active = TRUE,
                -- Foydalanuvchi QAYTDI: "sog'indik" bosqichi noldan
                -- boshlanadi. Aks holda u qaytganidan keyin ham 15/30
                -- kunlik eslatmalar ketaverardi.
                inactive_stage = 0,
                inactive_notified_at = NULL
        ''', user_id, username)


@with_db_retry()
async def has_started(user_id: int) -> bool:
    """
    Foydalanuvchi kamida bir marta /start bosganini (ya'ni `users`
    jadvalida allaqachon mavjudligini) tekshiradi.

    Guest Mode uchun ishlatiladi: Guest Mode orqali murojaat qilgan, lekin
    hali botga /start bermagan (demak, kredit balansi hali "ochilmagan")
    foydalanuvchilarni AI so'rovi yuborilishidan OLDIN aniqlash uchun.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval('SELECT 1 FROM users WHERE user_id = $1', user_id)
        return bool(val)


@with_db_retry()
async def log_user_activity(user_id: int, username: Optional[str], activity_type: str) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO user_activity (user_id, username, activity_type)
            VALUES ($1, $2, $3)
        ''', user_id, username, activity_type)


def format_dt_for_tashkent(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert a timezone-aware or naive datetime (assumed UTC if naive)
    to Asia/Tashkent and return formatted string. Return None if dt is None.
    Always appends explicit 'Asia/Tashkent' label to avoid '+05' only.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        dt_tashkent = dt.astimezone(TASHKENT_TZ)
    except Exception:
        dt = dt.replace(tzinfo=timezone.utc)
        dt_tashkent = dt.astimezone(TASHKENT_TZ)
    return dt_tashkent.strftime("%Y-%m-%d %H:%M:%S") + " Asia/Tashkent"


@with_db_retry()
async def get_all_users() -> List[Dict[str, Any]]:
    """
    Return all active users with basic metadata.
    Includes both raw datetimes and formatted strings for display.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT user_id, username, created_at, last_seen, plan_type, is_banned, premium_until
            FROM users
            WHERE is_active = TRUE
            ORDER BY user_id
        ''')
        result = []
        for r in rows:
            created_raw = r.get('created_at')
            last_raw = r.get('last_seen')
            result.append({
                'user_id': r['user_id'],
                'username': r.get('username'),
                'display_name': f"@{r.get('username')}" if r.get('username') else f"ID:{r['user_id']}",
                'plan_type': r.get('plan_type') or 'free',
                'is_banned': bool(r.get('is_banned')),
                'premium_until': r.get('premium_until'),
                'created_at_raw': created_raw,
                'last_seen_raw': last_raw,
                'created_at': format_dt_for_tashkent(created_raw),
                'last_seen': format_dt_for_tashkent(last_raw)
            })
        return result


@with_db_retry()
async def get_user_by_username(username: str) -> Optional[int]:
    """
    Return user_id for given username or None.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval('SELECT user_id FROM users WHERE username = $1', username)


@with_db_retry()
async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Return user row by user_id with both raw datetimes and formatted strings, or None.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''
            SELECT user_id, username, created_at, last_seen, is_active
            FROM users
            WHERE user_id = $1
        ''', user_id)
        if not row:
            return None
        created_raw = row.get('created_at')
        last_raw = row.get('last_seen')
        return {
            'user_id': row['user_id'],
            'username': row.get('username'),
            'display_name': f"@{row.get('username')}" if row.get('username') else f"ID:{row['user_id']}",
            'created_at_raw': created_raw,
            'last_seen_raw': last_raw,
            'created_at': format_dt_for_tashkent(created_raw),
            'last_seen': format_dt_for_tashkent(last_raw),
            'is_active': bool(row.get('is_active'))
        }


@with_db_retry()
async def get_user_by_identifier(identifier: str) -> Optional[int]:
    """
    Accept either a numeric string (user_id) or username string.
    If numeric -> return that user_id if exists.
    If not numeric -> treat as username and look up user_id.
    """
    global pool
    if pool is None:
        await create_db_pool()
    identifier = identifier.strip()
    if identifier.isdigit():
        uid = int(identifier)
        async with pool.acquire() as conn:
            exists = await conn.fetchval('SELECT 1 FROM users WHERE user_id = $1', uid)
            return uid if exists else None
    if identifier.startswith("@"):
        identifier = identifier[1:]
    async with pool.acquire() as conn:
        return await conn.fetchval('SELECT user_id FROM users WHERE username = $1', identifier)


@with_db_retry()
async def deactivate_user(user_id: int) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('UPDATE users SET is_active = FALSE WHERE user_id = $1', user_id)


@with_db_retry()
async def get_users_count() -> int:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval('SELECT COUNT(*) FROM users WHERE is_active = TRUE')


@with_db_retry()
async def is_admin(user_id: int) -> bool:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval('SELECT 1 FROM admins WHERE user_id = $1', user_id)
        return bool(val)


@with_db_retry()
async def get_admins() -> List[Dict[str, Any]]:
    """
    Return admins with created_at formatted (suitable for displaying in lists).
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT user_id, username, created_at FROM admins ORDER BY user_id')
        result = []
        for r in rows:
            created_raw = r.get('created_at')
            result.append({
                'user_id': r['user_id'],
                'username': r.get('username'),
                'display_name': f"@{r.get('username')}" if r.get('username') else f"ID:{r['user_id']}",
                'created_at': format_dt_for_tashkent(created_raw)
            })
        return result


@with_db_retry()
async def get_panel_admins() -> List[Dict[str, Any]]:
    """Panelga kira oladigan HAMMA odam — adminlar VA superadminlar.

    ⚠️ `get_admins()` faqat `admins` jadvalini o'qiydi, superadmin esa
    alohida jadvalda turadi. Jonli bazada (2026-09-15) `admins` BO'SH,
    superadmin esa bitta — ya'ni `get_admins()` ga tayangan ro'yxat
    «panelga hech kim kira olmaydi» deb ko'rsatgan bo'lardi, holbuki
    bitta odam kira oladi. Huquq tekshiruvi (`web.huquq_bormi`)
    ikkalasini ham ko'radi, shuning uchun ro'yxat ham ko'rishi shart —
    aks holda ekran «kim kira oladi» degan savolga YOLG'ON javob beradi.

    `username` avval `admins` dan, bo'lmasa `users` dan olinadi: admin
    qo'shilgandan keyin nomini o'zgartirgan bo'lishi mumkin.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''SELECT COALESCE(a.user_id, s.user_id) AS user_id,
                      COALESCE(a.username, u.username)  AS username,
                      a.created_at,
                      (s.user_id IS NOT NULL)           AS is_super
                 FROM admins a
                 FULL OUTER JOIN superadmins s ON s.user_id = a.user_id
                 LEFT JOIN users u ON u.user_id = COALESCE(a.user_id, s.user_id)
                ORDER BY is_super DESC, user_id''')
        return [{
            'user_id': r['user_id'],
            'username': r['username'],
            'display_name': f"@{r['username']}" if r['username'] else f"ID:{r['user_id']}",
            'created_at': format_dt_for_tashkent(r['created_at']) if r['created_at'] else None,
            'is_super': bool(r['is_super']),
        } for r in rows]


@with_db_retry()
async def get_admin_meta(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Return admin meta. For program logic 'created_at' is raw datetime (useful for comparisons).
    Also return 'created_at_str' formatted for display.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT user_id, username, created_at FROM admins WHERE user_id = $1', user_id)
        if not row:
            return None
        created_raw = row.get('created_at')
        return {
            'user_id': row['user_id'],
            'username': row.get('username'),
            'created_at': created_raw,
            'created_at_str': format_dt_for_tashkent(created_raw),
            'display_name': f"@{row.get('username')}" if row.get('username') else f"ID:{row['user_id']}"
        }


@with_db_retry()
async def add_admin(user_id: int, username: Optional[str] = None) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO admins (user_id, username, created_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET username = COALESCE(EXCLUDED.username, admins.username)
        ''', user_id, username)


@with_db_retry()
async def remove_admin(user_id: int) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM admins WHERE user_id = $1', user_id)


@with_db_retry()
async def log_admin_action(admin_id: int, action: str, target_user_id: Optional[int] = None, details: Optional[str] = None) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO admin_audit (admin_id, action, target_user_id, details)
            VALUES ($1, $2, $3, $4)
        ''', admin_id, action, target_user_id, details)


@with_db_retry()
async def is_superadmin(user_id: int) -> bool:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval('SELECT 1 FROM superadmins WHERE user_id = $1', user_id)
        return bool(val)


DEFAULT_MAINTENANCE_MESSAGE = "🛠 Bot hozirda texnik ta'til rejimida. Birozdan so'ng qaytadan urinib ko'ring."


@with_db_retry()
async def get_maintenance() -> Dict[str, Any]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT maintenance_active, maintenance_message FROM bot_settings WHERE id = 1')
        if not row:
            return {'active': False, 'message': DEFAULT_MAINTENANCE_MESSAGE}
        return {
            'active': bool(row['maintenance_active']),
            'message': row['maintenance_message'] or DEFAULT_MAINTENANCE_MESSAGE,
        }


@with_db_retry()
async def get_maintenance_notice_for(user_id: int) -> Optional[str]:
    """
    Bitta so'rovda: agar texnik ta'til yoqilgan bo'lsa va user_id admin/
    superadmin bo'lmasa — ko'rsatiladigan xabarni qaytaradi. Aks holda None
    (foydalanuvchi odatdagidek davom etishi kerak).
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            SELECT
                s.maintenance_active,
                s.maintenance_message,
                EXISTS(SELECT 1 FROM admins WHERE user_id = $1) AS is_admin,
                EXISTS(SELECT 1 FROM superadmins WHERE user_id = $1) AS is_superadmin
            FROM bot_settings s
            WHERE s.id = 1
            ''',
            user_id,
        )
        if not row or not row['maintenance_active'] or row['is_admin'] or row['is_superadmin']:
            return None
        return row['maintenance_message'] or DEFAULT_MAINTENANCE_MESSAGE


@with_db_retry()
async def set_maintenance(active: bool, message: Optional[str] = None) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            UPDATE bot_settings
            SET maintenance_active = $1,
                maintenance_message = COALESCE($2, maintenance_message)
            WHERE id = 1
            ''',
            active, message,
        )


def get_watch_target(user_id: int) -> Optional[int]:
    """
    Sync, O(1), I/O yo'q — asosiy xabar oqimidan har xabarda chaqiriladi.
    user_id kuzatuvda va guruh sozlangan bo'lsa guruh_id, aks holda None.
    """
    if _watch_group_id and user_id in _watched_user_ids:
        return _watch_group_id
    return None


@with_db_retry()
async def load_watch_cache() -> None:
    """Bot ishga tushganda bir marta chaqiriladi — DB'dagi holatni keshga yuklaydi."""
    global pool, _watch_group_id, _watched_user_ids
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        _watch_group_id = await conn.fetchval('SELECT group_id FROM watch_settings WHERE id = 1')
        rows = await conn.fetch('SELECT user_id FROM watchlist')
        _watched_user_ids = {r['user_id'] for r in rows}


# ─────────────────────────────────────────────────────────────
# TELEGRAM BUSINESS ULANISHLARI — RAM kesh (REJA.md 0.5)
# ─────────────────────────────────────────────────────────────
# `load_watch_cache()` bilan bir xil naqsh: har `business_message`da
# sinxron o'qiladi, startup'da yuklanadi va `business_connection`
# update'ida O'SHA handlerning o'zida yangilanadi. Yangilanmasa — ulanish
# uzilgan, bot esa javob berishda davom etadi va hech narsa xato bermaydi.
_biznes_kesh: Dict[str, Dict[str, Any]] = {}


def biznes_ulanish_ol(conn_id: str) -> Optional[Dict[str, Any]]:
    """Sync, I/O yo'q. Keshda yo'q bo'lsa None."""
    return _biznes_kesh.get(conn_id)


@with_db_retry()
async def biznes_ulanish_yoz(conn_id: str, owner_id: int, owner_chat: int,
                             yoqilgan: bool, huquqlar: Dict[str, bool]) -> Dict[str, Any]:
    """Ulanishni yozadi VA keshni yangilaydi. `rejim` saqlanadi — qayta
    ulanish egasi tanlagan rejimni tashlab yubormasin.

    ⚠️ Kesh DB'dan OLDIN: baza yiqilsa ham uzilgan ulanish keshda
    "yoqilgan" bo'lib qolmasin."""
    eski = _biznes_kesh.get(conn_id) or {}
    _biznes_kesh[conn_id] = {
        "owner_id": owner_id, "owner_chat": owner_chat, "yoqilgan": yoqilgan,
        "huquqlar": dict(huquqlar), "rejim": eski.get("rejim", "buyruq"),
        "ish_vaqti": eski.get("ish_vaqti"), "avto_belgi": eski.get("avto_belgi", True)}
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rejim = await conn.fetchrow(
            '''
            INSERT INTO biznes_ulanish (conn_id, owner_id, owner_chat, yoqilgan, huquqlar)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (conn_id) DO UPDATE SET
                owner_id = EXCLUDED.owner_id, owner_chat = EXCLUDED.owner_chat,
                yoqilgan = EXCLUDED.yoqilgan, huquqlar = EXCLUDED.huquqlar,
                yangilangan = NOW()
            RETURNING rejim, ish_vaqti, avto_belgi
            ''',
            conn_id, owner_id, owner_chat, yoqilgan, json.dumps(huquqlar))
    _biznes_kesh[conn_id]["rejim"] = rejim["rejim"]
    _biznes_kesh[conn_id]["ish_vaqti"] = rejim["ish_vaqti"]
    _biznes_kesh[conn_id]["avto_belgi"] = rejim["avto_belgi"]
    return _biznes_kesh[conn_id]


@with_db_retry()
async def biznes_keshni_yukla() -> None:
    """Bot ishga tushganda bir marta — jadvaldagi holatni keshga yuklaydi."""
    global pool, _biznes_kesh
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT conn_id, owner_id, owner_chat, yoqilgan, huquqlar, rejim, '
            'ish_vaqti, avto_belgi FROM biznes_ulanish')
    _biznes_kesh = {
        r['conn_id']: {
            "owner_id": r['owner_id'], "owner_chat": r['owner_chat'],
            "yoqilgan": r['yoqilgan'],
            # asyncpg JSONB'ni kodeksiz satr qilib qaytaradi.
            "huquqlar": (json.loads(r['huquqlar'])
                         if isinstance(r['huquqlar'], str) else dict(r['huquqlar'])),
            "rejim": r['rejim'],
            "ish_vaqti": r['ish_vaqti'],
            "avto_belgi": r['avto_belgi'],
        } for r in rows
    }


def biznes_faol_egalar() -> Dict[int, int]:
    """{owner_id: owner_chat} — yoqilgan ulanishlar (hisobot, ogohlantirish)."""
    return {v["owner_id"]: v["owner_chat"] for v in _biznes_kesh.values()
            if v["yoqilgan"]}


def biznes_egasi_ulanishi(owner_id: int) -> Optional[tuple]:
    """(conn_id, yozuv) — egasining ulanishi (/biznes ekrani uchun).
    Bir nechta bo'lsa yoqilgani afzal."""
    topilgan = [(k, v) for k, v in _biznes_kesh.items() if v["owner_id"] == owner_id]
    topilgan.sort(key=lambda kv: not kv[1]["yoqilgan"])
    return topilgan[0] if topilgan else None


@with_db_retry()
async def biznes_rejim_yoz(owner_id: int, rejim: str) -> None:
    if rejim not in BIZNES_REJIMLAR:
        raise ValueError(rejim)
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE biznes_ulanish SET rejim = $2 WHERE owner_id = $1',
            owner_id, rejim)
    for yozuv in _biznes_kesh.values():
        if yozuv["owner_id"] == owner_id:
            yozuv["rejim"] = rejim


# Karta (uzluksiz 13-19 raqam yoki 4-4-4-4 guruh) va pasport.
# Telefon (12 raqam) ATAYLAB o'tadi — do'kon telefoni bilimning eng oddiy
# qismi; `_SECRET_RE` (9+ raqam) uni ham rad etardi. "Istalgan ajratgichli
# 13+ raqam" ham EMAS: narx ro'yxati "50 000 80 000 120 000" — 16 raqam.
_BILIM_SIR_RE = re.compile(
    r"(?<!\d)\d{13,19}(?!\d)"
    r"|(?<!\d)\d{4}([ -])\d{4}\1\d{4}\1\d{4}(?!\d)"
    r"|\b[A-Za-z]{2}\s?\d{7}\b")


def clean_biznes_bilim(matn: str) -> tuple:
    """(toza_matn, xato_sababi). Sof funksiya — testda tekshiriladi.

    KESILMAYDI, rad etiladi: kesilgan bilim oxiridagi narxlarni jimgina
    yo'qotardi va egasi buni bilmasdi. Yangi qatorlar SAQLANADI — bilimni
    egasining o'zi yozadi va u `developer` xabarda chegaralangan blok.
    """
    matn = "\n".join(" ".join(q.split())
                     for q in str(matn or "").strip().splitlines()).strip()
    if not matn:
        return "", "bo'sh"
    if len(matn) > BIZNES_BILIM_MAX:
        return "", f"juda uzun ({len(matn)} belgi, chegara {BIZNES_BILIM_MAX})"
    if _BILIM_SIR_RE.search(matn):
        return "", "karta yoki pasport raqami bor"
    return matn, None


# ── Bilim va uslub RAM keshi (AUDIT 3.2-3.3) ─────────────────────────
# Har qoralama/avtojavobda o'qiladi (jonli o'lchov: 0,63 s — 4 so'rov).
# Bitta jarayon (CLAUDE.md: panel ham shu jarayonda), shuning uchun HAR
# YOZUV shu modulda keshni o'zi bekor qiladi. TTL — faqat sug'urta:
# unutilgan bekor qilish ham 10 daqiqadan oshmaydi.
_BIZNES_KESH_TTL = 600
_bilim_kesh: Dict[int, tuple] = {}     # egasi -> (bilim, vaqt)
_uslub_kesh: Dict[int, tuple] = {}     # egasi -> (dict, vaqt) — faqat standart `namuna`


def _keshdan(kesh: dict, egasi: int):
    bor = kesh.get(egasi)
    if bor and time.monotonic() - bor[1] < _BIZNES_KESH_TTL:
        return bor[0]
    return None


def biznes_keshni_bekor(egasi: int) -> None:
    """Egasining bilim/uslub keshi — keyingi o'qish bazadan."""
    _bilim_kesh.pop(egasi, None)
    _uslub_kesh.pop(egasi, None)


@with_db_retry()
async def biznes_bilim_ol(owner_id: int) -> str:
    bor = _keshdan(_bilim_kesh, owner_id)
    if bor is not None:
        return bor
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        bilim = await conn.fetchval(
            'SELECT bilim FROM biznes_profil WHERE owner_id = $1', owner_id) or ""
    _bilim_kesh[owner_id] = (bilim, time.monotonic())
    return bilim


@with_db_retry()
async def biznes_bilim_yoz(owner_id: int, bilim: str) -> None:
    """`clean_biznes_bilim()` dan O'TGAN matn keladi."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO biznes_profil (owner_id, bilim) VALUES ($1, $2) '
            'ON CONFLICT (owner_id) DO UPDATE SET bilim = EXCLUDED.bilim, '
            'yangilangan = NOW()', owner_id, bilim)
    biznes_keshni_bekor(owner_id)


@with_db_retry()
async def biznes_mavzu_ol(owner_id: int) -> Optional[int]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            'SELECT dm_mavzu FROM biznes_profil WHERE owner_id = $1', owner_id)


@with_db_retry()
async def biznes_mavzu_yoz(owner_id: int, thread_id: Optional[int]) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO biznes_profil (owner_id, bilim, dm_mavzu) VALUES ($1, '', $2) "
            "ON CONFLICT (owner_id) DO UPDATE SET dm_mavzu = EXCLUDED.dm_mavzu",
            owner_id, thread_id)


async def biznes_mavzumi(chat_id: int, thread_id: int) -> bool:
    """Shu mavzu egasining «💼 Biznes» mavzusimi — mavzu nomlash uni
    o'zgartirmasin. Xato — False emas, True (nomlamaslik xavfsiz tomon)."""
    global pool
    try:
        if pool is None:
            await create_db_pool()
        async with pool.acquire() as conn:
            return bool(await conn.fetchval(
                'SELECT 1 FROM biznes_profil WHERE owner_id = $1 AND dm_mavzu = $2',
                chat_id, thread_id))
    except Exception:
        return True


def clean_biznes_namuna(matn: str) -> Optional[str]:
    """Namuna bo'la oladimi — sof funksiya. Karta raqami bor xabar
    O'TMAYDI: namunalar boshqa mijozlarga ketadigan promptga qo'shiladi,
    egasi bir mijozga yuborgan kartasi boshqasining javobiga ko'chmasin."""
    matn = str(matn or "").strip()
    if not 2 <= len(matn) <= 1000 or _BILIM_SIR_RE.search(matn):
        return None
    return matn


@with_db_retry()
async def biznes_namuna_qosh(owner_id: int, matn: str) -> tuple:
    """`clean_biznes_namuna()` dan O'TGAN matn. Qaytadi: (namuna_jami,
    uslub_jami) — chaqiruvchi qayta o'rganish vaqtini hal qiladi."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                'INSERT INTO biznes_namuna (owner_id, matn) VALUES ($1, $2)',
                owner_id, matn)
            await conn.execute(
                'DELETE FROM biznes_namuna WHERE owner_id = $1 AND id NOT IN ('
                'SELECT id FROM biznes_namuna WHERE owner_id = $1 '
                'ORDER BY id DESC LIMIT $2)', owner_id, BIZNES_NAMUNA_MAX)
            r = await conn.fetchrow(
                "INSERT INTO biznes_profil (owner_id, bilim, namuna_jami) "
                "VALUES ($1, '', 1) ON CONFLICT (owner_id) DO UPDATE SET "
                "namuna_jami = biznes_profil.namuna_jami + 1 "
                "RETURNING namuna_jami, uslub_jami", owner_id)
    biznes_keshni_bekor(owner_id)
    return r['namuna_jami'], r['uslub_jami']


@with_db_retry()
async def biznes_uslub_ol(owner_id: int, namuna: int = BIZNES_NAMUNA_KORSAT) -> dict:
    """Uslub tavsifi, egasining qoidalari, oxirgi `namuna` ta xabari va
    oxirgi tuzatishlari (eskidan yangiga). Standart `namuna` — RAM keshdan."""
    if namuna == BIZNES_NAMUNA_KORSAT:
        bor = _keshdan(_uslub_kesh, owner_id)
        if bor is not None:
            return bor
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        p = await conn.fetchrow(
            'SELECT uslub, uslub_egasi, namuna_jami FROM biznes_profil '
            'WHERE owner_id = $1', owner_id)
        nam = await conn.fetch(
            'SELECT matn FROM biznes_namuna WHERE owner_id = $1 '
            'ORDER BY id DESC LIMIT $2', owner_id, namuna)
        tah = await conn.fetch(
            "SELECT loyiha, yakuniy FROM biznes_loyiha WHERE owner_id = $1 "
            "AND holat = 'tahrirlandi' AND yakuniy IS NOT NULL "
            "ORDER BY id DESC LIMIT $2", owner_id, BIZNES_TAHRIR_KORSAT)
    natija = {
        "uslub": p['uslub'] if p else None,
        "uslub_egasi": p['uslub_egasi'] if p else None,
        "jami": p['namuna_jami'] if p else 0,
        "namunalar": [r['matn'] for r in reversed(nam)],
        "tahrirlar": [(r['loyiha'], r['yakuniy']) for r in reversed(tah)],
    }
    if namuna == BIZNES_NAMUNA_KORSAT:
        _uslub_kesh[owner_id] = (natija, time.monotonic())
    return natija


@with_db_retry()
async def biznes_uslub_yoz(owner_id: int, uslub: Optional[str], jami: int) -> None:
    """Model yozgan tavsif; `jami` — qaysi namuna sanog'ida o'rganildi."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO biznes_profil (owner_id, bilim, uslub, uslub_jami) "
            "VALUES ($1, '', $2, $3) ON CONFLICT (owner_id) DO UPDATE SET "
            "uslub = EXCLUDED.uslub, uslub_jami = EXCLUDED.uslub_jami",
            owner_id, uslub, jami)
    biznes_keshni_bekor(owner_id)


def clean_uslub_egasi(matn: str) -> tuple:
    """(toza, xato) — `clean_biznes_bilim` qoidasi, o'z chegarasi bilan."""
    toza, xato = clean_biznes_bilim(matn)
    if not xato and len(toza) > BIZNES_USLUB_MAX:
        return "", f"juda uzun ({len(toza)} belgi, chegara {BIZNES_USLUB_MAX})"
    return toza, xato


@with_db_retry()
async def biznes_uslub_egasi_yoz(owner_id: int, matn: Optional[str]) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO biznes_profil (owner_id, bilim, uslub_egasi) "
            "VALUES ($1, '', $2) ON CONFLICT (owner_id) DO UPDATE SET "
            "uslub_egasi = EXCLUDED.uslub_egasi", owner_id, matn)
    biznes_keshni_bekor(owner_id)


@with_db_retry()
async def biznes_namunalar_ochir(owner_id: int) -> None:
    """Namunalar va o'rganilgan tavsif o'chadi; egasining qoidalari va
    tuzatish tarixi (loyihalar) qoladi."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('DELETE FROM biznes_namuna WHERE owner_id = $1', owner_id)
            await conn.execute(
                'UPDATE biznes_profil SET uslub = NULL, namuna_jami = 0, '
                'uslub_jami = 0 WHERE owner_id = $1', owner_id)
    biznes_keshni_bekor(owner_id)


@with_db_retry()
async def biznes_loyiha_yarat(owner_id: int, conn_id: str, chat_id: int,
                              mijoz_matni: str, loyiha: str,
                              variantlar: Optional[List[str]] = None) -> int:
    """Yangi loyiha. O'sha chatdagi eski kutayotgan loyiha ESKIRADI —
    yangisi butun suhbatni (eski xabarni ham) ko'rib yozilgan."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE biznes_loyiha SET holat = 'eskirgan' "
                "WHERE owner_id = $1 AND chat_id = $2 AND holat = 'kutmoqda'",
                owner_id, chat_id)
            yangi = await conn.fetchval(
                'INSERT INTO biznes_loyiha (owner_id, conn_id, chat_id, mijoz_matni, '
                'loyiha, variantlar) VALUES ($1, $2, $3, $4, $5, $6::jsonb) RETURNING id',
                owner_id, conn_id, chat_id, mijoz_matni, loyiha,
                json.dumps(variantlar) if variantlar is not None else None)
    return yangi


@with_db_retry()
async def biznes_birinchimi(owner_id: int, chat_id: int, message_id: int) -> bool:
    """Shu xabar birinchi marta ko'rilyaptimi — atomik (`ON CONFLICT DO
    NOTHING RETURNING`). Ikki jarayon bir vaqtda so'rasa ham bittasi True."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        return bool(await conn.fetchval(
            'INSERT INTO biznes_korilgan (owner_id, chat_id, message_id) '
            'VALUES ($1, $2, $3) ON CONFLICT DO NOTHING RETURNING 1',
            owner_id, chat_id, message_id))


@with_db_retry()
async def biznes_tozala() -> None:
    """Kunlik tozalash (hisobot kuzatuvchisidan). Ilgari 30 kunlik loyiha
    tozalash HAR qoralama tranzaksiyasida, indekssiz, butun jadval bo'yicha
    ishlardi (AUDIT S2)."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'DELETE FROM biznes_loyiha '
            'WHERE yaratilgan < NOW() - make_interval(days => $1::int)', 30)
        await conn.execute(
            'DELETE FROM biznes_korilgan '
            'WHERE vaqt < NOW() - make_interval(days => $1::int)', 2)


@with_db_retry()
async def biznes_loyiha_eskirt(owner_id: int, chat_id: int) -> None:
    """Egasi mijozga o'zi yozdi — o'sha chatdagi loyiha endi o'rinsiz."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE biznes_loyiha SET holat = 'eskirgan' "
            "WHERE owner_id = $1 AND chat_id = $2 AND holat = 'kutmoqda'",
            owner_id, chat_id)


@with_db_retry()
async def biznes_loyiha_band(loyiha_id: int, owner_id: int,
                             holat: str = "kutmoqda",
                             yangi: str = "yuborilmoqda") -> Optional[Dict[str, Any]]:
    """Loyihani ATOMIK egallaydi: `holat` → `yangi`. Yutqazgan so'rov None
    oladi va hech narsa qilmaydi.

    ⛔️ SELECT-keyin-UPDATE EMAS: tugmani ikki marta bosish — ikki parallel
    so'rov, ikkalasi ham "kutmoqda" ni o'qib, ikki xabar yuborardi.
    24 soat — Telegram qoidasi: eskisini baribir yuborib bo'lmaydi.
    `AND owner_id` — begona loyiha id'si bilan bosilgan tugma ishlamasin.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'UPDATE biznes_loyiha SET holat = $4 '
            'WHERE id = $1 AND owner_id = $2 AND holat = $3 '
            'AND yaratilgan > NOW() - make_interval(hours => $5::int) '
            'RETURNING id, conn_id, chat_id, mijoz_matni, loyiha, variantlar',
            loyiha_id, owner_id, holat, yangi, BIZNES_LOYIHA_TTL_SOAT)
    if not row:
        return None
    d = dict(row)
    # asyncpg JSONB'ni kodeksiz satr qilib qaytaradi.
    v = d.get("variantlar")
    d["variantlar"] = json.loads(v) if isinstance(v, str) else (v or [])
    return d


@with_db_retry()
async def biznes_loyiha_yakun(loyiha_id: int, owner_id: int, holat: str,
                              yakuniy: Optional[str] = None) -> None:
    """⚠️ `AND owner_id` — id odatda `biznes_loyiha_band()` (egasi tekshirilgan)
    natijasidan keladi, lekin qoida bitta: loyihaga tegadigan HAR so'rov
    egasi bo'yicha filtrlanadi (AUDIT.md S1, test_biznes_owner.py)."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE biznes_loyiha SET holat = $3, yakuniy = COALESCE($4, yakuniy) '
            'WHERE id = $1 AND owner_id = $2', loyiha_id, owner_id, holat, yakuniy)
    # `tahrirlandi` — uslubning "tuzatishlar" qismi o'zgardi.
    if holat == "tahrirlandi":
        biznes_keshni_bekor(owner_id)


@with_db_retry()
async def biznes_belgi_yoz(owner_id: int, yoqilgan: bool) -> None:
    """Avtomat javob belgisi (🤖) — egasi darajasida, keshda ham."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE biznes_ulanish SET avto_belgi = $2 WHERE owner_id = $1',
            owner_id, yoqilgan)
    for yozuv in _biznes_kesh.values():
        if yozuv["owner_id"] == owner_id:
            yozuv["avto_belgi"] = yoqilgan


@with_db_retry()
async def biznes_ish_vaqti_yoz(owner_id: int, oraliq: Optional[str]) -> None:
    """`oraliq` — "HH:MM-HH:MM" (biznes.vaqt_ajrat dan o'tgan) yoki None = doim."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE biznes_ulanish SET ish_vaqti = $2 WHERE owner_id = $1',
            owner_id, oraliq)
    for yozuv in _biznes_kesh.values():
        if yozuv["owner_id"] == owner_id:
            yozuv["ish_vaqti"] = oraliq


@with_db_retry()
async def biznes_chat_holati(owner_id: int, chat_id: int) -> Dict[str, Any]:
    """{'ochirilgan': bool, 'pauza': bool} — pauza SQL'da NOW() bilan
    solishtiriladi, ya'ni Python va baza soatlari ajralib qolmaydi."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT ochirilgan, COALESCE(pauza_gacha > NOW(), FALSE) AS pauza, '
            'pauza_sababi FROM biznes_chat WHERE owner_id = $1 AND chat_id = $2',
            owner_id, chat_id)
    pauza = bool(row and row['pauza'])
    return {"ochirilgan": bool(row and row['ochirilgan']), "pauza": pauza,
            "uzatish": pauza and row['pauza_sababi'] == 'uzatish'}


@with_db_retry()
async def biznes_loyiha_ol(lid: int, owner_id: int) -> Optional[Dict[str, Any]]:
    """«💾 Eslab qol» uchun: yuborilgan tanlovning savoli va javobi."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT mijoz_matni, yakuniy, holat, variantlar FROM biznes_loyiha '
            'WHERE id = $1 AND owner_id = $2', lid, owner_id)
    return dict(row) if row else None


@with_db_retry()
async def biznes_pauza(owner_id: int, chat_id: int, soat: int,
                       sabab: str = "egasi") -> None:
    """`sabab` — 'egasi' | 'uzatish'. Yangi pauza "bandman" bayrog'ini
    tushiradi: har uzatishga bitta."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO biznes_chat (owner_id, chat_id, pauza_gacha, pauza_sababi, '
            'band_yuborildi) VALUES ($1, $2, NOW() + make_interval(hours => $3::int), '
            '$4, FALSE) ON CONFLICT (owner_id, chat_id) DO UPDATE SET '
            'pauza_gacha = EXCLUDED.pauza_gacha, pauza_sababi = EXCLUDED.pauza_sababi, '
            'band_yuborildi = FALSE', owner_id, chat_id, soat, sabab)


@with_db_retry()
async def biznes_kutayotgan_tanlov(owner_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
    """Shu chatdagi hal qilinmagan `[tanlov:]` (eslatmada tugmalari qayta)."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, variantlar FROM biznes_loyiha WHERE owner_id = $1 "
            "AND chat_id = $2 AND holat = 'kutmoqda' AND variantlar IS NOT NULL "
            "AND yaratilgan > NOW() - make_interval(hours => $3::int) "
            "ORDER BY id DESC LIMIT 1", owner_id, chat_id, BIZNES_LOYIHA_TTL_SOAT)
    if not row:
        return None
    v = row['variantlar']
    return {"id": row['id'], "variantlar": json.loads(v) if isinstance(v, str) else list(v)}


@with_db_retry()
async def biznes_chat_ochir(owner_id: int, chat_id: int, ochirilgan: bool) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO biznes_chat (owner_id, chat_id, ochirilgan) VALUES ($1, $2, $3) '
            'ON CONFLICT (owner_id, chat_id) DO UPDATE SET ochirilgan = EXCLUDED.ochirilgan',
            owner_id, chat_id, ochirilgan)


@with_db_retry()
async def biznes_ekran_stat(owner_id: int, kun) -> Dict[str, int]:
    """/biznes bosh ekrani uchun: bugungi javob/uzatish va 30 kunlik
    qoralamalardan nechtasi o'zgartirilmay ketgani (3-bosqich mezoni)."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        faol = await conn.fetch(
            '''
            SELECT activity_type, COUNT(*) AS soni FROM user_activity
            WHERE user_id = $1 AND activity_type = ANY($3::text[])
              AND (activity_time AT TIME ZONE 'Asia/Tashkent')::date = $2
            GROUP BY activity_type
            ''', owner_id, kun,
            ["biznes_avtojavob", "biznes_yuborildi", "biznes_uzatish"])
        lo = await conn.fetchrow(
            "SELECT COUNT(*) FILTER (WHERE holat = 'yuborildi') AS tahrirsiz, "
            "COUNT(*) FILTER (WHERE holat IN ('yuborildi', 'tahrirlandi')) AS jami "
            "FROM biznes_loyiha WHERE owner_id = $1 AND variantlar IS NULL "
            "AND yaratilgan > NOW() - make_interval(days => 30)", owner_id)
    f = {r['activity_type']: r['soni'] for r in faol}
    return {"javob": f.get("biznes_avtojavob", 0) + f.get("biznes_yuborildi", 0),
            "uzatish": f.get("biznes_uzatish", 0),
            "tahrirsiz": lo['tahrirsiz'] or 0, "yuborilgan": lo['jami'] or 0}


@with_db_retry()
async def biznes_chatlar(owner_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Egasining oxirgi business chatlari — `/biznes` → «Chatlar» ro'yxati.
    Tarix kaliti `thread_id = -owner_id` (REJA.md 0.4)."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT m.chat_id, MAX(m.id) AS oxirgi,
                   (SELECT x.content FROM chat_messages x
                     WHERE x.chat_id = m.chat_id AND x.thread_id = $2
                       AND x.role = 'user'
                     ORDER BY x.id DESC LIMIT 1) AS matn,
                   COALESCE(BOOL_OR(c.ochirilgan), FALSE) AS ochirilgan
            FROM chat_messages m
            LEFT JOIN biznes_chat c ON c.owner_id = $1 AND c.chat_id = m.chat_id
            WHERE m.thread_id = $2 AND m.thread_id < 0
            GROUP BY m.chat_id
            ORDER BY oxirgi DESC
            LIMIT $3
            ''', owner_id, -owner_id, limit)
    return [dict(r) for r in rows]


# ── 4-BOSQICH: hisobot, javobsiz chatlar, kartoteka, panel ──────────
_TELEFON_RE = re.compile(r"^\+?[\d\s\-()]{7,24}$")


def clean_mijoz_maydon(ism, telefon, qiziqish) -> tuple:
    """MODEL yozgan kartoteka maydonlari — ishonchsiz chegara (REJA.md 4.3).

    Telefon regex bilan tekshiriladi va faqat raqamlarga keltiriladi
    (9-15 raqam, bo'lmasa None — soxta raqam kartotekada yolg'on
    bo'lardi). Qolgani bir qatorga yig'iladi va uzunligi kesiladi: yangi
    qator CSV'da ham, egasiga ko'rsatishda ham shaklni buzardi.
    Sof funksiya — testda tekshiriladi.
    """
    def _qator(q, n):
        q = " ".join(str(q or "").split())[:n]
        return q or None

    tel = None
    t = str(telefon or "").strip()
    if t and _TELEFON_RE.match(t):
        raqam = re.sub(r"\D", "", t)
        if 9 <= len(raqam) <= 15:
            tel = ("+" if t.startswith("+") or len(raqam) >= 12 else "") + raqam
    return _qator(ism, 60), tel, _qator(qiziqish, 200)


@with_db_retry()
async def biznes_mijoz_korildi(owner_id: int, chat_id: int,
                               tg_ism: Optional[str], username: Optional[str]) -> None:
    """Mijoz yozdi — Telegram bergan ism/username va vaqt. Har mijoz
    xabarida: bitta yengil UPSERT."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'INSERT INTO biznes_mijoz (owner_id, chat_id, tg_ism, username) '
            'VALUES ($1, $2, $3, $4) ON CONFLICT (owner_id, chat_id) DO UPDATE SET '
            'tg_ism = EXCLUDED.tg_ism, username = EXCLUDED.username, oxirgi = NOW()',
            owner_id, chat_id, (tg_ism or "")[:100] or None, (username or "")[:64] or None)


@with_db_retry()
async def biznes_mijoz_yangila(owner_id: int, chat_id: int, ism, telefon,
                               qiziqish) -> None:
    """Model ajratgan maydonlar. Bo'sh (None) maydon eskisini O'CHIRMAYDI —
    kechagi yozishmada telefon yo'q degani mijozda telefon yo'q degani emas."""
    ism, telefon, qiziqish = clean_mijoz_maydon(ism, telefon, qiziqish)
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE biznes_mijoz SET ism = COALESCE($3, ism), '
            'telefon = COALESCE($4, telefon), qiziqish = COALESCE($5, qiziqish) '
            'WHERE owner_id = $1 AND chat_id = $2',
            owner_id, chat_id, ism, telefon, qiziqish)


@with_db_retry()
async def biznes_mijozlar(owner_id: int, limit: int = 1000) -> List[Dict[str, Any]]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT chat_id, tg_ism, username, ism, telefon, qiziqish, oxirgi '
            'FROM biznes_mijoz WHERE owner_id = $1 ORDER BY oxirgi DESC LIMIT $2',
            owner_id, limit)
    return [dict(r) for r in rows]


@with_db_retry()
async def biznes_hisobot_band(owner_id: int, kun) -> bool:
    """Bugungi ertalabki hisobotni ATOMIK egallaydi. Deploy yoki ikkinchi
    aylanish uni ikki marta yubormasin (`digest_sent_date` naqshi)."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        qator = await conn.fetch(
            'UPDATE biznes_ulanish SET hisobot_sana = $2 '
            'WHERE owner_id = $1 AND (hisobot_sana IS NULL OR hisobot_sana < $2) '
            'RETURNING 1', owner_id, kun)
    return bool(qator)


@with_db_retry()
async def biznes_kun_hisobi(owner_id: int, kun, chat_limit: int = 20,
                            xabar_limit: int = 8) -> Dict[str, Any]:
    """Bir kunlik (Toshkent) biznes hisobi. `chatlar` — mini model
    xulosasi va kartoteka uchun: har chatdan oxirgi `xabar_limit` ta."""
    global pool
    if pool is None:
        await create_db_pool()
    thread = -owner_id
    async with pool.acquire() as conn:
        son = await conn.fetchrow(
            '''
            SELECT COUNT(DISTINCT chat_id) AS mijozlar, COUNT(*) AS xabarlar
            FROM chat_messages
            WHERE thread_id = $1 AND thread_id < 0 AND role = 'user'
              AND (created_at AT TIME ZONE 'Asia/Tashkent')::date = $2
            ''', thread, kun)
        faollik = await conn.fetch(
            '''
            SELECT activity_type, COUNT(*) AS soni FROM user_activity
            WHERE user_id = $1 AND activity_type = ANY($3::text[])
              AND (activity_time AT TIME ZONE 'Asia/Tashkent')::date = $2
            GROUP BY activity_type
            ''', owner_id, kun,
            ["biznes_avtojavob", "biznes_yuborildi", "biznes_uzatish", "biznes_loyiha"])
        xabarlar = await conn.fetch(
            '''
            SELECT chat_id, role, content FROM (
                SELECT chat_id, role, content, id,
                       ROW_NUMBER() OVER (PARTITION BY chat_id ORDER BY id DESC) AS n
                FROM chat_messages
                WHERE thread_id = $1 AND thread_id < 0 AND chat_id IN (
                    SELECT chat_id FROM chat_messages
                    WHERE thread_id = $1 AND thread_id < 0 AND role = 'user'
                      AND (created_at AT TIME ZONE 'Asia/Tashkent')::date = $2
                    GROUP BY chat_id ORDER BY MAX(id) DESC LIMIT $3)
            ) t WHERE n <= $4 ORDER BY chat_id, id
            ''', thread, kun, chat_limit, xabar_limit)
    f = {r['activity_type']: r['soni'] for r in faollik}
    chatlar: Dict[int, list] = {}
    for r in xabarlar:
        chatlar.setdefault(r['chat_id'], []).append((r['role'], r['content']))
    return {
        "mijozlar": son['mijozlar'] or 0, "xabarlar": son['xabarlar'] or 0,
        "javoblar": f.get("biznes_avtojavob", 0) + f.get("biznes_yuborildi", 0),
        "uzatish": f.get("biznes_uzatish", 0), "loyiha": f.get("biznes_loyiha", 0),
        "chatlar": chatlar,
    }


@with_db_retry()
async def biznes_javobsizlar(dan_daqiqa: int, gacha_daqiqa: int,
                             owner_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Oxirgi xabari MIJOZNIKI bo'lgan chatlar: u `gacha_daqiqa` dan
    ko'proq, lekin `dan_daqiqa` dan kamroq oldin yozilgan.

    Oyna ikki tomonlama ataylab: pastki chegara — "hali javob berishga
    ulgurmagan" chatni ogohlantirmaslik; yuqorisi — deploy'dan keyin RAM
    bayrog'i (`_javobsiz_aytilgan`) bo'sh bo'lganda eski chatlar yana
    ogohlantirilmasin.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT t.chat_id, -t.thread_id AS owner_id, t.content, t.created_at,
                   m.tg_ism, m.username
            FROM (SELECT DISTINCT ON (chat_id, thread_id)
                         chat_id, thread_id, role, content, created_at
                  FROM chat_messages
                  WHERE thread_id < 0
                    AND created_at > NOW() - make_interval(mins => $1::int)
                    AND ($3::bigint IS NULL OR thread_id = $3)
                  ORDER BY chat_id, thread_id, id DESC) t
            LEFT JOIN biznes_mijoz m
                   ON m.owner_id = -t.thread_id AND m.chat_id = t.chat_id
            WHERE t.role = 'user'
              AND t.created_at < NOW() - make_interval(mins => $2::int)
            ORDER BY t.created_at LIMIT 50
            ''', dan_daqiqa, gacha_daqiqa,
            None if owner_id is None else -owner_id)
    return [dict(r) for r in rows]


@with_db_retry()
async def biznes_panel_stats() -> Dict[str, Any]:
    """Panel kartasi (REJA.md 4.5): faol ulanishlar, bugungi biznes
    so'rovlari, bugungi token ichida biznes ulushi. Kun — Toshkent.

    ⚠️ `user_history.created_at` mintaqasiz UTC (`token_stats` izohi),
    `user_activity.activity_time` esa TIMESTAMPTZ — ikkisi ikki xil
    ifoda bilan kesiladi, bittasi ikkinchisiga ko'chirilmasin.
    ⛔️ SUM `::bigint` — aks holda `Decimal`, va panel 500 bilan yiqiladi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        ulanish = await conn.fetchval(
            'SELECT COUNT(DISTINCT owner_id) FROM biznes_ulanish WHERE yoqilgan')
        sorov = await conn.fetchval(
            '''SELECT COUNT(*) FROM user_activity
               WHERE activity_type = ANY($1::text[])
                 AND (activity_time AT TIME ZONE 'Asia/Tashkent')::date =
                     (NOW() AT TIME ZONE 'Asia/Tashkent')::date''',
            ["biznes_buyruq", "biznes_loyiha", "biznes_avtojavob"])
        token = await conn.fetchrow(
            '''SELECT COALESCE(SUM(kirish + chiqish), 0)::bigint AS jami,
                      COALESCE(SUM(kirish + chiqish) FILTER
                               (WHERE manba = 'biznes'), 0)::bigint AS biznes
               FROM user_history
               WHERE ((created_at AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Tashkent')::date =
                     (NOW() AT TIME ZONE 'Asia/Tashkent')::date''')
    return {"ulanishlar": ulanish or 0, "sorovlar": sorov or 0,
            "token": token['biznes'] or 0, "token_jami": token['jami'] or 0}


# Oxirgi bazaga YOZILGAN kuzatuv holati. Faqat holat o'zgarganda
# yoziladi.
#
# ⛔️ CHASTOTA CHEKLOVI SHART. `_send_watch_copy()` kuzatilayotgan
# odamning HAR xabarida ishlaydi — guruh yiqilgan bo'lsa har xabarda
# `UPDATE` ketardi. Holat o'zgarishi (yiqildi / tuzaldi) esa kamdan-kam
# hodisa, ya'ni alohida taymer kerak emas: juftlik o'zgarmasa yozilmaydi.
_watch_holat_ram: tuple = (None, None)


@with_db_retry()
async def watch_holat_yoz(ok: bool, sabab: Optional[str] = None) -> None:
    """Kuzatuv guruhiga yuborish natijasini yozadi.

    `ok=True`  — yetkazildi; banner o'chadi.
    `ok=False` — GURUH darajasidagi xato (`config.guruh_xato_sababi()`
                 tanigan sabab). Xabarga xos xatolar bu yerga KELMAYDI:
                 ular keyingi xabarda o'zi tuzaladi va bannerni doim
                 yonib turadigan — ya'ni ma'nosiz — qilib qo'yardi.

    ⚠️ Chaqiruvchi buni `try/except` ichida chaqiradi: hisob yuritish
    javob yo'lidan muhimroq emas (`_token_saqla()` bilan bir xil qoida).
    """
    global _watch_holat_ram, pool
    yangi = (bool(ok), None if ok else (sabab or "")[:200])
    if yangi == _watch_holat_ram:
        return
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        if ok:
            await conn.execute(
                "UPDATE watch_settings SET oxirgi_ok_vaqt = NOW() WHERE id = 1")
        else:
            await conn.execute(
                "UPDATE watch_settings SET oxirgi_xato_vaqt = NOW(), "
                "oxirgi_xato_sabab = $1 WHERE id = 1", yangi[1])
    # Faqat YOZILGANDAN keyin — aks holda yiqilgan yozuv «yozilgan»
    # bo'lib qolardi va holat boshqa hech qachon yangilanmasdi.
    _watch_holat_ram = yangi


@with_db_retry()
async def get_watch_health() -> Dict[str, Any]:
    """Boshqaruv ekranidagi banner uchun: guruh bormi, oxirgi xato qachon."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT group_id, oxirgi_xato_vaqt, oxirgi_xato_sabab, "
            "oxirgi_ok_vaqt FROM watch_settings WHERE id = 1")
    if row is None:
        return {"guruh": False, "sabab": None, "vaqt": None}
    xato, ok = row["oxirgi_xato_vaqt"], row["oxirgi_ok_vaqt"]
    # Xato oxirgi muvaffaqiyatdan KEYIN bo'lsagina banner yonadi —
    # alohida «tozalash» amali yo'q, ya'ni unutib qo'yiladigan qadam ham
    # yo'q: muvaffaqiyatli yuborish bannerni o'zi o'chiradi.
    tirik = bool(xato) and (ok is None or xato > ok)
    # ⚠️ `vaqt` — xom `datetime`, tayyor satr emas: formatlash panelning
    # ishi (`web/api.py::_sana` izohiga qarang).
    return {
        "guruh": row["group_id"] is not None,
        "sabab": row["oxirgi_xato_sabab"] if tirik else None,
        "vaqt": xato if tirik else None,
    }


@with_db_retry()
async def get_watch_group_id() -> Optional[int]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval('SELECT group_id FROM watch_settings WHERE id = 1')


@with_db_retry()
async def set_watch_group_id(group_id: int) -> None:
    global pool, _watch_group_id, _watch_holat_ram
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        # ⚠️ Yangi guruh — eski sabab BEKOR. Aks holda banner o'chgan
        # guruhning xatosini yangi, sog'lom guruh ustida ko'rsatib turardi.
        await conn.execute(
            'UPDATE watch_settings SET group_id = $1, oxirgi_ok_vaqt = NOW(), '
            'oxirgi_xato_vaqt = NULL, oxirgi_xato_sabab = NULL WHERE id = 1',
            group_id)
    _watch_group_id = group_id
    _watch_holat_ram = (True, None)


@with_db_retry()
async def add_watch(user_id: int, added_by: int) -> None:
    global pool, _watched_user_ids
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''
            INSERT INTO watchlist (user_id, added_by, added_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id) DO UPDATE SET added_by = EXCLUDED.added_by, added_at = NOW()
            ''',
            user_id, added_by,
        )
    _watched_user_ids.add(user_id)


@with_db_retry()
async def remove_watch(user_id: int) -> None:
    global pool, _watched_user_ids
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM watchlist WHERE user_id = $1', user_id)
    _watched_user_ids.discard(user_id)


@with_db_retry()
async def get_watchlist() -> List[Dict[str, Any]]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''
            SELECT w.user_id, w.added_at, u.username
            FROM watchlist w
            LEFT JOIN users u ON u.user_id = w.user_id
            ORDER BY w.added_at DESC
            '''
        )
        return [
            {'user_id': r['user_id'], 'username': r['username'], 'added_at': r['added_at']}
            for r in rows
        ]


@with_db_retry()
async def create_history_table():
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                tokens_used BIGINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Token hisobi uchun qo'shimcha ustunlar. Jadval o'zi ANCHADAN
        # beri bor edi, lekin unga HECH KIM yozmasdi — ya'ni kunlik
        # bepul grant qancha yeyilayotganini faqat Railway logidan
        # bilish mumkin edi. Endi shu yerga yoziladi.
        #
        # ⚠️ Keshlangan ulush ALOHIDA saqlanadi. OpenAI tasdiqlagan
        # (2026-09-09): keshdan kelgan token ham grantdan AYNAN
        # shunchalik yeydi. Ya'ni bu raqam kvotani kamaytirmaydi, lekin
        # so'rov boshi kun bo'yi bir xil qolayotganini ko'rsatadi —
        # tushib ketsa, demak prefiks har xabarda o'zgarib turibdi.
        for ustun in ("kirish BIGINT DEFAULT 0",
                      "chiqish BIGINT DEFAULT 0",
                      "keshdan BIGINT DEFAULT 0",
                      "model VARCHAR(60)",
                      # 'biznes' — Telegram Business yo'lidagi chaqiruv
                      # (panelning biznes token ulushi, REJA.md 4.5).
                      "manba VARCHAR(20)"):
            await conn.execute(
                f"ALTER TABLE user_history ADD COLUMN IF NOT EXISTS {ustun}")
        # Kunlik yig'indi shu indeks ustida ishlaydi. Usiz har ochilishda
        # butun jadval o'qilardi.
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_history_kun "
            "ON user_history (created_at)")
        # ⚠️ Kompozit indeks BU YERDA EMAS — `indekslarni_qur()` da,
        # fon vazifasida.

@with_db_retry()
async def get_superadmin_id() -> Optional[int]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval('SELECT user_id FROM superadmins LIMIT 1')


@with_db_retry()
async def add_superadmin(user_id: int) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('INSERT INTO superadmins (user_id) VALUES ($1) ON CONFLICT DO NOTHING', user_id)


@with_db_retry()
async def remove_superadmin(user_id: int) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM superadmins WHERE user_id = $1', user_id)

@with_db_retry()
async def ensure_profile_columns():
    """
    users jadvaliga profil uchun kerakli yangi ustunlarni xavfsiz qo'shadi.
    Agar ustunlar mavjud bo'lsa, xatolik bermaydi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        columns = [
            "ADD COLUMN IF NOT EXISTS current_model VARCHAR(50) DEFAULT 'GPT-4.1 mini'",
            "ADD COLUMN IF NOT EXISTS plan_type VARCHAR(20) DEFAULT 'free'",
            "ADD COLUMN IF NOT EXISTS daily_requests_used INT DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS total_tokens_used BIGINT DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS media_analysis_active BOOLEAN DEFAULT TRUE",
            # Kunlik limit qaysi (Toshkent) sanaga tegishli ekanini saqlaydi —
            # check_and_consume_quota() shu sanani bugungi sana bilan solishtirib,
            # farq bo'lsa hisobni avtomatik nolanadi (alohida cron/scheduler shart emas).
            "ADD COLUMN IF NOT EXISTS daily_usage_date DATE DEFAULT (NOW() AT TIME ZONE 'Asia/Tashkent')::DATE",
            # is_active'dan ATAYLAB mustaqil: is_active save_user() tomonidan har
            # kiruvchi xabarda avtomatik TRUE qilinadi (botni bloklagan/bloklamagan
            # holatini kuzatadi). is_banned esa FAQAT admin panel orqali qo'lda
            # o'zgaradi — shuning uchun ban avtomatik "bekor" bo'lib qolmaydi.
            "ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE",
            # SHAXSIY referal sharti (bloger/hamkor uchun). NULL = umumiy
            # sozlama, u ham NULL bo'lsa core/config.py qiymati. Uch bosqichli
            # zanjir ATAYLAB: hech bir bosqich qolganini o'chirib tashlamaydi.
            "ADD COLUMN IF NOT EXISTS referral_required INT",
            "ADD COLUMN IF NOT EXISTS referral_reward_days INT",
            # Taklif TO'LQINI. Admin taklif yuborganda raqam oshadi; mukofot
            # olinganda referral_rewarded_round shu raqamga tenglashadi.
            # Ikkalasi teng bo'lsa — bu to'lqinda mukofot allaqachon olingan.
            # Aks holda bitta havola bilan cheksiz kun yig'ish mumkin edi.
            "ADD COLUMN IF NOT EXISTS referral_round INT DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS referral_rewarded_round INT",
            # NULL = muddatsiz premium (yoki free/hech qachon premium bo'lmagan).
            # Muddat o'tsa, check_and_consume_quota() foydalanuvchini avtomatik
            # free'ga tushiradi (kunlik limit auto-reset qanday ishlasa, shunday).
            "ADD COLUMN IF NOT EXISTS premium_until TIMESTAMPTZ",
            # Fayl yaratish/tahrirlash uchun ALOHIDA kunlik sanoq — ball
            # byudjetidan mustaqil, shuning uchun fayl limiti tugagach ham
            # oddiy suhbat ishlashda davom etadi. daily_usage_date bilan
            # bir xil naqsh: sana farq qilsa hisob avtomatik nolanadi.
            "ADD COLUMN IF NOT EXISTS daily_files_used INTEGER DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS daily_files_date DATE DEFAULT (NOW() AT TIME ZONE 'Asia/Tashkent')::DATE",
            # QAYSI premium_until uchun "muddat tugayapti" ogohlantirishi
            # yuborilganini saqlaydi. `premium_reminded_for IS DISTINCT FROM
            # premium_until` — to'liq "eslatish kerakmi?" testi: tarif
            # uzaytirilsa qiymat mos kelmay qoladi va eslatma o'zi qayta
            # yoqiladi, alohida nolash kerak emas.
            "ADD COLUMN IF NOT EXISTS premium_reminded_for TIMESTAMPTZ",
            # Pro imkoniyatlari uchun ALOHIDA kunlik sanoqlar —
            # daily_files_used/date bilan aynan bir xil naqsh (sana farq
            # qilsa avtomatik nolanadi, alohida cron kerak emas).
            "ADD COLUMN IF NOT EXISTS daily_images_used INTEGER DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS daily_images_date DATE DEFAULT (NOW() AT TIME ZONE 'Asia/Tashkent')::DATE",
            "ADD COLUMN IF NOT EXISTS daily_research_used INTEGER DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS daily_research_date DATE DEFAULT (NOW() AT TIME ZONE 'Asia/Tashkent')::DATE",
            # Telegram Business avtojavoblari (REJA.md 3-bosqich).
            "ADD COLUMN IF NOT EXISTS daily_biznes_used INTEGER DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS daily_biznes_date DATE DEFAULT (NOW() AT TIME ZONE 'Asia/Tashkent')::DATE",
            # Kunlik daydjest (Pro): digest_hour NULL = obuna o'chirilgan.
            # digest_sent_date takroriy yuborishdan himoya qiladi.
            "ADD COLUMN IF NOT EXISTS digest_hour SMALLINT",
            "ADD COLUMN IF NOT EXISTS digest_topics TEXT",
            "ADD COLUMN IF NOT EXISTS digest_sent_date DATE",
            # Bir kunda BIR NECHTA soat: "7,12,21". digest_hour eskirdi,
            # lekin o'chirilmadi — quyidagi ko'chirish undan o'qiydi.
            # digest_sent_hour bo'lmasa, kunning birinchi daydjesti
            # qolganlarini ham "yuborilgan" deb yopib qo'yardi.
            "ADD COLUMN IF NOT EXISTS digest_hours TEXT",
            "ADD COLUMN IF NOT EXISTS digest_sent_hour SMALLINT",
            # "Sog'indik" xabarlari: 7 -> 15 -> 30 kun, keyin yana boshidan.
            # inactive_stage — INACTIVE_STEPS ro'yxatidagi o'rin.
            "ADD COLUMN IF NOT EXISTS inactive_stage SMALLINT DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS inactive_notified_at TIMESTAMPTZ",
        ]
        for col in columns:
            try:
                await conn.execute(f"ALTER TABLE users {col};")
            except Exception as e:
                pass

        # BIR MARTALIK TO'LDIRISH — referral_round qo'shilgunga qadar
        # mukofot OLGAN foydalanuvchilar uchun. Ularda rewarded_round NULL
        # bo'lib qolardi, ya'ni "hali olmagan" deb hisoblanib, o'sha eski
        # taklif bo'yicha yana bir mukofot olishardi. Nol-to'lqinni yopamiz.
        #
        # Mukofot OLMAGANLARGA tegilmaydi: allaqachon tarqatilgan taklif
        # ular uchun ishlab tursin.
        #
        # Keyingi ishga tushirishlarda bu so'rov hech kimga tegmaydi —
        # mukofot olganlarning rewarded_round'i endi NULL emas.
        try:
            await conn.execute('''
                UPDATE users SET referral_rewarded_round = 0
                 WHERE referral_rewarded_round IS NULL
                   AND EXISTS (SELECT 1 FROM referrals r
                                WHERE r.referrer_id = users.user_id
                                  AND r.rewarded_at IS NOT NULL)
            ''')
        except Exception:
            logger.exception("referral_rewarded_round to'ldirilmadi")

        # Eski bitta soatli obunalarni yangi ro'yxatga ko'chirish. Bir
        # martalik: keyingi ishga tushirishlarda digest_hours endi NULL
        # emas, ya'ni hech kimga tegmaydi.
        try:
            await conn.execute('''
                UPDATE users SET digest_hours = digest_hour::text
                 WHERE digest_hours IS NULL AND digest_hour IS NOT NULL
            ''')
        except Exception:
            logger.exception("digest_hours ko'chirilmadi")


# ─────────────────────────────────────────────────────────────
# 🧠 UZOQ MUDDATLI XOTIRA
# ─────────────────────────────────────────────────────────────
# `content` ni MODEL yozadi (services/ai.py: update_memory asbobi), ya'ni
# bu ISHONCHSIZ manba. Shuning uchun cheklovlar shu yerda turadi — tool
# sxemasining "description" iga ishonib qolinmaydi: ko'rsatma kafolat emas.

MAX_MEMORIES = 40        # to'lganda model o'zi keraksizini o'chirib joy ochadi
MAX_MEMORY_LEN = 200

# Karta / hisob / telefon / pasport raqami. Model buni saqlamaslikka
# ko'rsatma olgan, lekin ikkinchi to'siq shu yerda — ko'rsatma kafolat emas.
#
# Chegara ATAYLAB 9 raqam: sana (2026-08-06 = 8 ta) va yil o'tib ketsin,
# karta (16), hisob (20), telefon (12) esa ushlansin. Pasport (AA1234567)
# atigi 7 raqam, shuning uchun u alohida naqsh bilan tutiladi.
_SECRET_RE = re.compile(
    r"\d(?:[\s-]?\d){8,}"          # 9+ raqam: karta, hisob, telefon
    r"|[A-Za-z]{2}\s?\d{7}\b"      # pasport: AA1234567
)


# Takrorni topishda e'tiborsiz qoldiriladigan so'zlar — deyarli har bir
# yozuvda uchraydi, shuning uchun o'xshashlik hisobiga kirsa hamma narsa
# hamma narsaga "o'xshab" ketardi.
_MEM_STOPWORDS = {"foydalanuvchi", "foydalanuvchining", "uning", "bilan",
                  "uchun", "ham", "bir", "boshqa"}


def _mem_keywords(text: str) -> set:
    return {w for w in re.findall(r"\w+", str(text or "").lower(), re.UNICODE)
            if len(w) > 2 and w not in _MEM_STOPWORDS}


def similar_index(content: str, existing: list) -> Optional[int]:
    """Mazmunan o'xshash mavjud yozuvning RAQAMI (1 dan), yoki None.

    Nega kerak: model "Foydalanuvchi Toshkentda yashaydi" ni saqlab qo'yib,
    keyin "Samarqandga ko'chdi" ni `update` emas, `add` bilan yozib yuboradi.
    Ikkala qarama-qarshi fakt yonma-yon qolsa bot chalkashadi. Bu yerda
    yozuv TO'SILMAYDI — model natijada eslatma oladi va o'zi tozalaydi
    (to'sib qo'yilsa model qayta-qayta urinib halqaga tushardi).

    ponytail: so'z kesishuvi, embedding emas — 40 ta yozuv uchun yetarli.
    Noto'g'ri ishora zarar qilmaydi: qaror baribir modelniki.
    """
    new = _mem_keywords(content)
    if not new:
        return None
    for i, old in enumerate(existing, 1):
        cur = _mem_keywords(old)
        if cur and len(new & cur) / min(len(new), len(cur)) >= 0.5:
            return i
    return None


def clean_memory(content: str) -> str:
    """Xotira yozuvini tozalaydi. Bo'sh satr qaytsa — yozuv rad etiladi.

    Sof funksiya — DB'siz test qilinadi (tests/test_memory.py).
    """
    # Yangi qatorlar OLIB TASHLANADI: xotira modelga `developer` xabari
    # sifatida ko'rsatiladi, ko'p qatorli matn esa u yerda soxta
    # "instruksiya" bo'lib ko'rinishi mumkin (prompt injection).
    content = " ".join(str(content or "").split())
    if _SECRET_RE.search(content):
        return ""
    return content[:MAX_MEMORY_LEN]


@with_db_retry()
async def get_memories(user_id: int) -> List[Dict[str, Any]]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT id, content, created_at, updated_at FROM user_memories '
            'WHERE user_id = $1 ORDER BY id', user_id)
    return [dict(r) for r in rows]


@with_db_retry()
async def add_memory(user_id: int, content: str) -> str:
    """Yangi fakt qo'shadi. Qaytgan satr to'g'ridan-to'g'ri modelga boradi."""
    content = clean_memory(content)
    if not content:
        return "rad etildi (bo'sh yoki maxfiy ma'lumot)"

    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        # Takrorni bazaning o'zida tekshiramiz — model xotirani ko'rib
        # tursa ham ba'zan aynan bir xil jumlani qayta yozib yuboradi.
        if await conn.fetchval(
                'SELECT 1 FROM user_memories WHERE user_id = $1 AND content = $2',
                user_id, content):
            return "allaqachon saqlangan"
        rows = await conn.fetch(
            'SELECT content FROM user_memories WHERE user_id = $1 ORDER BY id',
            user_id)
        if len(rows) >= MAX_MEMORIES:
            return (f"xotira to'la ({MAX_MEMORIES} ta) — avval keraksiz "
                    "yozuvni o'chiring")
        await conn.execute(
            'INSERT INTO user_memories (user_id, content) VALUES ($1, $2)',
            user_id, content)

    # Yozuv SAQLANDI, keyin eslatma beriladi — model o'zi qaror qiladi.
    dup = similar_index(content, [r["content"] for r in rows])
    if dup:
        return (f"saqlandi — lekin {dup}-yozuv shunga o'xshash. Agar u "
                "eskirgan bo'lsa, uni delete qiling; ikkalasi ham to'g'ri "
                "bo'lsa, hech narsa qilmang")
    return "saqlandi"


# ⚠️ Quyidagi ikkalasida `AND user_id = $N` MAJBURIY: mem_id modelning
# bergan raqamidan kelib chiqadi, ya'ni xato bo'lishi mumkin. Egalik
# tekshiruvisiz model boshqa odamning xotirasiga tegib ketardi.
@with_db_retry()
async def update_memory(user_id: int, mem_id: int, content: str) -> str:
    content = clean_memory(content)
    if not content:
        return "rad etildi (bo'sh yoki maxfiy ma'lumot)"

    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        res = await conn.execute(
            'UPDATE user_memories SET content = $1, updated_at = NOW() '
            'WHERE id = $2 AND user_id = $3',
            content, mem_id, user_id)
    return "yangilandi" if res.endswith("1") else "topilmadi"


@with_db_retry()
async def delete_memory(user_id: int, mem_id: int) -> str:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        res = await conn.execute(
            'DELETE FROM user_memories WHERE id = $1 AND user_id = $2',
            mem_id, user_id)
    return "o'chirildi" if res.endswith("1") else "topilmadi"


@with_db_retry()
async def clear_memories(user_id: int) -> None:
    """Hammasini o'chirish — "hammasini unut" so'roviga."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM user_memories WHERE user_id = $1', user_id)


# ─────────────────────────────────────────────────────────────
# ⏰ ESLATMALAR VA REJALASHTIRILGAN VAZIFALAR
# ─────────────────────────────────────────────────────────────
# `text` va `run_at` ni MODEL yozadi — ya'ni bu ham xotira kabi ISHONCHSIZ
# manba. Tekshiruvlar shu yerda turadi, tool sxemasining "description" iga
# ishonib qolinmaydi: ko'rsatma kafolat emas.

def clean_reminder_text(text: str) -> str:
    """Eslatma matnini tozalaydi. Bo'sh satr qaytsa — rad etiladi.

    Sof funksiya — DB'siz test qilinadi (tests/test_reminders.py).
    """
    return " ".join(str(text or "").split())[:REMINDER_MAX_LEN]


def parse_run_at(when: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Model bergan vaqt satrini Toshkent vaqtidagi datetime'ga aylantiradi.

    Kutiladigan format: "YYYY-MM-DD HH:MM" (yoki "T" ajratgichi bilan).
    None qaytsa — vaqt yaroqsiz va eslatma YARATILMAYDI. Jim qolib
    noto'g'ri vaqtga qo'yishdan ko'ra ochiq xato qaytargan yaxshi.
    """
    raw = str(when or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=TASHKENT_TZ)
            break
        except ValueError:
            continue
    else:
        return None

    now = now or datetime.now(TASHKENT_TZ)
    # O'tmish rad etiladi (1 daqiqa bardosh — model "hozir" deb hisoblab
    # bir necha soniya orqada qolgan vaqt yozishi normal).
    if dt < now - timedelta(minutes=1):
        return None
    if dt > now + timedelta(days=REMINDER_MAX_AHEAD_DAYS):
        return None
    return dt


def _add_months(dt: datetime, n: int) -> datetime:
    """Oy qo'shadi, oy oxirini QIRQADI: 31-yanvar + 1 oy = 28/29-fevral."""
    import calendar
    month = dt.month - 1 + n
    year = dt.year + month // 12
    month = month % 12 + 1
    return dt.replace(year=year, month=month,
                      day=min(dt.day, calendar.monthrange(year, month)[1]))


def next_run_at(current: datetime, repeat: str,
                now: Optional[datetime] = None) -> Optional[datetime]:
    """Keyingi ishga tushish vaqti. None = takrorlanmaydi, o'chirilsin.

    Bot bir necha kun o'chib turgan bo'lsa `current` ancha orqada qoladi —
    shuning uchun kelajakka CHIQIB OLGUNCHA suriladi, aks holda watcher
    bitta eslatmani ketma-ket o'nlab marta yuborardi.
    """
    if repeat == "once" or repeat not in REMINDER_REPEATS:
        return None
    now = now or datetime.now(TASHKENT_TZ)
    nxt = current
    # Tavan: buzuq ma'lumot cheksiz siklga aylanmasin.
    for _ in range(500):
        if repeat == "daily":
            nxt += timedelta(days=1)
        elif repeat == "weekly":
            nxt += timedelta(days=7)
        else:
            nxt = _add_months(nxt, 1)
        if nxt > now:
            return nxt
    return None


@with_db_retry()
async def create_scheduled_task(user_id: int, text: str, when: str,
                                repeat: str = "once") -> str:
    """Eslatma yaratadi. Qaytgan satr to'g'ridan-to'g'ri modelga boradi."""
    text = clean_reminder_text(text)
    if not text:
        return "rad etildi (matn bo'sh)"
    if repeat not in REMINDER_REPEATS:
        return f"noma'lum takrorlanish — {', '.join(REMINDER_REPEATS)} dan biri bo'lishi kerak"
    run_at = parse_run_at(when)
    if run_at is None:
        return ("vaqt yaroqsiz — 'YYYY-MM-DD HH:MM' formatida, o'tmishda "
                "bo'lmagan va 2 yildan uzoq bo'lmagan vaqt bering")

    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            'SELECT COUNT(*) FROM scheduled_tasks WHERE user_id = $1 AND active',
            user_id)
        if n >= MAX_ACTIVE_REMINDERS:
            return (f"eslatmalar to'la ({MAX_ACTIVE_REMINDERS} ta) — "
                    "avval keraksizini bekor qiling")
        await conn.execute(
            'INSERT INTO scheduled_tasks (user_id, text, run_at, repeat) '
            'VALUES ($1, $2, $3, $4)',
            user_id, text, run_at, repeat)
    return f"qo'yildi: {run_at:%Y-%m-%d %H:%M}" + (
        f" ({repeat})" if repeat != "once" else "")


@with_db_retry()
async def list_scheduled_tasks(user_id: int) -> List[Dict[str, Any]]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT id, text, run_at, repeat FROM scheduled_tasks '
            'WHERE user_id = $1 AND active ORDER BY run_at', user_id)
    return [dict(r) for r in rows]


# ⚠️ `AND user_id = $N` MAJBURIY: raqam modelning bergan indeksidan kelib
# chiqadi, ya'ni xato bo'lishi mumkin. Egalik tekshiruvisiz model boshqa
# odamning eslatmasini bekor qilib qo'yardi (xotira bilan bir xil xavf).
@with_db_retry()
async def cancel_scheduled_task(user_id: int, task_id: int) -> str:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        # O'chirib tashlaymiz, bayroq qo'ymaymiz: bekor qilingan eslatma
        # hech qachon kerak bo'lmaydi, lekin jadvalda yotib qolardi.
        # AND user_id — model bergan raqam bilan BEGONA eslatmani
        # o'chirib bo'lmasin.
        res = await conn.execute(
            'DELETE FROM scheduled_tasks WHERE id = $1 AND user_id = $2',
            task_id, user_id)
    return "bekor qilindi" if res.endswith("1") else "topilmadi"


@with_db_retry()
async def due_scheduled_tasks(limit: int = 100) -> List[Dict[str, Any]]:
    """Muddati kelgan faol eslatmalar."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT id, user_id, text, run_at, repeat FROM scheduled_tasks '
            'WHERE active AND run_at <= NOW() ORDER BY run_at LIMIT $1', limit)
    return [dict(r) for r in rows]


@with_db_retry()
async def advance_scheduled_task(task_id: int, run_at: datetime,
                                 repeat: str) -> None:
    """Yuborilgandan keyin: keyingi vaqtga suradi yoki BUTUNLAY o'chiradi.

    Bir martalik eslatma yuborilgach qator O'CHIRILADI (ilgari
    active=FALSE qilinardi). Sabab: ular hech qachon qayta kerak
    bo'lmaydi, lekin jadvalda abadiy yotib, o'sib boraveradi.
    """
    nxt = next_run_at(run_at, repeat)
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        if nxt is None:
            await conn.execute(
                'DELETE FROM scheduled_tasks WHERE id = $1', task_id)
        else:
            await conn.execute(
                'UPDATE scheduled_tasks SET run_at = $2, last_sent_at = NOW() '
                'WHERE id = $1', task_id, nxt)


@with_db_retry()
@with_db_retry()
async def pro_tarifmi(user_id: int) -> bool:
    """Shu odamda Pro imkoniyatlari ochiqmi — FAQAT ko'rsatish uchun.

    ⚠️ Bu DARVOZA EMAS. Haqiqiy tekshiruv `check_and_consume_quota()`
    ichida qoladi; bu yerda hech narsa sarflanmaydi va hech narsa
    o'zgarmaydi, shuning uchun `/help` ekranini ochish kvotaga tegmaydi.

    Shart o'sha funksiyadagi bilan bir xil bo'lishi SHART: tarif 'free'
    emas VA muddati o'tmagan. Ikki joyda ikki xil shart bo'lsa, ekran
    "Pro ochiq" deb turar, bot esa rad etardi — bu shikoyatning eng
    yomon turi, chunki foydalanuvchi o'zini aldangandek his qiladi.

    Admin ham True oladi: unga hamma narsa ochiq, va o'z ekranida
    "yopiq" ko'rish xatoga o'xshaydi.
    """
    global pool
    if pool is None:
        await create_db_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.plan_type, u.premium_until,
                   EXISTS(SELECT 1 FROM admins WHERE user_id = $1) AS is_admin,
                   EXISTS(SELECT 1 FROM superadmins WHERE user_id = $1) AS is_super
            FROM users u WHERE u.user_id = $1
            """, user_id)

    if row is None:
        return False
    if row['is_admin'] or row['is_super']:
        return True
    if (row['plan_type'] or 'free') == 'free':
        return False
    muddat = row['premium_until']
    return muddat is None or muddat > datetime.now(timezone.utc)


async def get_full_user_profile(user_id: int) -> Optional[Dict[str, Any]]:
    global pool
    if pool is None:
        await create_db_pool()

    async with pool.acquire() as conn:
        user_row = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
        if not user_row:
            return None
            
        msg_count = await conn.fetchval(
            'SELECT COUNT(*) FROM user_activity WHERE user_id = $1', user_id
        )
        
        total_tokens = await conn.fetchval(
            'SELECT SUM(tokens_used)::bigint FROM user_history WHERE user_id = $1', user_id
        )

        # ANIQLIK UCHUN MUHIM: agar foydalanuvchining oxirgi kredit
        # yozuvi kechagi (yoki undan oldingi) Toshkent kuniga tegishli
        # bo'lsa, u hali BUGUN hech narsa sarflamagan — haqiqiy nolinash
        # check_and_consume_quota() ichida, foydalanuvchi keyingi AI
        # so'rovini yuborganda sodir bo'ladi. Profil buni bazaga
        # yozmasdan turib, faqat KO'RSATISH uchun oldindan to'g'rilaydi —
        # aks holda profilda kechagi eski raqam ko'rinib qolar edi.
        today_tashkent = datetime.now(TASHKENT_TZ).date()
        usage_date = user_row.get('daily_usage_date')
        raw_daily_used = user_row.get('daily_requests_used', 0) or 0
        daily_used = 0 if usage_date != today_tashkent else raw_daily_used

        # Barcha kunlik sanoqlar bir xil qoida bo'yicha — DAILY_COUNTERS
        # yagona manba, shuning uchun yangi sanoq qo'shilganda bu yer
        # o'z-o'zidan to'g'ri ishlaydi.
        counters = {
            used_col: (0 if user_row.get(date_col) != today_tashkent
                       else (user_row.get(used_col, 0) or 0))
            for used_col, date_col, _ in DAILY_COUNTERS.values()
        }

        return {
            **counters,
            'user_id': user_row['user_id'],
            'username': user_row.get('username') or "Mavjud emas",
            'is_active': user_row.get('is_active', True),
            'is_banned': user_row.get('is_banned', False),
            'plan_type': user_row.get('plan_type', 'free'),
            'premium_until': user_row.get('premium_until'),
            'current_model': GPT_MODEL_DISPLAY_NAME,
            'media_analysis_active': user_row.get('media_analysis_active', True),
            'daily_requests_used': daily_used,
            'digest_hour': user_row.get('digest_hour'),
            'digest_topics': user_row.get('digest_topics'),
            'total_tokens_used': total_tokens or 0,
            'total_messages': msg_count or 0,
            'created_at': user_row.get('created_at'),
            'last_seen': user_row.get('last_seen')
        }


@with_db_retry()
async def ban_user(user_id: int) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('UPDATE users SET is_banned = TRUE WHERE user_id = $1', user_id)


@with_db_retry()
async def unban_user(user_id: int) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('UPDATE users SET is_banned = FALSE WHERE user_id = $1', user_id)


@with_db_retry()
async def is_banned(user_id: int) -> bool:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval('SELECT is_banned FROM users WHERE user_id = $1', user_id)
        return bool(val)


@with_db_retry()
async def set_user_plan(user_id: int, plan_type: str) -> None:
    """Set plan_type directly. For 'free' this also clears any premium_until."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        if plan_type == 'free':
            await conn.execute(
                'UPDATE users SET plan_type = $2, premium_until = NULL WHERE user_id = $1',
                user_id, plan_type,
            )
        else:
            await conn.execute('UPDATE users SET plan_type = $2 WHERE user_id = $1', user_id, plan_type)


# Tarif muddatini QOLGAN VAQT USTIGA qo'shadigan yagona SQL. Sotib olish,
# sovg'a, referal mukofoti va promokod — hammasi shu bittasidan foydalanadi,
# shuning uchun uchta ehtiyot chorasi ham hamma joyda bir xil ishlaydi.
# USTIDAN YOZISH — «Muddatni belgilash» amali. Qo'shmaydi, almashtiradi.
#
# ⚠️ XATTI-HARAKATI O'ZGARMASIN. `tests/test_pro_grant.py` 4-bandi admin
# panelini shu SQL matni orqali muzlatadi: unda `NOW() +` bo'lishi va
# `GREATEST` BO'LMASLIGI shart. Muddat qanday yozilishi (`make_interval`
# yoki eski `|| ' days'`) tekshiruvga kirmaydi — ikkalasi ham `NOW() +`
# ni saqlaydi, ya'ni ustidan yozish xatti-harakati o'zgarmaydi. Ikkinchisi
# qo'shilsa amal jimgina «qo'shish» ga aylanadi va tuzatish imkoniyati
# yo'qoladi — xato bilan 3650 kun bergan adminda uni qisqartirish yo'li
# qolmaydi.
_YOZ_MUDDAT_SQL = ("UPDATE users SET plan_type = $2, premium_until = "
                   "NOW() + make_interval(days => $3::int) WHERE user_id = $1")
_YOZ_CHEKSIZ_SQL = ("UPDATE users SET plan_type = $2, premium_until = NULL "
                    "WHERE user_id = $1")

_EXTEND_PLAN_SQL = """
    UPDATE users SET
      premium_until = CASE
          -- Muddatsiz tarifi bor foydalanuvchi HECH QACHON muddatliga
          -- tushirilmaydi (aks holda cheksiz obunani 30 kunga almashtirardik).
          WHEN plan_type <> 'free' AND premium_until IS NULL THEN NULL
          -- GREATEST(..., NOW()): muddati allaqachon o'tgan, lekin hali
          -- xabar yozmagani uchun free'ga tushirilmagan foydalanuvchining
          -- kunlari O'TMISHDAGI sanaga qo'shilib ketmasin — aks holda u pul
          -- to'lab hech narsa olmagan bo'lardi.
          ELSE GREATEST(COALESCE(premium_until, NOW()), NOW())
               + make_interval(days => $3::int)
      END,
      -- Tarif faqat YAXSHILANADI: cheksiz 'premium' foydalanuvchi Pro sotib
      -- olsa, 10k/kun limitiga pasaytirilmaydi.
      plan_type = CASE WHEN plan_type = 'premium' THEN 'premium' ELSE $2 END,
      -- Muddat uzaytirildi — eski "tugayapti" ogohlantirishi bekor bo'ladi.
      premium_reminded_for = NULL
    WHERE user_id = $1
"""


@with_db_retry()
async def set_user_premium(user_id: int, days: Optional[int], *,
                           plan: str = 'pro', extend: bool = False) -> None:
    """Tarif beradi. days=None — muddatsiz.

    extend=False (DEFAULT) — muddatni USTIDAN yozadi (tuzatish amali).
    extend=True — qolgan muddat USTIGA qo'shadi (sovg'a, to'lov, referal,
    promokod): 20 kuni qolganida 1 oy olgan odam 50 kun oladi, 30 emas.

    ⚠️ `plan` STANDART QIYMATI `'premium'` EDI va bu jonli xato edi.
    Paneldagi tugma «Pro berish» deb yozilgan, `PLAN_LIMITS` da esa
    `premium` — CHEKSIZ limitli alohida tarif. Ya'ni admin «7 kunlik Pro»
    bergan odam aslida cheksiz limitli tarif olardi, panelning Limitlar
    ekrani esa uni umuman boshqara olmasdi (u yerda faqat Bepul va Pro
    bor). Ustiga-ustak o'sha odam Boshqaruv ekranida to'rtinchi rang
    bo'lib — «Premium 1» — ko'rinib turardi, va admin «Pro obunachilar 2»
    bilan taqqoslab tushunmasdi.

    Chaqiruvchilar buni ATAYLAB yozmaydi: bitta standart qiymat bo'lsa
    keyingi chaqiruvchi ham xuddi shu tuzoqqa tushardi. `premium` faqat
    bazadagi eski qatorlarda qoladi (`TARIF_NOMI` izohiga qarang).
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        if days is None:
            await conn.execute(_YOZ_CHEKSIZ_SQL, user_id, plan)
        elif not extend:
            await conn.execute(_YOZ_MUDDAT_SQL, user_id, plan, int(days))
        else:
            await conn.execute(_EXTEND_PLAN_SQL, user_id, plan, int(days))


def _soniyaga(dt):
    """Mikrosoniyalarni tashlaydi — taqqoslash aniqligi bir soniya.

    Panel sanani `isoformat(timespec="seconds")` bilan oladi, ya'ni
    mikrosoniya unga umuman yetib bormaydi. Ularni taqqoslashga
    qo'shish har safar «o'zgargan» degan yolg'on javob berardi.
    """
    return dt.replace(microsecond=0) if dt is not None else None


@with_db_retry()
async def set_user_premium_checked(
        user_id: int, days: Optional[int], *, plan: str = "pro",
        kutilgan_tarif: str, kutilgan_muddat) -> Optional[Dict[str, Any]]:
    """Muddatni USTIDAN yozadi — lekin faqat holat kutilganday bo'lsa.

    NEGA: bu amal muddatni almashtiradi, ya'ni admin ekranda ko'rgan
    «20 kun» ni o'chiradi. Agar o'sha 20 kun ekran ochilgandan keyin
    o'zgargan bo'lsa (odam pul to'lagan, promokod ishlatgan, referal
    mukofoti kelgan), admin O'ZI KO'RMAGAN narsani o'chirgan bo'ladi.

    ⚠️ Tekshiruv va yozuv BITTA TRANZAKSIYADA, `FOR UPDATE` qulfi
    bilan. Alohida `SELECT` + `UPDATE` bo'lsa, ikkisining orasida
    to'lov o'tib ketishi mumkin — ya'ni himoya bor ko'rinib, aslida
    yo'q bo'lardi.

    Qaytadi:
      `None`                                 — bunday foydalanuvchi yo'q
      `{"ok": False, "hozir": {...}}`        — holat o'zgargan, HECH NARSA yozilmadi
      `{"ok": True,  "oldin": {...}}`        — yozildi; `oldin` auditga ketadi
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT plan_type, premium_until FROM users "
                "WHERE user_id = $1 FOR UPDATE", user_id)
            if row is None:
                return None
            tarif = row["plan_type"] or "free"
            muddat = row["premium_until"]
            holat = {"tarif": tarif, "muddat": muddat}
            if (tarif != kutilgan_tarif
                    or _soniyaga(muddat) != _soniyaga(kutilgan_muddat)):
                return {"ok": False, "hozir": holat}
            if days is None:
                await conn.execute(_YOZ_CHEKSIZ_SQL, user_id, plan)
            else:
                await conn.execute(_YOZ_MUDDAT_SQL, user_id, plan, int(days))
            return {"ok": True, "oldin": holat}


@with_db_retry()
async def reset_user_quota(user_id: int) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    today_tashkent = datetime.now(TASHKENT_TZ).date()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE users SET daily_requests_used = 0, daily_usage_date = $2 WHERE user_id = $1',
            user_id, today_tashkent,
        )


@with_db_retry()
async def refund_quota(user_id: int, cost: int) -> None:
    """
    STT/hujjat/vision muvaffaqiyatsiz bo'lib, hech qanday haqiqiy AI javobi
    berilmagan so'rovlar uchun oldin check_and_consume_quota() tomonidan
    yechilgan ballarni qaytaradi. Xuddi shu FOR UPDATE patternida ishlaydi —
    race condition (parallel so'rovlar) oldini olish uchun.

    Agar foydalanuvchining hisobi allaqachon boshqa (bugungidan farqli)
    Toshkent kuniga tegishli bo'lsa — hech narsa qaytarilmaydi, chunki bu
    hisob keyingi so'rovda avtomatik nolanadi va bekorga tegib ketish
    ertangi kun balansini buzadi.
    """
    global pool
    if pool is None:
        await create_db_pool()

    today_tashkent = datetime.now(TASHKENT_TZ).date()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                'SELECT daily_requests_used, daily_usage_date FROM users WHERE user_id = $1 FOR UPDATE',
                user_id,
            )
            if row is None or row['daily_usage_date'] != today_tashkent:
                return
            new_used = max(0, (row['daily_requests_used'] or 0) - cost)
            await conn.execute(
                'UPDATE users SET daily_requests_used = $2 WHERE user_id = $1',
                user_id, new_used,
            )


@with_db_retry()
async def check_and_consume_daily(user_id: int, kind: str) -> Dict[str, Any]:
    """
    Kunlik SANOQ (ball tizimidan alohida): fayl, rasm, chuqur tadqiqot.

    check_and_consume_quota() bilan bir xil naqsh: `FOR UPDATE` qulfi,
    admin/superadmin bypass, ban ustunligi, muddati o'tgan premium'ni
    darhol free'ga tushirish, Toshkent kuni bo'yicha avtomatik nolanish.
    Farqi — ball emas, dona hisoblanadi va tugagani suhbatga ta'sir qilmaydi.

    `limit == 0` — bu tarifda imkoniyat UMUMAN yo'q (bepul uchun rasm va
    tadqiqot). Rad javobi cheklovga yetganidan farqlanmaydi, chaqiruvchi
    limit==0 bo'yicha "bu Pro imkoniyati" xabarini ko'rsatadi.

    Qaytaradi: {'allowed', 'used', 'limit', 'unlimited', 'plan'}
    """
    # Noma'lum kind — KeyError, ATAYLAB: bu dasturchi xatosi, jimgina
    # noto'g'ri sanoqni yechgandan ko'ra darhol yiqilgani yaxshi.
    used_col, date_col, limit_key = DAILY_COUNTERS[kind]

    global pool
    if pool is None:
        await create_db_pool()

    today_tashkent = datetime.now(TASHKENT_TZ).date()

    async with pool.acquire() as conn:
        async with conn.transaction():
            # ⚠️ Ustun nomlari f-string bilan qo'yiladi, chunki SQL
            # identifikatorni $1 parametr qilib bo'lmaydi. XAVFSIZ: qiymatlar
            # FAQAT DAILY_COUNTERS ro'yxatidan keladi, foydalanuvchidan emas.
            row = await conn.fetchrow(
                f'''
                SELECT
                    u.plan_type,
                    u.premium_until,
                    u.{used_col},
                    u.{date_col},
                    u.is_banned,
                    EXISTS(SELECT 1 FROM admins WHERE user_id = $1) AS is_admin,
                    EXISTS(SELECT 1 FROM superadmins WHERE user_id = $1) AS is_superadmin
                FROM users u
                WHERE u.user_id = $1
                FOR UPDATE
                ''',
                user_id,
            )

            if row is None or row['is_admin'] or row['is_superadmin']:
                return {'allowed': True, 'used': 0,
                        'limit': daily_limit('free', limit_key),
                        'unlimited': True, 'plan': 'admin'}

            if row['is_banned']:
                return {'allowed': False, 'banned': True, 'used': 0, 'limit': 0,
                        'unlimited': False, 'plan': row['plan_type'] or 'free'}

            plan_type = row['plan_type'] or 'free'
            premium_until = row['premium_until']
            if (plan_type != 'free' and premium_until is not None
                    and premium_until <= datetime.now(timezone.utc)):
                # Muddati o'tgan premium — ball kvotasidagi kabi darhol
                # free'ga tushiramiz (alohida cron shart emas).
                await conn.execute(
                    "UPDATE users SET plan_type = 'free', premium_until = NULL WHERE user_id = $1",
                    user_id,
                )
                plan_type = 'free'

            limit = daily_limit(plan_type, limit_key)
            if limit is None:
                # Cheksiz tarif ('premium') — hisoblagichga umuman tegilmaydi.
                return {'allowed': True, 'used': 0, 'limit': 0,
                        'unlimited': True, 'plan': plan_type}

            used = row[used_col] or 0
            if row[date_col] != today_tashkent:
                used = 0  # yangi Toshkent kuni

            # limit == 0 bo'lsa doim shu yerga tushadi ("tarifda yo'q").
            if used + 1 > limit:
                return {'allowed': False, 'used': used, 'limit': limit,
                        'unlimited': False, 'plan': plan_type}

            await conn.execute(
                f'UPDATE users SET {used_col} = $2, {date_col} = $3 WHERE user_id = $1',
                user_id, used + 1, today_tashkent,
            )
            return {'allowed': True, 'used': used + 1, 'limit': limit,
                    'unlimited': False, 'plan': plan_type}


@with_db_retry()
async def refund_daily(user_id: int, kind: str) -> None:
    """Natija chiqmasa sanoqni qaytaradi (urinish bekor hisoblanadi).

    refund_quota() bilan bir xil ehtiyot chorasi: agar hisob boshqa kunga
    tegishli bo'lsa hech narsa qilinmaydi, aks holda ertangi kun balansi
    buzilardi.
    """
    used_col, date_col, _ = DAILY_COUNTERS[kind]

    global pool
    if pool is None:
        await create_db_pool()

    today_tashkent = datetime.now(TASHKENT_TZ).date()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                f'SELECT {used_col}, {date_col} FROM users WHERE user_id = $1 FOR UPDATE',
                user_id,
            )
            if row is None or row[date_col] != today_tashkent:
                return
            await conn.execute(
                f'UPDATE users SET {used_col} = $2 WHERE user_id = $1',
                user_id, max(0, (row[used_col] or 0) - 1),
            )


# Eski nomlar — mavjud chaqiruvchilar buzilmasin.
async def check_and_consume_file_quota(user_id: int) -> Dict[str, Any]:
    return await check_and_consume_daily(user_id, "files")


async def refund_file_quota(user_id: int) -> None:
    await refund_daily(user_id, "files")


@with_db_retry()
async def check_and_consume_quota(user_id: int, cost: int) -> Dict[str, Any]:
    """
    Xabar GPT'ga yuborilishidan OLDIN chaqiriladi: foydalanuvchining kunlik
    ball byudjetini tekshiradi va agar yetarli bo'lsa, xuddi shu tranzaksiya
    ichida ballarni sarflaydi.

    MUHIM — RACE CONDITION: qator `FOR UPDATE` bilan qulflanadi, shuning
    uchun bitta foydalanuvchi bir vaqtning o'zida bir nechta xabar yuborsa
    ham (masalan tez-tez bosilgan tugmalar), ikkalasi ham bir xil "eski"
    hisobni o'qib, limitdan oshib ketolmaydi.

    Admin/superadmin — `admins`/`superadmins` jadvallaridan bitta so'rov
    ichida tekshiriladi (alohida chaqiruv shart emas) va ularga hech qanday
    limit qo'llanmaydi.

    Qaytaradi: {'allowed': bool, 'used': int, 'limit': int, 'unlimited': bool}
    """
    global pool
    if pool is None:
        await create_db_pool()

    today_tashkent = datetime.now(TASHKENT_TZ).date()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                '''
                SELECT
                    u.plan_type,
                    u.premium_until,
                    u.daily_requests_used,
                    u.daily_usage_date,
                    u.is_banned,
                    EXISTS(SELECT 1 FROM admins WHERE user_id = $1) AS is_admin,
                    EXISTS(SELECT 1 FROM superadmins WHERE user_id = $1) AS is_superadmin
                FROM users u
                WHERE u.user_id = $1
                FOR UPDATE
                ''',
                user_id,
            )

            # Foydalanuvchi hali bazada yo'q (kutilmagan holat — odatda
            # save_user() bundan oldin chaqirilgan bo'ladi) yoki admin/superadmin —
            # limitsiz o'tkazamiz.
            if row is None or row['is_admin'] or row['is_superadmin']:
                return {'allowed': True, 'used': 0, 'limit': DAILY_FREE_LIMIT,
                        'unlimited': True, 'plan': 'admin'}

            # Ban — admin/superadmin bo'lmagan har qanday rejadan (free yoki
            # premium) ustun turadi, shuning uchun plan_type tekshiruvidan oldin.
            if row['is_banned']:
                return {'allowed': False, 'banned': True, 'used': 0, 'limit': 0,
                        'unlimited': False, 'plan': row['plan_type'] or 'free'}

            plan_type = row['plan_type'] or 'free'
            premium_until = row['premium_until']
            premium_expired = (
                plan_type != 'free' and premium_until is not None and premium_until <= datetime.now(timezone.utc)
            )
            if premium_expired:
                # Muddat o'tgan — kunlik limit hisobi qanday avtomatik
                # nolanishini eslatadi: shu yerda darhol free'ga tushiramiz,
                # alohida cron/scheduler shart emas.
                await conn.execute(
                    "UPDATE users SET plan_type = 'free', premium_until = NULL WHERE user_id = $1",
                    user_id,
                )
                plan_type = 'free'

            point_limit, _ = plan_limits(plan_type)
            if point_limit is None:
                # Cheksiz tarif ('premium') — hisoblagichga umuman tegilmaydi.
                # 'unlimited': True bu yerda "hech narsa yechilmadi, refund
                # qilma" degani (handlers/messages.py:_refund_quota guardi).
                return {'allowed': True, 'used': 0, 'limit': 0,
                        'unlimited': True, 'plan': plan_type}

            used = row['daily_requests_used'] or 0
            usage_date = row['daily_usage_date']
            is_new_day = usage_date != today_tashkent

            if is_new_day:
                used = 0  # yangi Toshkent kuni boshlangan — hisob nolanadi

            if used + cost > point_limit:
                # Limitga yetgan, lekin agar shu bilan birga yangi kun ham
                # boshlangan bo'lsa — hisobni 0 ga tushirib qo'yamiz (ball
                # qo'shmasdan), keyingi so'rov to'g'ri hisobdan boshlansin.
                if is_new_day:
                    await conn.execute(
                        'UPDATE users SET daily_requests_used = 0, daily_usage_date = $2 WHERE user_id = $1',
                        user_id, today_tashkent,
                    )
                return {'allowed': False, 'used': used, 'limit': point_limit,
                        'unlimited': False, 'plan': plan_type}

            new_used = used + cost
            await conn.execute(
                'UPDATE users SET daily_requests_used = $2, daily_usage_date = $3 WHERE user_id = $1',
                user_id, new_used, today_tashkent,
            )
            return {'allowed': True, 'used': new_used, 'limit': point_limit,
                    'unlimited': False, 'plan': plan_type}


# ═══════════════════════════════════════════════════════════════════
#  TELEGRAM STARS TO'LOVLARI
# ═══════════════════════════════════════════════════════════════════

@with_db_retry()
async def grant_paid_pro(*, charge_id: str, payer_id: int, beneficiary_id: int,
                         stars: int, days: int, payload: str) -> bool:
    """To'lovni yozadi VA Pro tarifni beradi — BITTA tranzaksiyada.

    Qaytaradi:
        True  — yangi to'lov, tarif berildi.
        False — bu charge_id allaqachon ishlangan (Telegram update'ni
                takroran yubordi). Hech narsa o'zgarmadi.

    NEGA BITTA TRANZAKSIYA: INSERT va UPDATE birga commit bo'ladi yoki
    birga bekor qilinadi. Ya'ni "to'lov bazaga yozilgan, lekin tarif
    berilmagan" holati MAVJUD EMAS — alohida solishtiruv (reconciliation)
    jarayoni ham, `granted` bayrog'i ham kerak emas.

    Takrorlanmaslik kodda emas, `star_payments.charge_id` UNIQUE cheklovida:
    ON CONFLICT DO NOTHING ... RETURNING bo'sh qaytsa, demak bu to'lov
    allaqachon ishlangan.
    """
    global pool
    if pool is None:
        await create_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                '''
                INSERT INTO star_payments
                    (charge_id, payer_id, beneficiary_id, stars, plan, days, payload)
                VALUES ($1, $2, $3, $4, 'pro', $5, $6)
                ON CONFLICT (charge_id) DO NOTHING
                RETURNING id
                ''',
                charge_id, payer_id, beneficiary_id, stars, days, payload,
            )
            if row is None:
                return False
            await conn.execute(_EXTEND_PLAN_SQL, beneficiary_id, 'pro', str(days))
            return True


@with_db_retry()
async def get_payment_by_id(payment_id: int) -> Optional[Dict[str, Any]]:
    """To'lovni ichki ID bo'yicha oladi.

    NEGA charge_id emas: Telegram'ning charge_id'si uzun, callback_data esa
    64 baytdan oshmasligi kerak — shuning uchun admin tugmalari SERIAL id
    bilan kalitlanadi va charge_id server tomonda topiladi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM star_payments WHERE id = $1', payment_id)
        return dict(row) if row else None


@with_db_retry()
async def all_payments(limit: int = 5000) -> List[Dict[str, Any]]:
    """Hamma to'lovlar — CSV eksporti uchun.

    ⚠️ `limit` MAJBURIY chegara, bezak emas: jadval o'sib ketsa bitta
    so'rov butun xotirani yeb qo'yardi. Eksport «hammasi» degani emas,
    «oxirgi N tasi» degani va panel buni aytadi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''SELECT id, created_at, payer_id, beneficiary_id, stars, days,
                      refunded_at
               FROM star_payments ORDER BY id DESC LIMIT $1''', limit)
        return [dict(r) for r in rows]


@with_db_retry()
async def get_user_payments(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Foydalanuvchining to'lovlari — u to'lovchi YOKI oluvchi bo'lgan."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''SELECT * FROM star_payments
               WHERE payer_id = $1 OR beneficiary_id = $1
               ORDER BY created_at DESC LIMIT $2''',
            user_id, limit,
        )
        return [dict(r) for r in rows]


@with_db_retry()
async def mark_payment_refunded(charge_id: str, admin_id: int) -> bool:
    """To'lovni qaytarilgan deb belgilaydi va berilgan kunlarni olib tashlaydi.

    DIQQAT — CHAQIRISH TARTIBI: bu funksiya Telegram'ning refundStarPayment
    chaqiruvi MUVAFFAQIYATLI bo'lgandan KEYIN chaqirilishi shart. Aks holda
    Telegram refund'ni rad etsa (muddat o'tgan, allaqachon qaytarilgan)
    foydalanuvchidan tarif olib qo'yilgan, lekin puli qaytmagan bo'lardi.

    Qaytaradi: False — bu to'lov allaqachon qaytarilgan (takroriy bosish).
    """
    global pool
    if pool is None:
        await create_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                '''UPDATE star_payments SET refunded_at = NOW(), refunded_by = $2
                   WHERE charge_id = $1 AND refunded_at IS NULL
                   RETURNING beneficiary_id, days''',
                charge_id, admin_id,
            )
            if row is None:
                return False
            # Muddatsiz tarifga tegmaymiz (premium_until IS NOT NULL sharti) —
            # undan kun ayirishning ma'nosi yo'q.
            await conn.execute(
                '''UPDATE users
                   SET premium_until = premium_until - make_interval(days => $2::int)
                   WHERE user_id = $1 AND premium_until IS NOT NULL''',
                row['beneficiary_id'], int(row['days']),
            )
            # Ayirgandan keyin muddat o'tmishda qolsa — darhol free'ga.
            await conn.execute(
                '''UPDATE users SET plan_type = 'free', premium_until = NULL
                   WHERE user_id = $1 AND premium_until IS NOT NULL
                     AND premium_until <= NOW()''',
                row['beneficiary_id'],
            )
            return True


@with_db_retry()
async def revenue_stats() -> Dict[str, Any]:
    """Admin statistikasi uchun daromad ko'rsatkichlari (bitta so'rov).

    Qaytarilgan to'lovlar summadan CHIQARIB tashlanadi — aks holda
    "daromad" haqiqiy emas, brutto raqam bo'lib qolardi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            SELECT
              COALESCE(SUM(stars) FILTER (
                  WHERE refunded_at IS NULL
                    AND created_at >= (NOW() AT TIME ZONE 'Asia/Tashkent')::date
              ), 0) AS stars_today,
              COALESCE(SUM(stars) FILTER (
                  WHERE refunded_at IS NULL AND created_at >= NOW() - INTERVAL '30 days'
              ), 0) AS stars_30d,
              COALESCE(SUM(stars) FILTER (WHERE refunded_at IS NULL), 0) AS stars_total,
              COUNT(*) FILTER (
                  WHERE refunded_at IS NULL AND created_at >= NOW() - INTERVAL '30 days'
              ) AS sales_30d,
              COUNT(*) FILTER (WHERE refunded_at IS NOT NULL) AS refunds
            FROM star_payments
            '''
        )
        by_plan = await conn.fetch(
            '''SELECT days, COUNT(*) AS cnt FROM star_payments
               WHERE refunded_at IS NULL GROUP BY days ORDER BY days'''
        )
        # Kunlik qator — daromad grafigi uchun.
        #
        # ⚠️ KUN TOSHKENT BO'YICHA kesiladi, UTC bo'yicha emas: yuqoridagi
        # `stars_today` ham shunday hisoblanadi, ikki xil kesim bo'lsa
        # grafikning oxirgi ustuni «Bugun» KPI si bilan to'g'ri
        # kelmasdi — bir ekranda ikki xil raqam.
        #
        # ⚠️ Qaytarilgan to'lov bu yerda ham chiqarib tashlanadi
        # (`refunded_at IS NULL`), aks holda grafik brutto ko'rsatib,
        # KPI netto ko'rsatardi.
        kunlik = await conn.fetch(
            '''SELECT (created_at AT TIME ZONE 'Asia/Tashkent')::date AS kun,
                      COALESCE(SUM(stars), 0) AS stars,
                      COUNT(*) AS soni
               FROM star_payments
               WHERE refunded_at IS NULL
                 AND created_at >= NOW() - INTERVAL '30 days'
               GROUP BY 1 ORDER BY 1'''
        )
        result = dict(row) if row else {}
        result['by_plan'] = [(r['days'], r['cnt']) for r in by_plan]
        result['daily'] = [
            {'kun': r['kun'], 'stars': r['stars'], 'soni': r['soni']}
            for r in kunlik
        ]
        return result


# ═══════════════════════════════════════════════════════════════════
#  REFERAL
# ═══════════════════════════════════════════════════════════════════

@with_db_retry()
async def add_referral(invited_id: int, referrer_id: int) -> bool:
    """Taklifni yozadi. False — bu foydalanuvchi allaqachon taklif qilingan.

    invited_id PRIMARY KEY bo'lgani uchun qayta-taklif suiiste'moli shu
    yerda emas, sxemada to'xtatiladi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''INSERT INTO referrals (invited_id, referrer_id) VALUES ($1, $2)
               ON CONFLICT (invited_id) DO NOTHING RETURNING invited_id''',
            invited_id, referrer_id,
        )
        return row is not None


@with_db_retry()
async def qualify_referral(invited_id: int) -> Optional[int]:
    """Taklif qilingan foydalanuvchi HAQIQIY xabar yozdi — taklifni hisobga oladi.

    Bonus /start da emas, birinchi haqiqiy xabarda beriladi: aks holda
    soxta akkauntlarni ochib /start bosish bilan cheksiz kun yig'ish mumkin.

    `AND qualified_at IS NULL` — SQL'ning o'zi idempotent, shuning uchun
    chaqiruvchi tomondagi kesh faqat optimizatsiya, to'g'rilik sharti emas.

    Qaytaradi: taklif qilgan foydalanuvchi ID'si (yangi hisobga olingan
    bo'lsa), aks holda None.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            '''UPDATE referrals SET qualified_at = NOW()
               WHERE invited_id = $1 AND qualified_at IS NULL
               RETURNING referrer_id''',
            invited_id,
        )


class _NotEnoughReferrals(Exception):
    """Ichki signal: tranzaksiyani bekor qilish uchun (rollback)."""


@with_db_retry()
async def claim_referral_reward(referrer_id: int, required: int,
                                reward_days: int, max_rewards: int) -> bool:
    """Yetarli do'st yig'ilgan bo'lsa mukofot beradi (atomik).

    `required` tadan KAM topilsa tranzaksiya bekor qilinadi — ya'ni
    "yarim mukofot" holati bo'lishi mumkin emas.
    """
    global pool
    if pool is None:
        await create_db_pool()

    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                # BITTA TO'LQINDA BITTA MUKOFOT. Qator FOR UPDATE bilan
                # qulflanadi: uchta do'st bir vaqtda birinchi savolini
                # bersa, ikkita parallel tranzaksiya ikki marta mukofot
                # berib yuborishi mumkin edi.
                wave = await conn.fetchrow(
                    '''SELECT COALESCE(referral_round, 0) AS round,
                              referral_rewarded_round AS claimed
                         FROM users WHERE user_id = $1 FOR UPDATE''',
                    referrer_id,
                )
                if wave is None or wave['claimed'] == wave['round']:
                    raise _NotEnoughReferrals()

                already = await conn.fetchval(
                    'SELECT COUNT(*) FROM referrals WHERE referrer_id = $1 AND rewarded_at IS NOT NULL',
                    referrer_id,
                )
                if already >= max_rewards * required:
                    raise _NotEnoughReferrals()

                rows = await conn.fetch(
                    '''
                    WITH picked AS (
                        SELECT invited_id FROM referrals
                        WHERE referrer_id = $1
                          AND qualified_at IS NOT NULL AND rewarded_at IS NULL
                        ORDER BY qualified_at
                        LIMIT $2
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE referrals SET rewarded_at = NOW()
                    WHERE invited_id IN (SELECT invited_id FROM picked)
                    RETURNING invited_id
                    ''',
                    referrer_id, required,
                )
                if len(rows) < required:
                    # Hali yetarli emas — belgilanganlarni qaytarib olamiz.
                    raise _NotEnoughReferrals()

                await conn.execute(_EXTEND_PLAN_SQL, referrer_id, 'pro', str(reward_days))
                # Shu to'lqin yopildi. Keyingi mukofot faqat admin yangi
                # taklif yuborganda (bump_referral_round) ochiladi.
                await conn.execute(
                    '''UPDATE users
                          SET referral_rewarded_round = COALESCE(referral_round, 0)
                        WHERE user_id = $1''', referrer_id)
                return True
        except _NotEnoughReferrals:
            return False


@with_db_retry()
async def get_referral_progress(referrer_id: int) -> Dict[str, int]:
    """(taklif qilingan, hisobga olingan, mukofot olingan) — /pro ekrani uchun."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''SELECT COUNT(*) AS invited,
                      COUNT(*) FILTER (WHERE qualified_at IS NOT NULL) AS qualified,
                      COUNT(*) FILTER (WHERE rewarded_at IS NOT NULL) AS rewarded
               FROM referrals WHERE referrer_id = $1''',
            referrer_id,
        )
        return dict(row) if row else {'invited': 0, 'qualified': 0, 'rewarded': 0}


@with_db_retry()
async def get_referral_config(user_id: Optional[int] = None) -> Dict[str, int]:
    """Referal sharti: SHAXSIY -> UMUMIY -> core/config.py.

    Uch bosqich bitta so'rovda hal qilinadi, chunki bu har bir mukofot
    hisoblashda chaqiriladi. `user_id=None` — faqat umumiy sozlama
    (admin ekrani uchun).

    max_rewards ATAYLAB sozlanmaydi: u abuse tavani, admin uni tasodifan
    ko'tarib qo'ysa cheksiz kun yig'ish yo'li ochilardi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''SELECT COALESCE(u.referral_required, s.referral_required) AS required,
                      COALESCE(u.referral_reward_days, s.referral_reward_days) AS days,
                      (u.referral_rewarded_round IS NOT NULL
                       AND u.referral_rewarded_round
                           = COALESCE(u.referral_round, 0)) AS claimed
                 FROM bot_settings s
                 LEFT JOIN users u ON u.user_id = $1
                WHERE s.id = 1''',
            user_id,
        )
    required = (row and row['required']) or REFERRAL_REQUIRED
    days = (row and row['days']) or REFERRAL_REWARD_DAYS
    return {'required': required, 'reward_days': days,
            'max_rewards': REFERRAL_MAX_REWARDS,
            'claimed': bool(row and row['claimed'])}


# Admin ham xato yozadi: "3 300" deb qo'yilsa bitta odam bir yilda Pro
# yig'ib olardi. Chegaralar shu yerda, ekranda emas.
REFERRAL_REQUIRED_MAX = 100
REFERRAL_REWARD_DAYS_MAX = 90


def clean_referral_config(required, reward_days) -> tuple[Optional[int], Optional[int], str]:
    """Admin kiritgan qiymatlarni tekshiradi. Sof funksiya — testda tekshiriladi."""
    try:
        req, days = int(required), int(reward_days)
    except (TypeError, ValueError):
        return None, None, "Ikkala qiymat ham butun son bo'lishi kerak."
    if not 1 <= req <= REFERRAL_REQUIRED_MAX:
        return None, None, f"Do'stlar soni 1 dan {REFERRAL_REQUIRED_MAX} gacha bo'lsin."
    if not 1 <= days <= REFERRAL_REWARD_DAYS_MAX:
        return None, None, f"Kunlar soni 1 dan {REFERRAL_REWARD_DAYS_MAX} gacha bo'lsin."
    return req, days, ""


@with_db_retry()
async def set_referral_config(required: int, reward_days: int,
                              user_id: Optional[int] = None) -> bool:
    """Referal shartini o'rnatadi. user_id=None — HAMMAGA (umumiy sozlama).

    False — bunday foydalanuvchi topilmadi (umumiy sozlamada hech qachon).
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        if user_id is None:
            await conn.execute(
                '''UPDATE bot_settings
                      SET referral_required = $1, referral_reward_days = $2
                    WHERE id = 1''',
                required, reward_days,
            )
            return True
        res = await conn.execute(
            '''UPDATE users SET referral_required = $2, referral_reward_days = $3
                WHERE user_id = $1''',
            user_id, required, reward_days,
        )
        return res.endswith(" 1")


@with_db_retry()
async def bump_referral_round(user_id: int) -> None:
    """Yangi taklif to'lqini — mukofot huquqi shu odam uchun qayta ochiladi.

    send_referral_invite() ichidan chaqiriladi, ya'ni taklif yuborilgan
    HAR QANDAY yo'lda avtomatik ishlaydi. Chaqiruvni admin oqimlariga
    tarqatib qo'ysak, uchinchi yo'l qo'shilganda unutilardi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''UPDATE users SET referral_round = COALESCE(referral_round, 0) + 1
                WHERE user_id = $1''', user_id)


@with_db_retry()
async def clear_referral_config(user_id: int) -> None:
    """Shaxsiy shartni olib tashlaydi — foydalanuvchi umumiy sozlamaga qaytadi."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''UPDATE users SET referral_required = NULL, referral_reward_days = NULL
                WHERE user_id = $1''', user_id)


# ═══════════════════════════════════════════════════════════════════
#  PROMOKODLAR
# ═══════════════════════════════════════════════════════════════════

# Admin ham xato yozadi, va promokod — pul. `KOD 3000 100000 -` deb
# qo'yilsa bitta kod bilan 100 000 odam 8 yillik Pro olardi.
PROMO_KOD_MAX = 32
PROMO_KUN_MAX = 3650
PROMO_SONI_MAX = 100000


def clean_promo_spec(code, days, max_uses, expires_raw):
    """Promokod parametrlarini tekshiradi. Sof funksiya — testda tekshiriladi.

    Qaytaradi: `(spec, xato)`. `spec` — `(KOD, kun, soni, expires_at|None)`,
    `xato` — bo'sh satr yoki sabab.

    ⚠️ Bu tekshiruvlar ILGARI `handlers/admin/promo.py` ichida, handler
    tanasida yozilgandi. Web panel ham aynan shu qoidalarga muhtoj, va
    ularni u yerda QAYTA yozish — `ACTION_LABELS` bilan bo'lgan xatoning
    aynan o'zi: ikki nusxa, ikkalasi ham asta-sekin ajraladi va bir kuni
    bir ekran qabul qilgan kodni ikkinchisi rad etadi. Shuning uchun
    qoida `clean_referral_config` yonida, bitta joyda turadi.

    `expires_raw`: `YYYY-MM-DD`, yoki `"-"`/bo'sh — muddatsiz.
    """
    kod = str(code or "").strip()
    if not kod or not kod.replace("_", "").isalnum() or len(kod) > PROMO_KOD_MAX:
        return None, (f"Kod faqat harf/raqam/pastki chiziqdan iborat va "
                      f"{PROMO_KOD_MAX} belgidan qisqa bo'lsin.")
    try:
        kun, soni = int(days), int(max_uses)
    except (TypeError, ValueError):
        return None, "KUN va MAX butun son bo'lishi kerak."
    if isinstance(days, bool) or isinstance(max_uses, bool):
        return None, "KUN va MAX butun son bo'lishi kerak."
    if not 0 < kun <= PROMO_KUN_MAX:
        return None, f"KUN 1 dan {PROMO_KUN_MAX} gacha bo'lsin."
    if not 0 < soni <= PROMO_SONI_MAX:
        return None, f"MAX 1 dan {PROMO_SONI_MAX} gacha bo'lsin."

    expires_at = None
    xom = str(expires_raw or "").strip()
    if xom and xom != "-":
        try:
            kun = datetime.strptime(xom, "%Y-%m-%d")
        except ValueError:
            return None, "MUDDAT formati: YYYY-MM-DD yoki «-»."
        # ⚠️ TANLANGAN KUNNING OXIRI, TOSHKENT VAQTI BILAN.
        #
        # Ilgari bu qator `replace(tzinfo=timezone.utc)` edi, ya'ni sana
        # UTC YARIM TUNIGA tushardi. Toshkent UTC+5 bo'lgani uchun panel
        # uni «21.09.2026 05:00» deb ko'rsatardi va admin «men 21-sentabr
        # deb yozgan edim-ku, nega ertalab soat beshda tugaydi?» degan
        # savolga tushardi. Yomoni — bu faqat ko'rinish emas edi:
        # `redeem_promo()` ham o'sha lahzani tekshiradi, ya'ni kod
        # tanlangan kunning deyarli hammasida ALLAQACHON o'lik bo'lardi.
        #
        # 23:59:59 — kun oxiri. Sekund aniqligi yetarli: kod sotib olish
        # emas, sovg'a; yarim tunda bir sekundlik teshik hech kimga
        # ta'sir qilmaydi, «bir kun yo'qoldi» esa har safar ta'sir qiladi.
        expires_at = kun.replace(hour=23, minute=59, second=59,
                                 tzinfo=TASHKENT_TZ)
        # Kechagi sana bilan yaratilgan kod — darhol o'lik kod: admin uni
        # ro'yxatda «Faol» deb ko'radi, foydalanuvchi esa ishlatolmaydi.
        if expires_at <= datetime.now(timezone.utc):
            return None, "Muddat kelajakda bo'lishi kerak."
    return (kod.upper(), kun, soni, expires_at), ""


@with_db_retry()
async def create_promo_code(code: str, days: int, max_uses: int,
                            expires_at, created_by: int) -> bool:
    """Yangi promokod. False — bunday kod allaqachon mavjud."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''INSERT INTO promo_codes (code, days, max_uses, expires_at, created_by)
               VALUES (UPPER($1), $2, $3, $4, $5)
               ON CONFLICT (code) DO NOTHING RETURNING code''',
            code, days, max_uses, expires_at, created_by,
        )
        return row is not None


@with_db_retry()
async def list_promo_codes(limit: int = 30) -> List[Dict[str, Any]]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT $1', limit)
        return [dict(r) for r in rows]


@with_db_retry()
async def get_promo_code(code: str) -> Optional[Dict[str, Any]]:
    """Bitta kod haqida ma'lumot (yuborishdan oldin tekshirish uchun)."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT * FROM promo_codes WHERE code = UPPER($1)', code)
        return dict(row) if row else None


@with_db_retry()
async def revoke_promo_code(code: str) -> bool:
    """Kodni bekor qiladi. ATAYLAB DELETE emas — ishlatilgan kodlar tarixi
    (promo_redemptions) saqlanib qolishi kerak."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'UPDATE promo_codes SET revoked = TRUE WHERE code = UPPER($1) RETURNING code',
            code,
        )
        return row is not None


@with_db_retry()
async def redeem_promo(user_id: int, code: str) -> Dict[str, Any]:
    """Promokodni ishlatadi. Bitta tranzaksiya, FOR UPDATE bilan qulflangan.

    Qaytaradi: {'ok': bool, 'reason': str, 'days': int}
    reason: 'invalid' | 'revoked' | 'expired' | 'exhausted' | 'already' | 'ok'
    """
    global pool
    if pool is None:
        await create_db_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                'SELECT * FROM promo_codes WHERE code = UPPER($1) FOR UPDATE', code)
            if row is None:
                return {'ok': False, 'reason': 'invalid', 'days': 0}
            if row['revoked']:
                return {'ok': False, 'reason': 'revoked', 'days': 0}
            if row['expires_at'] is not None and row['expires_at'] <= datetime.now(timezone.utc):
                return {'ok': False, 'reason': 'expired', 'days': 0}
            if row['used_count'] >= row['max_uses']:
                return {'ok': False, 'reason': 'exhausted', 'days': 0}

            claimed = await conn.fetchrow(
                '''INSERT INTO promo_redemptions (code, user_id) VALUES (UPPER($1), $2)
                   ON CONFLICT (code, user_id) DO NOTHING RETURNING code''',
                code, user_id,
            )
            if claimed is None:
                return {'ok': False, 'reason': 'already', 'days': 0}

            await conn.execute(
                'UPDATE promo_codes SET used_count = used_count + 1 WHERE code = UPPER($1)', code)
            await conn.execute(
                _EXTEND_PLAN_SQL, user_id, row['plan'] or 'pro', str(row['days']))
            return {'ok': True, 'reason': 'ok', 'days': row['days']}


# ═══════════════════════════════════════════════════════════════════
#  TARIF MUDDATI
# ═══════════════════════════════════════════════════════════════════

@with_db_retry()
async def giveaway_stats() -> Dict[str, Any]:
    """Admin paneli uchun "bepul berilgan Pro" ko'rsatkichlari.

    Promokod va referal — bu haqiqiy xarajat (berilgan har bir kun sotilmagan
    kun), shuning uchun admin ularni daromad kabi ko'rib turishi kerak.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        promo = await conn.fetchrow(
            '''SELECT
                 COUNT(*) FILTER (
                     WHERE NOT revoked
                       AND (expires_at IS NULL OR expires_at > NOW())
                       AND used_count < max_uses
                 ) AS active_codes,
                 COUNT(*) AS total_codes,
                 COALESCE(SUM(used_count), 0) AS redemptions,
                 COALESCE(SUM(used_count * days), 0) AS promo_days
               FROM promo_codes''')
        ref = await conn.fetchrow(
            '''SELECT
                 COUNT(*) AS invited,
                 COUNT(*) FILTER (WHERE qualified_at IS NOT NULL) AS qualified,
                 COUNT(*) FILTER (WHERE rewarded_at IS NOT NULL) AS rewarded
               FROM referrals''')
        result = dict(promo) if promo else {}
        result.update(dict(ref) if ref else {})
        return result


@with_db_retry()
async def take_expiry_reminders(within_days: int = 3) -> List[Dict[str, Any]]:
    """Muddati tugayotganlarni oladi va DARHOL "eslatildi" deb belgilaydi.

    `RETURNING` bilan bitta so'rovda belgilash va olish — shuning uchun bot
    ikki nusxada ishlab ketsa ham eslatma ikki marta yuborilmaydi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''UPDATE users SET premium_reminded_for = premium_until
               WHERE plan_type <> 'free'
                 AND premium_until IS NOT NULL
                 AND premium_until BETWEEN NOW()
                                       AND NOW() + make_interval(days => $1::int)
                 AND premium_reminded_for IS DISTINCT FROM premium_until
               RETURNING user_id, premium_until, plan_type''',
            int(within_days),
        )
        return [dict(r) for r in rows]


@with_db_retry()
async def take_inactive_users(limit: int = 40) -> List[Dict[str, Any]]:
    """Uzoq ko'rinmagan foydalanuvchilarni oladi va DARHOL belgilaydi.

    take_expiry_reminders() bilan bir xil naqsh: belgilash va olish BITTA
    `UPDATE ... RETURNING` ichida, ya'ni bot ikki nusxada ishlasa ham
    bitta odamga ikkita xabar ketmaydi.

    Bosqichlar INACTIVE_STEPS dan olinadi: 7 -> 15 -> 30 -> yana 7.
    Hisob boshlanish nuqtasi — oxirgi FAOLLIK yoki oxirgi XABAR, qaysi
    biri keyinroq bo'lsa. Shuning uchun xabar yuborilgach sanoq qaytadan
    boshlanadi va odam har kuni turtilmaydi.

    ⚠️ last_seen bu yerda O'ZGARTIRILMAYDI. Eski kodning asosiy xatosi
    shu edi: u xabar yuborgach last_seen = NOW() qilardi, ya'ni foydalanuvchi
    hech qachon kirmagan bo'lsa ham "hozir kirgan" bo'lib qolardi va
    haqiqiy faollik ma'lumoti yo'q bo'lardi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    steps = ",".join(str(int(d)) for d in INACTIVE_STEPS)
    async with pool.acquire() as conn:
        rows = await conn.fetch(f'''
            WITH picked AS (
                SELECT user_id
                  FROM users
                 WHERE is_active = TRUE
                   AND COALESCE(is_banned, FALSE) = FALSE
                   AND last_seen IS NOT NULL
                   AND GREATEST(last_seen, COALESCE(inactive_notified_at, last_seen))
                       < NOW() - make_interval(days =>
                           (ARRAY[{steps}])[COALESCE(inactive_stage, 0) + 1])
                 ORDER BY GREATEST(last_seen, COALESCE(inactive_notified_at, last_seen))
                 LIMIT $1
                 FOR UPDATE SKIP LOCKED
            )
            UPDATE users u SET
                inactive_notified_at = NOW(),
                -- Keyingi bosqich; oxirgisidan keyin yana boshiga qaytadi.
                inactive_stage = (COALESCE(u.inactive_stage, 0) + 1)
                                 % {len(INACTIVE_STEPS)}
              FROM picked p
             WHERE u.user_id = p.user_id
            RETURNING u.user_id, u.username, COALESCE(u.inactive_stage, 0) AS next_stage
        ''', limit)
        return [dict(r) for r in rows]


@with_db_retry()
async def take_due_digests() -> List[Dict[str, Any]]:
    """Shu soatda daydjest kutayotganlarni oladi va DARHOL belgilaydi.

    take_expiry_reminders() bilan bir xil naqsh: belgilash va olish BITTA
    `UPDATE ... RETURNING` ichida, shuning uchun bot ikki nusxada ishlab
    ketsa ham foydalanuvchi kuniga ikkita daydjest olmaydi.

    Pro tugasa daydjest O'ZI to'xtaydi (plan_type/premium_until sharti),
    lekin digest_hour TOZALANMAYDI — tarif uzaytirilsa qayta sozlash
    shart emas, obuna o'zi tiklanadi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            UPDATE users
               SET digest_sent_date = (NOW() AT TIME ZONE 'Asia/Tashkent')::date,
                   digest_sent_hour = EXTRACT(HOUR FROM (NOW() AT TIME ZONE 'Asia/Tashkent'))::int
             WHERE digest_hours IS NOT NULL
               AND digest_topics IS NOT NULL
               AND plan_type <> 'free'
               AND (premium_until IS NULL OR premium_until > NOW())
               AND is_active = TRUE
               AND COALESCE(is_banned, FALSE) = FALSE
               -- Hozirgi soat foydalanuvchi tanlagan ro'yxatda bormi.
               AND EXTRACT(HOUR FROM (NOW() AT TIME ZONE 'Asia/Tashkent'))::int
                   = ANY(string_to_array(digest_hours, ',')::int[])
               -- SANA VA SOAT birga tekshiriladi. Faqat sana bo'lsa,
               -- kunning birinchi daydjesti qolgan soatlarni ham
               -- "yuborilgan" deb yopib qo'yardi.
               AND (digest_sent_date IS DISTINCT FROM (NOW() AT TIME ZONE 'Asia/Tashkent')::date
                    OR digest_sent_hour IS DISTINCT FROM
                       EXTRACT(HOUR FROM (NOW() AT TIME ZONE 'Asia/Tashkent'))::int)
            RETURNING user_id, digest_topics
        ''')
        return [dict(r) for r in rows]


def parse_digest_hours(raw) -> list[int]:
    """"7,12,21" yoki [7,12,21] -> [7, 12, 21]. Yaroqsizlari tashlanadi.

    ⚠️ Soatlar MIJOZDAN keladi (callback_data), ya'ni ishonchsiz manba —
    tekshiruv shu yerda, ekranda emas. Sof funksiya, tests/test_digest.py
    da tekshiriladi.
    """
    if raw is None:
        return []
    parts = raw.split(",") if isinstance(raw, str) else raw
    hours = set()
    for p in parts:
        try:
            h = int(str(p).strip())
        except (TypeError, ValueError):
            continue
        if isinstance(p, bool):        # True -> 1 bo'lib o'tib ketmasin
            continue
        if 0 <= h <= 23:
            hours.add(h)
    return sorted(hours)


@with_db_retry()
async def set_digest(user_id: int, hours,
                     topics: Optional[str] = None) -> None:
    """Daydjest obunasi. hours=None yoki bo'sh ro'yxat — o'chiradi.

    topics=None bo'lsa mavjud mavzular saqlanib qoladi (COALESCE) — soat
    almashtirilganda mavzularni qayta yozdirmaslik uchun.
    """
    global pool
    if pool is None:
        await create_db_pool()
    clean = parse_digest_hours(hours)
    async with pool.acquire() as conn:
        if not clean:
            await conn.execute(
                '''UPDATE users SET digest_hours = NULL, digest_hour = NULL
                    WHERE user_id = $1''', user_id)
            return
        await conn.execute(
            '''UPDATE users SET
                 digest_hours = $2,
                 -- Eski ustun ham yangilanadi: kod qaytarilsa ham
                 -- foydalanuvchi obunasiz qolib ketmasin.
                 digest_hour = $3,
                 digest_topics = COALESCE($4, digest_topics),
                 -- Sozlangan zahoti yubormaslik uchun shu soatni
                 -- "yuborilgan" deb belgilaymiz: aks holda soat allaqachon
                 -- o'tgan bo'lsa daydjest darhol kelib qolardi.
                 digest_sent_date = (NOW() AT TIME ZONE 'Asia/Tashkent')::date,
                 digest_sent_hour = EXTRACT(HOUR FROM (NOW() AT TIME ZONE 'Asia/Tashkent'))::int
               WHERE user_id = $1''',
            user_id, ",".join(str(h) for h in clean), clean[0], topics)


@with_db_retry()
async def expire_premiums() -> List[int]:
    """Muddati tugaganlarni free'ga tushiradi va ro'yxatini qaytaradi.

    check_and_consume_quota() ichidagi inline downgrade ATAYLAB qoldirilgan:
    u foydalanuvchi xabar yozganda darhol ishlaydi, bu esa foydalanuvchi
    umuman yozmasa ham 6 soat ichida ishlaydi. Ikkalasi ham idempotent.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''UPDATE users
               SET plan_type = 'free', premium_until = NULL, premium_reminded_for = NULL
               WHERE plan_type <> 'free'
                 AND premium_until IS NOT NULL AND premium_until <= NOW()
               RETURNING user_id'''
        )
        return [r['user_id'] for r in rows]


# ═══════════════════════════════════════════════════════════════════
#  ADMIN PANEL: JURNALLAR, LIMITLAR, REJALASHTIRILGAN TARQATMA
# ═══════════════════════════════════════════════════════════════════

# Xato jurnalida saqlanadigan eng ko'p yozuv. U diagnostika vositasi,
# arxiv emas — cheksiz o'sishi kerak emas.
ERROR_LOG_KEEP = 500


@with_db_retry()
async def log_error(kind: str, message: str, user_id: Optional[int] = None) -> None:
    """Xatoni jurnalga yozadi (admin panelida ko'rish uchun).

    ⚠️ HECH QACHON istisno otmaydi: bu funksiya `except` bloklaridan
    chaqiriladi, ya'ni bu yerdagi xato ASL xatoni yashirib yuborardi.
    """
    global pool
    try:
        if pool is None:
            await create_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO error_log (kind, message, user_id) VALUES ($1, $2, $3)',
                (kind or "other")[:50], (message or "")[:2000], user_id)
            # Eng eskilarini shu yerda yig'ishtiramiz — alohida tozalash
            # vazifasi kerak bo'lmasligi uchun.
            await conn.execute(
                '''DELETE FROM error_log WHERE id < (
                       SELECT MIN(id) FROM (
                           SELECT id FROM error_log ORDER BY id DESC LIMIT $1
                       ) t)''', ERROR_LOG_KEEP)
    except Exception:
        logger.exception("log_error yozib bo'lmadi")


# ⚠️ FILTR BITTA JOYDA QURILADI. Ro'yxat va SANOQ bir xil shartni
# ishlatishi SHART — aks holda panel «142 tadan 1-20» deb yozib, sahifa
# oxiriga yetganda bo'sh ro'yxat chiqarardi va buni hech narsa
# ko'rsatmasdi. Shu sababli ikkalasi ham shu yordamchidan o'tadi.
#
# ⚠️ Qiymatlar HAR DOIM parametr ($1, $2…), hech qachon satrga qo'shib
# yozilmaydi. Bu admin kiritgan matn bo'lsa ham shunday: admin kiritishi
# ham ishonchsiz chegara (CLAUDE.md, «Model output is an untrusted
# boundary» bo'limidagi qoidaning aynan o'zi).
def _jurnal_filtri(ustunlar: tuple, q: Optional[str], kun: Optional[int],
                   boshlangich: list) -> tuple:
    """(shartlar_satri, argumentlar). `boshlangich` — allaqachon bor args."""
    shartlar: List[str] = []
    args = list(boshlangich)

    if kun:
        # ⚠️ `make_interval(days => $N::int)`, satr yopishtirish EMAS.
        # Eski `($N || ' days')::interval` da asyncpg $N ni `text` deb
        # bilardi va int berilsa DataError tashlardi — butun jurnal
        # ekrani va ogohlantirish kuzatuvchisi shu bitta satrda yiqilgan
        # edi. `str()` bilan yopish ishlagan, lekin tuzoq joyida qolgan:
        # keyingi yozuvchi yana int beradi. `make_interval` da tur
        # to'g'ridan-to'g'ri int, ya'ni tuzoqning o'zi yo'q.
        args.append(int(kun))
        shartlar.append(
            f"created_at >= NOW() - make_interval(days => ${len(args)}::int)")

    frag = (q or "").strip()[:64]
    if len(frag) >= 2:
        args.append(f"%{frag}%")
        n = len(args)
        shartlar.append("(" + " OR ".join(f"{u} ILIKE ${n}" for u in ustunlar) + ")")

    return (" WHERE " + " AND ".join(shartlar) if shartlar else ""), args


@with_db_retry()
async def recent_errors(limit: int = 15, offset: int = 0, *,
                        q: Optional[str] = None,
                        kun: Optional[int] = None) -> List[Dict[str, Any]]:
    global pool
    if pool is None:
        await create_db_pool()
    shart, args = _jurnal_filtri(("kind", "message"), q, kun, [limit, offset])
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f'''SELECT id, kind, message, user_id, created_at FROM error_log
                {shart}
                ORDER BY id DESC LIMIT $1 OFFSET $2''', *args)
        return [dict(r) for r in rows]


@with_db_retry()
async def count_errors(q: Optional[str] = None,
                       kun: Optional[int] = None) -> int:
    """Filtrga tushgan xatolar soni — ro'yxat bilan AYNAN bir shartda."""
    global pool
    if pool is None:
        await create_db_pool()
    shart, args = _jurnal_filtri(("kind", "message"), q, kun, [])
    async with pool.acquire() as conn:
        return await conn.fetchval(
            f"SELECT COUNT(*) FROM error_log{shart}", *args) or 0


# ═══════════════════════════════════════════════════════════════════
#  TOKEN HISOBI
# ═══════════════════════════════════════════════════════════════════
# NEGA: bot kunlik BEPUL grant ustida ishlaydi va uning qanchasi
# yeyilgani hech qayerda ko'rinmasdi — faqat Railway logidagi [TOKEN]
# qatorlarida. Ya'ni eng qimmat xavf eng ko'rinmas joyda turardi.
#
# ⚠️ YOZISH JAVOBNI KUTTIRMAYDI va HECH QACHON yiqilmaydi: hisob
# javobdan muhimroq emas. Xato bo'lsa jim o'tadi, logda iz qoladi.
TOKEN_SAQLASH_KUN = 90          # undan eskisi qirqiladi


@with_db_retry()
async def token_yoz(user_id: Optional[int], model: str, kirish: int,
                    chiqish: int, keshdan: int = 0,
                    manba: Optional[str] = None) -> None:
    """Bitta model chaqiruvining sarfini yozadi."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            '''INSERT INTO user_history
                   (user_id, tokens_used, kirish, chiqish, keshdan, model, manba)
               VALUES ($1, $2, $3, $4, $5, $6, $7)''',
            user_id, (kirish or 0) + (chiqish or 0),
            kirish or 0, chiqish or 0, keshdan or 0, (model or "")[:60], manba)


@with_db_retry()
async def token_tozala() -> int:
    """Eski qatorlarni o'chiradi. Qaytadi: o'chirilgan soni."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        holat = await conn.execute(
            "DELETE FROM user_history WHERE created_at < NOW() - "
            f"INTERVAL '{int(TOKEN_SAQLASH_KUN)} days'")
    try:
        return int(str(holat).rsplit(" ", 1)[-1])
    except (ValueError, IndexError):
        return 0


@with_db_retry()
async def token_stats(kunlar: int = 30) -> Dict[str, Any]:
    """Panel uchun: bugun, kecha va kunlik qator.

    ⚠️ KUN TOSHKENT BO'YICHA. `created_at` ustuni TIMESTAMP (mintaqasiz)
    va NOW() dan to'ladi, ya'ni UTC. Kesim UTC bo'yicha olinsa, «bugun»
    soat 05:00 da almashardi va admin ertalab kechagi raqamni ko'rardi.

    ⛔️ Har bir SUM() `::bigint` ga o'tkaziladi. Postgres'da SUM(BIGINT)
    NUMERIC qaytaradi, asyncpg uni `Decimal` qiladi, va `Decimal` JSON
    ga serializatsiya QILINMAYDI — ya'ni butun Boshqaruv ekrani 500
    bilan yiqiladi. Jadval bo'sh ekan SUM NULL qaytargani uchun bu
    deployda emas, birinchi foydalanuvchi kelganda chiqdi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    kunlar = max(1, min(int(kunlar), 365))
    async with pool.acquire() as conn:
        qator = await conn.fetch(
            f'''SELECT ((created_at AT TIME ZONE 'UTC')
                          AT TIME ZONE 'Asia/Tashkent')::date AS kun,
                       COALESCE(SUM(kirish), 0)::bigint  AS kirish,
                       COALESCE(SUM(chiqish), 0)::bigint AS chiqish,
                       COALESCE(SUM(keshdan), 0)::bigint AS keshdan,
                       COUNT(*) AS raund
                FROM user_history
                WHERE created_at >= NOW() - INTERVAL '{kunlar} days'
                GROUP BY 1 ORDER BY 1''')
        eng = await conn.fetch(
            '''SELECT user_id, COALESCE(SUM(kirish + chiqish), 0)::bigint AS jami,
                      COUNT(*) AS raund
               FROM user_history
               WHERE created_at >= NOW() - INTERVAL '7 days'
                 AND user_id IS NOT NULL
               GROUP BY user_id ORDER BY jami DESC LIMIT 10''')
    return {
        "kunlik": [dict(r) for r in qator],
        "eng_qimmat": [dict(r) for r in eng],
    }


@with_db_retry()
async def last_activity_at() -> Optional[datetime]:
    """Oxirgi foydalanuvchi amali qachon bo'lgan.

    «Bot jim» ogohlantirishi uchun: polling yiqilsa ham, OpenAI yiqilsa
    ham, baza yozilmay qolsa ham natija bitta — yangi qator paydo
    bo'lmaydi. Shu sababli bu YAGONA raqam uchala buzilishni ham
    ko'rsatadi, va u indeksdan bitta qator o'qiydi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT MAX(activity_time) FROM user_activity")


@with_db_retry()
async def error_summary() -> Dict[str, Any]:
    """Xatolar bo'yicha qisqacha: sutkalik/haftalik son va turlari."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            '''SELECT COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS day,
                      COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS week,
                      COUNT(*) AS total,
                      COUNT(DISTINCT user_id) FILTER (
                          WHERE created_at >= NOW() - INTERVAL '24 hours') AS users_day
               FROM error_log''')
        kinds = await conn.fetch(
            '''SELECT kind, COUNT(*) AS cnt FROM error_log
               WHERE created_at >= NOW() - INTERVAL '7 days'
               GROUP BY kind ORDER BY cnt DESC LIMIT 6''')
        out = dict(row) if row else {}
        out['kinds'] = [(r['kind'], r['cnt']) for r in kinds]
        return out


# Audit ustunlari: qidiruv amal nomi, tafsilot va IKKALA tomonning
# username'i bo'yicha ishlaydi. «Kim nima qilgan» ham, «kimga qilingan»
# ham bitta qidiruv maydonidan topilishi kerak.
_AUDIT_QIDIRUV = ("a.action", "a.details", "u.username", "t.username")


def _audit_filtri(admin_id: Optional[int], q: Optional[str],
                  kun: Optional[int], boshlangich: list) -> tuple:
    """Audit uchun filtr — `created_at` emas, `action_time` ustunida."""
    shartlar: List[str] = []
    args = list(boshlangich)
    if admin_id is not None:
        args.append(admin_id)
        shartlar.append(f"a.admin_id = ${len(args)}")
    if kun:
        args.append(int(kun))               # int — `_jurnal_filtri` ga qarang
        shartlar.append(
            f"a.action_time >= NOW() - make_interval(days => ${len(args)}::int)")
    frag = (q or "").strip()[:64]
    if len(frag) >= 2:
        args.append(f"%{frag}%")
        n = len(args)
        shartlar.append(
            "(" + " OR ".join(f"{u} ILIKE ${n}" for u in _AUDIT_QIDIRUV) + ")")
    return (" WHERE " + " AND ".join(shartlar) if shartlar else ""), args


# Sanoq ham AYNAN shu JOIN'lardan o'tishi shart: qidiruv `u.username` va
# `t.username` ga tegadi, ya'ni JOIN'siz sanoq boshqa raqam berardi.
_AUDIT_FROM = '''FROM admin_audit a
                LEFT JOIN users u ON u.user_id = a.admin_id
                LEFT JOIN users t ON t.user_id = a.target_user_id'''


@with_db_retry()
async def get_admin_audit(limit: int = 10, offset: int = 0,
                          admin_id: Optional[int] = None, *,
                          q: Optional[str] = None,
                          kun: Optional[int] = None) -> List[Dict[str, Any]]:
    """Audit jurnali sahifasi: admin, matn va sana oralig'i bo'yicha."""
    global pool
    if pool is None:
        await create_db_pool()
    shart, args = _audit_filtri(admin_id, q, kun, [limit, offset])
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f'''SELECT a.id, a.admin_id, a.action, a.target_user_id, a.details,
                       a.action_time, u.username AS admin_username,
                       t.username AS target_username
                {_AUDIT_FROM}
                {shart}
                ORDER BY a.id DESC LIMIT $1 OFFSET $2''', *args)
        return [dict(r) for r in rows]


@with_db_retry()
async def count_admin_audit(admin_id: Optional[int] = None, *,
                            q: Optional[str] = None,
                            kun: Optional[int] = None) -> int:
    global pool
    if pool is None:
        await create_db_pool()
    shart, args = _audit_filtri(admin_id, q, kun, [])
    async with pool.acquire() as conn:
        return await conn.fetchval(
            f"SELECT COUNT(*) {_AUDIT_FROM}{shart}", *args) or 0


@with_db_retry()
async def search_users(fragment: str, limit: int = 12) -> List[Dict[str, Any]]:
    """Foydalanuvchini username BO'LAGI bo'yicha qidiradi.

    Ilgari faqat ANIQ @username yoki ID ishlardi — admin nomni to'liq
    eslay olmasa hech narsa topolmasdi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    frag = (fragment or "").strip().lstrip("@")
    if len(frag) < 2:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''SELECT user_id, username, plan_type, is_banned, last_seen
               FROM users
               WHERE username ILIKE $1
               ORDER BY last_seen DESC NULLS LAST
               LIMIT $2''', f"%{frag}%", limit)
        return [dict(r) for r in rows]


@with_db_retry()
async def get_limit_overrides() -> Dict[str, Any]:
    """Bazadagi limit o'zgartirishlari. Bo'sh dict = config'dagi qiymat."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        raw = await conn.fetchval(
            'SELECT limit_overrides FROM bot_settings WHERE id = 1')
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return dict(raw)


@with_db_retry()
async def set_limit_override(plan: str, key: str,
                             value: Optional[int]) -> Dict[str, Any]:
    """Bitta limitni o'zgartiradi va YANGI to'plamni qaytaradi.

    `value=None` — o'zgartirishni olib tashlaydi, ya'ni config'dagi
    qiymatga qaytadi (cheksizlik EMAS: cheksiz uchun premium tarifi bor).
    """
    current = await get_limit_overrides()
    bolim = dict(current.get(plan) or {})
    if value is None:
        bolim.pop(key, None)
    else:
        bolim[key] = int(value)
    if bolim:
        current[plan] = bolim
    else:
        current.pop(plan, None)
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE bot_settings SET limit_overrides = $1::jsonb WHERE id = 1',
            json.dumps(current))
    return current


# ── Rejalashtirilgan tarqatma ──────────────────────────────────────

@with_db_retry()
async def create_scheduled_broadcast(admin_id: int, src_chat_id: int,
                                     src_message_id: int, buttons: list,
                                     segment: str, run_at: datetime) -> int:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            '''INSERT INTO scheduled_broadcasts
                   (admin_id, src_chat_id, src_message_id, buttons, segment, run_at)
               VALUES ($1, $2, $3, $4::jsonb, $5, $6) RETURNING id''',
            admin_id, src_chat_id, src_message_id,
            json.dumps(buttons or []), segment, run_at)


@with_db_retry()
async def list_scheduled_broadcasts() -> List[Dict[str, Any]]:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''SELECT id, admin_id, segment, run_at FROM scheduled_broadcasts
               WHERE sent_at IS NULL ORDER BY run_at''')
        return [dict(r) for r in rows]


@with_db_retry()
async def cancel_scheduled_broadcast(broadcast_id: int) -> bool:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        res = await conn.execute(
            'DELETE FROM scheduled_broadcasts WHERE id = $1 AND sent_at IS NULL',
            broadcast_id)
        return res.endswith("1")


@with_db_retry()
async def due_scheduled_broadcasts() -> List[Dict[str, Any]]:
    """Vaqti kelgan tarqatmalar. Oluvchilar YUBORISH paytida hisoblanadi."""
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            '''SELECT id, admin_id, src_chat_id, src_message_id, buttons, segment
               FROM scheduled_broadcasts
               WHERE sent_at IS NULL AND run_at <= NOW()
               ORDER BY run_at LIMIT 5''')
        out = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get('buttons'), str):
                try:
                    d['buttons'] = json.loads(d['buttons'])
                except Exception:
                    d['buttons'] = []
            out.append(d)
        return out


@with_db_retry()
async def mark_broadcast_sent(broadcast_id: int) -> None:
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE scheduled_broadcasts SET sent_at = NOW() WHERE id = $1',
            broadcast_id)


# ═══════════════════════════════════════════════════════════════════
#  STATISTIKA — TELEGRAM EKRANI VA WEB PANEL UCHUN BITTA MANBA
# ═══════════════════════════════════════════════════════════════════
# ⚠️ Bu ikki funksiya `handlers/admin/stats.py` dan KO'CHIRILDI (REJA
# 3.2). Sabab: web panel o'sha raqamlarni ko'rsatadi, va so'rovlar
# handler ichida qolsa web ularni qayta yozishga majbur bo'lardi —
# ikki nusxa, bittasi o'zgarganda ikkinchisi jimgina eskirardi va
# "panelda 100, Telegramda 103" degan holat chiqardi. Endi ikkala
# ekran ham AYNAN shu satrlardan o'qiydi.

# Adminlar hamma sanoqdan chiqarib tashlanadi — ular bot mijozi emas.
# ⚠️ Ikkala so'rovda ham BIR XIL bo'lishi shart: ilgari `total_users`
# ularni chiqarib, tarif sanog'i chiqarmagan va ekranda "jami 100,
# free+pro+premium = 103" chiqib, admin raqamlarga ishonmay qolgan edi.
_ODDIY_USER = """
      AND user_id NOT IN (SELECT user_id FROM admins)
      AND user_id NOT IN (SELECT user_id FROM superadmins)
"""


@with_db_retry()
async def top_users(days: int, limit: int) -> List[Dict[str, Any]]:
    """Eng faol foydalanuvchilar — `days` kun ichida, `limit` tagacha.

    `days` va `limit` SQL ga PARAMETR bo'lib ketadi, satr sifatida
    yopishtirilmaydi. Hozir ikkalasini ham kod beradi, lekin web
    panelda ular URL dan kelishi mumkin — o'sha kun uchun qoldirilgan
    himoya (model chiqargan ma'lumot kabi, bu ham ishonchsiz chegara).
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f'''
            SELECT user_id, username, COUNT(*) AS activity_count
            FROM user_activity
            WHERE activity_time >= NOW() - make_interval(days => $1::int)
              {_ODDIY_USER}
            GROUP BY user_id, username
            ORDER BY activity_count DESC
            LIMIT $2
        ''', int(days), int(limit))
        return [dict(r) for r in rows]


# Tarif shartlari — UCHALASI KESISHMAYDI, ya'ni pro + free + ban = jami.
# Bloklangan odam «bepul» sanog'ida ham turgan bo'lsa, chiplardagi
# sonlar qo'shilganda jamidan oshib ketardi va admin raqamlarga
# ishonmay qolardi (bu xato bir marta bo'lgan — `_ODDIY_USER` izohiga
# qarang).
#
# ⚠️ SHARTLAR SHU YERDA, BITTA JOYDA. Ilgari ular uchta so'rovda uch
# marta yozilgandi va uchtasi ham boshqacha edi: `list_users` bloklangan
# odamni «pro» sanog'idan chiqarardi, `activity_stats` esa chiqarmasdi,
# `daily_report_stats` esa adminlarni ham qo'shib sanardi. Natijada
# bitta ekranda «Pro obunachilar 2», ikkinchisida «Pro 1 · Premium 1»,
# uchinchisida «2 tasi Pro» chiqib turardi — uchta raqam, uchta ta'rif.
_PRO_SHART = "(is_banned IS NOT TRUE AND COALESCE(plan_type,'free') <> 'free')"
_FREE_SHART = "(is_banned IS NOT TRUE AND COALESCE(plan_type,'free') = 'free')"
_BAN_SHART = "(is_banned = TRUE)"

_TARIF_SHARTI = f"""
    CASE $3::text
      WHEN 'pro'  THEN {_PRO_SHART}
      WHEN 'free' THEN {_FREE_SHART}
      WHEN 'ban'  THEN {_BAN_SHART}
      ELSE TRUE
    END
"""


# Ro'yxat tartibi. Kalit paneldan keladi, ya'ni ISHONCHSIZ — shuning
# uchun u SQL ga yopishtirilmaydi, balki SHU ro'yxatdan tanlanadi.
_TARTIB = {
    "faollik": "last_seen DESC NULLS LAST, user_id",
    "yangi":   "created_at DESC NULLS LAST, user_id",
}


@with_db_retry()
async def list_users(q: Optional[str] = None, tarif: str = "all",
                     limit: int = 20, offset: int = 0,
                     tartib: str = "faollik") -> Dict[str, Any]:
    """Web paneldagi foydalanuvchilar jadvali: qidiruv + filtr + sahifa.

    Nega yangi funksiya: `get_all_users()` da na chegara, na filtr bor —
    u HAMMA qatorni tortadi, `search_users()` esa faqat username
    bo'yicha qidiradi va sahifalamaydi. Sahifani Python tomonda kesish
    har bosilganda butun jadvalni o'qish degani.

    ⚠️ `q` — ADMIN yozgan matn, ya'ni ishonchsiz. U SQL ga PARAMETR
    bo'lib ketadi, satrga yopishtirilmaydi.

    Adminlar ro'yxatda yo'q (`_ODDIY_USER`) — panelning boshqa hamma
    sanog'i ham ularsiz, ikki xil «jami» ko'rsatish mumkin emas.
    Adminlar Sozlamalar → Adminlar ekranida boshqariladi.
    """
    global pool
    if pool is None:
        await create_db_pool()

    # ⚠️ `tarif == "nofaol"` — BOTNI BLOKLAGANLAR (`is_active = FALSE`).
    # Qolgan hamma filtr faqat FAOL qatorlarni ko'radi, ya'ni shart
    # ikkalasi uchun bir xil bo'lolmaydi. Ilgari bu ro'yxat Jurnal
    # ekranida alohida jadval edi — bir xil odamlar ikki ekranda ikki
    # xil ustun bilan ko'rsatilardi.
    nofaol = tarif == "nofaol"
    faollik = "is_active = FALSE" if nofaol else "is_active = TRUE"
    if nofaol:
        tarif = "all"
    buyruq = _TARTIB.get(tartib, _TARTIB["faollik"])

    frag = (q or "").strip().lstrip("@") or None
    # Faqat raqamdan iborat so'rov — ID bo'lishi mumkin. `int()` ni
    # ataylab cheklaymiz: BIGINT dan katta son so'rovni yiqitardi.
    uid = None
    if frag and frag.isdigit() and len(frag) <= 18:
        uid = int(frag)

    qidiruv = """
        AND ($1::text IS NULL
             OR username ILIKE '%' || $1 || '%'
             OR ($2::bigint IS NOT NULL AND user_id = $2))
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(f'''
            SELECT user_id, username, plan_type, is_banned, premium_until,
                   created_at, last_seen
            FROM users
            WHERE {faollik} {_ODDIY_USER} {qidiruv}
              AND {_TARIF_SHARTI}
            ORDER BY {buyruq}
            LIMIT $4 OFFSET $5
        ''', frag, uid, tarif, int(limit), int(offset))

        jami = await conn.fetchval(f'''
            SELECT COUNT(*) FROM users
            WHERE {faollik} {_ODDIY_USER} {qidiruv}
              AND {_TARIF_SHARTI}
        ''', frag, uid, tarif)

        # Chip yorliqlaridagi sonlar — qidiruvdan QAT'I NAZAR: ular
        # «shu toifada nechta bor» degan ma'noni bildiradi.
        sanoq = await conn.fetchrow(f'''
            SELECT COUNT(*) AS all,
                   COUNT(*) FILTER (WHERE {_PRO_SHART})  AS pro,
                   COUNT(*) FILTER (WHERE {_FREE_SHART}) AS free,
                   COUNT(*) FILTER (WHERE {_BAN_SHART})  AS ban
            FROM users WHERE is_active = TRUE {_ODDIY_USER}
        ''')
        # Nofaollar alohida sanaladi: ular yuqoridagi to'rttasiga
        # kirmaydi (`is_active = FALSE`), ya'ni chip soni bo'lmasa
        # admin ro'yxat bor-yo'qligini bosib ko'rishga majbur bo'lardi.
        nofaol_soni = await conn.fetchval(f'''
            SELECT COUNT(*) FROM users WHERE is_active = FALSE {_ODDIY_USER}
        ''')
        return {
            "rows": [dict(r) for r in rows],
            "jami": jami or 0,
            "sanoq": dict(sanoq, nofaol=nofaol_soni or 0) if sanoq else {},
        }


@with_db_retry()
async def activity_stats(kunlar: int = 7) -> Dict[str, Any]:
    """Statistika ekranining hamma raqami — bitta ulanishda.

    Qaytaradi: `total_users`, tarif sanoqlari, eng faollar, oxirgi
    foydalanuvchi, `kunlar` kunlik faollik va 30 kunlik turlar kesimi.

    `kunlar` — grafik oynasi (7 / 30 / 90). Panelda tanlanadi, shuning
    uchun u ISHONCHSIZ qiymat: SQL ga parametr bo'lib ketadi va bu yerda
    chegaralanadi.
    """
    kunlar = max(1, min(int(kunlar), 365))
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        total_users = await conn.fetchval(f'''
            SELECT COUNT(*) FROM users
            WHERE is_active = TRUE {_ODDIY_USER}
        ''')

        # ⚠️ To'rttasi QO'SHILGANDA `total_users` ga TENG bo'ladi va bu
        # shart: panel ularni bitta doiraga chizadi. Ilgari bloklangan
        # odam ham `free_count` ichida turardi, ya'ni doira jamidan
        # oshib ketishi mumkin edi.
        plan_counts = await conn.fetchrow(f'''
            SELECT
                COUNT(*) FILTER (WHERE {_FREE_SHART}) AS free_count,
                COUNT(*) FILTER (WHERE is_banned IS NOT TRUE
                                   AND plan_type = 'pro') AS pro_count,
                COUNT(*) FILTER (WHERE is_banned IS NOT TRUE
                                   AND COALESCE(plan_type,'free')
                                       NOT IN ('free', 'pro')) AS premium_count,
                COUNT(*) FILTER (WHERE {_BAN_SHART}) AS ban_count
            FROM users
            WHERE is_active = TRUE {_ODDIY_USER}
        ''')

        most_active_30days = await conn.fetchrow(f'''
            SELECT user_id, username, COUNT(*) AS activity_count
            FROM user_activity
            WHERE activity_time >= NOW() - INTERVAL '30 days' {_ODDIY_USER}
            GROUP BY user_id, username ORDER BY activity_count DESC LIMIT 1
        ''')

        most_active_today = await conn.fetchrow(f'''
            SELECT user_id, username, COUNT(*) AS activity_count
            FROM user_activity
            WHERE activity_time >= CURRENT_DATE {_ODDIY_USER}
            GROUP BY user_id, username ORDER BY activity_count DESC LIMIT 1
        ''')

        last_user = await conn.fetchrow(f'''
            SELECT user_id, username, created_at FROM users
            WHERE TRUE {_ODDIY_USER}
            ORDER BY created_at DESC LIMIT 1
        ''')

        # Kun chegarasi Toshkent bo'yicha — server UTC da ishlaydi, ya'ni
        # aks holda "bugun" soat 05:00 da boshlanardi.
        #
        # ⚠️ Oyna ham KUNGA tekislangan. Ilgari u `NOW() - INTERVAL '7
        # days'` edi — ya'ni aylanma 168 soat — va eng chekkadagi kun
        # HAR DOIM chala chiqardi: ertalab ochilgan panelda 7 kun oldingi
        # kunning faqat ertalabki soatlari sanalardi va grafik o'sha
        # yerdan «pastdan» boshlanardi. Bu tushish emas, kesilgan kun.
        daily_activity = await conn.fetch(f'''
            SELECT (activity_time AT TIME ZONE 'Asia/Tashkent')::date AS day,
                   COUNT(*) AS total, COUNT(DISTINCT user_id) AS uniq_users
            FROM user_activity
            WHERE activity_time >= NOW() - make_interval(days => $1::int + 1)
              AND (activity_time AT TIME ZONE 'Asia/Tashkent')::date
                  > (NOW() AT TIME ZONE 'Asia/Tashkent')::date - $1::int
              {_ODDIY_USER}
            GROUP BY day ORDER BY day
        ''', kunlar)

        # Turlar ro'yxati `core/config.py::ACTIVITY_TYPES` dan keladi va
        # SQL ga PARAMETR bo'lib uzatiladi — satrga yopishtirilmaydi.
        # ⚠️ Tur ro'yxati bu yerda FILTRLANMAYDI. Ilgari `= ANY($1)`
        # turardi va u yig'indini buzardi: ekranda «24 soatda 150
        # so'rov» yozilib, ustunlar qo'shilganda 142 chiqardi —
        # `ACTIVITY_TYPES` da yo'q turlar (masalan `start`) jimgina
        # tushib qolardi. Endi hammasi qaytadi, panel ro'yxatda
        # yo'qlarini «Boshqa» qatoriga yig'adi (web/api.py::_turlar).
        type_breakdown = await conn.fetch(f'''
            SELECT activity_type, COUNT(*) AS cnt
            FROM user_activity
            WHERE activity_time >= NOW() - INTERVAL '30 days'
              {_ODDIY_USER}
            GROUP BY activity_type ORDER BY cnt DESC
        ''')

        return {
            'total_users': total_users or 0,
            'free_count': (plan_counts or {}).get('free_count', 0) or 0,
            'pro_count': (plan_counts or {}).get('pro_count', 0) or 0,
            'premium_count': (plan_counts or {}).get('premium_count', 0) or 0,
            'ban_count': (plan_counts or {}).get('ban_count', 0) or 0,
            'kunlar': kunlar,
            'most_active_30days': dict(most_active_30days) if most_active_30days else None,
            'most_active_today': dict(most_active_today) if most_active_today else None,
            'last_user': dict(last_user) if last_user else None,
            'daily_activity': [dict(r) for r in daily_activity],
            'type_breakdown': [(r['activity_type'], r['cnt']) for r in type_breakdown],
        }


@with_db_retry()
async def daily_report_stats() -> Dict[str, Any]:
    """Kunlik avtomatik hisobot va panel KPI'lari — bitta so'rovda.

    ⚠️ HAR BIR SANOQDAN ADMINLAR CHIQARILADI (`_ODDIY_USER`). Ilgari bu
    funksiya ularni qo'shib sanardi, `activity_stats()` esa chiqarardi —
    ya'ni bitta ekranning yuqorisida «Pro obunachilar 2», pastida esa
    «Pro 1 · Premium 1» turardi va farq admin edi. Qoida oddiy: admin
    botning mijozi emas, ya'ni HECH QAYERDA sanalmaydi.
    """
    global pool
    if pool is None:
        await create_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f'''
            SELECT
              (SELECT COUNT(*) FROM users
                 WHERE created_at >= NOW() - INTERVAL '24 hours'
                   {_ODDIY_USER}) AS new_users,
              (SELECT COUNT(*) FROM users
                 WHERE is_active = TRUE {_ODDIY_USER}) AS total_users,
              (SELECT COUNT(DISTINCT user_id) FROM user_activity
                 WHERE activity_time >= NOW() - INTERVAL '24 hours'
                   {_ODDIY_USER}) AS active_users,
              (SELECT COUNT(*) FROM star_payments
                 WHERE refunded_at IS NULL
                   AND created_at >= NOW() - INTERVAL '24 hours') AS sales,
              (SELECT COALESCE(SUM(stars), 0) FROM star_payments
                 WHERE refunded_at IS NULL
                   AND created_at >= NOW() - INTERVAL '24 hours') AS stars,
              (SELECT COUNT(*) FROM error_log
                 WHERE created_at >= NOW() - INTERVAL '24 hours') AS errors,
              -- Pro ta'rifi `list_users()` dagi chip bilan AYNAN bir xil
              -- (`_PRO_SHART`): bloklangan odam Pro sanog'ida turmaydi.
              (SELECT COUNT(*) FROM users
                 WHERE is_active = TRUE AND {_PRO_SHART}
                   {_ODDIY_USER}) AS pro_users,
              -- ⬇️ Uchtasi web paneldagi KPI kartochkalari uchun (REJA
              -- 6.1). Kunlik hisobot ularni o'qimaydi — ortiqcha kalit
              -- unga zarar qilmaydi, lekin ALOHIDA so'rov qilish
              -- kerak bo'lardi va raqamlar bir-biriga mos kelmasligi
              -- mumkin edi (ikki so'rov — ikki lahza).
              --
              -- ⚠️ `prev_actions` — AYNAN oldingi 24 soat (48…24 soat
              -- oldin), ya'ni «kechagiga nisbatan» foizi bir xil
              -- uzunlikdagi ikki oraliqni solishtiradi. Ikkalasi ham
              -- aylanma oyna, shuning uchun mintaqa vaqti ularga ta'sir
              -- qilmaydi — «bugun» tushunchasi bu yerda ishlatilmaydi.
              (SELECT COUNT(*) FROM user_activity
                 WHERE activity_time >= NOW() - INTERVAL '48 hours'
                   AND activity_time <  NOW() - INTERVAL '24 hours'
                   {_ODDIY_USER}) AS prev_actions,
              (SELECT COUNT(DISTINCT user_id) FROM user_activity
                 WHERE activity_time >= NOW() - INTERVAL '7 days'
                   {_ODDIY_USER}) AS active_7d,
              -- ⚠️ Muddatsiz (cheksiz) Pro bu sanoqqa TUSHMAYDI va bu
              -- to'g'ri: unda `premium_until IS NULL`, ya'ni tugaydigan
              -- muddati yo'q. `IS NOT NULL` sharti aynan shuning uchun.
              (SELECT COUNT(*) FROM users
                 WHERE is_active = TRUE AND premium_until IS NOT NULL
                   AND premium_until BETWEEN NOW()
                                         AND NOW() + INTERVAL '7 days'
                   {_ODDIY_USER}) AS pro_expiring
            ''')

        # ⚠️ TUR KESIMI TO'LIQ QAYTADI — na `LIMIT 5`, na tur filtri.
        # Ilgari ikkalasi ham bor edi va shuning uchun panelda
        # «24 soatda 150 so'rov» yozilib, ustunlar qo'shilganda 142
        # chiqardi: farq `ACTIVITY_TYPES` da yo'q turlar (`start`) va
        # beshinchidan keyingi turlar edi. Endi `actions` ham SHU
        # ro'yxatdan hisoblanadi, ya'ni yig'indi ta'rifan jamiga teng.
        turlar = await conn.fetch(
            f'''SELECT activity_type, COUNT(*) AS cnt FROM user_activity
                WHERE activity_time >= NOW() - INTERVAL '24 hours'
                  {_ODDIY_USER}
                GROUP BY activity_type ORDER BY cnt DESC''')

        out = dict(row) if row else {}
        kesim = [(r['activity_type'], r['cnt']) for r in turlar]
        out['types_24h'] = kesim
        out['actions'] = sum(c for _t, c in kesim)
        # Kunlik hisobot uchun: eng ko'p ishlatilgan 5 ta AMAL.
        # ⚠️ Filtr shu yerda, LIMIT dan oldin. Filtrsiz ro'yxatga `start`
        # ham tushardi — u so'rov emas, buyruq — va «eng ko'p
        # ishlatilgani» ro'yxatining bir o'rnini bekorga egallardi.
        out['top_types'] = [(t, c) for t, c in kesim if t in ACTIVITY_TYPES][:5]
        return out
