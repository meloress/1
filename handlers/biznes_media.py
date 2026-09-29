# -*- coding: utf-8 -*-
"""Telegram Business — ovoz, dumaloq video, rasm, hujjat → MATN.

Hammasi BITTA yo'lga tushadi: media matnga aylanadi va oddiy matn oqimidan
o'tadi (3 s debounce, JSON qaror, Bilim, Uslub — eval'dan o'tgan yagona yo'l).
Tarixga ham shu matn yoziladi: keyin "o'sha rasm" nima ekanini model biladi,
egasi esa qoralamada bot nimani tushunganini ko'radi.

Xarajat (botda bor narsalar qayta ishlatiladi):
  • ovoz / dumaloq video — `speech_to_text_smart` (gpt-4o-mini-transcribe),
    `BIZNES_OVOZ_MAX_SONIYA` dan uzuni eshitilmaydi;
  • rasm — `rasm_tavsifi` (mini model — bepul grantning 10× katta chelagi),
    ≤ `RASM_MAX_TOMON` px o'lcham: 800 px = 735 token, 1280 px = 1 605
    (o'lchangan, 2026-09-28). Javob modeli rasmni emas, 1-3 gap matnni o'qiydi;
  • hujjat — `extract_text_from_document` (mahalliy, 0 token), boshidan
    `BIZNES_HUJJAT_BELGI` belgi;
  • egasining rasmi/hujjati tavsiflanmaydi — u nima yuborganini o'zi biladi;
  • Kuzatuv/Buyruq rejimida aylantirilmaydi — faqat belgi ("[rasm]").
Aylantirib bo'lmasa — jim emas: "[ovozli xabar — eshitib bo'lmadi]" matni
oqimga tushadi, prompt esa mazmunni taxmin qilmaslikni aytadi.
"""
import os
import re
import tempfile
from datetime import date

from aiogram.types import Message

from core.config import (BIZNES_HUJJAT_BELGI, BIZNES_HUJJAT_MAX_MB,
                         BIZNES_MEDIA_KUNLIK, BIZNES_OVOZ_MAX_SONIYA)
from core.loader import bot, logger
from services.ai import extract_text_from_document, rasm_tavsifi, speech_to_text_smart

RASM_MAX_TOMON = 800

# Kuniga egasi bo'yicha aylantirishlar soni. Bitta suhbatdosh 500 ta ovoz
# yuborsa — 500 ta STT emas. ponytail: RAM, qayta ishga tushsa nolga tushadi.
_sanoq: dict = {}

# Karta raqami tavsifda qolmasin (model ko'pincha o'zi yashiradi — bu kafolat).
_KARTA_RE = re.compile(r"\b(?:\d[ -]?){12,15}(\d{4})\b")
_TIZIM_RE = re.compile(r"\[TIZIM XABARI:[^\]]*\]")


def media_bormi(message: Message) -> bool:
    return any(getattr(message, k, None) for k in
               ("voice", "video_note", "audio", "photo", "document", "video"))


def _ruxsat(egasi: int) -> bool:
    bugun = date.today()
    for eski in [k for k in _sanoq if k[1] != bugun]:
        _sanoq.pop(eski, None)          # kechagi sanoqlar RAMda qolmasin
    kalit = (egasi, bugun)
    if _sanoq.get(kalit, 0) >= BIZNES_MEDIA_KUNLIK:
        return False
    _sanoq[kalit] = _sanoq.get(kalit, 0) + 1
    return True


async def _yukla(file_id: str) -> bytes:
    fayl = await bot.get_file(file_id)
    return (await bot.download_file(fayl.file_path)).read()


async def _ovoz(file_id: str, davom: int, belgi: str, kengaytma: str) -> str:
    if davom > BIZNES_OVOZ_MAX_SONIYA:
        return f"[{belgi}, {davom // 60} daqiqa — juda uzun, eshitilmadi]"
    yol = os.path.join(tempfile.gettempdir(), f"bz_{file_id[-24:]}{kengaytma}")
    try:
        fayl = await bot.get_file(file_id)
        await bot.download_file(fayl.file_path, yol)
        matn = (await speech_to_text_smart(yol, is_pro=True) or "").strip()
    except Exception as e:
        logger.warning(f"[BIZNES] ovoz o'qilmadi: {e}")
        matn = ""
    finally:
        try:
            os.remove(yol)
        except OSError:
            pass
    return f"[{belgi}] {matn}" if matn else f"[{belgi} — eshitib bo'lmadi]"


