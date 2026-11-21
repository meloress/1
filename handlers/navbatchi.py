"""Navbatchi — egasining O'Z Telegram akkauntidan guruhda javob berib turish.

Telegram Business guruhda ishlamaydi (`BusinessBotRights.can_reply` — faqat
shaxsiy chatlar, Bot API 10.4), shuning uchun bu USERBOT: Telethon egasining
sessiyasi bilan, shu jarayonning ichida (eski_bot kabi). Sozlama
(`USERBOT_SESSION`, `USERBOT_API_ID`, `USERBOT_API_HASH`) yo'q bo'lsa umuman
yoqilmaydi — botning qolgan qismiga ta'siri nol.

Egasi guruhda O'Z akkauntidan yozadi (buyruq xabari darhol o'chiriladi):
  «vexon, men kelgunimcha dasturlash savollariga javob berib tur» — navbat
  «vexon to'xta» / «vexon stop»                                    — to'xtaydi
  «vexon belgi o'chir» / «vexon belgi yoq»                         — ᵃᵛᵗᵒʲᵃᵛᵒᵇ
Egasi guruhga ODDIY xabar yozsa — u qaytdi, navbat tugaydi.

⛔️ Xavfsizlik KODDA, modelga ishonib emas (guruh ataylab buzishga urinadi):
- buyruq FAQAT egasining o'z xabari (`event.out`). Guruhdagi begona
  «vexon to'xta» — suhbat, model unga hazil bilan javob qaytaradi.
- shaxsiy chatlarga tegilmaydi (`event.is_group`), faqat navbat yoqilgan guruh.
- guruhda ORALIQ soniyada bitta javob, navbatga MAX_JAVOB, NAVBAT_SOAT dan
  keyin o'zi to'xtaydi — spamga o'xshasa Telegram AKKAUNTNI cheklaydi.
- `USERBOT_SESSION` — akkauntning TO'LIQ kaliti: hech qachon logga chiqmaydi.
"""
import asyncio
import html
import logging
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

NAVBAT_SOAT = 3            # unutilgan navbat guruhni kun bo'yi to'ldirmasin
ORALIQ = 20.0              # bitta guruhda javoblar orasidagi eng kam vaqt (s)
MAX_JAVOB = 30             # bitta navbatda
KONTEKST = 15              # modelga ko'rinadigan oxirgi guruh xabarlari
VAZIFA_MIN_SOZ = 3         # «vexon zo'r» — buyruq emas, oddiy gap

_BUYRUQ_RE = re.compile(r"^\s*(?:vexon|вексон)\b[\s,:;!.\-—]*(.*)$", re.I | re.S)
_TOXTA = {"to'xta", "toxta", "stop", "bas", "тўхта", "стоп"}

# Ish holati — RAM: deploy navbatni tugatadi (egasi qayta yoqadi; zarari yo'q).
_NAVBAT: dict[int, "Navbat"] = {}
BELGI_YOQIQ = True          # ᵃᵛᵗᵒʲᵃᵛᵒᵇ — standart yoniq
_EGASI: dict = {}           # {"id", "ism", "username"} — sessiya egasi
_YOZILGAN: set[tuple[int, int]] = set()   # o'zimiz yuborgan (chat, id)
_YOZYAPTI: set[int] = set()               # hozir yuborilayotgan chatlar
_CLIENT = None


@dataclass
class Navbat:
    vazifa: str
    nom: str
    boshlandi: float = field(default_factory=time.time)
    oxirgi_javob: float = 0.0
    javoblar: list = field(default_factory=list)          # (kim, savol, javob)
    tarix: deque = field(default_factory=lambda: deque(maxlen=KONTEKST))

    @property
    def tugash(self) -> float:
        return self.boshlandi + NAVBAT_SOAT * 3600


def buyruq(matn: str) -> tuple[str, str] | None:
    """Egasining xabari → ("boshla", vazifa) / ("toxta", "") / ("belgi", "1"|"0")
    yoki None (oddiy gap)."""
    m = _BUYRUQ_RE.match(matn or "")
    if not m:
        return None
    qolgan = " ".join(m.group(1).split())
    past = re.sub(r"[‘’`ʻʼ]", "'", qolgan.lower()).rstrip("!. ")
    if past in _TOXTA:
        return ("toxta", "")
    if re.fullmatch(r"belgi(ni)?\s+o'?chir", past):
        return ("belgi", "0")
    if re.fullmatch(r"belgi(ni)?\s+yoq", past):
        return ("belgi", "1")
    if len(qolgan.split()) >= VAZIFA_MIN_SOZ:
        return ("boshla", qolgan)
    return None


def javob_mumkinmi(nav: Navbat, hozir: float) -> str | None:
    """None — javob berish mumkin; aks holda sabab ("limit" / "tez")."""
    if len(nav.javoblar) >= MAX_JAVOB:
        return "limit"
    if hozir - nav.oxirgi_javob < ORALIQ:
        return "tez"
    return None


