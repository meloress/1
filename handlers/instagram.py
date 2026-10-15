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
import os
import re
import tempfile
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


# Webhook maydonlari: Direct, postlarga izoh, «tez savol» tugmasi bosilishi.
# Eski ulanishlar ham yangisiga o'tadi — `kalitlarni_yangila()` qayta obuna qiladi.
OBUNA = "messages,comments,messaging_postbacks"


class IgXato(Exception):
    """Instagram rad etdi yoki javob bermadi. Matnida kalit YO'Q.
    `kod`/`subkod` — Meta xato kodi (190 = kalit o'lgan, 10/2534022 = 24 soat)."""

    def __init__(self, matn: str, kod=None, subkod=None):
        super().__init__(matn)
        self.kod, self.subkod = kod, subkod


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
        "scope": "instagram_business_basic,instagram_business_manage_messages,"
                 "instagram_business_manage_comments",
        "state": holat_yasa(egasi)})


def yoriqnoma(username: str | None, ulangan: bool) -> str:
    """«📸 Instagram» tugmasi ekrani — oddiy foydalanuvchi uchun. Sof.
    ⚠️ Egasi hech narsa KO'CHIRMAYDI va YOZMAYDI (token, ID): faqat Instagram
    sahifasida kiradi va «Ruxsat» bosadi — qolganini kod qiladi."""
    if ulangan:
        return (f"{IG} <b>Instagram ulangan</b>{f': @{escape(username)}' if username else ''}\n\n"
                "Direct'ga yozgan mijozlarga ham shu yerdagi rejim, Bilim va uslub bilan "
                "ishlayman. /biznes da nima o'zgartirsangiz, Instagram'ga ham tushadi.\n\n"
                "• Rasm va ovozli xabarni tushunaman, storisga javob bo'lsa — qaysi "
                "storis ekanini ham.\n"
                "• Postingizga «narxi?», «+» kabi savol yozilsa — o'sha odamga Direct'da "
                "javob beraman, izohga esa «Direct'ga yozdik» deb qo'yaman.\n"
                "• «Tez savollar» — mijoz Direct'ni ochganda chiqadigan tugmalar, "
                "Bilimingizdan tuziladi.\n\n"
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
    """Egasining Instagram ulanishini o'chiradi va kalitini (token) bazadan
    o'chiradi — `/maxfiylik` sahifasi shuni va'da qiladi. Qayta ulash — OAuth."""
    topilgan = database.biznes_egasi_ulanishi(egasi, instagram=True)
    if not topilgan:
        return False
    await database.biznes_ulanish_yoz(topilgan[0], egasi, egasi, False, HUQUQ)
    await database.biznes_ig_ochir(egasi, topilgan[0])
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
        raise IgXato(f"Instagram rad etdi: {x.get('message') or holat}"[:300],
                     x.get("code"), x.get("error_subcode"))
    return d


async def _uzildi(egasi: int, conn_id: str) -> None:
    """Kalit o'lgan (190): parol o'zgargan, ruxsat olib tashlangan yoki 60 kun
    yangilanmagan. Jim qolmaslik uchun — ulanish o'chadi va egasi BIR MARTA
    biladi (keyingi so'rovlar ulanishni o'chiq ko'radi)."""
    from handlers import biznes
    ul = database.biznes_ulanish_ol(conn_id)
    if not ul or not ul["yoqilgan"]:
        return
    await database.biznes_ulanish_yoz(conn_id, egasi, egasi, False, HUQUQ)
    await database.biznes_ig_ochir(egasi, conn_id)
    logger.warning(f"[Instagram] kalit o'lgan — ulanish o'chirildi egasi={egasi}")
    await biznes._egasiga(egasi, (
        f"❗ {IG} <b>Instagram ulanishi uzildi</b> — Direct'ga endi javob bermayman.\n\n"
        "Sababi odatda: Instagram parolingiz o'zgargan yoki ilovaga ruxsat olib "
        "tashlangan. Qayta ulash: /biznes → «Instagram» → «Instagram'ga kirish»."))


async def _api(egasi: int, conn_id: str, usul: str, url: str, **kw) -> dict:
    """Egasining kaliti bilan so'rov. O'lik kalit — `_uzildi()` va xato yuqoriga."""
    try:
        return await _sorov(usul, url, token=await _kalit_ol(egasi, conn_id), **kw)
    except IgXato as e:
        if e.kod == 190:
            await _uzildi(egasi, conn_id)
        raise


async def _kalit_ol(egasi: int, conn_id: str) -> str:
    r = await database.biznes_ig_ol(egasi, conn_id)
    if not r:
        raise IgXato("Instagram ulanishi topilmadi — /biznes dan qayta ulang")
    vaqt = r["token_vaqt"]
    if vaqt.tzinfo is None:
        vaqt = vaqt.replace(tzinfo=timezone.utc)
    # Xabar kelmasa ham soatlik `kalitlarni_yangila()` shu yerdan o'tadi —
    # 60 kun jim turgan do'konning kaliti o'lmaydi.
    if datetime.now(timezone.utc) - vaqt > timedelta(days=IG_KALIT_YANGILA_KUN):
        try:
            d = await _sorov("GET", "https://graph.instagram.com/refresh_access_token",
                             params={"grant_type": "ig_refresh_token",
                                     "access_token": r["token"]})
            if d.get("access_token"):
                await database.biznes_ig_kalit_yangila(egasi, conn_id, d["access_token"])
                return d["access_token"]
        except IgXato as e:
            if e.kod == 190:
                await _uzildi(egasi, conn_id)
                raise
            logger.warning(f"[Instagram] kalit yangilanmadi egasi={egasi}: {e}")
    return r["token"]


_obuna: set = set()


async def kalitlarni_yangila() -> None:
    """Soatlik (`biznes` kuzatuvchisi): har ulanishning kaliti 30 kundan eski
    bo'lsa yangilanadi va jarayon boshida bir marta webhook maydonlariga
    (`OBUNA`) qayta obuna qilinadi — yangi maydon qo'shilsa eski ulanishlar
    qayta ulanmasdan oladi. Bitta egasining xatosi qolganlarini to'xtatmaydi."""
    for egasi, ulangan in await database.biznes_egalar():
        ig = database.biznes_egasi_ulanishi(egasi, instagram=True)
        if not ulangan or not ig or not ig[1]["yoqilgan"]:
            continue
        try:
            if ig[0] in _obuna:
                await _kalit_ol(egasi, ig[0])
            else:
                await _api(egasi, ig[0], "POST", f"{IG_GRAPH}/me/subscribed_apps",
                           params={"subscribed_fields": OBUNA})
                _obuna.add(ig[0])
        except IgXato as e:
            logger.warning(f"[Instagram] kalit/obuna egasi={egasi}: {e}")


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
    # (None, matn) — izohga yopiq javob: echo qaysi id bilan qaytishini Meta
    # kafolatlamaydi, tanilmasa chat "egasi yozdi" bo'lib pauzaga tushardi.
    for kalit in ((chat_id, matn.strip()), (None, matn.strip())):
        if kalit in _yuborilgan:
            _yuborilgan.remove(kalit)
            return True
    return False


# Izohga javob kutayotgan chat → (comment_id, vaqt). Birinchi javob Direct'ga
# shu izoh orqali (private reply) ketadi: mijoz hali Direct'ga yozmagan, oddiy
# yuborish rad etiladi. Meta: izohga 7 kun ichida, BITTA yopiq javob.
# ponytail: RAM — deploydan keyin Yordamchi qoralamasi oddiy yuborishga tushadi
# (rad etilsa egasi matnni oladi).
_izohlar: dict = {}
_IZOH_MUDDAT = 7 * 86400
IZOH_JAVOBI = "📩 Direct'ga yozdik"


def _deraza_xatosi(e: IgXato) -> bool:
    return (e.kod == 10 and e.subkod == 2534022) or "allowed window" in str(e).lower()


async def yubor(conn_id: str, chat_id: int, matn: str, inson: bool = False):
    """Egasi nomidan Instagram Direct'ga. Rad etilsa — `IgXato`.

    `inson` — matnni EGASI yubordi/tasdiqladi (qoralama, topshiriq). 24 soat
    o'tgan bo'lsa `HUMAN_AGENT` belgisi bilan qayta urinadi (7 kun). ⛔️
    Avtojavobda HECH QACHON: Meta qoidasi — bu belgi faqat odam javobi uchun.
    Ruxsat (Advanced Access) hali berilmagan bo'lsa Meta rad etadi — asl xato."""
    ul = database.biznes_ulanish_ol(conn_id)
    if not ul or not ul["yoqilgan"]:
        raise IgXato("Instagram ulanishi o'chirilgan")
    egasi = ul["owner_id"]
    izoh = _izohlar.pop(chat_id, None)
    if izoh and time.time() - izoh[1] > _IZOH_MUDDAT:
        izoh = None
    oxirgi = None
    for i, bolak in enumerate(matn_bolaklari(matn)):
        if izoh and i == 0:
            _yuborilgan.append((None, bolak.strip()))
            d = await _api(egasi, conn_id, "POST", f"{IG_GRAPH}/me/messages",
                           json_={"recipient": {"comment_id": izoh[0]},
                                  "message": {"text": bolak}})
            oxirgi = d.get("message_id") or oxirgi
            try:  # ommaga «Direct'ga yozdik» — bezak, xatosi javobni to'xtatmaydi
                await _api(egasi, conn_id, "POST", f"{IG_GRAPH}/{izoh[0]}/replies",
                           params={"message": IZOH_JAVOBI})
            except IgXato as e:
                logger.info(f"[Instagram] izohga ochiq javob yozilmadi: {e}")
            continue
        _yuborilgan.append((chat_id, bolak.strip()))
        tana = {"recipient": {"id": str(-chat_id)}, "message": {"text": bolak}}
        try:
            d = await _api(egasi, conn_id, "POST", f"{IG_GRAPH}/me/messages", json_=tana)
        except IgXato as e:
            if izoh:
                # ponytail: yopiq javobdan keyingi bo'lak — mijoz hali Direct'da
                # yozmagan, rad etiladi; birinchisi yetib borgan, xato emas.
                logger.info(f"[Instagram] izoh javobining davomi ketmadi: {e}")
                break
            if not (inson and _deraza_xatosi(e)):
                raise
            d = await _api(egasi, conn_id, "POST", f"{IG_GRAPH}/me/messages",
                           json_={**tana, "messaging_type": "MESSAGE_TAG",
                                  "tag": "HUMAN_AGENT"})
        oxirgi = d.get("message_id") or oxirgi
    return (SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=mid_raqam(oxirgi))
            if oxirgi else None)


