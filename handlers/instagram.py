"""Instagram Direct — Telegram Business'ning ikkinchi kanali (2026-10-15).

Egasi /biznes → «📸 Instagram ulash» ni bosadi, Instagram'da ruxsat beradi —
va Telegram'da sozlangan HAMMA narsa (rejim, Bilim, uslub, kutish, pauza, ish
vaqti) Instagram Direct'da ham ishlaydi. Javob yozuvchi kod ikkinchi marta
yozilmagan: Instagram xabari Telegram xabari shaklidagi obyektga
(`_xabar()`) aylanib, o'sha `biznes.biznes_xabar()` dan o'tadi; mijozga
yuborish esa `biznes._mijozga()` ichida `ig:` ulanishda shu yerga buriladi.

Kalitlar:
  • ulanish — `biznes_ulanish.conn_id = 'ig:<IG ID>'` (huquqlar doim
    o'qish + javob: Instagram'da ular alohida yoqilmaydi);
  • mijoz chati — `-IGSID`. Business chati doim shaxsiy (musbat id), ya'ni
    manfiy son Telegram mijozi bilan HECH QACHON to'qnashmaydi: tarix,
    kartoteka, qoralama — hammasi o'zgarishsiz ishlaydi (`chatmi()`).

⛔️ Ishonchsiz chegara: webhook tanasi `X-Hub-Signature-256` (ilova siri bilan
HMAC) tekshirilmaguncha o'qilmaydi; OAuth `state` — egasining imzolangan id'si,
aks holda kimdir o'z Instagram'ini boshqa egaga ulab qo'yardi.
⛔️ Kalit (access token) logga, egasiga va xato matniga hech qachon chiqmaydi:
`_sorov()` xatoni URL'siz qayta ko'taradi (`from None`).
⛔️ 24 soat qoidasi Instagram'da ham bor — rad etilgan yuborish "yuborildi"
deyilmaydi (chaqiruvchilar Telegram'dagi kabi egasiga matnni qaytaradi).
"""
import asyncio
import hashlib
import hmac
import json
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from html import escape
from types import SimpleNamespace
from urllib.parse import urlencode

import aiohttp
from aiohttp import web

from core.config import (BOT_TOKEN, IG_APP_ID, IG_APP_SECRET, IG_GRAPH,
                         IG_KALIT_YANGILA_KUN, IG_MATN_BAYT, IG_VERIFY_TOKEN,
                         CUSTOM_EMOJI, WEB_APP_URL)
from core.loader import logger
from db import database

PREFIKS = "ig:"
# Instagram logosi (animatsiyali custom emoji) — egasiga ketadigan HTML matnda.
# Premium bo'lmagan ko'zda ichidagi 📸 ko'rinadi. Tugmada: icon="instagram".
IG = f'<tg-emoji emoji-id="{CUSTOM_EMOJI["instagram"]}">📸</tg-emoji>'
HUQUQ = {"can_reply": True, "can_read_messages": True}
_TIMEOUT = aiohttp.ClientTimeout(total=20)
_STATE_TTL = 1800


class IgXato(Exception):
    """Instagram rad etdi yoki javob bermadi. Matnida kalit YO'Q."""


def sozlanganmi() -> bool:
    return bool(IG_APP_ID and IG_APP_SECRET and IG_VERIFY_TOKEN and WEB_APP_URL)


def bizniki(conn_id) -> bool:
    return isinstance(conn_id, str) and conn_id.startswith(PREFIKS)


def chatmi(chat_id) -> bool:
    """Instagram mijozining chati (`-IGSID`). Sof."""
    return isinstance(chat_id, int) and chat_id < 0


def havola(username: str | None) -> str | None:
    return f"https://ig.me/m/{username}" if username else None


def mid_raqam(mid: str) -> int:
    """Instagram `mid` (satr) → BIGINT `message_id` (dublikat jadvali). Sof."""
    return int.from_bytes(hashlib.sha256(mid.encode()).digest()[:8], "big") >> 1


# ── OAuth ─────────────────────────────────────────────────────────────
def _kalit() -> bytes:
    # Bot tokenining HOSILASI (panel cookie'si kabi) — imzodan token tiklanmaydi.
    return hashlib.sha256(f"instagram:{BOT_TOKEN}".encode()).digest()


