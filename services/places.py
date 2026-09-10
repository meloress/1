"""Yaqin atrofdagi joylarni topish — OpenStreetMap Overpass API.

NEGA OSM: kalit ham, ro'yxatdan o'tish ham, to'lov ham kerak emas va
`around:` filtri aynan «shu nuqtadan N metr ichida» degan so'rovni beradi.
Toshkentda o'lchab ko'rildi (2026-09-10, markazdan 3 km):
dorixona 60+, kafe/restoran 60+, shifoxona 23, zapravka 3 — nomlari
bilan, tanib bo'ladigan holda.

⚠️ ISHONCHLILIK — ENG ZAIF JOY. O'sha o'lchovda 11 so'rovdan 4 tasi
javob berdi: qolganlari `504`, o'qish yoki ulanish timeouti bilan
yiqildi, javob berganlari esa 22-40 soniya oldi. Shuning uchun:
  * uchala mirror BIR VAQTDA so'raladi va birinchi javob bergani olinadi
    (ketma-ket urinish 45 soniyagacha cho'zilardi);
  * javob bo'lmasa bo'sh ro'yxat emas, XATO qaytariladi — chaqiruvchi
    «joy yo'q» bilan «server javob bermadi» ni farqlashi shart, aks
    holda bot yo'q joyda «yaqin atrofda hech narsa yo'q» deb aldaydi.

⚠️ TURKUMNI MODEL BERADI, lekin Overpass so'rovini BIZ quramiz.
Model yozgan narsa — ishonchsiz chegara: agar u to'g'ridan-to'g'ri
so'rov matniga qo'yilsa, noto'g'ri (yoki qasddan buzilgan) qator butun
so'rovni o'zgartirib yuborardi. Shuning uchun model faqat `kalit=qiymat`
juftini beradi va u `_TURKUM_RE` bilan tekshiriladi.
"""
import asyncio
import math
import re
from typing import List, Optional

import aiohttp

from core.loader import logger

