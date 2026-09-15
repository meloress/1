"""Web admin panel — bot jarayonining ICHIDA ko'tariladigan aiohttp server.

Nega alohida Railway service emas: REJA.md 3.1. Qisqasi — limit va
kuzatuv sozlamalari RAM keshida yashaydi, ikki jarayonda web bazaga
yozardi-yu bot eski qiymat bilan ishlashda davom etardi.

`aiohttp` allaqachon bog'liqliklarda (aiogram uni ishlatadi), ya'ni
yangi kutubxona qo'shilmadi.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from aiohttp import web

from web.auth import (
    COOKIE_NAME, SESSION_TTL, admin_only, chastota_oshdimi,
    huquq_bormi, init_data_tekshir, sessiya_ochi, sessiya_yasa,
)
from db import database as database_module

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"


@web.middleware
async def xato_darvozasi(request: web.Request, handler):
    """⚠️ Paneldagi xato BOTNI YIQITMASLIGI kerak (REJA 9-bo'lim).

    Har qanday kutilmagan istisno shu yerda to'xtaydi: foydalanuvchiga
    JSON, logga to'liq traceback. Ushlanmagan istisno aiohttp'ni
    yiqitmaydi, lekin sababi ko'rinmay qolardi.
    """
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        logger.exception(f"[web] {request.method} {request.path} yiqildi")
        return web.json_response({"error": "server xatosi"}, status=500)


async def sessiya_ochish(request: web.Request):
    """Mini App ochilganda birinchi so'rov: Telegram imzosini cookie'ga almashtirish."""
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() \
        or (request.remote or "?")
    if chastota_oshdimi(ip):
        return web.json_response({"error": "juda ko'p urinish"}, status=429)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "JSON emas"}, status=400)

    try:
        data = init_data_tekshir(body.get("init_data") or "")
    except Exception as exc:
        logger.info(f"[web] imzo rad etildi ({ip}): {exc}")
        return web.json_response({"error": "imzo noto'g'ri"}, status=401)

    user = data.user
    if user is None or not await huquq_bormi(user.id):
        return web.json_response({"error": "admin emas"}, status=403)

    javob = web.json_response(await _kim(user.id, user.first_name))
    javob.set_cookie(
        COOKIE_NAME, sessiya_yasa(user.id),
        max_age=SESSION_TTL, httponly=True, secure=True, samesite="Lax")
    return javob


async def _kim(user_id: int, ism: Optional[str] = None) -> dict:
    """Panel chetidagi kartochka uchun: ism va rol.

    Ikkala kirish yo'li ham SHU yerdan o'qiydi — ilgari `/api/session`
    Telegram'dagi ismni, `/api/me` esa `ID:641…` ni qaytarardi, ya'ni
    panel qayta ochilganda salomlashuv o'zgarib qolardi.

    ⚠️ Bu yerdagi ikki DB so'rovi BEZAK uchun: huquq allaqachon
    `huquq_bormi()` da tekshirilgan, bu faqat chap tarafdagi kartochka
    matni. Shuning uchun xato YUTILADI — aks holda bazadagi bir
    soniyalik uzilish muvaffaqiyatli kirishni 500 ga aylantirib,
    adminni panelga umuman kiritmay qo'yardi.
    """
    rol = "Admin"
    try:
        if not ism:
            meta = await database_module.get_admin_meta(user_id) or {}
            ism = meta.get("username") or meta.get("display_name")
        if await database_module.is_superadmin(user_id):
            rol = "Superadmin"
    except Exception:
        logger.warning(f"[web] {user_id} uchun ism/rol o'qilmadi — bezak qiymati ishlatiladi")
    return {"ism": ism or f"ID:{user_id}", "rol": rol}


@admin_only
async def men(request: web.Request):
    """Cookie hali amal qiladimi — panel qayta ochilganda shu tekshiriladi."""
    return web.json_response(await _kim(request["user_id"]))


async def chiqish(request: web.Request):
    javob = web.json_response({"ok": True})
    javob.del_cookie(COOKIE_NAME)
    return javob


async def sahifa(request: web.Request):
    return web.FileResponse(STATIC / "panel.html")


def build_app() -> web.Application:
    app = web.Application(middlewares=[xato_darvozasi])
    app.router.add_get("/", sahifa)
    app.router.add_post("/api/session", sessiya_ochish)
    app.router.add_get("/api/me", men)
    app.router.add_post("/api/logout", chiqish)
    # Ma'lumot endpointlari `web/api.py` da — bu fayl darvoza, u ekran
    # (REJA 3.2). Import shu yerda: `api` ham `auth` ni chaqiradi.
    from web import api
    api.register(app)
    app.router.add_static("/static/", STATIC)
    return app


async def start_web_server() -> None:
    """Polling bilan yonma-yon ishlaydi — `main()` da `create_task` bilan.

    Port Railway'dan `PORT` orqali keladi; qotirilgan port yo'q.
    """
    port = int(os.getenv("PORT", "8080"))
    runner = web.AppRunner(build_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"✅ Web panel {port}-portda ishga tushdi")
