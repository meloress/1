"""Navbatchi — egasining O'Z Telegram akkauntidan guruhda javob berib turish.

Telegram Business guruhda ishlamaydi (`BusinessBotRights.can_reply` — faqat
shaxsiy chatlar, Bot API 10.4), shuning uchun bu USERBOT: Telethon egasining
sessiyasi bilan, shu jarayonning ichida (eski_bot kabi). Sozlama
(`USERBOT_SESSION`, `USERBOT_API_ID`, `USERBOT_API_HASH`) yo'q bo'lsa umuman
yoqilmaydi — botning qolgan qismiga ta'siri nol.

Egasi guruhda O'Z akkauntidan yozadi (boshla/to'xta guruhda QOLADI va Vexon
unga egasining profilidan tabiiy javob qaytaradi; belgi buyrug'i o'chadi):
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

Tabiiylik — XULQ ham (2026-11-22, egasi: «botligi sezilmasin umuman»): matn
qanchalik odamdek bo'lmasin, har xabarga 3 soniyada, doim reply bilan javob
— bot. Shuning uchun kodda: o'qish kechikishi (`oqish_vaqti`), telefonda
terish tezligi (`terish_vaqti`), ba'zi xabarni o'tkazib yuborish
(`OTKAZISH`), matn o'rniga reaksiya, ikki qisqa xabarga bo'lish (`bolaklar`).
Reply — DOIM (egasi so'radi, 2026-11-22: «reply bilan yozsin har doim»).
"""
import asyncio
import html
import logging
import os
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

NAVBAT_SOAT = 3            # unutilgan navbat guruhni kun bo'yi to'ldirmasin
ORALIQ = 20.0              # bitta guruhda javoblar orasidagi eng kam vaqt (s)
MAX_JAVOB = 120            # bitta navbatda (hammaga javob — 30 tez tugardi)
MENGA_ORALIQ = 3.0         # u bilan gaplashayotganlarga javoblar orasidagi eng kam vaqt (s)
MENGA_NAVBAT = 5           # javob kutayotgan «menga» xabarlar soni (ko'pi)
KONTEKST = 15              # modelga ko'rinadigan oxirgi guruh xabarlari
VAZIFA_MIN_SOZ = 3         # «vexon zo'r» — buyruq emas, oddiy gap
REAKSIYA_ODAM_ORALIQ = 600  # bitta odamning reaksiyalariga — 10 daqiqada bitta javob
# Odamdek kechikish (o'qish 3-100 s, reaksiyaga 8-45 s, terish 25 s gacha). Egasi
# 2026-11-22: «kutishni o'chir, tez-tez javob bersin» — o'chiq: o'qish 0, terish
# 1,5-6 s. Qolgan xulq (o'tkazish, reply'siz, reaksiya, 2 xabar) o'zgarmaydi.
KUTISH_YOQIQ = False
OTKAZISH = 0.25            # o'ziga qaratilmagan, savol emas xabarni o'tkazib yuborish

_SAVOL_RE = re.compile(r"\?|(?<!\w)(nima\w*|nega|qanday|qanaqa|qachon|qayer\w*|kim|"
                       r"qancha|nechi\w*)(?!\w)|\w(mi|mu)(?!\w)", re.I)
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
    uslub: str = ""          # egasining Biznes uslubi (biznes_uslub.uslub_bloki)
    reaksiyalar: int = 0
    # Javobga chog'lanib turgan xabar: (e, kim, matn, odam_id, menga) yoki None.
    nishon: tuple | None = None
    kutayotgan: int = 0      # navbatda turgan «menga» xabarlar
    korilgan: set = field(default_factory=set)        # (msg_id, odam, emoji) — reaksiyalar
    reaksiya_javob: dict = field(default_factory=dict)  # odam → oxirgi javob vaqti

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


def oqish_vaqti(menga: bool) -> float:
    """Javobdan oldingi kechikish (s): odam xabarni darhol ko'rmaydi. O'ziga
    qaratilganini tezroq; ba'zan telefon cho'ntakda — 1-2 daqiqa."""
    if not KUTISH_YOQIQ:
        return 0.0
    if menga:
        return random.uniform(3, 18)
    if random.random() < 0.15:
        return random.uniform(45, 100)
    return random.uniform(6, 40)


def terish_vaqti(matn: str) -> float:
    """«yozmoqda…» qancha turadi: telefonda ~3,5-6 belgi/s va bir oz o'ylash."""
    if not KUTISH_YOQIQ:
        return min(6.0, 1.5 + len(matn) / 40)
    return max(2.0, min(25.0, random.uniform(1.0, 2.5) + len(matn) / random.uniform(3.5, 6.0)))


