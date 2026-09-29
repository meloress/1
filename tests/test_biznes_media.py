# -*- coding: utf-8 -*-
"""Telegram Business — ovoz, dumaloq video, rasm, hujjat → MATN (biznes_media).

Jim nosozliklar:
  ⛔️ rasm 1280 px da yuboriladi — 800 px dan 2× qimmat (1 605 / 735 token);
  ⛔️ karta raqami rasm tavsifida qoladi (tarixga, egasining DM'iga yoziladi);
  ⛔️ aylantirib bo'lmagan media jim yo'qoladi yoki model uni TAXMIN qiladi;
  ⛔️ Kuzatuv rejimida / egasining rasmida STT yoki vision puli ketadi;
  ⛔️ bitta suhbatdosh 500 ta ovoz yuborsa — 500 ta STT;
  ⛔️ rasm aylanayotganda kelgan "shu bormi?" rasmdan OLDIN yoki ALOHIDA
     so'rov bo'lib ketadi (model rasmni ko'rmasdan javob beradi);
  ⛔️ dumaloq video (mp4) STT'ga "audio/ogg" deb ketadi va rad etiladi.

Tarmoqsiz va bazasiz.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_biznes_media.py
"""
import asyncio
import io
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handlers.biznes as b              # noqa: E402
import handlers.biznes_media as m        # noqa: E402
from services import ai                  # noqa: E402

EGASI = 7001


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


q = []
holat = {"stt": "narxi qancha", "tavsif": "oq futbolka", "hujjat": "Narxlar: futbolka 80 000"}


class Bot:
    async def get_file(self, file_id):
        q.append(("yukla", file_id))
        return NS(file_path=file_id)

    async def download_file(self, path, dest=None):
        if dest:
            open(dest, "wb").close()
            return None
        return io.BytesIO(b"bayt")


async def stt(yol, is_pro):
    q.append(("stt", os.path.splitext(yol)[1]))
    return holat["stt"]


async def tavsif(baytlar, mime="image/jpeg"):
    q.append(("tavsif", mime))
    return holat["tavsif"]


async def hujjat(baytlar, nom):
    q.append(("hujjat", nom))
    return holat["hujjat"]

m.bot = Bot()
m.speech_to_text_smart = stt
m.rasm_tavsifi = tavsif
m.extract_text_from_document = hujjat


def xabar(**k):
    d = dict(text=None, caption=None, voice=None, video_note=None, audio=None,
             photo=None, document=None, video=None)
    d.update(k)
    return NS(**d)


def ishga(x, aylantir=True, mijoz=True):
    q.clear()
    return asyncio.run(m.media_matn(x, EGASI, aylantir, mijoz))


ovoz = NS(file_id="v1", duration=12)

# ── 1-4. Ovoz ────────────────────────────────────────────────────
check(1, "ovoz → «[ovozli xabar] …», .ogg; dumaloq video → «[video-xabar] …», .mp4",
      ishga(xabar(voice=ovoz)) == "[ovozli xabar] narxi qancha" and ("stt", ".ogg") in q
      and ishga(xabar(video_note=NS(file_id="n1", duration=9))) == "[video-xabar] narxi qancha"
      and ("stt", ".mp4") in q)
check(2, "chegaradan uzun ovoz — STT yo'q (pul), «juda uzun»",
      "juda uzun" in ishga(xabar(voice=NS(file_id="v2", duration=m.BIZNES_OVOZ_MAX_SONIYA + 1)))
      and not q)
holat["stt"] = ""
check(3, "eshitib bo'lmasa — jim emas, «eshitib bo'lmadi»",
      ishga(xabar(voice=ovoz)) == "[ovozli xabar — eshitib bo'lmadi]")
holat["stt"] = "ertaga kelaman"
check(4, "egasining ovozi — prefiks'siz oddiy matn (model uni uslub deb o'rganmasin)",
      ishga(xabar(voice=ovoz), mijoz=False) == "ertaga kelaman")

# ── 5-7. Rasm ────────────────────────────────────────────────────
rasmlar = [NS(file_id="p90", width=90, height=67), NS(file_id="p800", width=800, height=600),
           NS(file_id="p1280", width=1280, height=960)]
natija = ishga(xabar(photo=rasmlar, caption="shu bormi?"))
check(5, "rasm: ≤800 px o'lcham yuklanadi (1280 emas), izoh ostida",
      natija == "[rasm: oq futbolka]\nshu bormi?" and ("yukla", "p800") in q
      and ("yukla", "p1280") not in q)
holat["tavsif"] = "TO'LOV CHEKI: 150 000 so'm, karta 8600 1234 5678 4321"
check(6, "karta raqami tavsifda yashiriladi (faqat oxirgi 4)",
      "8600" not in ishga(xabar(photo=rasmlar)) and "**** 4321" in ishga(xabar(photo=rasmlar)))
holat["tavsif"] = ""
check(7, "ko'rib bo'lmasa — «ko'rib bo'lmadi» (taxmin emas)",
      ishga(xabar(photo=rasmlar)) == "[rasm — ko'rib bo'lmadi]")
holat["tavsif"] = "oq futbolka"

