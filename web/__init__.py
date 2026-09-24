"""Web admin panel — bot jarayonining ICHIDA ko'tariladigan aiohttp server.

Nega alohida Railway service emas: REJA.md 3.1. Qisqasi — limit va
kuzatuv sozlamalari RAM keshida yashaydi, ikki jarayonda web bazaga
yozardi-yu bot eski qiymat bilan ishlashda davom etardi.

`aiohttp` allaqachon bog'liqliklarda (aiogram uni ishlatadi), ya'ni
yangi kutubxona qo'shilmadi.
"""

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional

from aiohttp import web

from web.auth import (
    COOKIE_NAME, SESSION_TTL, XFF_TEKSHIR, _klient_ip, admin_only,
    chastota_oshdimi, huquq_bormi, init_data_tekshir, sessiya_ochi,
    sessiya_yasa,
)
from db import database as database_module

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"

# CSP hisoboti — bitta IP dan daqiqasiga nechta. Bitta sahifa o'nlab
# buzilish yuborishi mumkin, ya'ni chegara kirishnikidan kengroq.
CSP_HISOBOT_LIMIT = 60


# ══ XAVFSIZLIK SARLAVHALARI ════════════════════════════════════════
# ⛔️ `X-Frame-Options` QO'SHILMAYDI. Mini App Telegram Web'da IFRAME
# ichida ochiladi — `DENY` ham, `SAMEORIGIN` ham panelni butunlay
# ishlamaydigan qilardi. Ramkani `frame-ancestors` boshqaradi, u esa
# aniq domen ro'yxatini qabul qiladi.
#
# ⚠️ CSP dastlab REPORT-ONLY, ya'ni HECH NARSA BLOKLANMAYDI. Ikki
# noaniqlik bor va ikkalasini ham faqat jonli sinov hal qiladi:
# panelda inline `style=…` atributlari bor (`panel.html` va JS yasagan
# HTML), hamda Telegram Desktop'ning o'rnatilgan webview'i
# `frame-ancestors` ga qanday javob berishi ma'lum emas.
_CSP = "; ".join([
    "default-src 'self'",
    # Telegram kutubxonasi shu manzildan keladi (`panel.html`:
    # telegram.org/js/telegram-web-app.js). Panelda inline `<script>`
    # YO'Q — tekshirildi — ya'ni `unsafe-inline` skriptlarga kerak emas.
    "script-src 'self' https://telegram.org",
    # Google Fonts uslub fayli + inline `style=` atributlari.
    "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'",
    "font-src 'self' https://fonts.gstatic.com",
    # `data:` — ichki SVG uchun; tashqi rasm yuklanmaydi.
    "img-src 'self' data:",
    # Panel FAQAT o'z serveriga murojaat qiladi.
    "connect-src 'self'",
    # ⚠️ RAMKA RUXSATI. `web.telegram.org` — Telegram Web (K va A
    # ikkalasi ham shu domenda). `*.telegram.org` esa `webk.`, `webz.`,
    # `weba.` kabi alohida joylashuvlarni qamraydi — ular ham
    # Telegram'niki. Desktop va telefon ilovalari ramka emas, o'rnatilgan
    # webview ishlatadi, ya'ni bu qoida ularga umuman tegmaydi.
    "frame-ancestors 'self' https://telegram.org https://*.telegram.org",
    # Panelda `<form>` ham, `<base>` ham, plagin ham yo'q.
    "base-uri 'none'",
    "form-action 'none'",
    "object-src 'none'",
    # Buzilishlar Railway logiga tushsin — telefonda brauzer konsolini
    # ochib bo'lmaydi, ya'ni usiz report-only hech narsa aytmaydi.
    "report-uri /csp-report",
])

_SARLAVHALAR = {
    # Brauzer `Content-Type` ni O'ZI taxmin qilmasin: noto'g'ri turda
    # yuborilgan fayl skript sifatida bajarilib ketmasin.
    "X-Content-Type-Options": "nosniff",
    # Tashqi saytga o'tilganda to'liq manzil (ID lar bilan) ketmasin.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy-Report-Only": _CSP,
}


@web.middleware
async def xato_darvozasi(request: web.Request, handler):
    """⚠️ Paneldagi xato BOTNI YIQITMASLIGI kerak (REJA 9-bo'lim).

    Har qanday kutilmagan istisno shu yerda to'xtaydi: foydalanuvchiga
    JSON, logga to'liq traceback. Ushlanmagan istisno aiohttp'ni
    yiqitmaydi, lekin sababi ko'rinmay qolardi.
    """
    try:
        javob = await handler(request)
    except web.HTTPException as e:
        # Sarlavhalar 404/405 kabi javoblarga ham tegishli.
        e.headers.update(_SARLAVHALAR)
        raise
    except Exception:
        logger.exception(f"[web] {request.method} {request.path} yiqildi")
        javob = web.json_response({"error": "server xatosi"}, status=500)
    javob.headers.update(_SARLAVHALAR)
    return javob