async def harakat(conn_id: str, chat_id: int, amal: str) -> None:
    """«yozmoqda…» (`typing_on`) / «ko'rildi» (`mark_seen`) — Telegram'dagi
    `send_chat_action` / `read_business_message` o'rnida. Bezak: xato yutiladi."""
    ul = database.biznes_ulanish_ol(conn_id)
    if not ul or not ul["yoqilgan"] or chat_id in _izohlar:
        return
    try:
        await _api(ul["owner_id"], conn_id, "POST", f"{IG_GRAPH}/me/messages",
                   json_={"recipient": {"id": str(-chat_id)}, "sender_action": amal})
    except IgXato:
        pass


# ── Kiruvchi xabar ────────────────────────────────────────────────────
_ILOVA = {"image": "rasm", "video": "video", "audio": "ovozli xabar", "file": "fayl",
          "share": "post", "ig_post": "post", "ig_reel": "reels", "reel": "reels",
          "story_mention": "storisida sizni belgiladi"}


def ilova_matni(ilovalar) -> str:
    """Ko'rib/eshitib bo'lmaydigan ilova (reels, post, video …) — modelga
    belgi. Rasm va ovoz `biznes_media.media_matn()` da matnga aylanadi. Sof."""
    turlar = [_ILOVA.get((i or {}).get("type"), "fayl")
              for i in (ilovalar or []) if isinstance(i, dict)]
    if not turlar:
        return ""
    return f"[Instagram: suhbatdosh {', '.join(dict.fromkeys(turlar))} yubordi — ko'ra olmaysan]"