def _imzo(p: str) -> str:
    return hmac.new(_kalit(), p.encode(), hashlib.sha256).hexdigest()[:32]


def holat_yasa(egasi: int, hozir: float | None = None) -> str:
    p = f"{egasi}.{int((hozir or time.time()) + _STATE_TTL)}"
    return f"{p}.{_imzo(p)}"


def holat_tekshir(state: str, hozir: float | None = None) -> int | None:
    """Imzo to'g'ri va muddati o'tmagan bo'lsa — egasining id'si. Sof."""
    try:
        uid, muddat, imzo = state.split(".")
        p = f"{int(uid)}.{int(muddat)}"
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(imzo, _imzo(p)) or int(muddat) < (hozir or time.time()):
        return None
    return int(uid)


def qaytish_manzili() -> str:
    return f"{WEB_APP_URL}/ig/ulash"


def ulash_havolasi(egasi: int) -> str:
    return "https://www.instagram.com/oauth/authorize?" + urlencode({
        "client_id": IG_APP_ID, "redirect_uri": qaytish_manzili(),
        "response_type": "code",
        "scope": "instagram_business_basic,instagram_business_manage_messages",
        "state": holat_yasa(egasi)})


def yoriqnoma(username: str | None, ulangan: bool) -> str:
    """«📸 Instagram» tugmasi ekrani — oddiy foydalanuvchi uchun. Sof.
    ⚠️ Egasi hech narsa KO'CHIRMAYDI va YOZMAYDI (token, ID): faqat Instagram
    sahifasida kiradi va «Ruxsat» bosadi — qolganini kod qiladi."""
    if ulangan:
        return (f"{IG} <b>Instagram ulangan</b>{f': @{escape(username)}' if username else ''}\n\n"
                "Direct'ga yozgan mijozlarga ham shu yerdagi rejim, Bilim va uslub bilan "
                "ishlayman. /biznes da nima o'zgartirsangiz, Instagram'ga ham tushadi.\n\n"
                "Boshqa akkaunt ulash — «Qayta ulash», to'xtatish — «Uzish».")
    return (
        f"{IG} <b>Instagram Direct'ni ulash</b>\n\n"
        "Ulasangiz, Direct'ga yozgan mijozlarga ham shu yerdagi rejim, Bilim va uslub bilan "
        "javob beraman (Yordamchi rejimida — qoralamani shu yerga yuboraman).\n\n"
        "<b>Oldin tekshiring:</b>\n"
        "1. Akkauntingiz <b>Professional</b> bo'lsin (Biznes yoki Autor): Instagram → "
        "Sozlamalar → Akkaunt turi va vositalar → Professional akkauntga o'tish.\n"
        "2. Xabarlarga ruxsat yoqilgan bo'lsin: Instagram → Sozlamalar → Xabarlar va "
        "hikoyalarga javoblar → Ulangan vositalar → <i>Allow access to messages</i>.\n\n"
        "<b>Ulash:</b>\n"
        f"3. Pastdagi «{IG} Instagram'ga kirish» tugmasini bosing.\n"
        "4. Instagram login va parolingizni kiriting — u Instagram'ning o'z sahifasi, "
        "parolingizni men ko'rmayman.\n"
        "5. «Ruxsat berish» (Allow) ni bosing.\n\n"
        "Boshqa hech narsa yozish yoki ko'chirish shart emas — ulanishim bilan shu "
        "yerga xabar beraman. Havola 30 daqiqa amal qiladi.")


