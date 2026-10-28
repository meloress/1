# -*- coding: utf-8 -*-
"""Business «Bilimga qo'shaymi?» — fakt ajratish sifati (JONLI model, qo'lda).

⚠️ `test_*.py` EMAS: haqiqiy OpenAI chaqiradi, natija tasodifiy. Umumiy test
to'plamiga kirmaydi. `_BIZNES_FAKT_PROMPT` o'zgarganda OLDIN va KEYIN.

Eng qimmat xato — OLMASLIK kerak bo'lgan narsani fakt deb olish: egasi
«✅ Qo'shish»ni o'ylamay bossa, «sizga 45 ming» bot nomidan HAMMA mijozga
narx bo'lib ketadi. Shuning uchun ikki raqam alohida:
  noto'g'ri — olinmasligi kerak bo'lgan juftlikdan fakt chiqdi (0 bo'lishi shart);
  topildi   — doimiy faktlarning nechtasi taklif qilindi (yuqori bo'lgani yaxshi).

Bazaga tegmaydi. Lokal kalit yaroqsiz bo'lsa (CLAUDE.md):
    PYTHONIOENCODING=utf-8 railway run python tests/eval_bilim.py [--takror N]
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handlers.biznes as b              # noqa: E402
from services import ai                  # noqa: E402

BILIM = ("Kiyim do'koni «Oq ko'ylak». Futbolka 80 000 so'm, ko'ylak 150 000 so'm. "
         "Ish vaqti 9:00-21:00.")

# (mijoz savoli, egasining o'zi yozgan javobi, fakt bo'lishi kerakmi)
H = [
    ("yetkazib berasizmi?", "Ha, Toshkent bo'ylab 20 ming, 1 kunda yetkazamiz", True),
    ("click bilan to'lasa bo'ladimi", "Ha, Click va Payme bor, naqd ham olamiz", True),
    ("qanaqa razmerlar bor", "S dan XXL gacha hammasi bor", True),
    ("manzilingiz qayerda", "Chilonzor 9-kvartal, Korzinka yonida", True),
    ("qaytarib bersa bo'ladimi", "Ha, 3 kun ichida chek bilan almashtirib beramiz", True),
    ("chegirma bormi", "Sizga 45 mingga beraman aka, doimiy mijozimsiz", False),
    ("buyurtmam qachon keladi", "Ertaga kechgacha olib boramiz", False),
    ("futbolka necha pul", "80 ming", False),                     # bilimda bor
    ("hozir do'kondamisiz", "hozir yo'qman, 1 soatdan keyin kelaman", False),
    ("Aka salom", "Vaalaykum assalom, eshitaman", False),
    ("aksiya bormi?", "Shu hafta hamma narsaga 10% chegirma", False),
]


async def bir_marta():
    async def hech(*a, **k):
        return None
    ai._token_saqla = hech
    xom = await ai.biznes_fakt_ajrat(BILIM, [(s, j) for s, j, _ in H])
    juftlar = [{"id": i, "yakuniy": j} for i, (_, j, _) in enumerate(H, 1)]
    # Cheklovsiz (`BIZNES_FAKT_TAKLIF_MAX` emas) — sifatni o'lchaymiz, sig'imni emas.
    b.BIZNES_FAKT_TAKLIF_MAX = len(H)
    olingan = b.fakt_takliflari(xom, juftlar, BILIM)
    return olingan


async def main():
    takror = int(sys.argv[sys.argv.index("--takror") + 1]) if "--takror" in sys.argv else 1
    jami_xato = jami_top = 0
    kerak = sum(1 for *_, f in H if f)
    for t in range(takror):
        olingan = await bir_marta()
        xato = [n for n in olingan if not H[n - 1][2]]
        top = [n for n in olingan if H[n - 1][2]]
        jami_xato += len(xato)
        jami_top += len(top)
        print(f"── {t + 1}-marta: topildi {len(top)}/{kerak}, noto'g'ri {len(xato)}")
        for n, f in olingan.items():
            belgi = "✅" if H[n - 1][2] else "❌"
            print(f"  {belgi} #{n} «{f['savol']}» → {f['javob']}")
    print(f"\nNATIJA: noto'g'ri {jami_xato} (0 bo'lishi shart), "
          f"topildi {jami_top}/{kerak * takror} = {jami_top * 100 // (kerak * takror)}%")


if __name__ == "__main__":
    asyncio.run(main())