def bolaklar(javob: str) -> list[str]:
    """Model bo'sh qator bilan ajratgan 2-3 qisqa gap — alohida xabarlar (odam
    shunday yozadi). Uzun qism bo'lsa (kod, tushuntirish) — bitta xabar."""
    qismlar = [q.strip() for q in javob.split("\n\n") if q.strip()]
    if 2 <= len(qismlar) <= 3 and all(len(q) <= 200 for q in qismlar):
        return qismlar
    return [javob]


def _belgila_html(matn_html: str, uid: int, ism: str) -> str:
    """Odamni bosiladigan qilib tilga olish (unga bildirishnoma boradi).
    Model ismini yozgan bo'lsa — o'sha so'z havola bo'ladi, aks holda boshiga."""
    nom = html.escape((ism or "").split(" ")[0])
    def havola(t):
        return f'<a href="tg://user?id={int(uid)}">{t}</a>'
    if len(nom) >= 2:
        m = re.search(rf"(?<![\w&]){re.escape(nom)}(?!\w)", matn_html, re.I)
        if m:
            return matn_html[:m.start()] + havola(m.group(0)) + matn_html[m.end():]
    return f"{havola(nom or 'aka')}, {matn_html}"


async def _kut(soniya: float) -> None:
    await asyncio.sleep(soniya)


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
         f"Javoblar: {len(nav.javoblar)}"
         + (f", reaksiyalar: {nav.reaksiyalar}" if nav.reaksiyalar else "")]
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
    """«yozmoqda…» — telefonda terilgandek (`terish_vaqti`)."""
    try:
        async with _CLIENT.action(chat_id, "typing"):
            await asyncio.sleep(terish_vaqti(matn))
    except Exception:
        pass


async def _reaksiya_qoy(e, rk: str) -> bool:
    """Xabarga reaksiya. Guruh reaksiyani cheklagan bo'lsa — jim (bezak)."""
    try:
        from telethon.tl.functions.messages import SendReactionRequest
        from telethon.tl.types import ReactionEmoji
        await _CLIENT(SendReactionRequest(peer=await e.get_input_chat(), msg_id=e.id,
                                          reaction=[ReactionEmoji(emoticon=rk)]))
        return True
    except Exception as x:
        logger.info(f"[Navbat] reaksiya qo'yilmadi: {type(x).__name__}")
        return False


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
    tur, qiymat = b
    # «vexon, ...» va «vexon to'xta» guruhda QOLADI — Vexon unga egasining
    # profilidan tabiiy javob qaytaradi (egasi so'radi, 2026-11-22: «xo'p,
    # siz kelguningizcha...», «bo'ldi, jim bo'ldim»). Bu ham bot uchun sahna.
    if tur == "toxta":
        nav = _NAVBAT.get(e.chat_id)
        if nav is not None:
            await _tasdiqla(e, "toxta", nav.vazifa)
            await toxtat(e.chat_id, "buyruq")
        return
    if tur == "belgi":
        # Texnik buyruq — guruhga kerak emas, o'chadi.
        try:
            await e.delete()
        except Exception as x:
            logger.info(f"[Navbat] buyruq o'chmadi: {x}")
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
        # ⛔️ Biznes uslubi BERILMAYDI (jonli sinov, 2026-11-23, egasi: «10/2,
        # vaziyatga kirishmayapti, yumor yo'q»): u MIJOZLARGA yozilgan
        # xabarlardan o'rganilgan — xushmuomala sotuvchi ohangi, «eng ustun»
        # sarlavhasi bilan hazil qoidasini bosib ketardi.
        _NAVBAT[e.chat_id] = Navbat(vazifa=qiymat, nom=nom)
    nav = _NAVBAT[e.chat_id]
    logger.info(f"[Navbat] yoqildi chat={e.chat_id}")
    await _tasdiqla(e, "boshla", qiymat)
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
    menga = bool(getattr(getattr(e, "message", None), "mentioned", False)) or _tilga_oldi(matn)
    odam_id = getattr(odam, "id", None)
    sabab = javob_mumkinmi(nav, hozir)
    if sabab == "limit":
        await toxtat(e.chat_id, f"{MAX_JAVOB} ta javob chegarasi")
        return
    if menga:
        # U bilan gaplashayotgan odam javobsiz QOLMAYDI (egasi, 2026-11-23: «u
        # bilan gaplashayotgan hammaga reply»): band yoki tez bo'lsa — tashlab
        # yuborilmaydi, navbat kutadi (MENGA_ORALIQ dan tez emas). Navbat
        # cheklangan — to'lsa jim (akkaunt spamga tushmasin).
        if nav.kutayotgan >= MENGA_NAVBAT:
            return
        nav.kutayotgan += 1
        try:
            # ponytail: 0,5 s so'rov — guruhdagi bir necha kishiga yetadi.
            while nav.nishon is not None or time.time() - nav.oxirgi_javob < MENGA_ORALIQ:
                if _NAVBAT.get(e.chat_id) is not nav:
                    return
                await asyncio.sleep(0.5)
        finally:
            nav.kutayotgan -= 1
    elif nav.nishon is not None or sabab:
        return
    elif not _SAVOL_RE.search(matn) and random.random() < OTKAZISH:
        return                                   # odam har xabarga yozmaydi
    # Joy OLDINDAN band qilinadi (await'siz): Telethon handler'lari parallel,
    # ikki xabar bir vaqtda kelsa ikkalasi ham «bo'sh» deb o'tib ketardi.
    nav.nishon = (e, kim, matn, odam_id, menga)
    oldingi_vaqt, nav.oxirgi_javob = nav.oxirgi_javob, time.time()
    try:
        await _kut(oqish_vaqti(menga))
        if _NAVBAT.get(e.chat_id) is not nav:
            return
        e, kim, matn, odam_id, menga = nav.nishon
        # Kontekst — kutish paytida kelganlari ham; nishon satri alohida beriladi.
        suhbat = list(nav.tarix)
        satr = f"{kim}: {matn[:300]}"
        if satr in suhbat:
            del suhbat[len(suhbat) - 1 - suhbat[::-1].index(satr)]
        from services import ai
        javob, eslab, rk = await ai.navbat_javobi(
            nav.vazifa, "\n".join(suhbat), f"{kim}: {matn}",
            egasi=_EGASI.get("ism") or "", menga=menga, uslub=nav.uslub,
            odam_haqida=await _faktlar(odam_id),
            oldingi=[j for _, _, j in nav.javoblar], user_id=_EGASI.get("id"),
            reply_qilingan=await _reply_qilingan(e))
        if eslab and odam_id:
            asyncio.create_task(_eslab_qol(odam_id, kim, eslab))
        if not (javob or rk) or _NAVBAT.get(e.chat_id) is not nav:
            nav.oxirgi_javob = oldingi_vaqt      # javob yo'q — joy bo'shaydi
            return
        if rk and await _reaksiya_qoy(e, rk):
            nav.reaksiyalar += 1
        if javob:
            if rk:
                await _kut(random.uniform(1, 3))
            if await _yubor(e, javob, nav):
                nav.javoblar.append((kim, matn, javob))
                nav.tarix.append(f"{_EGASI.get('ism') or 'egasi'} (sen): {javob}")
        # ORALIQ yuborilgan paytdan sanaladi (FloodWait kelajakni qo'ygan bo'lsa — o'sha).
        nav.oxirgi_javob = max(nav.oxirgi_javob, time.time())
    finally:
        nav.nishon = None


