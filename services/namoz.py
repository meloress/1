"""Namoz vaqtlari — `namoz_vaqti` asbobi va karta vidjeti.

⛔️ O'zbekistonning RASMIY vaqtlari har shahar uchun alohida hisoblanmaydi:
bu TOSHKENT jadvali + shaharning DOIMIY daqiqa farqi (Nukus +39, Andijon
−12 ...; namoz-vaqti.uz `offset_min`, Din ishlari qo'mitasi xulosasi). Nukusni
o'z koordinatasi bilan astronomik hisoblash rasmiy jadvaldan 2-4 daqiqa farq
qiladi (o'lchangan, 2026-11-10) — namoz vaqtida bu xato. Shuning uchun:

  1) shahar `UZ_FARQ` da → rasmiy Toshkent jadvali + o'sha farq;
  2) jadvalda yo'q O'zbekiston joyi → Toshkent jadvali + uzunlik farqi
     (69,24° − uzunlik) × 4 daqiqa — 47 shaharning ko'pchiligi aynan shu,
     lekin hammasi emas (Ohangaron, Xiva), shuning uchun "taxminiy";
  3) chet el → o'z koordinatasi bilan astronomik hisob.

Toshkent jadvali — namoz-vaqti.uz JSON'i, oyiga BIR so'rov (keshda). Sayt
javob bermasa — shu yerdagi hisob: u rasmiy jadvalning butun 2026 yiliga
±1 daqiqa ichida tushadi (aynan bir xil formula topilmadi — panjara
qidiruvida eng yaxshisi shu). Ya'ni jadval DOIM bor, "xizmat yo'q" holati yo'q.

Hisob usuli — o'sha yilga solishtirib tanlangan: Bomdod va Xufton 15,5°,
Asr Hanafiy, Shom = quyosh botishi + 3,5 daqiqa (2026 yilning 365 kunida 2190 vaqtdan
hech biri ±1 daqiqadan ko'p farq qilmaydi). Algoritm PrayTimes.org
(bir iteratsiya, yuqori kenglikda "angle-based" — Aladhan ham shuni qiladi).

⚠️ Geocoder o'zbekcha nomlarda adashadi («Farg‘ona» → 68,3° uzunlik, ya'ni
14 daqiqa xato; «Yangiyo‘l», «Zarafshon» ham) — jadvaldagi shahar geocoder'ga
UMUMAN bormaydi.
"""
import logging
import math
import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

logger = logging.getLogger(__name__)

FAJR_BURCHAK = 15.5
XUFTON_BURCHAK = 15.5
SHOM_QOSHIMCHA = 3.5        # daqiqa; 3 da yilning 5 kunida 2 daqiqa farq qilardi
TOSHKENT = (41.2995, 69.2401)
TOSHKENT_TZ = "Asia/Tashkent"
NOMLAR = ("Bomdod", "Quyosh", "Peshin", "Asr", "Shom", "Xufton")

_JADVAL_URL = ("https://namoz-vaqti.uz/lotin/namoz-vaqtlari/toshkent-shahri/oylik/"
               "{ym}?format=json")
