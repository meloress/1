"""Namoz vaqtlari: hisob, rasmiy jadval, joy aniqlash, asbob va karta.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_namoz.py

Tarmoqqa murojaat qilmaydi: namoz-vaqti.uz jadvali, geocoder va Telegram
o'rniga soxta funksiya qo'yiladi.
"""
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _manba import kod
from core.config import INTERNAL_TOOL_NAMES
from services import ai, namoz, obhavo
from services import vidjet as v
from handlers import messages as msg
from handlers import profile as pf

ILDIZ = Path(__file__).parent.parent
failures = []


def check(n, label, cond):
    if cond:
        print(f"[{n}] {label} OK")
    else:
        print(f"[{n}] {label} XATO")
        failures.append(label)


def daq(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


# ─────────────────────────────────────────────────────────────
# 1-3. HISOB RASMIY TOSHKENT JADVALIGA TUSHADIMI
# ─────────────────────────────────────────────────────────────
# namoz-vaqti.uz, Toshkent shahri, 2026 (har oyning 1 va 16-kuni). To'liq
# yil (2190 vaqt) ham ±1 ichida — 2026-11-10 da tekshirilgan.
RASMIY = {
    "01.01.2026": "06:23 07:49 12:27 15:23 17:07 18:30",
    "16.01.2026": "06:22 07:46 12:33 15:38 17:23 18:43",
    "01.02.2026": "06:13 07:35 12:37 15:57 17:42 19:00",
    "16.02.2026": "05:58 07:17 12:37 16:15 18:01 19:17",
    "01.03.2026": "05:40 06:58 12:35 16:29 18:16 19:32",
    "16.03.2026": "05:15 06:34 12:32 16:43 18:33 19:49",
    "01.04.2026": "04:46 06:07 12:27 16:56 18:52 20:08",
    "16.04.2026": "04:18 05:42 12:23 17:06 19:08 20:28",
    "01.05.2026": "03:52 05:21 12:20 17:16 19:24 20:50",
    "16.05.2026": "03:28 05:04 12:19 17:25 19:40 21:12",
    "01.06.2026": "03:10 04:52 12:21 17:33 19:54 21:32",
    "16.06.2026": "03:04 04:49 12:24 17:39 20:01 21:44",
    "01.07.2026": "03:08 04:54 12:27 17:42 20:04 21:45",
    "16.07.2026": "03:23 05:04 12:29 17:40 19:58 21:34",
    "01.08.2026": "03:44 05:18 12:29 17:32 19:44 21:13",
    "16.08.2026": "04:05 05:33 12:27 17:19 19:25 20:48",
    "01.09.2026": "04:27 05:49 12:23 17:01 19:00 20:18",
    "16.09.2026": "04:45 06:04 12:18 16:41 18:35 19:50",
    "01.10.2026": "05:01 06:20 12:13 16:19 18:09 19:23",
    "16.10.2026": "05:17 06:36 12:09 15:57 17:45 18:59",
    "01.11.2026": "05:34 06:54 12:07 15:36 17:22 18:38",
    "16.11.2026": "05:50 07:12 12:08 15:21 17:07 18:25",
    "01.12.2026": "06:05 07:29 12:12 15:13 16:59 18:19",
    "16.12.2026": "06:17 07:42 12:19 15:14 16:59 18:21",
}
eng_katta, aniq = 0, 0
for kun, qator in RASMIY.items():
    k, o, y = map(int, kun.split("."))
    bizniki = namoz.hisobla(date(y, o, k), *namoz.TOSHKENT, namoz.TOSHKENT_TZ)
    for a, b in zip(bizniki, qator.split()):
        eng_katta = max(eng_katta, abs(daq(a) - daq(b)))
        aniq += a == b
check(1, f"o'z hisobimiz rasmiy Toshkent jadvalidan ±1 daqiqa ({aniq}/144 aynan)",
      eng_katta <= 1 and aniq >= 110)

# Qutb kuni: Tromsø, dekabr — quyosh chiqmaydi.
check(2, "qutb kunida jadval yo'q (None), xato emas",
      namoz.hisobla(date(2026, 12, 20), 69.65, 18.96, "Europe/Oslo") is None)
# Yozgi yuqori kenglik: London, iyun — quyosh 15,5° gacha tushmaydi.
lon = namoz.hisobla(date(2026, 6, 21), 51.5, -0.13, "Europe/London")
check(3, "yuqori kenglikda yozda ham Bomdod/Xufton bor va tartib to'g'ri",
      lon is not None and daq(lon[0]) < daq(lon[1]) < daq(lon[2]) < daq(lon[3])
      < daq(lon[4]) < daq(lon[5]))

# ─────────────────────────────────────────────────────────────
# 4-7. SHAHAR NOMI VA FARQ
# ─────────────────────────────────────────────────────────────
check(4, "nom shakllari: ‘/’/ʻ, «shahri», katta harf, inglizcha, ruscha",
      namoz.uz_shahar("Farg‘ona shahri") == ("Farg'ona", -10)
      and namoz.uz_shahar("FARGʻONA") == ("Farg'ona", -10)
      and namoz.uz_shahar("Fergana") == ("Farg'ona", -10)
      and namoz.uz_shahar("Нукус") == ("Nukus", 39)
      and namoz.uz_shahar("Samarqand, O'zbekiston") == ("Samarqand", 9)
      and namoz.uz_shahar("Chirchiq") is None and namoz.uz_shahar("") is None)
check(5, "uzunlik farqi — rasmiy jadvaldagi bilan bir xil (Nukus, Andijon, Buxoro)",
      namoz.uzunlik_farqi(59.6058) == 39 and namoz.uzunlik_farqi(72.3507) == -12
      and namoz.uzunlik_farqi(64.4307) == 19)


async def _geo_tushmasin(joy):
    raise AssertionError("jadvaldagi shahar geocoder'ga bormasligi kerak")

namoz_geo_asl = obhavo.joy_top
obhavo.joy_top = _geo_tushmasin
try:
    jadvalda = asyncio.run(namoz.joy_ol("Farg‘ona"))
    geo_yoq = True
except AssertionError:
    geo_yoq = False
check(6, "jadvaldagi shahar geocoder'ga BORMAYDI (u «Farg‘ona»ni 14 daqiqa adashtirgan)",
      geo_yoq and jadvalda == (("r", -10), "Farg'ona"))


async def _geo(joy):
    return {"Chirchiq": {"nom": "Chirchiq", "mamlakat": "O‘zbekiston", "lat": 41.47,
                         "lon": 69.58, "tz": "Asia/Tashkent", "cc": "UZ",
                         "viloyat": "Toshkent viloyati"},
            "Makka": {"nom": "Makka", "mamlakat": "Saudiya Arabistoni", "lat": 21.4266,
                      "lon": 39.8256, "tz": "Asia/Riyadh", "cc": "SA", "viloyat": ""},
            "Yomon": {"nom": "Yomon", "mamlakat": "", "lat": 1, "lon": 1, "tz": "../etc",
                      "cc": "XX", "viloyat": ""}}[joy]

obhavo.joy_top = _geo
ch = asyncio.run(namoz.joy_ol("Chirchiq"))
mk = asyncio.run(namoz.joy_ol("Makka"))
try:
    asyncio.run(namoz.joy_ol("Yomon"))
    yomon_tz = False
except obhavo.XizmatYoq:
    yomon_tz = True
check(7, "jadvalda yo'q O'zbekiston joyi — taxminiy (t); chet el — o'z koordinatasi (a)",
      ch == (("t", -1), "Chirchiq, Toshkent viloyati")
      and mk == (("a", 21.4266, 39.8256, "Asia/Riyadh"), "Makka, Saudiya Arabistoni")
      and yomon_tz)

# ─────────────────────────────────────────────────────────────
# 8-11. RASMIY JADVAL (KESH) VA HOLAT
# ─────────────────────────────────────────────────────────────
_KUN = "05:44 07:05 12:07 15:27 17:12 18:30".split()


class _Javob:
    def __init__(self, d, status=200):
        self.d, self.status = d, status

    async def json(self, content_type=None):
        return self.d

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


so_rovlar = []


def _sessiya(javob):
    class S:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, url, **k):
            so_rovlar.append(url)
            if isinstance(javob, Exception):
                raise javob
            return _Javob(javob)
    return S