def sabab(xato: str) -> str:
    """Meta xatosi → egasi tushunadigan sabab va nima qilish. Sof."""
    x = (xato or "").lower()
    if any(s in x for s in ("developer role", "tester", "not authorized application",
                            "app not active", "invalid platform app")):
        return ("bu Instagram akkaunt hozircha ulanishga ruxsat etilmagan — xizmat Meta "
                "tekshiruvida. Biroz keyin qayta urinib ko'ring yoki bot egasiga yozing.")
    if any(s in x for s in ("professional", "business account", "creator", "personal account")):
        return ("akkaunt Professional emas. Instagram → Sozlamalar → Akkaunt turi va "
                "vositalar → Professional akkauntga o'ting va qayta ulang.")
    if any(s in x for s in ("code has been used", "expired", "invalid authorization code")):
        return "havola eskirgan — /biznes → «Instagram» → «Instagram'ga kirish» ni qayta bosing."
    return f"Instagram rad etdi ({xato[:150]}). Bir ozdan keyin qayta urinib ko'ring."


async def uz(egasi: int) -> bool:
    """Egasining Instagram ulanishini o'chiradi (kalit qoladi: qayta ulash bir bosish)."""
    topilgan = database.biznes_egasi_ulanishi(egasi, instagram=True)
    if not topilgan:
        return False
    await database.biznes_ulanish_yoz(topilgan[0], egasi, egasi, False, HUQUQ)
    logger.info(f"[Instagram] uzildi egasi={egasi}")
    return True


def imzo_togrimi(tana: bytes, sarlavha: str | None) -> bool:
    """Meta webhook imzosi: `sha256=` + HMAC(ilova siri, xom tana). Sof."""
    if not IG_APP_SECRET or not sarlavha or not sarlavha.startswith("sha256="):
        return False
    kutilgan = hmac.new(IG_APP_SECRET.encode(), tana, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sarlavha[7:], kutilgan)


# ── HTTP ──────────────────────────────────────────────────────────────
async def _sorov(usul: str, url: str, *, token: str | None = None,
                 params: dict | None = None, data: dict | None = None,
                 json_: dict | None = None) -> dict:
    sarlavha = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
            async with s.request(usul, url, headers=sarlavha, params=params,
                                 data=data, json=json_) as r:
                holat = r.status
                try:
                    d = await r.json(content_type=None)
                except Exception:
                    d = {}
    except asyncio.TimeoutError:
        raise IgXato("Instagram javob bermadi") from None
    except aiohttp.ClientError as e:
        # ⛔️ `from None`: asl xato URL'ni (ichida access_token) olib yuradi.
        raise IgXato(f"Instagram'ga ulanib bo'lmadi ({type(e).__name__})") from None
    if not isinstance(d, dict):
        d = {}
    if holat >= 400 or d.get("error"):
        x = d.get("error") if isinstance(d.get("error"), dict) else {}
        raise IgXato(f"Instagram rad etdi: {x.get('message') or holat}"[:300])
    return d


async def _kalit_ol(egasi: int, conn_id: str) -> str:
    r = await database.biznes_ig_ol(egasi, conn_id)
    if not r:
        raise IgXato("Instagram ulanishi topilmadi — /biznes dan qayta ulang")
    vaqt = r["token_vaqt"]
    if vaqt.tzinfo is None:
        vaqt = vaqt.replace(tzinfo=timezone.utc)
    # ponytail: yangilash faqat ishlatilganda — 60 kun birorta ham xabarsiz
    # qolgan ulanishning kaliti o'ladi va egasi qayta ulaydi; kerak bo'lsa
    # kunlik kuzatuvchiga ko'chiriladi.
    if datetime.now(timezone.utc) - vaqt > timedelta(days=IG_KALIT_YANGILA_KUN):
        try:
            d = await _sorov("GET", "https://graph.instagram.com/refresh_access_token",
                             params={"grant_type": "ig_refresh_token",
                                     "access_token": r["token"]})
            if d.get("access_token"):
                await database.biznes_ig_kalit_yangila(egasi, conn_id, d["access_token"])
                return d["access_token"]
        except IgXato as e:
            logger.warning(f"[Instagram] kalit yangilanmadi egasi={egasi}: {e}")
    return r["token"]