async def sessiya_ochish(request: web.Request):
    """Mini App ochilganda birinchi so'rov: Telegram imzosini cookie'ga almashtirish."""
    # ⚠️ VAQTINCHA TEKSHIRUV. Railway proksisi haqiqiy IP ni
    # `X-Forwarded-For` ning qaysi pozitsiyasiga qo'yishi
    # hujjatlashtirilmagan — buni faqat jonli so'rov ko'rsatadi.
    # `XFF_TEKSHIR=1` muhit o'zgaruvchisi bilan yoqiladi va aniqlangach
    # o'chiriladi: bu qator IP manzillarni logga yozadi.
    if XFF_TEKSHIR:
        logger.info("[XFF] xom=%r peer=%r cf=%r real=%r",
                    request.headers.get("X-Forwarded-For"),
                    request.remote,
                    request.headers.get("CF-Connecting-IP"),
                    request.headers.get("X-Real-IP"))
    ip = _klient_ip(request)
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
    # ⚠️ O'CHIRISH — QO'YISH BILAN BIR XIL ATRIBUTLARDA. aiohttp'ning
    # `del_cookie()` si faqat `domain`/`path` ni oladi, ya'ni `Secure`
    # va `SameSite` siz yuboradi. Brauzer bunday `Set-Cookie` ni
    # mavjudiga mos kelmadi deb hisoblasa, cookie O'CHMAY qoladi —
    # ya'ni «chiqish» tugmasi jimgina ishlamagan bo'lardi.
    javob.set_cookie(
        COOKIE_NAME, "", max_age=0, httponly=True, secure=True,
        samesite="Lax")
    return javob


# ══ KESH BUZISH ═════════════════════════════════════════
# HTML'dagi `/static/*.css` va `/static/*.js` havolalariga faylning
# O'Z hash'i qo'shiladi. Deploydan keyin admin eski JS bilan qolib
# ketmaydi, o'zgarmagan fayl esa keshda qoladi — shuning uchun bitta
# umumiy versiya emas, HAR FAYLGA O'Z hash'i.
#
# ⚠️ Versiya QO'LDA YOZILMAYDI. Qo'lda yozilgan raqam bir marta
# unutiladi va o'shanda kesh buzish borday ko'rinib, aslida
# ishlamaydi — ya'ni bag bo'lmaganidan ham yomon.
#
# Natija bir marta hisoblanadi: konteyner fayl tizimi deploy
# davomida o'zgarmaydi, ya'ni har so'rovda qayta o'qish bekor ish.
# `logo.jpg` ATAYLAB tegilmaydi (faqat .css/.js) — `REJA.md` 3.2.1
# ga ko'ra logotip manzili bitta va o'zgarmas.
_STATIK_RE = re.compile(r'(?:href|src)="(/static/[^"?]+\.(?:css|js))"')
_SAHIFA_KESH: Optional[str] = None


def _versiyala(html: str) -> str:
    """Har bir CSS/JS havolasiga `?v=<hash>` qo'shadi."""
    def almash(m):
        yol = m.group(1)
        fayl = STATIC / yol[len("/static/"):]
        try:
            h = hashlib.sha256(fayl.read_bytes()).hexdigest()[:10]
        except OSError:
            # Fayl yo'q — havolani TEGMASDAN qoldiramiz. Panel kesh
            # buzilmagan holda ishlashda davom etadi; yiqilmaydi.
            logger.warning(f"[web] {yol} o'qilmadi — versiyasiz beriladi")
            return m.group(0)
        return m.group(0).replace(yol, f"{yol}?v={h}")
    return _STATIK_RE.sub(almash, html)


async def csp_hisobot(request: web.Request):
    """CSP buzilishini logga yozadi.

    ⚠️ ATAYLAB `@admin_only` SIZ: hisobotni BRAUZER yuboradi va u
    bizning sarlavhamizni ham, cookie'ni ham qo'shmaydi. Shuning uchun
    u `/api/` ostida ham emas — «har `/api/*` himoyalangan» qoidasi
    buzilmasin.

    Hech narsa qaytarmaydi va hech narsani o'zgartirmaydi: bu faqat
    log. Chegara bor, chunki bitta sahifa o'nlab buzilish yuborishi
    mumkin.
    """
    if chastota_oshdimi(f"csp:{_klient_ip(request)}", CSP_HISOBOT_LIMIT):
        return web.Response(status=429)
    try:
        d = await request.json()
    except Exception:
        return web.Response(status=400)
    r = (d or {}).get("csp-report") or d
    if isinstance(r, dict):
        logger.warning("[CSP] %s <- %s (%s)",
                       str(r.get("violated-directive"))[:120],
                       str(r.get("blocked-uri"))[:200],
                       str(r.get("document-uri"))[:200])
    return web.Response(status=204)


async def sahifa(request: web.Request):
    global _SAHIFA_KESH
    if _SAHIFA_KESH is None:
        _SAHIFA_KESH = _versiyala(
            (STATIC / "panel.html").read_text(encoding="utf-8"))
    return web.Response(text=_SAHIFA_KESH, content_type="text/html")


def build_app() -> web.Application:
    app = web.Application(middlewares=[xato_darvozasi])
    app.router.add_get("/", sahifa)
    app.router.add_post("/api/session", sessiya_ochish)
    app.router.add_post("/csp-report", csp_hisobot)
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