def _oy(times):
    return {"meta": {"offset_min": 0}, "period_table": [
        {"date": f"{k:02d}.11.2026", "times": dict(zip(namoz._KALITLAR, times))}
        for k in range(1, 31)]}


asl_sessiya = namoz.aiohttp.ClientSession
namoz.aiohttp.ClientSession = _sessiya(_oy(_KUN))
namoz._KESH.clear(); namoz._XATO.clear()
r1 = asyncio.run(namoz.toshkent_kuni(date(2026, 11, 10)))
r2 = asyncio.run(namoz.toshkent_kuni(date(2026, 11, 11)))
check(8, "rasmiy jadval oyiga BIR so'rov (keyingi kun keshdan)",
      r1 == (_KUN, True) and r2[1] is True and len(so_rovlar) == 1
      and "toshkent-shahri/oylik/2026-11" in so_rovlar[0])

namoz.aiohttp.ClientSession = _sessiya(_oy(["5:44"] + _KUN[1:]))
namoz._KESH.clear(); namoz._XATO.clear()
buzuq = asyncio.run(namoz.toshkent_kuni(date(2026, 11, 10)))
so_rovlar.clear()
namoz.aiohttp.ClientSession = _sessiya(OSError("tarmoq yo'q"))
namoz._KESH.clear(); namoz._XATO.clear()
yiq1 = asyncio.run(namoz.toshkent_kuni(date(2026, 11, 10)))
yiq2 = asyncio.run(namoz.toshkent_kuni(date(2026, 11, 10)))
check(9, "buzuq shakl yoki sayt yo'q — o'z hisobimiz; yiqilgan sayt har so'rovda kutilmaydi",
      buzuq[1] is False and buzuq[0][0] != "5:44" and yiq1[1] is False and yiq1[0]
      and len(so_rovlar) == 1 and yiq2[1] is False)

