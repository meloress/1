"""Web panel darvozasi: `initData` imzosi, sessiya cookie'si va `@admin_only`.

Uch qatlamdan ikkitasi shu faylda (uchinchisi — menyu tugmasi,
`services/menu.py`). REJA.md 4-bo'limiga qarang.

⚠️ Bu yerda HECH QANDAY ma'lumot qaytarilmaydi. Har bir `/api/*` handler
`@admin_only` bilan boshlanadi va u `is_admin()` ni HAR SO'ROVDA
qaytadan chaqiradi — 12 soatlik cookie adminlikdan chiqarilgan odamni
o'sha muddat davomida ichkarida ushlab turmasligi kerak.
"""

import asyncio
import functools
import hashlib
import hmac
import logging
import os
import time
from typing import Optional

from aiohttp import web
from aiogram.utils.web_app import safe_parse_webapp_init_data

from core.config import BOT_TOKEN
from db import database as database_module

logger = logging.getLogger(__name__)

COOKIE_NAME = "sid"
SESSION_TTL = 12 * 3600          # REJA 4.2: 12 soat
INIT_DATA_MAX_AGE = 5 * 60       # qayta ishlatishga qarshi: 5 daqiqa

# ── Har so'rovdagi imzo ─────────────────────────────────────────────
# Panel HAR so'rovga Telegram bergan `initData` ni shu sarlavhada
# qo'shadi va server uni HAR SAFAR bot tokeni bilan qayta tekshiradi.
#
# ⚠️ Nega yoshi 24 soat, `/api/session` dagi 5 daqiqa emas: `initData`
# Mini App ochilganda BIR MARTA beriladi va keyin YANGILANMAYDI —
# `auth_date` o'sha lahzada qotadi. 5 daqiqalik chegara bu yerda
# panelni besh daqiqadan keyin o'ligiga aylantirardi. 24 soat —
# Telegram hujjatining o'z tavsiyasi.
#
# Cookie YO'Q QILINMADI: brauzerda (Telegramdan tashqarida) ochilgan
# panelda `initData` umuman bo'lmaydi, va `/api/session` dagi 5
# daqiqalik qat'iy tekshiruv aynan o'sha cookie'ni berish uchun turadi.
# Ya'ni ikkita yo'l bor va ikkalasi ham imzoga tayanadi.
INIT_DATA_HEADER = "X-Telegram-Init-Data"
INIT_DATA_SOROV_MAX_AGE = 24 * 3600
SESSION_RATE_LIMIT = 10          # bitta IP — daqiqasiga 10 ta urinish
# Bitta ADMIN — daqiqasiga nechta yozuv.
#
# ⚠️ BU SON ODAMNI EMAS, SKRIPTNI to'xtatish uchun. Admin allaqachon
# imzo va huquq tekshiruvidan o'tgan, ya'ni bu chegara asosiy himoya
# emas — u o'g'irlangan sessiya yoki adashgan sikl minglab yozuv
# qilishini cheklaydi. Shuning uchun u haqiqiy foydalanishga YAQIN
# qilib tanlanmaydi: yaqin qo'yilgan chegara qonuniy portlashda ham
# ishlab ketadi va admin uni e'tiborsiz qoldirishni o'rganadi —
# o'shanda haqiqiysi ham o'tib ketadi.
#
# Odam sekundiga ikkita yozuvni davomiy qila olmaydi; skript esa
# yuzlabini qiladi. O'lchov: test to'plamining eng og'ir fayli bir
# necha soniyada 31 ta yozuv qiladi — ya'ni 30 juda tor edi.
YOZUV_RATE_LIMIT = 120

