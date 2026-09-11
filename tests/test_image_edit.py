"""Rasmni tahrirlash (edit_image) — jimgina buziladigan joylar.

Bu asbobning uchta xususiyati bor va uchalasi ham noto'g'ri bo'lsa
DASTUR YIQILMAYDI, shunchaki natija yomon bo'ladi — ya'ni testsiz
sezilmaydi:

  1) `elif call_item.name == "edit_image"` dispatch'dagi bare `else`
     dan OLDIN turishi shart. Aks holda «fonni o'zgartir» jimgina
     DuckDuckGo so'roviga aylanadi (generate_image'da aynan shu xato
     uchun alohida test bor).
  2) Manba rasm MODEL PARAMETRI BO'LMASLIGI shart — u chatdan olinadi.
     Sxemaga rasm/url maydoni qo'shilsa, model uni o'ylab topadi.
  3) `size="auto"` va `input_fidelity="high"` — ikkalasi ham natijaning
     o'ziga tegadi: birinchisisiz vertikal selfie kvadratga kesiladi,
     ikkinchisisiz odamning yuzi boshqa odamnikiga aylanadi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_image_edit.py
"""
import asyncio
import base64
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import INTERNAL_TOOL_NAMES  # noqa: E402
from services import ai  # noqa: E402

xatolar = []


def check(n, label, cond):
    if cond:
        print(f"[{n}] {label} OK")
    else:
        print(f"[{n}] {label} XATO")
        xatolar.append(label)


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG = b"\xff\xd8\xff" + b"0" * 64
WEBP = b"RIFF" + b"1234" + b"WEBP" + b"0" * 64
PDF = b"%PDF-1.7" + b"0" * 64


# ── 1. Manba baytlari — ishonchsiz chegara ───────────────────────
check(1, "PNG taniladi", ai._is_image_bytes(PNG))
check(2, "JPEG taniladi", ai._is_image_bytes(JPEG))
check(3, "WEBP taniladi", ai._is_image_bytes(WEBP))
# ⚠️ Fayl NOMI emas, baytlari hal qiladi. «rasm.png» nomli PDF
# asbobni yoqib yuborardi va OpenAI xatosi foydalanuvchiga
# tushunarsiz uzr bo'lib qaytardi.
check(4, "«.png» nomli PDF rad etiladi", not ai._is_image_bytes(PDF))
check(5, "bo'sh fayl rad etiladi", not ai._is_image_bytes(b""))
check(6, "None rad etiladi", not ai._is_image_bytes(None))
check(7, "hajm chegarasi bor",
      not ai._is_image_bytes(PNG + b"0" * ai.EDIT_IMAGE_MAX_SIZE))


# ── 2. Sxema: rasm model orqali O'TMAYDI ─────────────────────────
maydonlar = set(ai._EDIT_IMAGE_TOOL["parameters"]["properties"])
check(8, "sxemada faqat `prompt` bor", maydonlar == {"prompt"})
check(9, "sxemada rasm/url/fayl maydoni YO'Q",
      not any(k in str(maydonlar).lower()
              for k in ("image", "url", "file", "b64")))
# Sxemada `size` ham yo'q: tahrirda o'lcham kirish rasmidan olinadi,
# modelga tanlov berish faqat kesilgan natijaga olib kelardi.
check(10, "sxemada `size` yo'q — o'lcham manbadan olinadi",
      "size" not in maydonlar)


# ── 3. Dispatch: bare `else` dan OLDIN ───────────────────────────
manba = inspect.getsource(ai)
check(11, "edit_image dispatch shoxi bor",
      'elif call_item.name == "edit_image":' in manba)
check(12, "u web-qidiruv `else` idan OLDIN turadi",
      manba.index('elif call_item.name == "edit_image":')
      < manba.rindex("            else:\n"))


# ── 4. Nomi sirqib chiqmaydi ─────────────────────────────────────
check(13, "edit_image INTERNAL_TOOL_NAMES da",
      "edit_image" in INTERNAL_TOOL_NAMES)
check(14, "javobdan nomi tozalanadi",
      "edit_image" not in ai.strip_internal_names(
          "men edit_image tool'ini chaqiraman"))


# ── 5. Bepul tarifda umuman biriktirilmaydi ──────────────────────
# `edit_enabled` HAR DOIM `image_enabled` ga bog'langan bo'lishi
# shart: aks holda bepul foydalanuvchi rasm yuborsa tahrirlash
# ochilib ketardi va bu to'g'ridan-to'g'ri pul.
check(15, "edit_enabled image_enabled'ga bog'langan",
      "edit_enabled = image_enabled and _is_image_bytes(" in manba)


# ── 6. Haqiqiy chaqiruv: qaysi parametrlar ketadi ────────────────
chaqiruv: dict = {}


class _Nat:
    def __init__(self):
        self.data = [type("D", (), {
            "b64_json": base64.b64encode(b"TAHRIRLANGAN").decode()})()]