# ── Yuborish ─────────────────────────────────────────────────────────
def matn_bolaklari(matn: str, chegara: int = IG_MATN_BAYT) -> list[str]:
    """Instagram matn chegarasi BAYTda — kirill va emoji 2-4 bayt. So'z
    o'rtasidan kesmaslikka harakat qiladi. Sof."""
    qolgan, bolaklar = (matn or "").strip(), []
    while qolgan:
        if len(qolgan.encode()) <= chegara:
            bolaklar.append(qolgan)
            break
        kes = len(qolgan.encode()[:chegara].decode("utf-8", "ignore"))
        joy = max(qolgan.rfind("\n", 0, kes), qolgan.rfind(" ", 0, kes))
        if joy > kes // 2:
            kes = joy
        bolaklar.append(qolgan[:kes].rstrip())
        qolgan = qolgan[kes:].lstrip()
    return bolaklar


# Bot yuborgan matnlar — Instagram ularni `is_echo` bilan QAYTARADI.
# Yuborishdan OLDIN yoziladi: echo API javobidan oldin kelishi mumkin, va
# tanilmagan echo "egasi o'zi yozdi" bo'lib, avtomatni pauzaga qo'yardi.
# ponytail: RAM, oxirgi 500 ta — echo soniyalar ichida keladi.
_yuborilgan: deque = deque(maxlen=500)


def _ozimizniki(chat_id: int, matn: str) -> bool:
    kalit = (chat_id, matn.strip())
    if kalit in _yuborilgan:
        _yuborilgan.remove(kalit)
        return True
    return False


async def yubor(conn_id: str, chat_id: int, matn: str):
    """Egasi nomidan Instagram Direct'ga. Rad etilsa — `IgXato`."""
    ul = database.biznes_ulanish_ol(conn_id)
    if not ul or not ul["yoqilgan"]:
        raise IgXato("Instagram ulanishi o'chirilgan")
    token = await _kalit_ol(ul["owner_id"], conn_id)
    oxirgi = None
    for bolak in matn_bolaklari(matn):
        _yuborilgan.append((chat_id, bolak.strip()))
        d = await _sorov("POST", f"{IG_GRAPH}/me/messages", token=token,
                         json_={"recipient": {"id": str(-chat_id)},
                                "message": {"text": bolak}})
        oxirgi = d.get("message_id") or oxirgi
    return (SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=mid_raqam(oxirgi))
            if oxirgi else None)


# ── Kiruvchi xabar ────────────────────────────────────────────────────
_ILOVA = {"image": "rasm", "video": "video", "audio": "ovozli xabar", "file": "fayl",
          "share": "post", "ig_reel": "reels", "reel": "reels",
          "story_mention": "storisida sizni belgiladi"}


def ilova_matni(ilovalar) -> str:
    """Matnsiz xabar (rasm, reels …) — modelga belgi. Sof.
    ponytail: rasm ko'rilmaydi (Telegram'dagi `biznes_media` URL emas, fayl
    oladi); kerak bo'lsa `rasm_tavsifi` ga URL'dan yuklab beriladi."""
    turlar = [_ILOVA.get((i or {}).get("type"), "fayl")
              for i in (ilovalar or []) if isinstance(i, dict)]
    if not turlar:
        return ""
    return f"[Instagram: suhbatdosh {', '.join(dict.fromkeys(turlar))} yubordi — ko'ra olmaysan]"


def hodisalar(d) -> list:
    """Webhook tanasidan xabar hodisalari (o'qildi, reaksiya … — tashlanadi). Sof."""
    if not isinstance(d, dict) or d.get("object") != "instagram":
        return []
    return [h for e in (d.get("entry") or []) if isinstance(e, dict)
            for h in (e.get("messaging") or [])
            if isinstance(h, dict) and isinstance(h.get("message"), dict)]


def _xabar(conn_id: str, chat_id: int, mid: str, matn: str, kimdan: int,
           ism: str | None, username: str | None, bot_ozi: bool):
    """`biznes_xabar()` o'qiydigan `Message` maydonlari — boshqasi yo'q."""
    nom = ism or (f"@{username}" if username else "Mijoz")
    return SimpleNamespace(
        business_connection_id=conn_id, chat=SimpleNamespace(id=chat_id, type="private"),
        message_id=mid_raqam(mid or f"{chat_id}:{time.time()}"), text=matn, caption=None,
        sender_business_bot=True if bot_ozi else None, reply_to_message=None,
        voice=None, video_note=None, audio=None, photo=None, document=None, video=None,
        from_user=SimpleNamespace(id=kimdan, full_name=f"{nom} (Instagram)",
                                  first_name=nom, username=username, language_code=None))