# Bir vaqtda so'raladigan mirrorlar — hammasi bepul va kalitsiz.
#
# TARTIB O'LCHOVDAN CHIQQAN (2026-09-10, Toshkent). `maps.mail.ru` bir xil
# so'rovga 1.6-4.9 soniyada javob berdi, klassik uchtasi esa 22-40 soniyada
# yoki umuman yiqildi. Shuning uchun u BIRINCHI, qolganlari zaxira.
# O'zbekiston bo'ylab tekshirildi: Samarqandda 14 ta zapravka, Namanganda
# eng yaqin dorixona 247 m, Toshkentda 30 ta bankomat.
#
# ⛔️ `overpass.osm.ch` ATAYLAB YO'Q. U 0.8 soniyada javob beradi — lekin
# faqat Shveytsariya ma'lumotini saqlaydi va O'zbekiston uchun 0 ta natija
# qaytaradi. «Birinchi javob bergani g'olib» poygasida u har safar yutib,
# botga «yaqin atrofda hech narsa yo'q» dedirtirardi. Shu sababli quyida
# BO'SH javob ham g'olib sanalmaydi — mirror qo'shishdan oldin uni
# O'ZBEKISTON koordinatasida sinab ko'ring.
# ponytail: hammasiga birdan so'rov ketadi — trafik kam bo'lgani uchun
# arziydi; yuk oshsa "birinchisi 5s javob bermasa keyingisini qo'sh"
# (hedged request) qilinadi.
OVERPASS_MIRRORS = (
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

# Umumiy vaqt chegarasi. Odatda eng tez mirror 2-5 soniyada javob beradi;
# bu chegara faqat u yiqilib, zaxiralar kutilayotgan holat uchun.
OVERPASS_TIMEOUT = 40

NEARBY_RADIUS_DEFAULT = 3000
NEARBY_RADIUS_MAX = 15000
NEARBY_LIMIT_DEFAULT = 8
NEARBY_LIMIT_MAX = 15

# `amenity=fuel`, `shop=supermarket`, `amenity=charging_station` ...
# Qiymatda bo'sh joy uchraydi (`cuisine=ice cream`), shuning uchun ruxsat
# etilgan, lekin qavs/tirnoq/nuqtali vergul — YO'Q: aynan ular Overpass
# so'rovining tuzilishini buzadigan belgilar.
_TURKUM_RE = re.compile(r"^[a-z_]{1,30}=[A-Za-z0-9_:.\- ]{1,40}$")


class PlacesUnavailable(Exception):
    """Manba javob bermadi — «joy topilmadi» bilan ARALASHTIRMASLIK uchun."""


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Ikki nuqta orasidagi masofa, metrda."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def clean_categories(raw) -> List[str]:
    """Model bergan turkumlardan faqat xavfsiz `kalit=qiymat` larni qoldiradi."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    natija = []
    for x in raw:
        if not isinstance(x, str):
            continue
        x = x.strip()
        if _TURKUM_RE.match(x) and x not in natija:
            natija.append(x)
    return natija[:6]


def build_query(lat: float, lon: float, categories: List[str],
                radius: int, limit: int) -> str:
    """Overpass so'rovi. `nwr` — nuqta, maydon va munosabat birdan.

    ⚠️ `nwr` `node` o'rniga ATAYLAB: zapravka va supermarket OSM'da
    ko'pincha NUQTA emas, MAYDON bo'lib chiziladi. Faqat `node` so'ralganda
    Toshkent markazidan 3 km da 1 ta zapravka chiqdi, `nwr` bilan 3 ta.
    `out center` maydonning markaziy koordinatasini beradi.
    """
    bloklar = "".join(
        f'nwr(around:{radius},{lat},{lon})["{k}"="{v}"];'
        for k, v in (c.split("=", 1) for c in categories)
    )
    ichki = max(10, OVERPASS_TIMEOUT - 10)
    return f"[out:json][timeout:{ichki}];({bloklar});out center {limit * 6};"


def _element_xy(el: dict):
    """Nuqtada `lat/lon`, maydonda `center` bo'ladi."""
    if el.get("lat") is not None and el.get("lon") is not None:
        return el["lat"], el["lon"]
    c = el.get("center") or {}
    if c.get("lat") is not None and c.get("lon") is not None:
        return c["lat"], c["lon"]
    return None, None


def parse_elements(elements, lat: float, lon: float, limit: int) -> List[dict]:
    """Overpass javobini masofa bo'yicha saralangan ro'yxatga aylantiradi.

    ⚠️ NOMSIZ joylar tashlanadi. OSM'da nomsiz nuqtalar ko'p va ular
    javobda «(nomsiz) 340 m» bo'lib chiqardi — bu foydalanuvchiga hech
    narsa bermaydi, faqat ro'yxatni to'ldirib, haqiqiy joyni pastga
    surib yuboradi.
    """
    natija = []
    ko_rilgan = set()
    for el in elements or []:
        teg = el.get("tags") or {}
        nom = (teg.get("name") or teg.get("brand") or "").strip()
        if not nom:
            continue
        y, x = _element_xy(el)
        if y is None:
            continue
        kalit = (nom.lower(), round(y, 4), round(x, 4))
        if kalit in ko_rilgan:
            continue
        ko_rilgan.add(kalit)
        natija.append({
            "name": nom,
            "lat": y,
            "lon": x,
            "distance": round(_haversine(lat, lon, y, x)),
            "kind": teg.get("amenity") or teg.get("shop") or teg.get("tourism") or "",
            "address": " ".join(filter(None, (
                teg.get("addr:street"), teg.get("addr:housenumber")))).strip(),
            "phone": (teg.get("phone") or teg.get("contact:phone") or "").strip(),
            "hours": (teg.get("opening_hours") or "").strip(),
        })
    natija.sort(key=lambda p: p["distance"])
    return natija[:limit]


async def _ask_mirror(session, url: str, query: str) -> Optional[list]:
    async with session.post(url, data={"data": query}) as resp:
        if resp.status != 200:
            raise PlacesUnavailable(f"{url}: HTTP {resp.status}")
        data = await resp.json(content_type=None)
        return data.get("elements") or []


async def find_nearby(lat: float, lon: float, categories: List[str], *,
                      radius: int = NEARBY_RADIUS_DEFAULT,
                      limit: int = NEARBY_LIMIT_DEFAULT) -> List[dict]:
    """Berilgan nuqta atrofidagi joylar, eng yaqinidan boshlab.

    Manba javob bermasa `PlacesUnavailable` ko'tariladi — bo'sh ro'yxat
    EMAS: «yaqin atrofda yo'q» deb aldash eng yomon natija bo'lardi.
    """
    turkumlar = clean_categories(categories)
    if not turkumlar:
        return []
    radius = max(100, min(int(radius or NEARBY_RADIUS_DEFAULT), NEARBY_RADIUS_MAX))
    limit = max(1, min(int(limit or NEARBY_LIMIT_DEFAULT), NEARBY_LIMIT_MAX))
    query = build_query(lat, lon, turkumlar, radius, limit)

    timeout = aiohttp.ClientTimeout(total=OVERPASS_TIMEOUT)
    headers = {"User-Agent": "TramplinBot/1.0 (Telegram bot; OSM Overpass)"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        vazifalar = [asyncio.create_task(_ask_mirror(session, m, query))
                     for m in OVERPASS_MIRRORS]
        elements = None
        bo_sh_keldi = False
        xatolar = []
        try:
            # ⚠️ BO'SH JAVOB G'OLIB EMAS. Mintaqaviy nusxani saqlaydigan
            # mirror (masalan osm.ch) bir zumda "0 ta" deb javob beradi va
            # to'liq bazadagi sekinroq mirrorni yutib ketardi — natijada
            # bot yo'q joydan «hech narsa topilmadi» der edi. Shuning uchun
            # bo'sh javob faqat ESLAB QOLINADI va boshqalari kutiladi.
            qolgan = set(vazifalar)
            while qolgan and elements is None:
                tayyor, qolgan = await asyncio.wait(
                    qolgan, return_when=asyncio.FIRST_COMPLETED)
                for v in tayyor:
                    try:
                        natija = v.result()
                    except Exception as e:
                        xatolar.append(type(e).__name__)
                        continue
                    if natija:
                        elements = natija
                        break
                    bo_sh_keldi = True
        finally:
            for v in vazifalar:
                v.cancel()

    if elements is None and bo_sh_keldi:
        # Hamma javob bergan, lekin hech qayerda joy yo'q — bu HALOL "yo'q".
        return []
    if elements is None:
        logger.warning(f"[NEARBY] hamma mirror yiqildi: {', '.join(xatolar)}")
        raise PlacesUnavailable("Overpass javob bermadi")
    return parse_elements(elements, lat, lon, limit)


# Yo'nalish havolasi. `rtext=~lat,lon` — boshlanish nuqtasi bo'sh, ya'ni
# Yandex foydalanuvchining O'Z joylashuvidan yo'l quradi; `rtt=auto` —
# avtomobilda. Yandex Navigator mintaqada eng ko'p ishlatiladigan ilova,
# havola telefonda o'sha ilovada ochiladi.
ROUTE_URL = "https://yandex.uz/maps/?rtext=~{lat:.5f},{lon:.5f}&rtt=auto"

# Yo'nalish havolasi nechta joy uchun beriladi. ⚠️ Havola ~25 token, 8 ta
# joyning hammasiga bersak modelning ishlatmaydigan narsasiga token
# ketardi — u baribir eng yaqin bittasiga tugma qo'yadi.
ROUTE_LINKS_FOR = 3


def route_url(place: dict) -> str:
    """Joyga yo'nalish havolasi."""
    return ROUTE_URL.format(lat=place["lat"], lon=place["lon"])


def format_places(places: List[dict]) -> str:
    """Model o'qiydigan ixcham ro'yxat.

    Koordinata ATAYLAB beriladi: model javobiga `[xarita:lat,lon,17]`
    yozib, foydalanuvchiga haqiqiy xarita ko'rsatishi uchun.

    ⚠️ YO'NALISH HAVOLASINI KOD QURADI, model emas. Rasm havolalarida
    o'rganilgan dars: modelga URL berilsa, u uni qayta yozib O'LIK
    havolaga aylantiradi. Bu yerda havola tayyor keladi — modelning ishi
    uni [tugma: ...] ichiga AYNAN ko'chirish.
    """
    if not places:
        return "Bu radiusda mos joy topilmadi."
    satrlar = []
    for i, p in enumerate(places, 1):
        qism = [f"{i}. {p['name']} — {p['distance']} m",
                f"koord: {p['lat']:.5f},{p['lon']:.5f}"]
        if p.get("address"):
            qism.append(p["address"])
        if p.get("hours"):
            qism.append(f"ish vaqti: {p['hours']}")
        if p.get("phone"):
            qism.append(f"tel: {p['phone']}")
        if i <= ROUTE_LINKS_FOR:
            qism.append(f"yo'nalish: {route_url(p)}")
        satrlar.append(" | ".join(qism))
    return "\n".join(satrlar)