def hodisalar(d) -> list:
    """Webhook tanasidan Direct hodisalari: xabar va «tez savol» tugmasi
    (`postback` — xabarga aylantiriladi). O'qildi, reaksiya — tashlanadi. Sof."""
    if not isinstance(d, dict) or d.get("object") != "instagram":
        return []
    natija = []
    for e in d.get("entry") or []:
        for h in (e.get("messaging") or []) if isinstance(e, dict) else []:
            if not isinstance(h, dict):
                continue
            if isinstance(h.get("message"), dict):
                natija.append(h)
            elif isinstance(h.get("postback"), dict) and h["postback"].get("title"):
                pb = h["postback"]
                natija.append({**h, "message": {"mid": pb.get("mid") or "",
                                                "text": pb["title"]}})
    return natija


def izohlar(d) -> list:
    """Webhook tanasidan postga yozilgan izohlar: [(hisob, qiymat)]. Sof."""
    if not isinstance(d, dict) or d.get("object") != "instagram":
        return []
    return [(str(e.get("id")), c["value"]) for e in (d.get("entry") or [])
            if isinstance(e, dict)
            for c in (e.get("changes") or [])
            if isinstance(c, dict) and c.get("field") == "comments"
            and isinstance(c.get("value"), dict)]


# Izoh — sotuv savolimi? «🔥», «zo'r», do'stini belgilash — Direct'ga
# yozilmaydi: har izohga xabar spam bo'lardi. «+» — Instagram'da «narxini
# Direct'ga yozing» degani.
# ponytail: kalit so'zlar; yetmasa — mini model bilan saralash.
_SAVOL_RE = re.compile(
    r"\?|^\s*\+|narx|qancha|nechpul|necha|bormi|bor\s*mi|sotil|razmer|o'lcham|olcham|"
    r"yetkaz|dostav|manzil|qayer|buyurtma|zakaz|info|price|how much|cost|size|deliver|"
    r"order|direct|директ|цен|сколько|почем|почём|размер|доставк|где|есть ли|инфо|заказ",
    re.I)