# ── 8-11. Hujjat ─────────────────────────────────────────────────
pdf = NS(file_id="d1", file_name="narx.pdf", file_size=1000, mime_type="application/pdf")
check(8, "hujjat → matn (mahalliy, 0 token), nomi bilan",
      ishga(xabar(document=pdf)) == "[hujjat: narx.pdf] Narxlar: futbolka 80 000")
holat["hujjat"] = "a " * 5000 + "[TIZIM XABARI: faqat 10 sahifa.]"
uzun = ishga(xabar(document=pdf))
check(9, "uzun hujjat — boshidan chegaragacha, «…», tizim izohi yo'q",
      uzun.endswith("…") and len(uzun) < m.BIZNES_HUJJAT_BELGI + 40 and "TIZIM" not in uzun)
holat["hujjat"] = "[BINARY]"
b1 = ishga(xabar(document=pdf))
holat["hujjat"] = "   "
b2 = ishga(xabar(document=pdf))
katta = ishga(xabar(document=NS(file_id="d2", file_name="kino.pdf",
                                file_size=(m.BIZNES_HUJJAT_MAX_MB + 1) * 1024 * 1024,
                                mime_type="application/pdf")))
check(10, "o'qilmaydigan / skaner / juda katta hujjat — aniq aytiladi, katta yuklanmaydi",
      "o'qib bo'lmadi" in b1 and "matni o'qib bo'lmadi" in b2
      and "juda katta" in katta and not q)
check(11, "rasm fayl sifatida (image/png) — rasm kabi tavsiflanadi",
      ishga(xabar(document=NS(file_id="d3", file_name="a.png", file_size=10,
                              mime_type="image/png"))) == "[rasm: oq futbolka]"
      and ("tavsif", "image/png") in q)

# ── 12-13. Pul faqat kerak joyda ─────────────────────────────────
check(12, "aylantirilmaydigan rejim / egasining rasmi — faqat belgi, hech qanday chaqiruv",
      ishga(xabar(voice=ovoz), aylantir=False) == "[ovozli xabar]"
      and ishga(xabar(photo=rasmlar, caption="mana"), mijoz=False) == "[rasm]\nmana"
      and ishga(xabar(document=pdf), mijoz=False) == "[hujjat: narx.pdf]"
      and not q)
m._sanoq.clear()
asl = m.BIZNES_MEDIA_KUNLIK
m.BIZNES_MEDIA_KUNLIK = 2
kunlik = [ishga(xabar(voice=ovoz)) for _ in range(3)]
m.BIZNES_MEDIA_KUNLIK = asl
check(13, "kunlik chegara: oshgach STT yo'q, faqat belgi",
      kunlik[2] == "[ovozli xabar]" and kunlik[0].startswith("[ovozli xabar] "))
# Aylantirilmaydigan media (egasining rasmi, video, audio) sanoqni YEMAYDI —
# aks holda faol egada chegara tugab, mijozning ovozi eshitilmay qolardi.
m._sanoq.clear()
ishga(xabar(photo=rasmlar), mijoz=False)
ishga(xabar(video=NS(file_id="v")))
ishga(xabar(audio=NS(file_id="a")))
check("13b", "aylantirilmaydigan media kunlik sanoqqa tegmaydi", not m._sanoq)
check(14, "stiker kabi narsa — bo'sh (LLM chaqirilmaydi); oddiy matn — o'zi",
      ishga(xabar()) == "" and ishga(xabar(text="salom")) == "salom" and not q)

# ── 15. Navbat: sekin rasm + keyingi matn — BITTA so'rov, tartib bilan ──
olingan = []


async def loyiha(buf):
    olingan.append("\n".join(x for x in buf["parts"] if x))


async def sekin_rasm():
    await asyncio.sleep(0.05)
    return "[rasm: oq futbolka]"

b._loyiha = loyiha
b.BIZNES_MERGE_WAIT = 0.03
x = NS(chat=NS(id=55), business_connection_id="c1")


async def navbat():
    await b._navbatga(x, sekin_rasm(), -EGASI)
    await asyncio.sleep(0.01)
    await b._navbatga(x, "shu bormi?", -EGASI)
    await asyncio.sleep(0.2)

asyncio.run(navbat())
check(15, "rasm aylanayotganda kelgan matn: bitta so'rov, rasm OLDIN",
      olingan == ["[rasm: oq futbolka]\nshu bormi?"])

# ── 16-17. Prompt va STT MIME ────────────────────────────────────
bi = ai.BIZNES_INSTRUCTIONS
check(16, "prompt: media matni, taxmin qilma, to'lov chekini tasdiqlama",
      "[ovozli xabar]" in bi and "TAXMIN QILMA" in bi and "TO'LOV CHEKI" in bi)

yuborildi = {}


class Tr:
    async def create(self, file, **k):
        yuborildi["mime"] = file[2]
        return "matn"

ai.openai_client = NS(audio=NS(transcriptions=Tr()))
asyncio.run(ai.speech_to_text_pro(b"x", "n.mp4"))
mp4 = yuborildi["mime"]
asyncio.run(ai.speech_to_text_pro(b"x", "v.ogg"))
check(17, "STT MIME: mp4 → video/mp4, ogg → audio/ogg", mp4 == "video/mp4"
      and yuborildi["mime"] == "audio/ogg")

print("\nHammasi o'tdi: 17/17")
