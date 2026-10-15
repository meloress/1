"""Instagram Direct webhook — 5-bosqich poydevori (faqat eshik).

NEGA ALOHIDA — Telegram Business `business_connection` update'i aiogram
orqali keladi, Meta esa HTTPS webhook (GET verify + POST event) yuboradi.
Ikkalasi bitta faylda aralashsa, imzo tekshiruvi va update ajratish
chalkashadi.

HOZIRGI HOLAT (1-faza): faqat Meta tekshiruvi javob beradi. Xabar qabul
qilib javob berish keyingi qadam — siz Page tokenni ulagach yoqiladi.
Shuning uchun bu route HECH QANDAY javob yubormaydi va hech qanday
Telegram holatiga tegmaydi.
"""

import hashlib
import hmac
import json
import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)


def _sir(key: str) -> str:
    """Meta siri: avval env, bo'lmasa config standarti (bo'sh)."""
    val = os.getenv(key, "")
    if val:
        return val
    try:
        from core import config as cfg
        return str(getattr(cfg, key, "") or "")
    except Exception:
        return ""


def imzo_togri(tana: bytes, sarlavha: str, sir: str) -> bool:
    """Meta `X-Hub-Signature-256: sha256=...` tekshiruvi. Sof funksiya."""
    if not tana or not sarlavha or not sir:
        return False
    if not sarlavha.startswith("sha256="):
        return False
    kutilgan = hmac.new(sir.encode(), tana, hashlib.sha256).hexdigest()
    return hmac.compare_digest(kutilgan, sarlavha[len("sha256="):])


async def tekshiruv(request: web.Request) -> web.Response:
    """Meta webhook verify (GET). Token mos bo'lmasa 403."""
    rejim = request.query.get("hub.mode", "")
    token = request.query.get("hub.verify_token", "")
    chal = request.query.get("hub.challenge", "")
    kut = _sir("IG_VERIFY_TOKEN")
    if rejim == "subscribe" and kut and token and hmac.compare_digest(token, kut):
        return web.Response(text=chal)
    return web.Response(status=403)


async def qabul(request: web.Request) -> web.Response:
    """Meta event (POST). Hozircha faqat imzoni tekshirib, jim qabul qiladi.

    Nega javob yo'q: Page token hali ulanmagan bo'lishi mumkin va har
    qanday javob noto'g'ri odamga ketishi mumkin. Keyingi qadamda shu yerda
    `handlers.instagram` chaqiriladi (Yordamchi qoralama).
    """
    sir = _sir("IG_APP_SECRET")
    if not sir:
        # Sozlanmagan serverni Meta tekshiruvi ham topolmasin.
        return web.Response(status=404)
    try:
        chegarasi = 64 * 1024
        try:
            from core import config as cfg
            chegarasi = int(getattr(cfg, "IG_WEBHOOK_MAX_BYTES", chegarasi) or chegarasi)
        except Exception:
            pass
        tana = await request.read()
        if len(tana) > chegarasi:
            return web.Response(status=413)
    except Exception:
        return web.Response(status=400)
    if not imzo_togri(tana, request.headers.get("X-Hub-Signature-256", ""), sir):
        return web.Response(status=403)
    try:
        hodisa = json.loads(tana.decode("utf-8"))
    except Exception:
        return web.Response(status=400)
    if not isinstance(hodisa, dict) or hodisa.get("object") != "instagram":
        return web.Response(status=404)
    # 2-faza oxiri: event → egani top → tarixga yoz (javob hali yo'q).
    # Har qanday xato yutiladi — Meta'ga 200 qaytadi, aks holda Meta qayta
    # yuborib dublikat qiladi. Noto'g'ri entry (ega topilmadi) — jim.
    try:
        from db import database as db
        from handlers import instagram as hi
        for entry in hodisa.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            qabul_id = str(entry.get("id") or "")
            if not qabul_id:
                continue
            ega = await db.instagram_egasi_top(qabul_id)
            if not ega:
                continue
            for xm in hi.hodisadan_xabarlar({"object": "instagram", "entry": [entry]}):
                toza = hi.matn_tozala(xm["matn"])
                if toza:
                    await db.instagram_xabar_yoz(ega["owner_id"], xm["sender"], "mijoz", toza)
                    # Yordamchi qoralama — egasining «💼 Biznes» mavzusiga.
                    # Xato yutiladi (ichida): Meta'ga 200 baribir qaytadi.
                    try:
                        top = db.biznes_egasi_ulanishi(ega["owner_id"])
                        if top:
                            await hi.mijoz_qoralamasi(
                                ega["owner_id"], top[1]["owner_chat"],
                                xm["sender"], toza)
                    except Exception:
                        pass
    except Exception:
        logger.exception("[instagram] saqlashda xato (javobsiz davom)")
    logger.info("[instagram] event qabul qilindi (poydevor, javobsiz)")
    return web.json_response({"ok": True})


def register(app: web.Application) -> None:
    app.router.add_get("/webhook/instagram", tekshiruv)
    app.router.add_post("/webhook/instagram", qabul)