_ismlar: dict = {}


async def _ism(egasi: int, conn_id: str, igsid: int) -> tuple:
    """(ism, username) — Instagram mijozining profili, RAM keshda."""
    if igsid in _ismlar:
        return _ismlar[igsid]
    try:
        d = await _sorov("GET", f"{IG_GRAPH}/{igsid}", token=await _kalit_ol(egasi, conn_id),
                         params={"fields": "name,username"})
        q = (d.get("name"), d.get("username"))
    except IgXato as e:
        logger.info(f"[Instagram] profil o'qilmadi: {e}")
        q = (None, None)
    if len(_ismlar) > 5000:       # ponytail: oddiy chegara, LRU shart emas
        _ismlar.clear()
    _ismlar[igsid] = q
    return q


async def xabar_keldi(h: dict) -> None:
    from handlers import biznes        # ⚠️ tsiklik import: biznes bu modulni oladi
    m = h["message"]
    if m.get("is_deleted") or m.get("is_unsupported"):
        return
    echo = bool(m.get("is_echo"))
    try:
        hisob = str((h["sender"] if echo else h["recipient"])["id"])
        igsid = int((h["recipient"] if echo else h["sender"])["id"])
    except (KeyError, TypeError, ValueError):
        return
    conn_id = PREFIKS + hisob
    ul = database.biznes_ulanish_ol(conn_id)
    if not ul or not ul["yoqilgan"]:
        return
    matn = (m.get("text") or "").strip() or ilova_matni(m.get("attachments"))
    if not matn:
        return
    chat_id, egasi = -igsid, ul["owner_id"]
    ism, username = (None, None) if echo else await _ism(egasi, conn_id, igsid)
    await biznes.biznes_xabar(_xabar(
        conn_id, chat_id, m.get("mid") or "", matn, egasi if echo else igsid,
        ism, username, echo and _ozimizniki(chat_id, matn)))


_fon: set = set()


def _fonda(korutina) -> None:
    async def ish():
        try:
            await korutina
        except Exception:
            logger.exception("[Instagram] xabar ishlanmadi")
    v = asyncio.create_task(ish())
    _fon.add(v)
    v.add_done_callback(_fon.discard)


# ── HTTP endpointlar (web/__init__.py ro'yxatga oladi) ────────────────
# ⚠️ `/api/` ostida EMAS va `@admin_only` SIZ: ularni Meta va egasining
# brauzeri chaqiradi. Himoya — imzo (webhook) va imzolangan `state` (OAuth).
async def webhook_tekshir(request: web.Request):
    """Meta webhook'ni ulaganda bir marta: `hub.challenge` ni qaytarish."""
    if not sozlanganmi():
        raise web.HTTPNotFound()
    q = request.query
    if (q.get("hub.mode") == "subscribe"
            and hmac.compare_digest(q.get("hub.verify_token", ""), IG_VERIFY_TOKEN)):
        return web.Response(text=q.get("hub.challenge", ""))
    return web.Response(status=403)


async def webhook(request: web.Request):
    if not sozlanganmi():
        raise web.HTTPNotFound()
    tana = await request.read()
    if not imzo_togrimi(tana, request.headers.get("X-Hub-Signature-256")):
        logger.warning("[Instagram] webhook imzosi noto'g'ri — rad etildi")
        return web.Response(status=403)
    try:
        d = json.loads(tana)
    except ValueError:
        return web.Response(status=400)
    # Meta 20 s ichida 200 kutadi, aks holda qayta yuboradi — ish FONDA.
    for h in hodisalar(d):
        _fonda(xabar_keldi(h))
    return web.Response(text="EVENT_RECEIVED")


async def _sahifa(matn: str, holat: int = 200) -> web.Response:
    """Brauzerda qoladigan sahifa — asosiy xabar baribir Telegram'ga ketadi."""
    try:
        from core.loader import bot
        nom = (await bot.me()).username or ""
    except Exception:
        nom = ""
    qayt = (f"<p><a href='https://t.me/{escape(nom)}' style='font-weight:600'>"
            "Telegram'ga qaytish →</a></p>" if nom else "")
    return web.Response(status=holat, content_type="text/html", text=(
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<body style='font:18px system-ui;padding:24px;max-width:480px;margin:auto'>"
        f"<p>{escape(matn)}</p>{qayt}"))


