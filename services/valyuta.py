"""Valyuta kursi — O'zbekiston Markaziy banki (cbu.uz, bepul, kalitsiz).

`valyuta` asbobi shu yerdan RASMIY kursni oladi va konvertatsiyani KOD
hisoblaydi — model arifmetikasi kafolat emas. Ilgari "dollar kursi"
veb-qidiruvga ketardi: bir raund + sahifa matni, raqam esa qaysi saytdan
o'qilganiga bog'liq edi.

⚠️ Bu MARKAZIY BANK kursi. Banklarning sotib olish/sotish kursi undan farq
qiladi — modelga shuni aytish shart, aks holda u "bankda shu narxda
olasiz" deb aldardi.
⚠️ `Nominal`: IDR, IRR, VND 10 tadan kotirovka qilinadi — e'tiborsiz
qoldirilsa natija 10 barobar xato.
"""
import re
import time

import aiohttp

_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
_TIMEOUT = aiohttp.ClientTimeout(total=10)
# Kurs kuniga bir marta o'zgaradi — har so'rovga Markaziy bankni urmaslik.
KESH_SONIYA = 1800
STANDART = ("USD", "EUR", "RUB")
KOD_MAX = 6

_kesh: dict = {"t": 0.0, "kurslar": None}


class XizmatYoq(Exception):
    pass


async def _yukla() -> dict:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as s:
            async with s.get(_URL) as r:
                if r.status != 200:
                    raise XizmatYoq(f"HTTP {r.status}")
                d = await r.json(content_type=None)
    except XizmatYoq:
        raise
    except Exception as e:
        raise XizmatYoq(type(e).__name__) from e
    kurslar = {}
    try:
        for x in d:
            kurslar[x["Ccy"]] = {
                "kod": x["Ccy"], "nom": x.get("CcyNm_UZ") or x["Ccy"],
                "kurs": float(x["Rate"]), "nominal": int(x.get("Nominal") or 1),
                "farq": float(x.get("Diff") or 0), "sana": x.get("Date", ""),
            }
    except (KeyError, TypeError, ValueError) as e:
        raise XizmatYoq(f"javob shakli: {e}") from e
    if "USD" not in kurslar:
        raise XizmatYoq("USD yo'q")
    return kurslar


async def kurslar() -> dict:
    if _kesh["kurslar"] and time.time() - _kesh["t"] < KESH_SONIYA:
        return _kesh["kurslar"]
    k = await _yukla()
    _kesh.update(t=time.time(), kurslar=k)
    return k


def toza_kodlar(kodlar) -> list:
    """Model yozgan kodlar: faqat 3 harfli lotin, takrorsiz, ko'pi bilan 6."""
    if isinstance(kodlar, str):
        kodlar = re.split(r"[\s,;]+", kodlar)
    out = []
    for k in kodlar or []:
        k = str(k).strip().upper()
        if k in ("SOM", "SUM", "UZS", "SO'M"):
            continue
        if re.fullmatch(r"[A-Z]{3}", k) and k not in out:
            out.append(k)
    return out[:KOD_MAX]


def bir_birlik(v: dict) -> float:
    """1 birlik valyuta necha so'm (Nominal hisobga olingan)."""
    return v["kurs"] / v["nominal"]


def hisobla(k: dict, summa: float, dan: str, ga: str) -> float | None:
    """`summa` `dan` → `ga`. UZS — so'm. Noma'lum kod — None."""
    def somda(kod):
        return 1.0 if kod == "UZS" else (bir_birlik(k[kod]) if kod in k else None)
    a, b = somda(dan), somda(ga)
    if a is None or b is None:
        return None
    return summa * a / b


def son(x: float) -> str:
    """12 345 678,9 — o'zbekcha yozuv (bo'sh joy, vergul). 1 dan kichik son
    4 xonagacha: IRR 0,006 so'm — 2 xonada "0,01" (yolg'on) yoki "0" bo'lardi."""
    aniqlik = 2 if abs(x) >= 1 else 4
    s = f"{x:,.{aniqlik}f}".replace(",", " ").replace(".", ",")
    return s.rstrip("0").rstrip(",") if "," in s else s


def _nom(v: dict) -> str:
    # Markaziy bank ba'zi nomlarni BOSH harflarda beradi ("EVRO").
    return v["nom"].capitalize() if v["nom"].isupper() else v["nom"]


def holat(k: dict, kodlar: list) -> dict:
    """Vidjet holati: {"d": sana, "r": [[kod, nom, 1 birlik so'mda, farq], ...]}."""
    qatorlar = [[c, _nom(k[c]), round(bir_birlik(k[c]), 4), round(k[c]["farq"] / k[c]["nominal"], 4)]
                for c in kodlar if c in k]
    return {"d": k["USD"]["sana"], "r": qatorlar, "t": int(time.time())}


def matn(k: dict, kodlar: list) -> str:
    satrlar = [f"Markaziy bank rasmiy kursi ({k['USD']['sana']}):"]
    for c in kodlar:
        v = k[c]
        o = son(abs(v["farq"] / v["nominal"]))
        belgi = "=" if o == "0" else "▲" if v["farq"] > 0 else "▼"
        satrlar.append(f"1 {c} ({_nom(v)}) = {son(bir_birlik(v))} so'm ({belgi}"
                       + ("" if o == "0" else f" {o}") + ")")
    return "\n".join(satrlar)