# ⚠️ XOM XFF TEKSHIRUVI — VAQTINCHA. `True` bo'lsa har `/api/session`
# so'rovida xom `X-Forwarded-For` va TCP peer manzili logga yoziladi.
# Railway proksisi haqiqiy IP ni qaysi pozitsiyaga qo'yishini aniqlash
# uchun kerak — bu hujjatlashtirilmagan va faqat jonli tekshiruv aytadi.
# ⛔️ Aniqlangach `False` ga qaytaring: bu qator IP manzillarni logga
# yozadi, ya'ni kerak bo'lmaganda yozilmasligi kerak.
XFF_TEKSHIR = os.getenv("XFF_TEKSHIR", "") == "1"

# Haqiqiy klient IP si XFF ning O'NGDAN nechanchisi. Izohni
# `_klient_ip()` da o'qing.
ISHONCHLI_PROKSI = 1

# ponytail: kalit -> [vaqt, ...] RAM'da. Bitta jarayon, bir necha admin
# — Redis ortiqcha. Kerak bo'lsa: bazaga jadval yoki nginx darajasida.
#
# ⚠️ HAJMI CHEGARALANGAN. Ilgari bu dict HECH QACHON tozalanmasdi:
# har yangi kalit abadiy qolardi, ya'ni soxta `X-Forwarded-For` bilan
# uni cheksiz o'stirish mumkin edi — xotira orqali DoS. Endi muddati
# o'tgani o'chiriladi va umumiy soni `CHASTOTA_MAX` bilan cheklangan.
CHASTOTA_OYNA = 60               # soniya
CHASTOTA_MAX = 2000              # kuzatiladigan kalitlar soni
_urinishlar: dict[str, list[float]] = {}


def _kalit() -> bytes:
    """Cookie imzosi uchun kalit — BOT_TOKEN dan OLINGAN HOSILA.

    Tokenning o'zi ishlatilmaydi: cookie imzosi sizib chiqsa ham undan
    tokenni tiklab bo'lmasin. Telegram `initData` uchun boshqa hosila
    ishlatadi, ya'ni ikki imzo bir-biriga aralashmaydi.
    """
    return hashlib.sha256(f"webpanel:{BOT_TOKEN}".encode()).digest()


