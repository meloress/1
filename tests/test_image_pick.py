"""Rasm qidiruvi: nomzad yig'ish, takror kesish, ko'rib tanlash, tarix.

JONLI NOSOZLIK (foydalanuvchi shikoyati):
  «BMW 540i rasmini top»            -> 4 ta rasm keldi
  «tuning qilingan body kit bilan»  -> O'SHA 4 ta rasm
  ... 6-7 marta takrorlandi         -> har safar O'SHA 4 ta
  «birinchi rasmdagi mashina rangi qanaqa?» -> bilmaydi

Sabablari uchta edi va uchalasi shu yerda tekshiriladi:
  1) Commons'da tuning rasmi yo'q, so'rov esa Commons javob bergunicha
     QISQARARDI va asl «BMW 540i» ga tushardi (ddgs zaxira bo'lgani
     uchun hech qachon ishlamasdi);
  2) takror faqat URL bo'yicha kesilardi — «... (2) (3) (4)» bitta
     suratning kadrlari o'tib ketardi;
  3) `[rasm:N]` tarixdan butunlay o'chirilardi, ya'ni model o'zi nima
     yuborganini bilmasdi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_image_pick.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import memory  # noqa: E402
from core.config import SEARCH_IMAGE_MAX, SEARCH_IMAGE_DEFAULT  # noqa: E402
from services import ai  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# ── 1. Takror kadrlar kesiladi ───────────────────────────────────
check(1, "«(2)» qo'shimchasi sarlavha o'zagini o'zgartirmaydi",
      ai._title_stem("BMW 540i (G30) China (2)")
      == ai._title_stem("BMW 540i (G30) China"))
check(2, "boshqa rasm boshqa o'zak",
      ai._title_stem("BMW 540i tuned") != ai._title_stem("BMW 540i"))

xom = [
    {"image": "https://a/1.jpg", "title": "BMW 540i (G30) China", "source": "c"},
    {"image": "https://a/2.jpg", "title": "BMW 540i (G30) China (2)", "source": "c"},
    {"image": "https://a/3.jpg", "title": "BMW 540i (G30) China (3)", "source": "c"},
    {"image": "https://a/4.jpg", "title": "BMW 540i SX body kit", "source": "d"},
]
nomzad, aloqasiz, takror = ai._clean_candidates(xom, [], set())
check(3, "bir suratning kadrlari bittaga tushadi", len(nomzad) == 2)
check(4, "takrorlar sanaladi", takror == 2)

# Allaqachon yuborilgan rasm qaytmaydi — foydalanuvchi shikoyatining o'zagi.
nomzad2, _, takror2 = ai._clean_candidates(xom, [], {"https://a/1.jpg"})
check(5, "avval yuborilgan havola tashlanadi",
      all(c["url"] != "https://a/1.jpg" for c in nomzad2))
check(6, "o'rniga keyingi kadr o'tadi", len(nomzad2) == 2 and takror2 == 2)


# ── 2. Model javobini o'qish ─────────────────────────────────────
check(7, "oddiy JSON o'qiladi",
      ai._parse_pick_json('{"chosen":[{"n":2,"desc":"qora sedan"}]}', 4)
      == [(2, "qora sedan")])
check(8, "matn ichidagi JSON ham o'qiladi",
      ai._parse_pick_json('Mana: {"chosen":[{"n":1,"desc":"a"}]} tayyor', 3)
      == [(1, "a")])
check(9, "chegaradan tashqari raqam tashlanadi",
      ai._parse_pick_json('{"chosen":[{"n":9,"desc":"x"},{"n":1,"desc":"y"}]}', 3)
      == [(1, "y")])
check(10, "takroriy raqam bir marta olinadi",
      len(ai._parse_pick_json('{"chosen":[{"n":1},{"n":1}]}', 3)) == 1)
check(11, "buzuq javobda bo'sh qaytadi",
      ai._parse_pick_json("javob yo'q", 3) == [])
check(12, "model hech nima tanlamasa bo'sh",
      ai._parse_pick_json('{"chosen":[]}', 3) == [])


# ── 3. Tanlov: model ko'radi va tavsif yozadi ────────────────────
CANDS = [{"url": f"https://a/{i}.jpg", "title": f"rasm {i}", "source": "s"}
         for i in range(1, 6)]


class SoxtaJavob:
    output_text = '{"chosen":[{"n":4,"desc":"kulrang sedan, yon tomondan"},' \
                  '{"n":2,"desc":"oq sedan"}]}'
    usage = None


async def _sinov_tanlov():
    ai.openai_client.responses.create = lambda **k: _q(SoxtaJavob())
    natija = await ai._pick_images_with_vision(CANDS, "tuning qilingani", 3)
    check(13, "model tanlagan tartib saqlanadi",
          [r["url"] for r in natija] == ["https://a/4.jpg", "https://a/2.jpg"])
    check(14, "tavsif rasmga biriktiriladi",
          natija[0]["desc"] == "kulrang sedan, yon tomondan")

    # Kerakligidan ko'p tanlansa kesiladi.
    natija = await ai._pick_images_with_vision(CANDS, "x", 1)
    check(15, "so'ralgan sondan oshmaydi", len(natija) == 1)

    # ⚠️ Ko'rish bosqichi yiqilsa RASM YO'QOLMASLIGI kerak — eski
    # xatti-harakat (birinchilarini olish) qaytadi.
    def _yiqil(**k):
        raise RuntimeError("model yo'q")
    ai.openai_client.responses.create = _yiqil
    natija = await ai._pick_images_with_vision(CANDS, "x", 2)
    check(16, "tanlov yiqilsa birinchilari qaytadi",
          [r["url"] for r in natija] == ["https://a/1.jpg", "https://a/2.jpg"])

    # Model "mos rasm yo'q" desa — aloqasiz rasm yuborgandan ko'ra bo'sh.
    class Bosh:
        output_text = '{"chosen":[]}'
        usage = None
    ai.openai_client.responses.create = lambda **k: _q(Bosh())
    check(17, "mos rasm bo'lmasa hech narsa yuborilmaydi",
          await ai._pick_images_with_vision(CANDS, "x", 3) == [])


def _q(value):
    async def _inner():
        return value
    return _inner()


asyncio.run(_sinov_tanlov())


# ── 4. Tarix: model o'zi nima yuborganini biladi ─────────────────
rasmlar = [{"url": "u1", "title": "BMW 540i", "desc": "kulrang sedan"},
           {"url": "u2", "title": "BMW 540i SX", "desc": "oq, body kit bilan"}]
tarix = ai.image_tokens_to_history("Mana [rasm:1] va [rasm:2] rasmlari.", rasmlar)
check(18, "belgi o'rnida tavsif qoladi",
      "kulrang sedan" in tarix and "oq, body kit bilan" in tarix)
check(19, "xom belgi tarixda qolmaydi",
      "[rasm:1]" not in tarix and "[rasm:2]" not in tarix)
check(20, "galereya belgisi ham tavsiflanadi",
      "kulrang sedan" in ai.image_tokens_to_history("[rasmlar]", rasmlar))
check(21, "rasm bo'lmasa belgi shunchaki o'chadi",
      ai.image_tokens_to_history("salom [rasm:1]", []).strip() == "salom")
check(22, "yaroqsiz raqam yiqitmaydi",
      "[rasm:9]" not in ai.image_tokens_to_history("[rasm:9]", rasmlar))


# ── 5. Katalog va sonlar ─────────────────────────────────────────
katalog = ai.format_image_catalog(rasmlar)
check(23, "katalogda tavsif ko'rinadi", "kulrang sedan" in katalog)
check(24, "katalogda URL YO'Q (token va o'lik havola)",
      "u1" not in katalog and "http" not in katalog)

check(25, "standart son 3", SEARCH_IMAGE_DEFAULT == 3)
check(26, "yuqori chegara 10 — «10 ta rasm topib ber» ishlaydi",
      SEARCH_IMAGE_MAX == 10)

# 5 tadan ko'p rasm slideshow'ga tushadi (ilgari bu shox o'lik edi:
# chegara 4 bo'lgani uchun hech qachon bajarilmasdi).
kop = [{"url": f"u{i}", "title": f"t{i}"} for i in range(1, 8)]
check(27, "5+ rasm slideshow bo'ladi",
      "<tg-slideshow>" in ai.embed_images("[rasmlar]", kop))
check(28, "2-4 rasm kollaj bo'ladi",
      "<tg-collage>" in ai.embed_images("[rasmlar]", kop[:3]))


# ── 6. Yuborilgan rasm xotirasi ──────────────────────────────────
memory.forget_sent_images(77)
memory.remember_sent_images(77, rasmlar)
check(29, "yuborilgan havolalar eslab qolinadi",
      memory.recent_sent_images(77) == {"u1", "u2"})
memory.forget_sent_images(77)
check(30, "/new bilan tozalanadi", memory.recent_sent_images(77) == set())

print("\nHammasi o'tdi: 30/30")