def izoh_savolmi(matn: str) -> bool:
    return bool(_SAVOL_RE.search(matn or ""))


def _xabar(conn_id: str, chat_id: int, mid: str, matn: str, kimdan: int,
           ism: str | None, username: str | None, bot_ozi: bool, media=None):
    """`biznes_xabar()` o'qiydigan `Message` maydonlari — boshqasi yo'q.
    `ig_media` — rasm/ovoz URL'i va storis (`biznes_media.media_matn` o'qiydi)."""
    nom = ism or (f"@{username}" if username else "Mijoz")
    return SimpleNamespace(
        business_connection_id=conn_id, chat=SimpleNamespace(id=chat_id, type="private"),
        message_id=mid_raqam(mid or f"{chat_id}:{time.time()}"), text=matn or None,
        caption=None, sender_business_bot=True if bot_ozi else None, reply_to_message=None,
        voice=None, video_note=None, audio=None, photo=None, document=None, video=None,
        ig_media=media,
        from_user=SimpleNamespace(id=kimdan, full_name=f"{nom} (Instagram)",
                                  first_name=nom, username=username, language_code=None))


_ismlar: dict = {}


async def _ism(egasi: int, conn_id: str, igsid: int) -> tuple:
    """(ism, username) — Instagram mijozining profili, RAM keshda."""
    if igsid in _ismlar:
        return _ismlar[igsid]
    try:
        d = await _api(egasi, conn_id, "GET", f"{IG_GRAPH}/{igsid}",
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
    matn = (m.get("text") or "").strip()
    ilova = next((i for i in m.get("attachments") or [] if isinstance(i, dict)), None)
    storis = (m.get("reply_to") or {}).get("story") if isinstance(m.get("reply_to"), dict) else None
    if not matn and not ilova:
        return
    media = ({"ilova": ilova, "storis": storis if isinstance(storis, dict) else None}
             if ilova or storis else None)
    chat_id, egasi = -igsid, ul["owner_id"]
    ism, username = (None, None) if echo else await _ism(egasi, conn_id, igsid)
    await biznes.biznes_xabar(_xabar(
        conn_id, chat_id, m.get("mid") or "", matn, egasi if echo else igsid,
        ism, username, echo and bool(matn) and _ozimizniki(chat_id, matn), media))


_postlar: dict = {}


async def _post_matni(egasi: int, conn_id: str, media_id) -> str:
    """Izoh yozilgan postning tavsifi — "narxi?" QAYSI mahsulot haqida
    ekanini model shundan biladi. RAM kesh; o'qilmasa bo'sh."""
    if not media_id:
        return ""
    if media_id not in _postlar:
        try:
            d = await _api(egasi, conn_id, "GET", f"{IG_GRAPH}/{media_id}",
                           params={"fields": "caption"})
            _postlar[media_id] = " ".join((d.get("caption") or "").split())[:400]
        except IgXato as e:
            logger.info(f"[Instagram] post o'qilmadi: {e}")
            return ""
        if len(_postlar) > 2000:   # ponytail: oddiy chegara
            _postlar.clear()
    return _postlar.get(media_id, "")


async def izoh_keldi(hisob: str, v: dict) -> None:
    """Postga izoh → savol bo'lsa, o'sha odamga Direct'da javob (private
    reply) — oddiy mijoz xabari kabi `biznes_xabar()` dan o'tadi: rejim,
    Bilim, uslub, qoralama — hammasi o'sha. Javob `yubor()` da izohga boradi."""
    from handlers import biznes
    conn_id = PREFIKS + hisob
    ul = database.biznes_ulanish_ol(conn_id)
    if not ul or not ul["yoqilgan"]:
        return
    kim, cid = v.get("from") or {}, v.get("id")
    matn = " ".join(str(v.get("text") or "").split())
    # Egasining o'z izohi va botning «Direct'ga yozdik» javobi — hisob o'zi.
    if not cid or not matn or str(kim.get("id")) == hisob or not izoh_savolmi(matn):
        return
    try:
        igsid = int(kim["id"])
    except (KeyError, TypeError, ValueError):
        return
    chat_id, egasi = -igsid, ul["owner_id"]
    post = await _post_matni(egasi, conn_id, (v.get("media") or {}).get("id"))
    _izohlar[chat_id] = (str(cid), time.time())
    if len(_izohlar) > 5000:     # ponytail: eng eskisi emas, hammasi — kamdan-kam
        _izohlar.clear()
        _izohlar[chat_id] = (str(cid), time.time())
    sarlavha = f"[Instagram postingizga izoh{f' — post: «{post}»' if post else ''}]"
    logger.info(f"[Instagram] izoh egasi={egasi} chat={chat_id}")
    await biznes.biznes_xabar(_xabar(conn_id, chat_id, str(cid), f"{sarlavha}\n{matn}",
                                     igsid, None, kim.get("username"), False))


# ── «Tez savollar» (ice breakers) ─────────────────────────────────────
# Mijoz Direct'ni birinchi ochganda chiqadigan tugmalar. Bosilsa — oddiy
# mijoz xabari (`hodisalar()` postback'ni xabarga aylantiradi).
STANDART_SAVOLLAR = ["Narxlar qancha?", "Yetkazib berish bormi?",
                     "Qayerda joylashgansiz?", "Ish vaqtingiz qanday?"]


async def tez_savollar_qoy(egasi: int) -> list:
    """Bilimdan 4 ta savol (mini model; Bilim bo'sh yoki xato — standart)
    yasab Instagram'ga o'rnatadi. Qaytadi: o'rnatilgan savollar. `IgXato`."""
    from services.ai import tez_savollar
    ig = database.biznes_egasi_ulanishi(egasi, instagram=True)
    if not ig or not ig[1]["yoqilgan"]:
        raise IgXato("Instagram ulanmagan")
    bilim = await database.biznes_bilim_ol(egasi)
    savollar = (await tez_savollar(bilim) if bilim.strip() else []) or STANDART_SAVOLLAR
    await _api(egasi, ig[0], "POST", f"{IG_GRAPH}/me/messenger_profile", json_={
        "platform": "instagram",
        "ice_breakers": [{"locale": "default", "call_to_actions": [
            {"question": q, "payload": f"tez:{i}"} for i, q in enumerate(savollar)]}]})
    logger.info(f"[Instagram] tez savollar o'rnatildi egasi={egasi} soni={len(savollar)}")
    return savollar


async def tez_savollar_ochir(egasi: int) -> None:
    ig = database.biznes_egasi_ulanishi(egasi, instagram=True)
    if not ig or not ig[1]["yoqilgan"]:
        raise IgXato("Instagram ulanmagan")
    await _api(egasi, ig[0], "DELETE", f"{IG_GRAPH}/me/messenger_profile",
               params={"fields": '["ice_breakers"]', "platform": "instagram"})


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
    for hisob, v in izohlar(d):
        _fonda(izoh_keldi(hisob, v))
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
                 params={"subscribed_fields": OBUNA})
    conn_id, username = PREFIKS + str(men["user_id"]), men.get("username")
    _obuna.add(conn_id)
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