def sessiya_yasa(user_id: int) -> str:
    """`user_id.muddat.imzo` — jadval kerak emas, hammasi cookie ichida."""
    payload = f"{user_id}.{int(time.time()) + SESSION_TTL}"
    imzo = hmac.new(_kalit(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{imzo}"


def sessiya_ochi(cookie: Optional[str]) -> Optional[int]:
    """Cookie'dan `user_id`. Imzo buzilgan yoki muddati o'tgan bo'lsa None."""
    if not cookie:
        return None
    try:
        uid_s, exp_s, imzo = cookie.rsplit(".", 2)
        kutilgan = hmac.new(_kalit(), f"{uid_s}.{exp_s}".encode(),
                            hashlib.sha256).hexdigest()
        # compare_digest — imzoni belgima-belgi taxminlashning oldini oladi.
        if not hmac.compare_digest(imzo, kutilgan):
            return None
        if int(exp_s) < time.time():
            return None
        return int(uid_s)
    except Exception:
        return None


def init_data_tekshir(init_data: str, max_age: int = INIT_DATA_MAX_AGE):
    """Telegram imzosi + yoshi. Xato bo'lsa ValueError.

    `safe_parse_webapp_init_data` HMAC ni o'zi tekshiradi (aiogram'da
    tayyor), lekin YOSHINI tekshirmaydi: bir marta o'g'irlangan
    `initData` abadiy amal qilardi.
    """
    data = safe_parse_webapp_init_data(BOT_TOKEN, init_data)
    if time.time() - data.auth_date.timestamp() > max_age:
        raise ValueError("initData eskirgan")
    return data


def imzodan_user_id(request: web.Request) -> Optional[int]:
    """So'rov sarlavhasidagi `initData` dan `user_id`. Yo'q/buzuq — None.

    Imzo bot tokeni bilan HAR SO'ROVDA qayta hisoblanadi, ya'ni
    sarlavhaning bir belgisi o'zgarsa ham so'rov rad etiladi.
    """
    xom = request.headers.get(INIT_DATA_HEADER)
    if not xom:
        return None
    try:
        data = init_data_tekshir(xom, INIT_DATA_SOROV_MAX_AGE)
    except Exception as exc:
        logger.info(f"[web] sarlavhadagi imzo rad etildi: {exc}")
        return None
    return data.user.id if data.user else None


def _klient_ip(request: web.Request) -> str:
    """Haqiqiy klient IP si.

    ⛔️ XFF NING BIRINCHI QIYMATI EMAS. Ilgari shunday edi va bu
    chegarani BEKOR qilardi: `X-Forwarded-For` ni mijozning O'ZI
    yozadi, ya'ni har so'rovda boshqa qiymat yuborib cheksiz urinish
    mumkin edi — hamda har bir soxta qiymat `_urinishlar` da abadiy
    kalit qoldirardi.

    Proksi haqiqiy IP ni ro'yxatning OXIRIGA qo'shadi, ya'ni ishonch
    o'ngdan chapga kamayadi: eng o'ngdagi — bizga eng yaqin proksi
    yozgan qiymat, eng chapdagi — mijozning o'zi yozgani.
    `ISHONCHLI_PROKSI` — o'ngdan nechanchisini olish (1 = eng o'ngdagi).

    ⚠️ Bu son Railway'ning necha qavat proksisi borligiga bog'liq va
    hujjatlashtirilmagan. `XFF_TEKSHIR=1` bilan deploy qilib logdagi
    `[XFF]` qatorlariga qarang, keyin shu sonni to'g'rilang.
    """
    xom = request.headers.get("X-Forwarded-For", "")
    qismlar = [q.strip() for q in xom.split(",") if q.strip()]
    if len(qismlar) >= ISHONCHLI_PROKSI:
        return qismlar[-ISHONCHLI_PROKSI]
    # XFF yo'q yoki kutilganidan qisqa — TCP peer o'zi. Proksi ortida
    # bu proksining manzili bo'ladi, ya'ni chegara hammaga umumiy
    # bo'lib qoladi; bu XAVFSIZ tomonga xato (ochiq qoldirishdan ko'ra).
    return request.remote or "?"


def _chastota_tozala() -> None:
    """Muddati o'tgan va ortiqcha kalitlarni olib tashlaydi."""
    hozir = time.time()
    for k in [k for k, v in _urinishlar.items()
              if not v or hozir - v[-1] > CHASTOTA_OYNA]:
        _urinishlar.pop(k, None)
    if len(_urinishlar) > CHASTOTA_MAX:
        # Eng eski faollikdagilari birinchi ketadi.
        tartib = sorted(_urinishlar.items(), key=lambda kv: kv[1][-1])
        for k, _v in tartib[:len(_urinishlar) - CHASTOTA_MAX]:
            _urinishlar.pop(k, None)


def chastota_oshdimi(kalit: str, chegara: int = SESSION_RATE_LIMIT) -> bool:
    """`CHASTOTA_OYNA` ichida `chegara` dan ko'p urinish bo'ldimi.

    `kalit` — kirish yo'lida IP, yozish yo'lida `admin:<user_id>`.
    Autentifikatsiyadan o'tgan admin uchun IP ma'nosiz: u mobil
    internetda har necha daqiqada IP almashtiradi.
    """
    hozir = time.time()
    _chastota_tozala()
    tarix = [t for t in _urinishlar.get(kalit, []) if hozir - t < CHASTOTA_OYNA]
    tarix.append(hozir)
    _urinishlar[kalit] = tarix
    return len(tarix) > chegara


# ══ TAKRORIY SO'ROV (idempotentlik) ══════════════════════════
# NEGA: tugmani o'chirish (panel.js) ikki bosishni EKRANDA to'xtatadi,
# lekin server uchun bu himoya emas — sekin tarmoq, sahifa yangilanishi
# yoki oddiygina ikkinchi ilova oynasi baribir ikkita so'rov yuboradi.
# `set_user_premium(..., extend=True)` esa kunlarni QO'SHADI, ya'ni
# ikkinchi so'rov jimgina 30 kunni 60 ga aylantirardi.
#
# ⭐ KALIT MAZMUNDAN OLINADI, tasodifiy EMAS. Tasodifiy UUID ikki
# bosishdan saqlamaydi: ikki bosish ikki xil UUID beradi va ikkala
# so'rov ham «yangi» bo'lib ko'rinadi. Bir xil yo'lga bir xil tana =
# bir xil kalit — mana shu ikki bosishni haqiqatan to'xtatadi.
#
# Oyna ATAYLAB qisqa: 10 soniya ikki bosish uchun yetarlicha uzun,
# «shu odamga yana 30 kun qo'shay» degan ATAYLAB takror uchun esa
# yetarlicha qisqa. Ataylab takror kerak bo'lsa mijoz o'zining
# `Idempotency-Key` sarlavhasini yuboradi va mazmun hash'i o'rniga
# o'sha ishlatiladi.
#
# ponytail: kalitlar RAM'da — panel bot jarayonining ICHIDA ishlaydi
# (REJA 3.1), ya'ni ikkinchi jarayon yo'q va bo'lishish muammosi ham
# yo'q. Cheklov ochiq: deploy paytida kalitlar yo'qoladi, ya'ni o'sha
# bir necha soniyada ikki bosish himoyasiz qoladi. Kerak bo'lsa keyingi
# qadam — `idempotency` jadvali (DB sxemasi o'zgaradi).
BIR_MARTA_OYNA = 10          # soniya
BIR_MARTA_MAX = 500          # kalitlar chegarasi — cheksiz o'smasin

_natijalar: dict[str, tuple] = {}      # kalit -> (vaqt, status, tana, tur)
_qulflar: dict[str, asyncio.Lock] = {}


def _bir_marta_kalit(request: web.Request, tana: bytes) -> str:
    """`user_id + yo'l + (sarlavha yoki tana hash'i)`.

    `user_id` kalit ichida: ikki admin bir vaqtda bir xil amalni
    qilsa, ular BOSHQA-BOSHQA amal — biri ikkinchisiniki bilan
    almashtirilmasligi kerak.
    """
    ustun = request.headers.get("Idempotency-Key", "")[:128]
    # ⚠️ `path_qs`, `path` EMAS. `/api/export?tur=users` va
    # `?tur=payments` bitta yo'lda, tanasi esa ikkalasida ham `{}` —
    # `path` bilan ular BITTA amal bo'lib ko'rinardi va ikkinchi
    # eksport jimgina birinchisining javobini qaytarardi.
    asos = f'{request.get("user_id")}|{request.path_qs}|{ustun}'.encode()
    return hashlib.sha256(asos + tana).hexdigest()


def _bir_marta_tozala() -> None:
    """Muddati o'tganini va ortiqchasini olib tashlaydi."""
    hozir = time.time()
    eski = [k for k, v in _natijalar.items() if hozir - v[0] > BIR_MARTA_OYNA]
    if len(_natijalar) - len(eski) > BIR_MARTA_MAX:
        qolgan = sorted(((v[0], k) for k, v in _natijalar.items()
                         if k not in set(eski)))
        eski += [k for _v, k in qolgan[:len(qolgan) - BIR_MARTA_MAX]]
    for k in eski:
        _natijalar.pop(k, None)
        # ⚠️ BAND qulf O'CHIRILMAYDI. O'chirilsa, kutib turgan ikkinchi
        # so'rov yangi qulf olib, birinchisi bilan YONMA-YON ishga
        # tushardi — ya'ni butun himoya bekor bo'lardi.
        q = _qulflar.get(k)
        if q is not None and not q.locked():
            _qulflar.pop(k, None)


def bir_marta(handler):
    """Bir xil amalni `BIR_MARTA_OYNA` ichida BIR MARTA bajaradi.

    ⚠️ `@admin_only` DAN PASTGA qo'yiladi: kalitga `request["user_id"]`
    kiradi, uni esa `admin_only` o'rnatadi.
    """
    @functools.wraps(handler)
    async def wrapper(request: web.Request):
        # ⚠️ `read()` tanani KESHLAYDI, ya'ni handler ichidagi
        # `request.json()` shundan keyin ham ishlaydi.
        tana = await request.read()
        kalit = _bir_marta_kalit(request, tana)
        _bir_marta_tozala()

        # ⭐ QULF — ishning YARMI SHU YERDA. Haqiqiy ikki bosishda
        # ikkinchi so'rov birinchisi HALI TUGAMASDAN keladi, ya'ni
        # «natijani keyin saqlash» o'z-o'zicha hech narsa bermaydi.
        # Ikkinchi so'rov shu yerda kutadi va tayyor javobni oladi.
        qulf = _qulflar.setdefault(kalit, asyncio.Lock())
        async with qulf:
            oldin = _natijalar.get(kalit)
            if oldin and time.time() - oldin[0] < BIR_MARTA_OYNA:
                logger.info(f"[web] takroriy so'rov yutildi: {request.path}")
                return web.Response(status=oldin[1], body=oldin[2],
                                    content_type=oldin[3])
            javob = await handler(request)
            # ⚠️ FAQAT 2xx keshlanadi. Xato javob keshlansa, admin
            # sababni tuzatib 10 soniya ichida qayta bosganda O'SHA
            # ESKI xatoni ko'rardi — holbuki amal umuman bajarilmagan,
            # ya'ni takrorlashdan hech qanday zarar yo'q. Keshning
            # vazifasi «ikki marta BAJARILMASIN», «ikki marta
            # URINILMASIN» emas.
            if 200 <= javob.status < 300:
                _natijalar[kalit] = (time.time(), javob.status,
                                     javob.body, javob.content_type)
            return javob
    return wrapper


def admin_only(handler):
    """Har `/api/*` handler ustidagi dekorator.

    ⚠️ `is_admin()` ATAYLAB keshlanmaydi — REJA 4.3.
    """
    @functools.wraps(handler)
    async def wrapper(request: web.Request):
        # ⚠️ TARTIB MUHIM: avval Telegram imzosi, keyin cookie.
        # Imzo kuchliroq dalil — u bot tokeni bilan shu yerda qayta
        # hisoblanadi va uni faqat Telegram yasay oladi; cookie esa
        # bizning o'z imzomiz va u o'g'irlansa 12 soat ishlardi.
        user_id = imzodan_user_id(request)
        if user_id is None:
            user_id = sessiya_ochi(request.cookies.get(COOKIE_NAME))
        if user_id is None:
            return web.json_response({"error": "sessiya yo'q"}, status=401)
        if not await huquq_bormi(user_id):
            return web.json_response({"error": "admin emas"}, status=403)
        request["user_id"] = user_id

        # ⚠️ Tezlik chegarasi FAQAT yozish so'rovlarida va IP emas,
        # ADMIN bo'yicha: bu yerga kelgan odam allaqachon imzo va huquq
        # tekshiruvidan o'tgan, ya'ni uni IP bilan emas, o'zi bilan
        # sanash to'g'ri — mobil internetda IP baribir almashib turadi.
        # O'qish so'rovlari chegaralanmaydi: ekranni ochish o'zi bir
        # nechta GET yuboradi va admin uni tez-tez yangilashi normal.
        if request.method != "GET" and chastota_oshdimi(
                f"admin:{user_id}", YOZUV_RATE_LIMIT):
            logger.warning(f"[web] {user_id} yozuv chegarasidan oshdi")
            return web.json_response(
                {"error": "Juda ko'p amal — bir daqiqa kuting."}, status=429)
        return await handler(request)
    return wrapper


async def huquq_bormi(user_id: int) -> bool:
    """Admin yoki superadmin. Bitta joyda — ikkalasini unutmaslik uchun."""
    return (await database_module.is_admin(user_id)
            or await database_module.is_superadmin(user_id))
