"""Web panel darvozasi: `initData` imzosi, sessiya cookie'si va `@admin_only`.

Uch qatlamdan ikkitasi shu faylda (uchinchisi — menyu tugmasi,
`services/menu.py`). REJA.md 4-bo'limiga qarang.

⚠️ Bu yerda HECH QANDAY ma'lumot qaytarilmaydi. Har bir `/api/*` handler
`@admin_only` bilan boshlanadi va u `is_admin()` ni HAR SO'ROVDA
qaytadan chaqiradi — 12 soatlik cookie adminlikdan chiqarilgan odamni
o'sha muddat davomida ichkarida ushlab turmasligi kerak.
"""

import functools
import hashlib
import hmac
import logging
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
SESSION_RATE_LIMIT = 10          # bitta IP — daqiqasiga 10 ta urinish

# ponytail: IP -> [vaqt, ...] RAM'da. Bitta jarayon, bitta admin — Redis
# ortiqcha. Kerak bo'lsa: bazaga jadval yoki nginx darajasida chegara.
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


def init_data_tekshir(init_data: str):
    """Telegram imzosi + yoshi. Xato bo'lsa ValueError.

    `safe_parse_webapp_init_data` HMAC ni o'zi tekshiradi (aiogram'da
    tayyor), lekin YOSHINI tekshirmaydi: bir marta o'g'irlangan
    `initData` abadiy amal qilardi.
    """
    data = safe_parse_webapp_init_data(BOT_TOKEN, init_data)
    if time.time() - data.auth_date.timestamp() > INIT_DATA_MAX_AGE:
        raise ValueError("initData eskirgan")
    return data


def chastota_oshdimi(ip: str) -> bool:
    """Daqiqada `SESSION_RATE_LIMIT` dan ko'p urinish bo'ldimi."""
    hozir = time.time()
    tarix = [t for t in _urinishlar.get(ip, []) if hozir - t < 60]
    tarix.append(hozir)
    _urinishlar[ip] = tarix
    return len(tarix) > SESSION_RATE_LIMIT


def admin_only(handler):
    """Har `/api/*` handler ustidagi dekorator.

    ⚠️ `is_admin()` ATAYLAB keshlanmaydi — REJA 4.3.
    """
    @functools.wraps(handler)
    async def wrapper(request: web.Request):
        user_id = sessiya_ochi(request.cookies.get(COOKIE_NAME))
        if user_id is None:
            return web.json_response({"error": "sessiya yo'q"}, status=401)
        if not await huquq_bormi(user_id):
            return web.json_response({"error": "admin emas"}, status=403)
        request["user_id"] = user_id
        return await handler(request)
    return wrapper


async def huquq_bormi(user_id: int) -> bool:
    """Admin yoki superadmin. Bitta joyda — ikkalasini unutmaslik uchun."""
    return (await database_module.is_admin(user_id)
            or await database_module.is_superadmin(user_id))