namoz.aiohttp.ClientSession = _sessiya(_oy(_KUN))
namoz._KESH.clear(); namoz._XATO.clear()
nk = asyncio.run(namoz.holat(("r", 39), "Nukus"))
check(10, "Nukus = Toshkent + 39 daqiqa (rasmiy usul), holat 1 KB dan kichik",
      nk["v"] == ["06:23", "07:44", "12:46", "16:06", "17:51", "19:09"]
      and nk["m"] == "r" and nk["q"] == "r:39" and nk["u"] == 300
      and len(v.namoz_holati(nk).encode()) < 1024)

namoz.aiohttp.ClientSession = _sessiya(OSError("yo'q"))
namoz._KESH.clear(); namoz._XATO.clear()
hk = asyncio.run(namoz.holat(("r", 0), "Toshkent"))
check(11, "sayt yo'q — vaqtlar baribir bor, manba «h» va matnda aytiladi",
      hk["m"] == "h" and len(hk["v"]) == 6 and "javob bermadi" in namoz.matn(hk))
namoz.aiohttp.ClientSession = _sessiya(_oy(_KUN))
namoz._KESH.clear(); namoz._XATO.clear()

# ─────────────────────────────────────────────────────────────
# 12-14. KARTA SO'ROVI (telefondan — ishonchsiz)
# ─────────────────────────────────────────────────────────────
check(12, "so'rov tekshiruvi: diapazon, mintaqa nomi, noma'lum tur",
      namoz.sorov_oqi("r:39") == ("r", 39) and namoz.sorov_oqi("t:-1") == ("t", -1)
      and namoz.sorov_oqi("a:21.4,39.8,Asia/Riyadh") == ("a", 21.4, 39.8, "Asia/Riyadh")
      and all(namoz.sorov_oqi(q) is None for q in (
          "r:500", "r:abc", "x:1", "a:91,0,Asia/Tashkent", "a:41,69,../../etc/passwd",
          "a:41,69,Foo/Bar", "a:41,69", "", "r:")))

chaqiruvlar = []


def _api_soxta(natija, outcome=None):
    async def f(method, payload, outcome=None, **k):
        chaqiruvlar.append((method, payload))
        if outcome is not None and natija is None and _api_soxta.o:
            outcome.append(_api_soxta.o)
        return natija
    _api_soxta.o = outcome
    return f


msg._telegram_api_request = _api_soxta(True)
for data in ("n:r:39", "n:a:21.4266,39.8256,Asia/Riyadh", "n:a:999,1,Asia/Riyadh", "n:zzz"):
    asyncio.run(pf.vidjet_sorovi({"id": data, "from": {"id": 7}, "data": data}))
jv = {p["widget_query_id"]: p for _, p in chaqiruvlar}
check(13, "\"n:\" so'roviga yangi kun; buzuq so'rovga ma'lumotsiz (lekin javob bor)",
      json.loads(jv["n:r:39"]["data"])["v"][0] == "06:23"
      and len(json.loads(jv["n:a:21.4266,39.8256,Asia/Riyadh"]["data"])["v"]) == 6
      and "data" not in jv["n:a:999,1,Asia/Riyadh"] and "data" not in jv["n:zzz"]
      and len(jv) == 4)