async def _reply_qilingan(e) -> str:
    """Xabar reply bo'lsa — nimaga: «sen: …» yoki «Ali: …». Busiz model
    reply'ning o'zini ko'rib, qaysi gapga javobligini bilmay «bog'dan-tog'dan»
    yozardi (jonli sinov, 2026-11-23). Xato — bo'sh (bezak)."""
    if not getattr(e, "is_reply", False):
        return ""
    try:
        r = await e.get_reply_message()
        matn = " ".join((getattr(r, "raw_text", "") or "").split())
        if not matn:
            return ""
        kim = "sen" if getattr(r, "out", False) else _ism(await r.get_sender())
        return f"{kim}: {matn[:400]}"
    except Exception:
        return ""


async def _yubor(e, javob: str, nav: "Navbat | None", *,
                 belgila: tuple | None = None) -> bool:
    """Egasining profilidan `e` ga REPLY (har qism ham — egasi «har doim
    reply» dedi): oldidan «yozmoqda…», belgi — oxirgisida; o'zimizniki deb
    belgilanadi. `belgila=(uid, ism)` — birinchi qismda odam tilga olinadi.
    True — hech bo'lmasa birinchi qism yetdi."""
    from services import ai
    qismlar = bolaklar(javob)
    for i, qism in enumerate(qismlar):
        if i:
            await _kut(random.uniform(0.5, 2.0))
        await _terish(e.chat_id, qism)
        oddiy = html.escape(qism)
        if belgila and i == 0:
            oddiy = _belgila_html(oddiy, *belgila)
        if BELGI_YOQIQ and i == len(qismlar) - 1:
            oddiy += f"\n{_belgi_html()}"
        # Egasida Premium bor — oddiy emoji bot paketidagi animatsiyalisiga
        # (`ai.html_premium`, botdagi bilan bir manba). Premium tugasa Telegram
        # rad etadi — o'sha xabar oddiy emoji bilan qayta ketadi.
        premium = ai.html_premium(oddiy)
        _YOZYAPTI.add(e.chat_id)
        try:
            try:
                m = await e.reply(premium, parse_mode="html", link_preview=False)
            except Exception as x:
                if premium == oddiy or getattr(x, "seconds", None):
                    raise
                logger.info(f"[Navbat] premium emoji rad etildi: {type(x).__name__}")
                m = await e.reply(oddiy, parse_mode="html", link_preview=False)
            if len(_YOZILGAN) > 500:
                _YOZILGAN.clear()
            _YOZILGAN.add((e.chat_id, getattr(m, "id", 0)))
        except Exception as x:
            # FloodWait — Telegram sekinla deyapti: shuncha vaqt jim turamiz.
            kut = getattr(x, "seconds", None)
            if kut and nav is not None:
                nav.oxirgi_javob = time.time() + kut
            logger.warning(f"[Navbat] yuborilmadi chat={e.chat_id}: {type(x).__name__}")
            return i > 0
        finally:
            _YOZYAPTI.discard(e.chat_id)
    return True


