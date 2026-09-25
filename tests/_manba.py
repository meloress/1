# -*- coding: utf-8 -*-
"""Manba kodini tekshiradigan testlar uchun yagona o'qish yo'li.

NEGA BOR — bu xato shu loyihada TO'RT MARTA takrorlandi va har safar
bir xil ko'rinishda: qo'riqchi test o'zi qo'riqlayotgan qoidani
TUSHUNTIRUVCHI izohni kod deb o'qidi va yashil bo'lib turaverdi.

  1. `@bir_marta` — `refund` NEGA chetda qoldirilganini aytuvchi izohda
     uchradi, ya'ni test dekorator yo'q joyda ham uni "bor" deb o'qidi;
  2. `del_cookie()` — u ISHLATILMASLIGI kerakligini aytuvchi izohda;
  3. «Ishonchingiz komilmi» — bu matn MUMKIN EMASligini aytuvchi
     izohda MISOL sifatida;
  4. «chat not found» — ro'yxat nusxalanmasligi kerakligini aytuvchi
     izohda.

Har safar tuzatish bir xil edi: izohlarni tashlash. Uchta joyda uchta
alohida nusxa paydo bo'lgandan keyin ular shu yerga yig'ildi.

⚠️ SATRLAR TASHLANMAYDI, DOKSATRLAR tashlanadi. Qo'riqchilarning
ko'pchiligi SQL matnini tekshiradi, SQL esa oddiy satr ichida yashaydi
(`"SELECT … make_interval(days => $1::int)"`) — satrlarni tashlash
o'sha tekshiruvlarning hammasini o'ldirardi. Xavf esa NASRDA: nasr
izohda va doksatrda bo'ladi, oddiy satrda emas.
"""

import io
import re
import tokenize
from pathlib import Path


def kod(yol) -> str:
    """Python manbasi — izohlar va doksatrlar BO'SH JOYGA almashtirilgan.

    ⛔️ MATN TARKIBI SAQLANADI, tokenlar qayta birlashtirilmaydi. Birinchi
    urinish `"\\n".join(token.string)` qilgan edi va u butun to'plamni
    yiqitdi: `def admin_only(` uch qatorga bo'linib ketdi, ya'ni KOD
    SHAKLINI qidiradigan har bir qo'riqchi («`def X(` ni top, o'sha
    yerdan keyingi e'longacha kes») ishlamay qoldi. Shuning uchun bu
    yerda faqat nasr o'z o'rnida bo'sh joyga almashtiriladi — qolgan har
    bir belgi AYNAN o'sha joyda qoladi, qator raqamlari ham.

    Tahlil qilib bo'lmasa xom matn qaytadi: qo'riqchi test sintaksis
    xatosi tufayli JIM o'tib ketmasligi kerak.
    """
    # `utf-8-sig` — BOM bilan yozilgan fayl `tokenize` ni yiqitadi.
    xom = Path(yol).read_text(encoding="utf-8-sig")
    try:
        toklar = list(tokenize.generate_tokens(io.StringIO(xom).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return xom

    satrlar = xom.splitlines(keepends=True)

    def ochir(boshi, oxiri, orniga=""):
        """(qator, ustun) oralig'ini bo'sh joyga almashtiradi.

        `orniga` — birinchi belgi o'rniga yoziladigan matn. Doksatr uchun
        `0` beriladi: tanasi FAQAT doksatrdan iborat sinf yoki funksiya
        (`services/places.py` dagi istisnolar) bo'shatib qo'yilsa manba
        sintaktik jihatdan buziladi, `0` esa yaroqli ifoda va blokni
        bo'sh qoldirmaydi.
        """
        r1, u1 = boshi
        r2, u2 = oxiri
        for r in range(r1, r2 + 1):
            if r - 1 >= len(satrlar):
                break
            s = satrlar[r - 1]
            a = u1 if r == r1 else 0
            b = u2 if r == r2 else len(s.rstrip("\r\n"))
            bosh = orniga if r == r1 else ""
            # Qator oxiri saqlanadi — aks holda qatorlar qo'shilib ketardi.
            satrlar[r - 1] = (s[:a] + bosh
                              + " " * max(0, b - a - len(bosh)) + s[b:])

    # Doksatr — o'z boshiga IFODA bo'lib turgan satr: undan oldin faqat
    # NEWLINE / NL / INDENT / DEDENT keladi. Oddiy satr (`x = "SELECT …"`,
    # `f("...")`) bu shartni qanoatlantirmaydi va TEGILMAYDI — SQL aynan
    # shunday satrlarda yashaydi va qo'riqchilarning ko'pi uni qidiradi.
    # ⛔️ `NL` IFODA CHEGARASI EMAS. `tokenize` mantiqiy qator oxirini
    # `NEWLINE`, qavs ichidagi yoki bo'sh qator ko'chishini esa `NL` deb
    # beradi. `NL` ni ham chegara deb olgan birinchi urinish
    #     {"pro":  st.get(...),
    #      "free": st.get(...)}
    # dagi kalitlarni DOKSATR deb o'chirib tashladi va manba
    # sintaktik jihatdan buzildi. Xuddi shu narsa ko'p qatorli
    # chaqiruv ichidagi f-string bilan ham bo'ldi.
    yangi_ifoda = True
    for t in toklar:
        if t.type == tokenize.COMMENT:
            ochir(t.start, t.end)
            continue
        if t.type == tokenize.STRING and yangi_ifoda:
            ochir(t.start, t.end, "0")
            yangi_ifoda = False
            continue
        if t.type in (tokenize.NL, tokenize.ENCODING):
            continue                      # chegara EMAS
        if t.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            yangi_ifoda = True
            continue
        yangi_ifoda = False
    return "".join(satrlar)


# JS va CSS uchun `tokenize` ishlamaydi (u Python leksikasi), shuning
# uchun izohlar oddiy regex bilan olib tashlanadi. Xavf bir xil: panel
# lug'atidagi izohda yozilgan MISOL matn kod deb o'qilgan edi.
_BLOK_IZOH = re.compile(r"/\*.*?\*/", re.S)
_QATOR_IZOH = re.compile(r"(?<![:\"'\\])//[^\r\n]*")


def css_kod(matn: str) -> str:
    """CSS — `/* … */` izohlarsiz."""
    return _BLOK_IZOH.sub("", matn)


def js_kod(matn: str) -> str:
    """JS — `/* … */` va `// …` izohlarsiz.

    ⚠️ `//` faqat URL ichida emasligiga ishonch hosil qilinadi
    (`https://…`), aks holda har havola kesib tashlanardi. Satr ichidagi
    `//` ni bu regex baribir ajrata olmaydi — shuning uchun JS
    tekshiruvlari kalit so'zni emas, KOD SHAKLINI qidirsin
    (`insertBefore(el, joy.firstChild)`, `function xyz(`).
    """
    return _QATOR_IZOH.sub("", _BLOK_IZOH.sub("", matn))
