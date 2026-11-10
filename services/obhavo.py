"""Ob-havo — Open-Meteo (bepul, kalitsiz): https://open-meteo.com

`ob_havo` asbobi shu yerdan HAQIQIY raqamlarni oladi. Ilgari ob-havo savoli
veb-qidiruvga ketardi: bir raund + sahifa matni (~2 000 token), raqamlar esa
model sahifadan qanday o'qisa shunday edi.

⚠️ "Joy topilmadi" va "xizmat javob bermadi" — ikki XIL javob (`find_nearby`
dagi qoida): ikkinchisini "bunday shahar yo'q" deb aytish yolg'on bo'lardi.
"""
import re
import time
from datetime import date

import aiohttp

_GEO = "https://geocoding-api.open-meteo.com/v1/search"
_PROGNOZ = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = aiohttp.ClientTimeout(total=10)
JOY_UZUN = 80


class JoyTopilmadi(Exception):
    pass


class XizmatYoq(Exception):
    pass


# WMO kodi → (o'zbekcha holat, belgi turi). Turlar vidjet ikonkasi bilan bir:
# q quyosh, qb qisman bulut, b bulut, t tuman, y yomg'ir, qr qor, m momaqaldiroq.
_WMO = {
    0: ("Ochiq osmon", "q"), 1: ("Asosan ochiq", "q"), 2: ("Qisman bulutli", "qb"),
    3: ("Bulutli", "b"), 45: ("Tuman", "t"), 48: ("Qirovli tuman", "t"),
    51: ("Mayda yomg'ir", "y"), 53: ("Mayda yomg'ir", "y"), 55: ("Kuchli mayda yomg'ir", "y"),
    56: ("Muzli yomg'ir", "y"), 57: ("Muzli yomg'ir", "y"),
    61: ("Yengil yomg'ir", "y"), 63: ("Yomg'ir", "y"), 65: ("Kuchli yomg'ir", "y"),
    66: ("Muzli yomg'ir", "y"), 67: ("Muzli yomg'ir", "y"),
    71: ("Yengil qor", "qr"), 73: ("Qor", "qr"), 75: ("Kuchli qor", "qr"), 77: ("Qor donalari", "qr"),
    80: ("Jala", "y"), 81: ("Jala", "y"), 82: ("Kuchli jala", "y"),
    85: ("Qor yog'ishi", "qr"), 86: ("Kuchli qor", "qr"),
    95: ("Momaqaldiroq", "m"), 96: ("Do'lli momaqaldiroq", "m"), 99: ("Do'lli momaqaldiroq", "m"),
}
_HAFTA = ("Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya")


def _holat(kod) -> tuple:
    return _WMO.get(int(kod or 0), ("Noma'lum", "b"))


def toza_joy(joy) -> str:
    """Model yozgan joy nomi — faqat so'rov parametri bo'ladi, lekin baribir
    qisqa va bir qatorli: ko'p qatorli "nom" so'rovni buzmasin."""
    return re.sub(r"\s+", " ", str(joy or "")).strip()[:JOY_UZUN]


async def _get(url: str, params: dict) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
            async with s.get(url, params=params) as r:
                if r.status != 200:
                    raise XizmatYoq(f"HTTP {r.status}")
                return await r.json()
    except XizmatYoq:
        raise
    except Exception as e:
        raise XizmatYoq(type(e).__name__) from e


async def joy_top(joy: str) -> dict:
    nom = toza_joy(joy)
    if not nom:
        raise JoyTopilmadi(joy)
    d = await _get(_GEO, {"name": nom, "count": 1, "language": "uz"})
    r = (d.get("results") or [None])[0]
    if not r:
        raise JoyTopilmadi(nom)
    return {"nom": r.get("name") or nom, "mamlakat": r.get("country") or "",
            "lat": float(r["latitude"]), "lon": float(r["longitude"])}


async def prognoz(lat: float, lon: float, nom: str = "") -> dict:
    """Karta holati (vidjet kalitlari bilan, 1024 baytdan ancha kichik)."""
    d = await _get(_PROGNOZ, {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "wind_speed_10m,weather_code,is_day",
        "hourly": "temperature_2m,weather_code,is_day", "forecast_hours": 13,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
    })
    try:
        c, h, k = d["current"], d["hourly"], d["daily"]
        holat, tur = _holat(c["weather_code"])
        tun = not c.get("is_day", 1)
        soatlar = []
        for i in range(2, 13, 2):       # keyingi 12 soat, 2 soatdan
            t = _holat(h["weather_code"][i])[1]
            soatlar.append([h["time"][i][11:16], t, round(h["temperature_2m"][i]),
                            0 if h["is_day"][i] else 1])
        kunlar = []
        for i, kun in enumerate(k["time"][:3]):
            nomi = ("Bugun", "Ertaga")[i] if i < 2 else _HAFTA[date.fromisoformat(kun).weekday()]
            kunlar.append([nomi, _holat(k["weather_code"][i])[1],
                           round(k["temperature_2m_max"][i]), round(k["temperature_2m_min"][i])])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise XizmatYoq(f"javob shakli: {e}") from e
    return {"j": nom, "v": c["time"][11:16], "h": round(c["temperature_2m"]),
            "s": holat, "k": tur, "tun": 1 if tun else 0,
            "f": round(c["apparent_temperature"]), "w": round(c["wind_speed_10m"]),
            "nm": round(c["relative_humidity_2m"]),
            "s2": soatlar, "k3": kunlar, "c": [round(lat, 2), round(lon, 2)],
            "t": int(time.time())}


async def ob_havo(joy: str) -> dict:
    j = await joy_top(joy)
    nom = j["nom"] + (f", {j['mamlakat']}" if j["mamlakat"] else "")
    return await prognoz(j["lat"], j["lon"], nom)


def matn(d: dict) -> str:
    """Odam o'qiydigan qisqa ko'rinish: model uchun ham, vidjet chizilmagan
    joyda zaxira uchun ham — raqamlar bitta manbadan."""
    soat = ", ".join(f"{s[0]} {s[2]}°" for s in d["s2"])
    kun = "; ".join(f"{x[0]}: {x[3]}…{x[2]}°" for x in d["k3"])
    return (f"🌤 {d['j']} — {d['v']} holatiga\n"
            f"Hozir {d['h']}°, {d['s'].lower()} (his qilinadi {d['f']}°). "
            f"Shamol {d['w']} km/soat, namlik {d['nm']}%.\n"
            f"Keyingi soatlar: {soat}.\nKunlar: {kun}.")