async def _rasm(baytlar: bytes, mime: str = "image/jpeg") -> str:
    tavsif = _KARTA_RE.sub(r"**** \1", await rasm_tavsifi(baytlar, mime))
    return f"[rasm: {tavsif}]" if tavsif else "[rasm — ko'rib bo'lmadi]"


async def _hujjat(message: Message) -> str:
    h = message.document
    nom = (h.file_name or "fayl")[:80]
    if (h.file_size or 0) > BIZNES_HUJJAT_MAX_MB * 1024 * 1024:
        return f"[hujjat: {nom} — juda katta, o'qilmadi]"
    try:
        baytlar = await _yukla(h.file_id)
    except Exception as e:
        logger.warning(f"[BIZNES] hujjat yuklanmadi: {e}")
        return f"[hujjat: {nom} — o'qib bo'lmadi]"
    if (h.mime_type or "").startswith("image/"):
        # Siqilmagan rasm fayl sifatida yuborilgan — rasm kabi.
        return await _rasm(baytlar, h.mime_type)
    matn = await extract_text_from_document(baytlar, nom)
    if matn.startswith(("[BINARY]", "[XATOLIK]")):
        return f"[hujjat: {nom} — o'qib bo'lmadi]"
    matn = " ".join(_TIZIM_RE.sub("", matn).split())
    if not matn:
        # Skanerlangan PDF: matn o'rniga rasm. OCR — qimmat, taxmin — xavfli.
        return f"[hujjat: {nom} — matni o'qib bo'lmadi]"
    qisqa = matn[:BIZNES_HUJJAT_BELGI]
    return f"[hujjat: {nom}] {qisqa}{'…' if len(matn) > len(qisqa) else ''}"


async def media_matn(message: Message, egasi: int, aylantir: bool,
                     mijoz: bool = True) -> str:
    """Xabarning matn ko'rinishi (izoh bilan). Media yo'q bo'lsa — matn/izoh,
    stiker kabi narsa — "" (LLM chaqirilmaydi, AUDIT 4.1).

    `aylantir` — Yordamchi/Avtomat, o'qish huquqi va Pro. `mijoz=False` —
    egasi: faqat ovoz aylantiriladi (bot uning javobini bilishi kerak),
    rasm/hujjat — belgi.
    """
    izoh = message.caption or ""
    if message.text:
        return message.text
    if not media_bormi(message):
        return izoh
    # ⚠️ Sanoq FAQAT haqiqatan aylantiriladigan media uchun yechiladi.
    # Ilgari tur tekshiruvidan oldin yechilardi: egasining rasmi/hujjati,
    # audio va video (hech qachon aylantirilmaydi) ham kunlik chegarani
    # yeb, mijozning ovozi «[ovozli xabar]» bo'lib qolardi.
    aylanadi = bool(message.voice or message.video_note
                    or (mijoz and (message.photo or message.document)))
    ol = aylantir and aylanadi and _ruxsat(egasi)
    if message.voice or message.video_note:
        ovoz = message.voice or message.video_note
        belgi = "ovozli xabar" if message.voice else "video-xabar"
        qism = (await _ovoz(ovoz.file_id, ovoz.duration or 0, belgi,
                            ".ogg" if message.voice else ".mp4")
                if ol else f"[{belgi}]")
        if not mijoz and qism.startswith(f"[{belgi}] "):
            # Egasining gapi tarixga oddiy matn bo'lib — model uni o'z
            # javob uslubi deb "[ovozli xabar]" yozishni o'rganmasin.
            qism = qism[len(belgi) + 3:]
    elif message.photo:
        if ol and mijoz:
            mos = [p for p in message.photo
                   if max(p.width, p.height) <= RASM_MAX_TOMON] or message.photo[:1]
            try:
                qism = await _rasm(await _yukla(mos[-1].file_id))
            except Exception as e:
                logger.warning(f"[BIZNES] rasm yuklanmadi: {e}")
                qism = "[rasm — ko'rib bo'lmadi]"
        else:
            qism = "[rasm]"
    elif message.document:
        qism = (await _hujjat(message) if ol and mijoz
                else f"[hujjat: {(message.document.file_name or 'fayl')[:80]}]")
    elif message.audio:
        qism = "[audio fayl]"
    else:
        qism = "[video]"
    return "\n".join(x for x in (qism, izoh) if x)