def _ism(odam) -> str:
    ism = " ".join(filter(None, [getattr(odam, "first_name", None),
                                 getattr(odam, "last_name", None)]))
    return (ism or getattr(odam, "username", None) or "kimdir")[:40]


def _tilga_oldi(matn: str) -> bool:
    """Egasini nomi yoki @username bilan atadimi (reply — `mentioned` da)."""
    past = (matn or "").lower()
    un = (_EGASI.get("username") or "").lower()
    if un and f"@{un}" in past:
        return True
    ism = (_EGASI.get("ism") or "").split(" ")[0].lower()
    return len(ism) >= 3 and re.search(rf"(?<!\w){re.escape(ism)}(?!\w)", past) is not None


def hisobot(nav: Navbat, sabab: str) -> str:
    """Navbat tugagach egasiga: kim nima so'radi, nima deyildi."""
    q = [f"⏸ <b>Navbat tugadi</b> — «{html.escape(nav.nom)}» ({html.escape(sabab)})",
         f"Javoblar: {len(nav.javoblar)}"]
    for kim, savol, javob in nav.javoblar:
        q.append(f"\n• <b>{html.escape(kim)}:</b> {html.escape(savol[:200])}\n"
                 f"  ↳ {html.escape(javob[:300])}")
    matn = "\n".join(q)
    return matn if len(matn) <= 3800 else matn[:3790] + "…"


def _belgi_html() -> str:
    from handlers.biznes import AVTO_BELGI          # yagona manba
    from handlers import pro
    nom = pro.BOT_USERNAME or "vexonai"
    return f'<a href="https://t.me/{html.escape(nom)}">{AVTO_BELGI}</a>'


async def _egasiga(matn: str) -> None:
    """@vexonai orqali egasining shaxsiy chatiga. Xato — jim (bezak)."""
    if not _EGASI.get("id"):
        return
    try:
        from core.loader import bot
        await bot.send_message(_EGASI["id"], matn, parse_mode="HTML",
                               disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"[Navbat] egasiga yetmadi: {e}")


async def _terish(chat_id: int, matn: str) -> None:
    """«yozmoqda…» — odam kabi: javob uzunligiga qarab 1,5-6 s."""
    try:
        async with _CLIENT.action(chat_id, "typing"):
            await asyncio.sleep(min(6.0, 1.5 + len(matn) / 40))
    except Exception:
        pass


async def toxtat(chat_id: int, sabab: str) -> None:
    nav = _NAVBAT.pop(chat_id, None)
    if nav is not None:
        logger.info(f"[Navbat] tugadi chat={chat_id} ({sabab}) javob={len(nav.javoblar)}")
        await _egasiga(hisobot(nav, sabab))


async def _egasi_yozdi(e) -> None:
    """Egasining O'Z xabari (yoki bizniki — o'tkazib yuboriladi)."""
    if (e.chat_id, e.id) in _YOZILGAN or e.chat_id in _YOZYAPTI:
        return
    b = buyruq(e.raw_text)
    if b is None:
        if e.chat_id in _NAVBAT:
            await toxtat(e.chat_id, "siz guruhga yozdingiz")
        return
    try:
        await e.delete()            # guruhdagilar buyruqni ko'rmasin
    except Exception as x:
        logger.info(f"[Navbat] buyruq o'chmadi: {x}")
    tur, qiymat = b
    if tur == "toxta":
        if e.chat_id in _NAVBAT:
            await toxtat(e.chat_id, "buyruq")
        return
    if tur == "belgi":
        global BELGI_YOQIQ
        BELGI_YOQIQ = qiymat == "1"
        await _egasiga("ᵃᵛᵗᵒʲᵃᵛᵒᵇ belgisi: " + ("yoniq" if BELGI_YOQIQ else "o'chiq"))
        return
    eski = _NAVBAT.get(e.chat_id)
    if eski is not None:            # yangi vazifa — hisob va kontekst qoladi
        eski.vazifa = qiymat
    else:
        try:
            nom = getattr(await e.get_chat(), "title", None) or "guruh"
        except Exception:
            nom = "guruh"
        _NAVBAT[e.chat_id] = Navbat(vazifa=qiymat, nom=nom)
    nav = _NAVBAT[e.chat_id]
    logger.info(f"[Navbat] yoqildi chat={e.chat_id}")
    await _egasiga(
        f"✅ <b>Navbat yoqildi</b> — «{html.escape(nav.nom)}»\n"
        f"Vazifa: {html.escape(qiymat)}\n"
        f"{NAVBAT_SOAT} soatdan keyin o'zi to'xtaydi. To'xtatish: guruhda "
        f"«vexon to'xta» yoki o'zingiz biror narsa yozing.\n"
        f"Belgi: {'yoniq' if BELGI_YOQIQ else 'o‘chiq'}")