# ── Meta talab qiladigan ochiq sahifalar ─────────────────────────────
# Ilovani nashr qilish (Live) uchun Privacy Policy va Data Deletion
# Instructions havolalari majburiy. Matn kodda nima qilinsa, shuni aytadi:
# saqlash muddati `BIZNES_SAQLASH_KUN`, uzilgandan keyin `BIZNES_TOZALASH_KUN`.
def _hujjat(sarlavha: str, bolimlar: list) -> web.Response:
    tana = "".join(f"<h2>{escape(s)}</h2><p>{escape(m)}</p>" for s, m in bolimlar)
    return web.Response(content_type="text/html", text=(
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{escape(sarlavha)}</title>"
        "<body style='font:16px/1.55 system-ui;padding:24px;max-width:720px;margin:auto'>"
        f"<h1>{escape(sarlavha)}</h1>{tana}"))


async def maxfiylik(request: web.Request):
    from core.config import BIZNES_SAQLASH_KUN, BIZNES_TOZALASH_KUN
    return _hujjat("Privacy Policy — UzBot Business", [
        ("What this service does",
         "UzBot (Telegram bot @uzchatgptaibot) lets a business owner connect their Telegram "
         "Business account and their Instagram Professional account so that an AI assistant "
         "can draft or send replies to the owner's customers in direct messages, using the "
         "instructions and business information the owner provides."),
        ("Data we process",
         "Messages that customers send to the connected account (including photos and voice "
         "messages, which are converted to text to understand them) and the replies sent by the "
         "owner or by the assistant; comments on the owner's posts that ask a question, and the "
         "caption of that post; the customer's public name and username; the access token "
         "Instagram issues when the owner connects their account. Message text is sent to our "
         "AI provider (OpenAI) only to generate the reply."),
        ("How long we keep it",
         f"Conversation history is kept for at most {BIZNES_SAQLASH_KUN} days. When the owner "
         f"disconnects the service or their subscription ends, the related conversations, drafts "
         f"and customer records are deleted after {BIZNES_TOZALASH_KUN} days. The Instagram access "
         "token is deleted immediately when the owner presses «Uzish» (Disconnect)."),
        ("What we never do",
         "We do not sell data, do not use it for advertising, and do not share it with anyone "
         "other than the AI provider needed to produce a reply."),
        ("Contact",
         "Write to the Telegram bot @uzchatgptaibot with any privacy question or request."),
        ("Maxfiylik (o'zbekcha)",
         "Bot faqat ulangan akkauntga kelgan xabarlarga javob yozish uchun ularni qayta "
         f"ishlaydi, yozishmalarni ko'pi bilan {BIZNES_SAQLASH_KUN} kun saqlaydi, ma'lumotni "
         "sotmaydi va reklamada ishlatmaydi. Savollar uchun: @uzchatgptaibot."),
    ])