async def _faktlar(odam_id) -> list:
    """Yozuvchi haqida avval eslab qolinganlar. Xato — bo'sh (javob baribir)."""
    if not odam_id or not _EGASI.get("id"):
        return []
    try:
        from db import database
        return await database.navbat_odam_ol(_EGASI["id"], odam_id)
    except Exception as x:
        logger.info(f"[Navbat] xotira o'qilmadi: {type(x).__name__}")
        return []


async def _eslab_qol(odam_id: int, ism: str, faktlar: list) -> None:
    """Fon vazifasi: tekshiruv (`clean_navbat_fakt`) va saqlash bazada."""
    try:
        from db import database
        await database.navbat_odam_qosh(_EGASI["id"], odam_id, ism, faktlar)
    except Exception as x:
        logger.info(f"[Navbat] xotira yozilmadi: {type(x).__name__}")


# Model javob bermasa — shu gaplar (navbat baribir yoqiladi / to'xtaydi).
_TASDIQ_ZAXIRA = {"boshla": "xo'p siz kelguningizcha shu yerdaman 😎",
                  "toxta": "bo'ldi jim bo'ldim 🤐"}


async def _tasdiqla(e, holat: str, vazifa: str) -> None:
    """Egasining ochiq buyrug'iga uning profilidan bir og'iz javob."""
    from services import ai
    matn = await ai.navbat_tasdiq(holat, vazifa, _EGASI.get("ism") or "",
                                  user_id=_EGASI.get("id"))
    nav = _NAVBAT.get(e.chat_id)
    if await _yubor(e, matn or _TASDIQ_ZAXIRA[holat], nav) and nav is not None:
        nav.tarix.append(f"{_EGASI.get('ism') or 'egasi'} (sen): {matn or _TASDIQ_ZAXIRA[holat]}")


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


def _reaksiya_nomi(r) -> str:
    em = getattr(r, "emoticon", None)
    if em:
        return em
    return "⭐" if type(r).__name__ == "ReactionPaid" else "stiker-emoji"