_TIMEOUT = aiohttp.ClientTimeout(total=8)
_KALITLAR = ("bomdod", "quyosh", "peshin", "asr", "shom", "xufton")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Toshkent jadvaliga DOIMIY farq, daqiqa (namoz-vaqti.uz `offset_min`,
# 2026-11-10 da 47 hududdan yig'ilgan). Kalit — `_kalit()` dan o'tgan nom.
UZ_FARQ = {
    "toshkent": ("Toshkent", 0), "toshkent viloyati": ("Toshkent viloyati", 0),
    "bekobod": ("Bekobod", 0), "ohangaron": ("Ohangaron", 0), "yangiyol": ("Yangiyo'l", 0),
    "andijon": ("Andijon", -12), "asaka": ("Asaka", -12), "xonobod": ("Xonobod", -12),
    "fargona": ("Farg'ona", -10), "margilon": ("Marg'ilon", -10), "qoqon": ("Qo'qon", -7),
    "quvasoy": ("Quvasoy", -11), "namangan": ("Namangan", -10),
    "guliston": ("Guliston", 2), "sirdaryo": ("Sirdaryo", 2), "yangiyer": ("Yangiyer", 2),
    "shirin": ("Shirin", 3), "jizzax": ("Jizzax", 6),
    "samarqand": ("Samarqand", 9), "kattaqorgon": ("Kattaqo'rg'on", 12),
    "qarshi": ("Qarshi", 14), "qashqadaryo": ("Qashqadaryo", 14), "shahrisabz": ("Shahrisabz", 10),
    "termiz": ("Termiz", 8), "denov": ("Denov", 8), "surxondaryo": ("Surxondaryo", 8),
    "navoiy": ("Navoiy", 15), "zarafshon": ("Zarafshon", 20),
    "buxoro": ("Buxoro", 19), "kogon": ("Kogon", 19),
    "urganch": ("Urganch", 34), "xorazm": ("Xorazm", 34), "xiva": ("Xiva", 35),
    "nukus": ("Nukus", 39), "qoraqalpogiston": ("Nukus", 39), "xojayli": ("Xo'jayli", 36),
    "chimboy": ("Chimboy", 36), "qongirot": ("Qo'ng'irot", 36), "tortkol": ("To'rtko'l", 32),
}
# Model inglizcha/ruscha yozsa ham topilsin. Faqat aniq o'sha shahar.
_TAXALLUS = {
    "tashkent": "toshkent", "ташкент": "toshkent", "samarkand": "samarqand",
    "самарканд": "samarqand", "bukhara": "buxoro", "бухара": "buxoro",
    "fergana": "fargona", "ferghana": "fargona", "фергана": "fargona",
    "andijan": "andijon", "андижан": "andijon", "наманган": "namangan",
    "karshi": "qarshi", "карши": "qarshi", "kokand": "qoqon", "коканд": "qoqon",
    "margilan": "margilon", "jizzakh": "jizzax", "джизак": "jizzax",
    "gulistan": "guliston", "гулистан": "guliston", "navoi": "navoiy", "навои": "navoiy",
    "termez": "termiz", "термез": "termiz", "urgench": "urganch", "ургенч": "urganch",
    "khiva": "xiva", "хива": "xiva", "нукус": "nukus", "zarafshan": "zarafshon",
    "shakhrisabz": "shahrisabz", "kattakurgan": "kattaqorgon",
}
_QOSHIMCHA_RE = re.compile(r"\s+(shahri|shahar|sh\.?|viloyati|city|region|г\.?)$")


def _kalit(joy: str) -> str:
    k = re.sub(r"[ʻʼ'‘’`]", "", str(joy or "").lower().strip())
    k = re.sub(r"\s+", " ", k.split(",")[0].strip())
    return _QOSHIMCHA_RE.sub("", k)


def uz_shahar(joy: str):
    """(ko'rsatiladigan nom, farq) yoki None — rasmiy jadvaldagi shahar."""
    k = _kalit(joy)
    return UZ_FARQ.get(_TAXALLUS.get(k, k)) if k else None


def uzunlik_farqi(lon: float) -> int:
    return round((TOSHKENT[1] - lon) * 4)


# ── Astronomiya (PrayTimes.org, gradusda) ─────────────────────────
def _sin(d): return math.sin(math.radians(d))
def _cos(d): return math.cos(math.radians(d))
def _tan(d): return math.tan(math.radians(d))
def _fix(a, b): return a - b * math.floor(a / b)


def _quyosh(jd: float) -> tuple:
    """(og'ish, vaqt tenglamasi soatda)."""
    d = jd - 2451545.0
    g = _fix(357.529 + 0.98560028 * d, 360)
    q = _fix(280.459 + 0.98564736 * d, 360)
    lam = _fix(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g), 360)
    e = 23.439 - 0.00000036 * d
    ra = _fix(math.degrees(math.atan2(_cos(e) * _sin(lam), _cos(lam))) / 15, 24)
    return math.degrees(math.asin(_sin(e) * _sin(lam))), q / 15 - ra


def _julian(y: int, m: int, d: int) -> float:
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    return (math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1))
            + d + 2 - a + a // 4 - 1524.5)