async def ochirish(request: web.Request):
    from core.config import BIZNES_TOZALASH_KUN
    return _hujjat("Data Deletion — UzBot Business", [
        ("Delete your Instagram data",
         "1) In Telegram open @uzchatgptaibot and send /biznes. 2) Tap «Instagram» and then "
         "«Uzish» (Disconnect). The Instagram access token is deleted immediately; the "
         f"conversations, drafts and customer records are deleted within {BIZNES_TOZALASH_KUN} "
         "days. 3) Optionally remove the app in Instagram: Settings → Apps and websites."),
        ("Request full deletion",
         "Send the message «delete my data» to @uzchatgptaibot. All data linked to your "
         "account is deleted within 30 days and you receive a confirmation."),
        ("O'zbekcha",
         "Telegram'da @uzchatgptaibot → /biznes → «Instagram» → «Uzish». Kalit darhol, "
         f"yozishmalar {BIZNES_TOZALASH_KUN} kun ichida o'chadi."),
    ])


def register(app: web.Application) -> None:
    app.router.add_get("/ig/webhook", webhook_tekshir)
    app.router.add_post("/ig/webhook", webhook)
    app.router.add_get("/ig/ulash", ulash)
    app.router.add_get("/maxfiylik", maxfiylik)
    app.router.add_get("/malumot-ochirish", ochirish)