check(14, "karta HTML 4 KB'ga sig'adi; izohda 6 vaqt; zaxirada modelga ko'rsatma yo'q",
      v.sigadimi(v.namoz_html()) and all(t in v.namoz_izohi(nk) for t in nk["v"])
      and all(t in v.namoz_matni(nk) for t in nk["v"])
      and "ayting" not in v.namoz_matni(nk) and "ayting" not in v.namoz_izohi(nk))

# ─────────────────────────────────────────────────────────────
# 15-19. ASBOB
# ─────────────────────────────────────────────────────────────
out = []
dm = asyncio.run(ai._run_namoz_task({"joy": "Nukus"}, out))
guruh = asyncio.run(ai._run_namoz_task({"joy": "Nukus"}, None))
check(15, "shaxsiy chat: karta navbatda, javob qisqa; guruh: 6 vaqt modelga to'liq",
      out and out[0]["tur"] == "namoz" and "1-2 gap" in dm and "06:23" in dm
      and "17:51" in guruh and "kartasi" not in guruh)
check(16, "saharlik = Bomdod, iftor = Shom — modelga aniq aytiladi",
      "Saharlik" in guruh and "iftor — Shom" in guruh)


async def _geo_yoq(joy):
    raise obhavo.JoyTopilmadi(joy)


async def _geo_ishlamaydi(joy):
    raise obhavo.XizmatYoq("timeout")

obhavo.joy_top = _geo_yoq
yoq = asyncio.run(ai._run_namoz_task({"joy": "Qwerty"}, []))
obhavo.joy_top = _geo_ishlamaydi
ish = asyncio.run(ai._run_namoz_task({"joy": "Qwerty"}, []))
check(17, "\"joy topilmadi\" va \"xizmat yo'q\" — ikki xil javob, vaqt o'ylab topilmaydi",
      "topilmadi" in yoq and "texnik" in ish and "O'YLAB TOPMANG" in ish)

obhavo.joy_top = lambda joy: _geo_qutb()


async def _geo_qutb():
    return {"nom": "Tromsø", "mamlakat": "Norvegiya", "lat": 69.65, "lon": 18.96,
            "tz": "Europe/Oslo", "cc": "NO", "viloyat": ""}

asl_holat = namoz.holat


async def _holat_qutb(joy, nom):
    return None

namoz.holat = _holat_qutb
qutb = asyncio.run(ai._run_namoz_task({"joy": "Tromsø"}, []))
namoz.holat = asl_holat
obhavo.joy_top = namoz_geo_asl
check(18, "qutb kuni — ochiq aytiladi, karta yo'q", "qutb" in qutb)

aik = kod(ILDIZ / "services" / "ai.py")
check(19, "namoz_vaqti: dispatch `else` dan OLDIN, nom INTERNAL_TOOL_NAMES'da, manifestda",
      0 < aik.index('elif call_item.name == "namoz_vaqti"')
      < aik.index("            else:\n                search_ran = True")
      and "namoz_vaqti" in INTERNAL_TOOL_NAMES and '_NAMOZ_TOOL["name"]' in aik)

# ─────────────────────────────────────────────────────────────
# 20. KARTA YUBORISH (rad etilsa — matn)
# ─────────────────────────────────────────────────────────────
chaqiruvlar.clear()
msg._telegram_api_request = _api_soxta(None, msg.OUTCOME_REJECTED)
qaytdi = asyncio.run(msg.karta_yubor(555, {"tur": "namoz", "d": nk}, None))
check(20, "namoz kartasi rad etilsa — 6 vaqt matn bilan qaytadi",
      chaqiruvlar[-1][0] == "sendWidget" and chaqiruvlar[-1][1]["allow_queries"] is True
      and "Shom: 17:51" in (qaytdi or ""))

namoz.aiohttp.ClientSession = asl_sessiya

# ─────────────────────────────────────────────────────────────
print("─" * 55)
if failures:
    print(f"❌ {len(failures)} ta tekshiruv yiqildi:")
    for f in failures:
        print(f"   • {f}")
    sys.exit(1)
print("✅ Namoz vaqti tekshiruvlari — hammasi o'tdi")
