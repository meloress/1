"""Yaqin atrofdagi joylarni topish (services/places.py + find_nearby tooli).

Tarmoqqa CHIQMAYDI: Overpass javobi qo'lda yasalgan. Bu ataylab —
test tashqi servis ishlayotganini emas, BIZNING mantiqni tekshiradi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_nearby.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import memory  # noqa: E402
from services import places  # noqa: E402
from services import ai  # noqa: E402

xatolar = []


def check(n, label, cond):
    if cond:
        print(f"[{n}] {label} OK")
    else:
        print(f"[{n}] {label} XATO")
        xatolar.append(label)


# ── 1. TURKUM TEKSHIRUVI — model yozgani ISHONCHSIZ chegara ───────
# Turkum to'g'ridan-to'g'ri Overpass so'roviga qo'yiladi. Qavs, tirnoq
# yoki nuqtali vergul o'tib ketsa, model yozgan qator so'rovning
# TUZILISHINI o'zgartirib yuborardi.
check(1, "oddiy turkum o'tadi",
      places.clean_categories(["amenity=fuel"]) == ["amenity=fuel"])
check(2, "bo'sh joyli qiymat o'tadi (cuisine=ice cream)",
      places.clean_categories(["cuisine=ice cream"]) == ["cuisine=ice cream"])
for yomon in ('amenity=fuel"];out;node["x"="y', "amenity=fuel;out", "a=b)", "=fuel",
              "amenity", "AMENITY=fuel", "amenity=fu'el"):
    check(f"3:{yomon[:18]}", "buzuq turkum rad etiladi",
          places.clean_categories([yomon]) == [])
check(4, "takror va ortiqchasi kesiladi",
      places.clean_categories(["amenity=fuel", "amenity=fuel"] +
                              [f"shop=s{i}" for i in range(9)]) ==
      ["amenity=fuel"] + [f"shop=s{i}" for i in range(5)])
check(5, "matn ham, ro'yxat ham qabul qilinadi",
      places.clean_categories("amenity=atm") == ["amenity=atm"])
check(6, "ro'yxat bo'lmasa bo'sh qaytadi",
      places.clean_categories(None) == [] and places.clean_categories(7) == [])

# ── 2. SO'ROV MATNI ───────────────────────────────────────────────
q = places.build_query(41.3, 69.2, ["amenity=fuel", "shop=supermarket"], 3000, 5)
check(7, "so'rovda ikkala turkum ham bor",
      '["amenity"="fuel"]' in q and '["shop"="supermarket"]' in q)
# ⚠️ `nwr` — zapravka va supermarket OSM'da ko'pincha NUQTA emas,
# MAYDON bo'lib chiziladi. Faqat `node` so'ralganda Toshkent markazidan
# 3 km da 1 ta zapravka chiqqan, `nwr` bilan 3 ta.
check(8, "nwr ishlatiladi (node emas) va markaz so'raladi",
      q.count("nwr(around:3000,41.3,69.2)") == 2 and "out center" in q)

# ── 3. MASOFA ─────────────────────────────────────────────────────
# Toshkent — Samarqand ≈ 270 km.
d = places._haversine(41.2995, 69.2401, 39.6542, 66.9597)
check(9, "masofa to'g'ri hisoblanadi", 260000 < d < 285000)
check(10, "bir nuqtaning o'ziga masofasi nol",
      places._haversine(41.3, 69.2, 41.3, 69.2) < 1)

# ── 4. JAVOBNI O'QISH ─────────────────────────────────────────────
XOM = [
    # Nuqta
    {"type": "node", "lat": 41.3005, "lon": 69.2401,
     "tags": {"name": "Yaqin", "amenity": "fuel", "opening_hours": "24/7"}},
    # Maydon — koordinata `center` ichida
    {"type": "way", "center": {"lat": 41.3200, "lon": 69.2401},
     "tags": {"name": "Uzoq", "amenity": "fuel"}},
    # Nomsiz — tashlanadi
    {"type": "node", "lat": 41.2996, "lon": 69.2401, "tags": {"amenity": "fuel"}},
    # Koordinatasiz — tashlanadi
    {"type": "way", "tags": {"name": "Koordinatasiz"}},
    # Aynan takror
    {"type": "node", "lat": 41.3005, "lon": 69.2401,
     "tags": {"name": "Yaqin", "amenity": "fuel"}},
]
p = places.parse_elements(XOM, 41.2995, 69.2401, 10)
check(11, "maydon `center` dan o'qiladi", any(x["name"] == "Uzoq" for x in p))
# ⚠️ Nomsiz joy foydalanuvchiga hech narsa bermaydi, faqat ro'yxatni
# to'ldirib haqiqiy joyni pastga surib yuboradi.
check(12, "nomsiz va koordinatasiz tashlanadi", len(p) == 2)
check(13, "takror bir marta olinadi",
      sum(1 for x in p if x["name"] == "Yaqin") == 1)
check(14, "eng yaqini birinchi", p[0]["name"] == "Yaqin")
check(15, "masofa metrda va butun", isinstance(p[0]["distance"], int))
check(16, "chegara ishlaydi", len(places.parse_elements(XOM, 41.2995, 69.2401, 1)) == 1)

matn = places.format_places(p)
# Koordinata ATAYLAB beriladi — modelga [xarita:lat,lon,16] yozish uchun.
check(17, "ro'yxatda koordinata bor", "41.30050,69.24010" in matn)
check(18, "ish vaqti ko'rsatiladi", "24/7" in matn)

# ── 5. «YO'Q» BILAN «JAVOB BERMADI» — BOSHQA-BOSHQA ──────────────
# Eng muhim tekshiruv. Manba yiqilganda «yaqin atrofda hech narsa yo'q»
# deyish — tekshirilmagan xulosani ishonch bilan aytish, ya'ni aldash.
async def _yiqilgan(*a, **k):
    raise places.PlacesUnavailable("test")


asl_find = ai.find_nearby
try:
    ai.find_nearby = _yiqilgan
    javob = asyncio.run(ai._run_nearby_task((41.3, 69.2), {"categories": ["amenity=fuel"]}))
finally:
    ai.find_nearby = asl_find
check(19, "manba yiqilganda TEXNIK sabab aytiladi", "nosozlik" in javob.lower())
check(20, "manba yiqilganda 'hech narsa yo'q' DEYILMAYDI",
      "DEMANG" in javob and "topilmadi" not in javob.split("DEMANG")[0])


async def _bo_sh(*a, **k):
    return []


try:
    ai.find_nearby = _bo_sh
    javob2 = asyncio.run(ai._run_nearby_task((41.3, 69.2), {"categories": ["amenity=fuel"]}))
finally:
    ai.find_nearby = asl_find
check(21, "rostdan bo'sh bo'lsa radiusni kengaytirish taklif qilinadi",
      "topilmadi" in javob2 and "kengaytir" in javob2)

# Joylashuvsiz — model uni so'rashi kerak
check(22, "joylashuvsiz chaqiruv Location so'rashga yo'naltiradi",
      "Location" in asyncio.run(ai._run_nearby_task(None, {"categories": ["amenity=fuel"]})))
check(23, "buzuq turkum tarmoqqa CHIQMAYDI",
      "kalit=qiymat" in asyncio.run(
          ai._run_nearby_task((41.3, 69.2), {"categories": ["); drop"]})))

# ── 6. XOTIRA: TTL ────────────────────────────────────────────────
memory.forget_location(-777)
check(24, "joylashuv yo'qda None", memory.recent_location(-777) is None)
memory.remember_location(-777, 41.3, 69.2)
check(25, "eslab qoladi", memory.recent_location(-777) == (41.3, 69.2))
# ⚠️ TTL qisqa va bu ataylab: odam mashinada ketyapti, yarim soatdan
# keyin u boshqa joyda. Eskirgan koordinata bo'yicha «eng yaqin»
# aytish — noto'g'ri javobni ishonch bilan aytish.
lat, lon, ts = memory.last_locations[-777]
memory.last_locations[-777] = (lat, lon, ts - memory.LOCATION_TTL - 1)
check(26, "TTL o'tgach unutiladi", memory.recent_location(-777) is None)
memory.remember_location(-777, 41.3, 69.2)
memory.forget_location(-777)
check(27, "/new tozalaydi", memory.recent_location(-777) is None)

# ── 7. TOOL FAQAT JOYLASHUV BORIDA BIRIKTIRILADI ─────────────────
# Bu shart — butun imkoniyatning token narxi. Joylashuvsiz sxema
# umuman yuborilmaydi, ya'ni oddiy suhbatga 0 token qo'shiladi.
yoq = ai._capability_manifest(file_task_enabled=True, image_enabled=True,
                              reminder_enabled=True, memory_enabled=True,
                              nearby_enabled=False)["content"]
check(28, "joylashuvsiz manifest uni MAVJUD EMAS deydi",
      "find_nearby" in yoq.split("NOT available")[1])
check(29, "manifest joylashuv so'rashni aytadi", "send" in yoq and "location" in yoq)

# ── 8. DISPATCH `else` DAN YUQORIDA ──────────────────────────────
# ⚠️ Bare `else` har qanday notanish tool nomini VEB QIDIRUVGA
# yo'naltiradi — `find_nearby` undan pastda qolsa, "eng yaqin
# zapravka" jimgina DuckDuckGo so'roviga aylanardi.
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "services", "ai.py"), encoding="utf-8").read()
check(30, "find_nearby dispatchi bare else dan YUQORIDA",
      src.index('elif call_item.name == "find_nearby"')
      < src.index('            else:\n                search_ran = True'))

# ── 9. JOYLASHUV SUHBATGA XABAR BO'LIB KIRADI ────────────────────
# ⚠️ JONLI XATO: avval joylashuvga tayyor kartochka bilan javob
# berilardi. Kartochka TARIXGA TUSHMAYDI, ya'ni model uchun ko'rinmas —
# u ekranda o'zining «lokatsiyangizni yuboring» degan gapini, keyin
# «Zapravka» degan javobni ko'rardi va yana «lokatsiyangizni yuboring»
# derdi. Endi joylashuv oddiy matn yo'lidan o'tadi.
msrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "handlers", "messages.py"), encoding="utf-8").read()
loc_fn = msrc.split("async def handle_location")[1].split("async def ")[0]
check(31, "joylashuv AI navbatiga qo'shiladi", "_queue_for_ai" in loc_fn)
check(32, "tayyor kartochka bilan javob berilmaydi", "message.answer" not in loc_fn)
check(33, "koordinata eslab qolinadi", "remember_location" in loc_fn)
# Koordinata tarixga YOZILMAYDI: u yerda qolib, ertaga «eng yaqin»
# savoliga eskirgan joy bo'yicha javob berilardi.
check(34, "tarixdagi izohda koordinata yo'q",
      "lat" not in msrc.split("_LOCATION_NOTE = ")[1].splitlines()[0])
# handle_text ham AYNAN shu yordamchidan o'tadi — ikkita alohida yo'l
# bo'lsa, biri kvota yoki navbatsiz qolardi.
check(35, "handle_text ham shu yordamchidan o'tadi",
      msrc.split("async def handle_text")[1].split("async def ")[0].count("_queue_for_ai") == 1)

print("─" * 55)
if xatolar:
    print(f"❌ {len(xatolar)} ta tekshiruv yiqildi:")
    for x in xatolar:
        print(f"   • {x}")
    sys.exit(1)
print("✅ nearby: barcha tekshiruvlar o'tdi (35/35).")