def _hisob(kun: date, lat: float, lon: float, tz_soat: float):
    """6 vaqt, mahalliy soatda (float). Quyosh chiqmaydigan/botmaydigan qutb
    kunida None — bunday joyda jadval yo'q."""
    jd = _julian(kun.year, kun.month, kun.day) - lon / (15 * 24)

    def tush(t):
        return _fix(12 - _quyosh(jd + t)[1], 24)

    def burchak(angle, t, ccw):
        decl = _quyosh(jd + t)[0]
        x = (-_sin(angle) - _sin(decl) * _sin(lat)) / (_cos(decl) * _cos(lat))
        if not -1 <= x <= 1:
            return math.nan
        v = math.degrees(math.acos(x)) / 15
        return tush(t) + (-v if ccw else v)

    def asr(t):
        decl = _quyosh(jd + t)[0]
        return burchak(-math.degrees(math.atan(1 / (2 + _tan(abs(lat - decl))))), t, False)

    t = [x / 24 for x in (5, 6, 12, 13, 18, 18)]   # boshlang'ich taxmin
    v = [burchak(FAJR_BURCHAK, t[0], True), burchak(0.833, t[1], True), tush(t[2]),
         asr(t[3]), burchak(0.833, t[4], False), burchak(XUFTON_BURCHAK, t[5], False)]
    if math.isnan(v[1]) or math.isnan(v[4]) or math.isnan(v[3]):
        return None
    v = [x + tz_soat - lon / 15 for x in v]
    # Yuqori kenglik (yozda quyosh 15,5° gacha tushmaydi): "angle-based".
    tun = _fix(v[1] - v[4], 24)
    for i, baza, ccw in ((0, v[1], True), (5, v[4], False)):
        ulush = (FAJR_BURCHAK if i == 0 else XUFTON_BURCHAK) / 60 * tun
        # ⚠️ NaN avval: `_fix(nan)` floor'da ValueError beradi.
        if math.isnan(v[i]) or (_fix(baza - v[i], 24) if ccw
                                else _fix(v[i] - baza, 24)) > ulush:
            v[i] = baza - ulush if ccw else baza + ulush
    v[4] += SHOM_QOSHIMCHA / 60
    return v


def _hhmm(daq: int) -> str:
    daq %= 1440
    return f"{daq // 60:02d}:{daq % 60:02d}"


def _daq(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _tz_soat(kun: date, tz: str) -> float:
    return datetime(kun.year, kun.month, kun.day, 12, tzinfo=ZoneInfo(tz)) \
        .utcoffset().total_seconds() / 3600


def hisobla(kun: date, lat: float, lon: float, tz: str):
    """["05:44", "07:05", ...] (`NOMLAR` tartibida) yoki None."""
    v = _hisob(kun, lat, lon, _tz_soat(kun, tz))
    return None if v is None else [_hhmm(int(math.floor(_fix(x, 24) * 60 + 0.5))) for x in v]


# ── Rasmiy Toshkent jadvali (keshda) ─────────────────────────────
_KESH: dict = {}            # "2026-11" → {"10.11.2026": [6 vaqt]}
_XATO: dict = {}            # "2026-11" → oxirgi muvaffaqiyatsiz urinish vaqti
_QAYTA_URINISH = 600        # sayt yiqilganda har so'rovda kutib turmaslik


async def _oy_jadvali(ym: str):
    if ym in _KESH:
        return _KESH[ym]
    if time.time() - _XATO.get(ym, 0) < _QAYTA_URINISH:
        return None
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
            async with s.get(_JADVAL_URL.format(ym=ym),
                             headers={"User-Agent": "Mozilla/5.0"}) as r:
                if r.status != 200:
                    raise ValueError(f"HTTP {r.status}")
                d = await r.json(content_type=None)
        if (d.get("meta") or {}).get("offset_min") not in (0, None):
            raise ValueError("Toshkent jadvali emas")
        jadval = {}
        for qator in d["period_table"]:
            v = [qator["times"][k] for k in _KALITLAR]
            if not all(isinstance(x, str) and _HHMM.match(x) for x in v):
                raise ValueError(f"vaqt shakli: {v}")
            jadval[qator["date"]] = v
        if len(jadval) < 28:
            raise ValueError(f"{len(jadval)} kun")
    except Exception as e:
        _XATO[ym] = time.time()
        logger.warning(f"[NAMOZ] rasmiy jadval olinmadi ({ym}): {type(e).__name__}: {e} "
                       "— o'z hisobimiz (±1 daqiqa)")
        return None
    _KESH[ym] = jadval
    return jadval


async def toshkent_kuni(kun: date) -> tuple:
    """(6 vaqt, rasmiymi). Sayt yo'q bo'lsa — o'z hisobimiz, False."""
    jadval = await _oy_jadvali(f"{kun:%Y-%m}")
    v = (jadval or {}).get(f"{kun:%d.%m.%Y}")
    if v:
        return v, True
    return hisobla(kun, *TOSHKENT, TOSHKENT_TZ), False


# ── Karta holati ─────────────────────────────────────────────────
# `q` — kartaning ertangi yangilash so'rovi ("n:" + q): "r:<farq>" — rasmiy
# jadval shahri, "t:<farq>" — taxminiy (uzunlik farqi), "a:lat,lon,tz" —
# chet el. `u` — shahar mintaqasining UTC farqi (daqiqa): sanoq TELEFON
# soatiga emas, SHAHAR soatiga qarab yurishi kerak.
_TZ_RE = re.compile(r"^[A-Za-z]+(?:/[A-Za-z0-9_+\-]+){0,2}$")


def sorov_oqi(q: str):
    """Kartadan kelgan `q` — telefondan, ya'ni ishonchsiz. ("r"|"t", farq)
    yoki ("a", lat, lon, tz); yaroqsiz bo'lsa None."""
    try:
        tur, _, qolgan = str(q).partition(":")
        if tur in ("r", "t"):
            farq = int(qolgan)
            return (tur, farq) if -120 <= farq <= 120 else None
        if tur == "a":
            lat, lon, tz = qolgan.split(",")
            lat, lon = float(lat), float(lon)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180
                    and len(tz) <= 40 and _TZ_RE.match(tz)):
                return None
            ZoneInfo(tz)
            return tur, lat, lon, tz
    except Exception:
        return None
    return None