async def reaksiya_keldi(u) -> None:
    """Telethon Raw `UpdateMessageReactions`: kimdir EGASINING xabariga
    reaksiya bosdi — o'sha odamni tilga olib, reaksiyasiga mos javob (egasi
    so'radi, 2026-11-22: «hamma reaksiyalarga»). Hech qachon ko'tarmaydi.

    ⛔️ Spam chegarasi kodda: bitta odamga 10 daqiqada bitta javob
    (`REAKSIYA_ODAM_ORALIQ`) — aks holda reaksiyani bosib-olib akkauntdan
    spam yozdirish mumkin; umumiy ORALIQ va MAX_JAVOB ham amal qiladi."""
    try:
        from telethon import utils
        chat_id = utils.get_peer_id(u.peer)
        nav = _NAVBAT.get(chat_id)
        if nav is None or _CLIENT is None:
            return
        hozir = time.time()
        # Telegram har safar oxirgi reaksiyalarning TO'LIQ ro'yxatini yuboradi —
        # yangisi `korilgan` da yo'qligi bilan topiladi.
        yangi = None
        for r in (getattr(u.reactions, "recent_reactions", None) or []):
            uid = utils.get_peer_id(r.peer_id)
            kalit = (u.msg_id, uid, _reaksiya_nomi(r.reaction))
            sana = getattr(r, "date", None)
            if (getattr(r, "my", False) or uid == _EGASI.get("id") or kalit in nav.korilgan
                    or (sana is not None and sana.timestamp() < nav.boshlandi - 2)):
                continue
            nav.korilgan.add(kalit)
            yangi = yangi or (uid, kalit[2])
        if yangi is None:
            return
        uid, emoji = yangi
        if (hozir - nav.reaksiya_javob.get(uid, 0) < REAKSIYA_ODAM_ORALIQ
                or nav.nishon is not None or javob_mumkinmi(nav, hozir)):
            return
        xabar = await _CLIENT.get_messages(chat_id, ids=u.msg_id)
        if xabar is None or not getattr(xabar, "out", False):
            return                                  # faqat egasining xabari
        odam = await _CLIENT.get_entity(uid)
        if getattr(odam, "bot", False):
            return
        kim = _ism(odam)
        if nav.nishon is not None:                  # get_* paytida band bo'ldi
            return
        nav.nishon = (xabar, kim, "", uid, True)
        oldingi_vaqt, nav.oxirgi_javob = nav.oxirgi_javob, hozir
        nav.reaksiya_javob[uid] = hozir
        try:
            # odam reaksiyani darhol ko'rmaydi (kutish yoqiq bo'lsa)
            await _kut(random.uniform(8, 45) if KUTISH_YOQIQ else 0.0)
            if _NAVBAT.get(chat_id) is not nav:
                return
            matn = " ".join((getattr(xabar, "raw_text", "") or "").split())[:200]
            from services import ai
            javob, _, _ = await ai.navbat_javobi(
                nav.vazifa, "\n".join(nav.tarix),
                f"[REAKSIYA] {kim} sening «{matn}» degan xabaringga {emoji} bosdi",
                egasi=_EGASI.get("ism") or "", menga=True, uslub=nav.uslub,
                odam_haqida=await _faktlar(uid),
                oldingi=[j for _, _, j in nav.javoblar], user_id=_EGASI.get("id"))
            nav.tarix.append(f"{kim}: [sening xabaringga {emoji} bosdi]")
            if not javob or _NAVBAT.get(chat_id) is not nav:
                nav.oxirgi_javob = oldingi_vaqt
                return
            if await _yubor(xabar, javob, nav, belgila=(uid, kim)):
                nav.javoblar.append((kim, f"[{emoji} reaksiya]", javob))
                nav.tarix.append(f"{_EGASI.get('ism') or 'egasi'} (sen): {javob}")
            nav.oxirgi_javob = max(nav.oxirgi_javob, time.time())
        finally:
            nav.nishon = None
    except Exception as x:
        logger.warning(f"[Navbat] reaksiya ishlanmadi: {type(x).__name__}: {x}")


async def _muddat_kuzatuvchi() -> None:
    """Guruh jim qolsa ham unutilgan navbat o'z vaqtida tugasin."""
    while True:
        await asyncio.sleep(60)
        hozir = time.time()
        for chat_id in [c for c, n in _NAVBAT.items() if hozir > n.tugash]:
            await toxtat(chat_id, "vaqt tugadi")


_KUZATUVCHI = False