async def _soxta_edit(**kw):
    chaqiruv.update(kw)
    return _Nat()


async def _soxta_generate(**kw):
    chaqiruv.update(kw)
    chaqiruv["_yaratish"] = True
    return _Nat()


class _Kvota:
    """DailyQuota o'rniga — yechildimi va muvaffaqiyat belgilandimi."""

    def __init__(self):
        self.yechildi = False
        self.muvaffaqiyat = False

    async def ensure_charged(self):
        self.yechildi = True
        return True

    def mark_success(self):
        self.muvaffaqiyat = True


async def _sinov():
    ai.openai_client.images.edit = _soxta_edit
    ai.openai_client.images.generate = _soxta_generate

    fayllar: list = []
    kvota = _Kvota()
    natija = await ai._run_image_task(
        "make the background a winter forest, keep the face unchanged",
        "1024x1024", quota=kvota, output_files=fayllar, round_num=1,
        source=PNG)

    check(16, "tahrirlash images.edit ga ketdi",
          "_yaratish" not in chaqiruv)
    check(17, "manba baytlari uzatildi", chaqiruv["image"][1] == PNG)
    # ⚠️ Ikkalasi ham natijaning SIFATIGA tegadi, xatoga emas —
    # olib tashlansa hech narsa yiqilmaydi, faqat rasm buziladi.
    check(18, "size=auto — vertikal rasm kvadratga kesilmaydi",
          chaqiruv.get("size") == "auto")
    check(19, "input_fidelity=high — yuz o'zgarib ketmaydi",
          chaqiruv.get("input_fidelity") == "high")
    check(20, "natija chaqiruvchining ro'yxatiga qo'yildi",
          len(fayllar) == 1 and fayllar[0][1] == b"TAHRIRLANGAN")
    check(21, "fayl nomi .png", fayllar[0][0].endswith(".png"))
    check(22, "kvota yechildi va muvaffaqiyat belgilandi",
          kvota.yechildi and kvota.muvaffaqiyat)
    check(23, "modelga BAJARILDI qaytdi va 'tahrirlandi' deyildi",
          natija.startswith("BAJARILDI") and "tahrirlandi" in natija)

    # Manbasiz — eski yo'l buzilmaganini tasdiqlaymiz.
    chaqiruv.clear()
    fayllar2: list = []
    natija2 = await ai._run_image_task(
        "a red fox", "1024x1536", quota=_Kvota(), output_files=fayllar2,
        round_num=1)
    check(24, "manbasiz chaqiruv hamon images.generate ga ketadi",
          chaqiruv.get("_yaratish") is True)
    check(25, "chizishda model bergan o'lcham saqlanadi",
          chaqiruv.get("size") == "1024x1536")
    check(26, "chizishda 'yaratildi' deyiladi", "yaratildi" in natija2)

    # Limit tugagan bo'lsa rasm umuman chaqirilmaydi.
    class _Tugagan(_Kvota):
        async def ensure_charged(self):
            return False

    chaqiruv.clear()
    fayllar3: list = []
    natija3 = await ai._run_image_task(
        "x", "1024x1024", quota=_Tugagan(), output_files=fayllar3,
        round_num=1, source=PNG)
    check(27, "limit tugasa API umuman chaqirilmaydi", chaqiruv == {})
    check(28, "limitda fayl qo'shilmaydi", fayllar3 == [])
    check(29, "limitda modelga TO'XTA qaytadi", natija3.startswith("TO'XTA"))


asyncio.run(_sinov())


# ── 7. Rasm izohi modelni TO'G'RI quvurga yuboradi ───────────────
# ⚠️ Umumiy fayl izohi «tahrirlash uchun run_python_sandbox
# ishlating» deydi. Rasmga nisbatan bu noto'g'ri: «fonni o'zgartir»
# python kodiga aylanib qolardi.
from handlers.messages import pending_file_note  # noqa: E402

izoh = pending_file_note("rasm.jpg")
check(30, "rasm izohi edit_image ni nomlaydi", "edit_image" in izoh)
check(31, "rasm izohida sandbox BIRINCHI o'rinda emas",
      izoh.index("edit_image") < izoh.index("run_python_sandbox"))
check(32, "rasmda nima borligini so'rasa tool kerak emasligi aytiladi",
      "hech qanday tool kerak emas" in izoh)
# Hujjat izohi o'zgarmagan bo'lishi kerak.
check(33, "hujjat izohi hamon sandbox haqida",
      "edit_image" not in pending_file_note("hisobot.xlsx"))


print("-" * 55)
if xatolar:
    print(f"{len(xatolar)} ta tekshiruv yiqildi:")
    for x in xatolar:
        print("   -", x)
    sys.exit(1)
print("image_edit: barcha tekshiruvlar o'tdi (33/33).")