async def ulanish_yarat(egasi: int, code: str) -> str:
    """OAuth kodi → uzun kalit → hisob → webhook obunasi → ulanish. @username."""
    from handlers import biznes
    d = await _sorov("POST", "https://api.instagram.com/oauth/access_token", data={
        "client_id": IG_APP_ID, "client_secret": IG_APP_SECRET,
        "grant_type": "authorization_code", "redirect_uri": qaytish_manzili(),
        "code": code})
    qisqa = d.get("access_token") or ((d.get("data") or [{}])[0] or {}).get("access_token")
    if not qisqa:
        raise IgXato("Instagram kalit bermadi")
    uzun = (await _sorov("GET", "https://graph.instagram.com/access_token", params={
        "grant_type": "ig_exchange_token", "client_secret": IG_APP_SECRET,
        "access_token": qisqa})).get("access_token")
    if not uzun:
        raise IgXato("Instagram uzun muddatli kalit bermadi")
    men = await _sorov("GET", f"{IG_GRAPH}/me", token=uzun,
                       params={"fields": "user_id,username"})
    if not men.get("user_id"):
        raise IgXato("Instagram hisobi o'qilmadi")
    await _sorov("POST", f"{IG_GRAPH}/me/subscribed_apps", token=uzun,
                 params={"subscribed_fields": "messages"})
    conn_id, username = PREFIKS + str(men["user_id"]), men.get("username")
    await database.biznes_ig_yoz(egasi, conn_id, username, uzun)
    await database.biznes_ulanish_yoz(conn_id, egasi, egasi, True, HUQUQ)
    await database.biznes_sozlamani_kochir(egasi, conn_id)
    logger.info(f"[Instagram] ulandi egasi={egasi} hisob={conn_id}")
    await biznes._egasiga(egasi, (
        f"{IG} <b>Instagram @{escape(username or '')} ulandi.</b>\n\n"
        "Telegram'dagi rejim, Bilim, uslub va sozlamalar Direct'da ham ishlaydi — "
        "/biznes da nima o'zgartirsangiz, ikkalasiga tushadi. Qoralamalar shu "
        "mavzuga «(Instagram)» belgisi bilan keladi."))
    return username or ""


async def ulash(request: web.Request):
    """Instagram ruxsatidan keyingi qaytish (`redirect_uri`)."""
    if not sozlanganmi():
        raise web.HTTPNotFound()
    egasi = holat_tekshir(request.query.get("state", ""))
    if egasi is None:
        return await _sahifa("Havola eskirgan. Telegram'da /biznes → «Instagram» → "
                             "«Instagram'ga kirish» ni qayta bosing.", 400)
    from handlers import biznes
    code = request.query.get("code", "").removesuffix("#_")
    if request.query.get("error") or not code:
        await biznes._egasiga(egasi, f"{IG} Instagram ulanmadi: ruxsat berilmadi. Qayta "
                                     f"urinish — /biznes → «{IG} Instagram».")
        return await _sahifa("Ulanish bekor qilindi. Telegram'ga qayting.", 400)
    try:
        username = await ulanish_yarat(egasi, code)
    except IgXato as e:
        logger.warning(f"[Instagram] ulanmadi egasi={egasi}: {e}")
        await biznes._egasiga(egasi, f"❗ {IG} Instagram ulanmadi: {escape(sabab(str(e)))}")
        return await _sahifa(f"Ulanmadi: {sabab(str(e))}", 502)
    return await _sahifa(f"✅ Instagram @{username} ulandi. Telegram'ga qayting — "
                         "u yerda xabar kutib turibdi.")


def register(app: web.Application) -> None:
    app.router.add_get("/ig/webhook", webhook_tekshir)
    app.router.add_post("/ig/webhook", webhook)
    app.router.add_get("/ig/ulash", ulash)