async def ishga_tushir() -> None:
    """main.py dan fon vazifasi va QR ulanishdan keyin. Sozlama yo'q — jim."""
    global _CLIENT, _KUZATUVCHI
    try:
        s = await _sozlama()
        if s is None:
            return
        sessiya, api_id, api_hash = s
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession
        client = TelegramClient(StringSession(sessiya), api_id, api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("[Navbat] sessiya yaroqsiz — /navbat_ulash bilan qayta ulang")
            await client.disconnect()
            return
        me = await client.get_me()
        _EGASI.update(id=me.id, ism=_ism(me), username=me.username or "")
        client.add_event_handler(xabar_keldi, events.NewMessage(func=lambda e: e.is_group))
        from telethon.tl.types import UpdateMessageReactions
        client.add_event_handler(reaksiya_keldi, events.Raw(UpdateMessageReactions))
        _CLIENT = client
        if not _KUZATUVCHI:
            _KUZATUVCHI = True
            asyncio.create_task(_muddat_kuzatuvchi())
        logger.info("[Navbat] userbot ulandi")
    except Exception as x:
        # ⛔️ Faqat turi: xabar matnida sessiya parchasi bo'lishi mumkin.
        logger.error(f"[Navbat] ishga tushmadi: {type(x).__name__}")


async def toxtat_hammasi() -> None:
    """SIGTERM'da: ulanish yopiladi (navbatlar RAM — baribir tugaydi)."""
    if _CLIENT is not None:
        await _CLIENT.disconnect()


# ═══════════════════════════════════════════════════════════════════
#  BOTNING O'ZIDA ULASH — QR (2026-11-22). ⛔️ FAQAT superadmin.
# ═══════════════════════════════════════════════════════════════════
# Egasi: «kodni botga yuborsam bo'lmaydimi?» — YO'Q: Telegram ichida biror
# chatga yuborilgan kirish kodini Telegram o'zi bekor qiladi (fishingga
# qarshi), buni aylanib o'tmaymiz. QR esa Telegram Desktop'ga kirishning
# rasmiy yo'li: kod umuman yo'q, egasi telefonda Qurilmalar → Kompyuterni
# ulash bilan skanerlaydi.
#
# Begonaga buyruqlar UMUMAN yo'q: filtr (`egami`) o'tkazmaydi — xabar oddiy
# matn bo'lib AI'ga ketadi, «ruxsat yo'q» degan iz ham qolmaydi. Menyuda yo'q.
#
# Saqlash: bazada Fernet bilan shifrlangan (kalit BOT_TOKEN'dan), Railway
# o'zgaruvchilari (USERBOT_*) bo'lsa — ular ustun. QR rasmi SERVERDA yasaladi
# (segno): kirish tokenini tashqi QR servisga berish = akkauntni berish.
QR_MUDDAT = 180             # skanerlash uchun jami vaqt (token ~30 s da yangilanadi)
PAROL_MUDDAT = 300
PAROL_URINISH = 3
_PAROL: dict[int, dict] = {}        # egasi → {"client", "chat", "urinish", "t"}
_ULASHMOQDA: set[int] = set()


def _fernet():
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    from core.config import BOT_TOKEN
    return Fernet(base64.urlsafe_b64encode(
        hashlib.sha256(b"navbatchi:" + (BOT_TOKEN or "").encode()).digest()))


def shifrla(d: dict) -> str:
    import json
    return _fernet().encrypt(json.dumps(d).encode()).decode()


def ochir(matn: str | None) -> dict | None:
    """Shifrni ochadi; buzilgan / boshqa token bilan yozilgan — None."""
    if not matn:
        return None
    try:
        import json
        return json.loads(_fernet().decrypt(matn.encode()))
    except Exception:
        return None


async def _saqlangan() -> dict:
    from db import database
    try:
        return ochir(await database.navbat_ulanish_ol()) or {}
    except Exception as x:
        logger.warning(f"[Navbat] ulanish o'qilmadi: {type(x).__name__}")
        return {}


async def _sozlama() -> tuple[str, int, str] | None:
    """(sessiya, api_id, api_hash): avval Railway o'zgaruvchilari, keyin baza."""
    sessiya = os.getenv("USERBOT_SESSION", "").strip()
    api_id = os.getenv("USERBOT_API_ID", "").strip()
    api_hash = os.getenv("USERBOT_API_HASH", "").strip()
    if sessiya and api_id.isdigit() and api_hash:
        return sessiya, int(api_id), api_hash
    d = await _saqlangan()
    if d.get("sessiya") and str(d.get("api_id", "")).isdigit() and d.get("api_hash"):
        return d["sessiya"], int(d["api_id"]), d["api_hash"]
    return None


async def egami(message) -> bool:
    """aiogram filtri: faqat superadmin, faqat shaxsiy chat."""
    u = getattr(message, "from_user", None)
    if u is None or getattr(getattr(message, "chat", None), "type", None) != "private":
        return False
    try:
        from db import database
        return await database.is_superadmin(u.id)
    except Exception:
        return False


def parol_kutilmoqda(message) -> bool:
    """aiogram filtri: QR'dan keyin ikki bosqichli parol kutilyapti. Bazaga
    bormaydi — `_PAROL` ga faqat superadmin tushadi."""
    u = getattr(message, "from_user", None)
    h = _PAROL.get(getattr(u, "id", None))
    if h is None or getattr(getattr(message, "chat", None), "type", None) != "private":
        return False
    if time.time() - h["t"] > PAROL_MUDDAT:
        _PAROL.pop(u.id, None)
        asyncio.create_task(_uzil(h["client"]))
        return False
    return bool(getattr(message, "text", None))


async def _uzil(client) -> None:
    try:
        await client.disconnect()
    except Exception:
        pass


async def _xabarni_ochir(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


def _qr_png(url: str) -> bytes:
    import io
    import segno
    b = io.BytesIO()
    segno.make(url, error="m").save(b, kind="png", scale=10, border=3)
    return b.getvalue()


async def navbat_api(message, command=None) -> None:
    """/navbat_api <api_id> <api_hash> — my.telegram.org dan."""
    await _xabarni_ochir(message)              # api_hash chatda qolmasin
    q = ((getattr(command, "args", None) or "").split())
    if len(q) != 2 or not q[0].isdigit() or not re.fullmatch(r"[0-9a-fA-F]{32}", q[1]):
        await message.answer(
            "Format: <code>/navbat_api 1234567 0123456789abcdef0123456789abcdef</code>\n"
            "https://my.telegram.org → API development tools dan oling.",
            parse_mode="HTML", disable_web_page_preview=True)
        return
    from db import database
    d = await _saqlangan()
    d.update(api_id=int(q[0]), api_hash=q[1].lower())
    await database.navbat_ulanish_yoz(shifrla(d))
    await message.answer("✅ API saqlandi (xabaringiz o'chirildi). Endi /navbat_ulash")


async def navbat_ulash(message) -> None:
    """/navbat_ulash — QR yuboradi; egasi telefonda skanerlaydi."""
    uid, chat = message.from_user.id, message.chat.id
    d = await _saqlangan()
    api_id = d.get("api_id") or (os.getenv("USERBOT_API_ID", "").strip() or None)
    api_hash = d.get("api_hash") or os.getenv("USERBOT_API_HASH", "").strip()
    if not (str(api_id or "").isdigit() and api_hash):
        await message.answer(
            "Avval API kalit kerak (bir martalik, 2 daqiqa):\n"
            "1. https://my.telegram.org → API development tools\n"
            "2. Bu yerga: <code>/navbat_api API_ID API_HASH</code>",
            parse_mode="HTML", disable_web_page_preview=True)
        return
    if uid in _ULASHMOQDA or uid in _PAROL:
        await message.answer("⏳ Ulanish allaqachon ketyapti.")
        return
    _ULASHMOQDA.add(uid)
    asyncio.create_task(_qr_jarayon(chat, uid, int(api_id), api_hash))


async def _qr_jarayon(chat: int, uid: int, api_id: int, api_hash: str) -> None:
    from aiogram.types import BufferedInputFile, InputMediaPhoto
    from core.loader import bot
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
    from telethon.sessions import StringSession
    izoh = ("📱 <b>Kompyuterda</b> oching, <b>telefonda</b>: Telegram → Sozlamalar → "
            "Qurilmalar → <b>Kompyuterni ulash</b> → shu QR'ni skanerlang.\n"
            "<i>3 daqiqa amal qiladi. Hech kimga ko'rsatmang.</i>")
    client, rasm, parolga = None, None, False
    try:
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        qr = await client.qr_login()
        tugash = time.time() + QR_MUDDAT
        while True:
            fayl = BufferedInputFile(_qr_png(qr.url), filename="qr.png")
            if rasm is None:
                rasm = await bot.send_photo(chat, fayl, caption=izoh, parse_mode="HTML",
                                            protect_content=True)
            else:
                await bot.edit_message_media(
                    InputMediaPhoto(media=fayl, caption=izoh, parse_mode="HTML"),
                    chat_id=chat, message_id=rasm.message_id)
            qoldi = tugash - time.time()
            try:
                await qr.wait(timeout=max(5.0, min(25.0, qoldi)))
                break
            except asyncio.TimeoutError:
                if time.time() >= tugash:
                    await bot.send_message(chat, "⌛ Vaqt tugadi. Qayta: /navbat_ulash")
                    return
                await qr.recreate()
            except SessionPasswordNeededError:
                parolga = True
                _PAROL[uid] = {"client": client, "chat": chat, "urinish": 0, "t": time.time()}
                await bot.send_message(
                    chat, "🔐 Ikki bosqichli parolingizni yozing.\n<i>Xabaringiz darhol "
                    "o'chiriladi, parol hech qayerga saqlanmaydi. 5 daqiqa.</i>",
                    parse_mode="HTML")
                return
        await _yakunla(client, uid, chat)
    except Exception as x:
        logger.warning(f"[Navbat] QR ulanish: {type(x).__name__}")
        try:
            await bot.send_message(chat, f"❌ Ulanmadi ({type(x).__name__}). Qayta: /navbat_ulash")
        except Exception:
            pass
    finally:
        _ULASHMOQDA.discard(uid)
        if rasm is not None:
            try:
                await bot.delete_message(chat, rasm.message_id)   # token eskirsin ham
            except Exception:
                pass
        if client is not None and not parolga:
            await _uzil(client)


async def parol_keldi(message) -> None:
    """QR'dan keyingi ikki bosqichli parol — darhol o'chiriladi, saqlanmaydi."""
    from telethon.errors import PasswordHashInvalidError
    uid = message.from_user.id
    h = _PAROL.get(uid)
    parol = message.text or ""
    await _xabarni_ochir(message)
    if h is None:
        return
    try:
        await h["client"].sign_in(password=parol)
    except PasswordHashInvalidError:
        h["urinish"] += 1
        if h["urinish"] >= PAROL_URINISH:
            _PAROL.pop(uid, None)
            await _uzil(h["client"])
            await message.answer("❌ Parol 3 marta noto'g'ri. Qayta: /navbat_ulash")
        else:
            await message.answer(f"❌ Parol noto'g'ri, qayta yozing "
                                 f"({PAROL_URINISH - h['urinish']} urinish qoldi).")
        return
    except Exception as x:
        _PAROL.pop(uid, None)
        await _uzil(h["client"])
        await message.answer(f"❌ Ulanmadi ({type(x).__name__}). Qayta: /navbat_ulash")
        return
    _PAROL.pop(uid, None)
    try:
        await _yakunla(h["client"], uid, h["chat"])
    finally:
        await _uzil(h["client"])


async def _yakunla(client, uid: int, chat: int) -> None:
    """Kirish bo'ldi: FAQAT egasining o'z akkaunti bo'lsa saqlanadi."""
    from core.loader import bot
    from db import database
    me = await client.get_me()
    if me.id != uid:
        # QR'ni boshqa telefon skanerlagan — begona akkaunt serverda qolmasin.
        try:
            await client.log_out()
        except Exception:
            pass
        await bot.send_message(chat, "❌ Bu boshqa akkaunt. Faqat o'zingizning "
                                     "akkauntingiz bilan skanerlang: /navbat_ulash")
        return
    d = await _saqlangan()
    d.update(sessiya=client.session.save())
    if not d.get("api_id"):        # API Railway'dan kelgan bo'lsa
        d.update(api_id=client.api_id, api_hash=client.api_hash)
    await database.navbat_ulanish_yoz(shifrla(d))
    await _uzil(client)
    await qayta_ulan()
    await bot.send_message(
        chat, f"✅ <b>Ulandi:</b> {html.escape(_ism(me))}\n\n"
              "Guruhda o'z akkauntingizdan yozing:\n"
              "• <code>vexon, guruhni qizitib tur, hazillash</code> — navbat\n"
              "• <code>vexon to'xta</code> — to'xtatish\n"
              "• <code>vexon belgi o'chir</code> / <code>vexon belgi yoq</code>\n"
              "Uzish: /navbat_uzish", parse_mode="HTML")


async def qayta_ulan() -> None:
    global _CLIENT
    if _CLIENT is not None:
        await _uzil(_CLIENT)
        _CLIENT = None
    _NAVBAT.clear()
    await ishga_tushir()


async def navbat_uzish(message) -> None:
    """/navbat_uzish — sessiya Telegram'da ham tugatiladi, API qoladi."""
    global _CLIENT
    from db import database
    if _CLIENT is not None:
        try:
            await _CLIENT.log_out()
        except Exception:
            await _uzil(_CLIENT)
        _CLIENT = None
    _NAVBAT.clear()
    d = await _saqlangan()
    d.pop("sessiya", None)
    await database.navbat_ulanish_yoz(shifrla(d) if d else None)
    qoshimcha = ("\n⚠️ Railway'da USERBOT_SESSION ham bor — uni o'zingiz o'chiring."
                 if os.getenv("USERBOT_SESSION") else "")
    await message.answer("🔌 Uzildi — sessiya Telegram'da ham tugatildi." + qoshimcha)


async def navbat_xotira(message, command=None) -> None:
    """/navbat_xotira — kim haqida nima eslab qolingan; «tozala» — hammasi."""
    from db import database
    uid = message.from_user.id
    if (getattr(command, "args", None) or "").strip().lower() == "tozala":
        soni = await database.navbat_odamlar_tozala(uid)
        await message.answer(f"🧹 Tozalandi: {soni} kishi.")
        return
    royxat = await database.navbat_odamlar_royxat(uid)
    if not royxat:
        await message.answer("🧠 Hali hech kim haqida eslab qolinmagan.")
        return
    q = ["🧠 <b>Navbatchi eslab qolganlar</b>"]
    for ism, faktlar in royxat:
        q.append(f"\n<b>{html.escape(ism)}</b>\n" + "\n".join(f"• {html.escape(f)}" for f in faktlar))
    q.append(f"\n<i>{database.NAVBAT_SAQLASH_KUN} kun yozmagan odam o'zi o'chadi. "
             "Hammasini o'chirish: /navbat_xotira tozala</i>")
    matn = "\n".join(q)
    await message.answer(matn if len(matn) <= 4000 else matn[:3990] + "…", parse_mode="HTML")


def royxatdan_otkaz(dp) -> None:
    """main.py: admin handlerlaridan keyin, AI'dan OLDIN. Har biri `egami`
    (yoki `_PAROL`) filtri bilan — begona uchun bu buyruqlar mavjud emas."""
    from aiogram.filters import Command
    dp.message.register(navbat_api, Command("navbat_api"), egami)
    dp.message.register(navbat_ulash, Command("navbat_ulash"), egami)
    dp.message.register(navbat_uzish, Command("navbat_uzish"), egami)
    dp.message.register(navbat_xotira, Command("navbat_xotira"), egami)
    dp.message.register(parol_keldi, parol_kutilmoqda)