async def joy_ol(joy: str) -> tuple:
    """Model yozgan joy → (kortej, ko'rsatiladigan nom). Jadvaldagi shahar
    geocoder'ga BORMAYDI (modul izohi). `obhavo.JoyTopilmadi` / `XizmatYoq`
    chaqiruvchiga chiqadi — ular ikki XIL javob."""
    from services import obhavo
    s = uz_shahar(joy)
    if s:
        return ("r", s[1]), s[0]
    j = await obhavo.joy_top(joy)
    if j.get("cc") == "UZ":
        nom = j["nom"] + (f", {j['viloyat']}" if j.get("viloyat") else "")
        return ("t", uzunlik_farqi(j["lon"])), nom
    tz = j.get("tz") or ""
    if not (_TZ_RE.match(tz) and sorov_oqi(f"a:{j['lat']},{j['lon']},{tz}")):
        raise obhavo.XizmatYoq(f"vaqt mintaqasi noma'lum: {tz!r}")
    nom = j["nom"] + (f", {j['mamlakat']}" if j["mamlakat"] else "")
    return ("a", j["lat"], j["lon"], tz), nom


async def holat(joy: tuple, nom: str) -> dict | None:
    """`joy` — `sorov_oqi()` shaklidagi kortej. None — qutb kuni."""
    if joy[0] == "a":
        _, lat, lon, tz = joy
        bugun = datetime.now(ZoneInfo(tz)).date()
        v, e = hisobla(bugun, lat, lon, tz), hisobla(bugun + timedelta(days=1), lat, lon, tz)
        if v is None or e is None:
            return None
        q, manba = f"a:{round(lat, 4)},{round(lon, 4)},{tz}", "a"
        u = int(_tz_soat(bugun, tz) * 60)
    else:
        tur, farq = joy
        bugun = datetime.now(ZoneInfo(TOSHKENT_TZ)).date()
        (v, r1), (e, r2) = (await toshkent_kuni(bugun),
                            await toshkent_kuni(bugun + timedelta(days=1)))
        v = [_hhmm(_daq(x) + farq) for x in v]
        e = [_hhmm(_daq(x) + farq) for x in e]
        # Manba: r — rasmiy, t — taxminiy farq, h — sayt yo'q, o'z hisobimiz.
        manba = tur if (r1 and r2) or tur == "t" else "h"
        q, u = f"{tur}:{farq}", 300
    return {"j": nom, "d": f"{bugun:%d.%m.%Y}", "v": v, "e": e[0], "u": u,
            "m": manba, "q": q, "t": int(time.time())}


_MANBA = {
    "r": "rasmiy jadval (O'zbekiston, Din ishlari qo'mitasi xulosasi asosida)",
    "t": ("Toshkent rasmiy jadvali + uzunlik farqi — TAXMINIY (±2 daqiqa); "
          "aniq vaqtni viloyat markazi jadvalidan tekshirishni ayting"),
    "h": ("rasmiy sayt hozir javob bermadi — o'z hisobimiz (rasmiy jadvaldan ±1 "
          "daqiqa)"),
    "a": ("astronomik hisob (Bomdod/Xufton 15,5°, Asr Hanafiy); mahalliy masjid "
          "jadvali bir necha daqiqa farq qilishi mumkin"),
}


def matn(d: dict) -> str:
    vaqt = ", ".join(f"{n} {t}" for n, t in zip(NOMLAR, d["v"]))
    return (f"🕌 {d['j']} — {d['d']}: {vaqt}. Ertaga Bomdod: {d['e']}.\n"
            f"Manba: {_MANBA[d['m']]}.")