async def _begona_yozdi(e) -> None:
    nav = _NAVBAT.get(e.chat_id)
    if nav is None:
        return
    hozir = time.time()
    if hozir > nav.tugash:
        await toxtat(e.chat_id, "vaqt tugadi")
        return
    matn = (e.raw_text or "").strip()
    sana = getattr(getattr(e, "message", None), "date", None)
    # Telegram sanasi butun soniya (kesilgan) — navbat yoqilgan soniyaning
    # o'zida kelgan xabar «oldingi» bo'lib qolmasin.
    if not matn or (sana is not None and sana.timestamp() < nav.boshlandi - 2):
        return
    try:
        odam = await e.get_sender()
    except Exception:
        odam = None
    if getattr(odam, "bot", False):
        return
    kim = _ism(odam)
    nav.tarix.append(f"{kim}: {matn[:300]}")
    sabab = javob_mumkinmi(nav, hozir)
    if sabab == "limit":
        await toxtat(e.chat_id, f"{MAX_JAVOB} ta javob chegarasi")
        return
    if sabab:
        return
    # Joy OLDINDAN band qilinadi: Telethon handler'lari parallel, ikki xabar
    # bir vaqtda kelsa ikkalasi ham «tez emas» deb o'tib ketardi.
    oldingi_vaqt, nav.oxirgi_javob = nav.oxirgi_javob, hozir
    menga = bool(getattr(getattr(e, "message", None), "mentioned", False)) or _tilga_oldi(matn)
    from services import ai
    javob = await ai.navbat_javobi(
        nav.vazifa, "\n".join(list(nav.tarix)[:-1]), f"{kim}: {matn}",
        egasi=_EGASI.get("ism") or "", menga=menga,
        oldingi=[j for _, _, j in nav.javoblar], user_id=_EGASI.get("id"))
    if not javob or _NAVBAT.get(e.chat_id) is not nav:
        nav.oxirgi_javob = oldingi_vaqt          # javob yo'q — joy bo'shaydi
        return
    await _terish(e.chat_id, javob)
    matn_html = html.escape(javob) + (f"\n{_belgi_html()}" if BELGI_YOQIQ else "")
    _YOZYAPTI.add(e.chat_id)
    try:
        m = await e.reply(matn_html, parse_mode="html", link_preview=False)
        if len(_YOZILGAN) > 500:
            _YOZILGAN.clear()
        _YOZILGAN.add((e.chat_id, getattr(m, "id", 0)))
    except Exception as x:
        # FloodWait — Telegram sekinla deyapti: shuncha vaqt jim turamiz.
        kut = getattr(x, "seconds", None)
        if kut:
            nav.oxirgi_javob = time.time() + kut
        logger.warning(f"[Navbat] yuborilmadi chat={e.chat_id}: {type(x).__name__}")
        return
    finally:
        _YOZYAPTI.discard(e.chat_id)
    nav.javoblar.append((kim, matn, javob))
    nav.tarix.append(f"{_EGASI.get('ism') or 'egasi'} (sen): {javob}")


async def xabar_keldi(e) -> None:
    """Telethon NewMessage. Hech qachon ko'tarmaydi."""
    try:
        if not getattr(e, "is_group", False):
            return                  # ⛔️ shaxsiy chatlar — tegilmaydi
        if e.out:
            await _egasi_yozdi(e)
        else:
            await _begona_yozdi(e)
    except Exception as x:
        logger.warning(f"[Navbat] xabar ishlanmadi: {type(x).__name__}: {x}")


async def _muddat_kuzatuvchi() -> None:
    """Guruh jim qolsa ham unutilgan navbat o'z vaqtida tugasin."""
    while True:
        await asyncio.sleep(60)
        hozir = time.time()
        for chat_id in [c for c, n in _NAVBAT.items() if hozir > n.tugash]:
            await toxtat(chat_id, "vaqt tugadi")


async def ishga_tushir() -> None:
    """main.py dan fon vazifasi. Sozlama yo'q — jim qaytadi."""
    global _CLIENT
    sessiya = os.getenv("USERBOT_SESSION", "").strip()
    api_id = os.getenv("USERBOT_API_ID", "").strip()
    api_hash = os.getenv("USERBOT_API_HASH", "").strip()
    if not (sessiya and api_id.isdigit() and api_hash):
        return
    try:
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession
        client = TelegramClient(StringSession(sessiya), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("[Navbat] sessiya yaroqsiz — tools/userbot_kirish.py qayta")
            await client.disconnect()
            return
        me = await client.get_me()
        _EGASI.update(id=me.id, ism=_ism(me), username=me.username or "")
        client.add_event_handler(xabar_keldi, events.NewMessage(func=lambda e: e.is_group))
        _CLIENT = client
        asyncio.create_task(_muddat_kuzatuvchi())
        logger.info("[Navbat] userbot ulandi")
    except Exception as x:
        logger.error(f"[Navbat] ishga tushmadi: {type(x).__name__}")


async def toxtat_hammasi() -> None:
    """SIGTERM'da: ulanish yopiladi (navbatlar RAM — baribir tugaydi)."""
    if _CLIENT is not None:
        await _CLIENT.disconnect()
