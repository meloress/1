"""CSV eksport — panel ham, Telegram Business kartotekasi ham shu yerdan.

Bitta nusxa ATAYLAB: formula in'eksiyasi himoyasi xavfsizlik nazorati,
formatlash emas — ikki nusxadan biri albatta eskirib, uni yo'qotardi.
"""
from typing import Any, List


def csv_katak(qiymat: Any) -> str:
    """Bitta katak — CSV qoidalari bo'yicha.

    ⛔️ FORMULA IN'EKSIYASI. Excel `=`, `+`, `-`, `@` bilan boshlangan
    katakni FORMULA deb o'qiydi, ya'ni username `=HYPERLINK(...)` bo'lsa
    faylni ochgan odamning mashinasida ishga tushardi. Bo'sh joy
    qo'shish buni to'xtatadi va ko'rinishga deyarli ta'sir qilmaydi.
    """
    if qiymat is None:
        return ""
    matn = str(qiymat)
    if matn[:1] in ("=", "+", "-", "@", "\t", "\r"):
        matn = "'" + matn
    if any(c in matn for c in ',";\n\r'):
        matn = '"' + matn.replace('"', '""') + '"'
    return matn


def csv_matn(sarlavhalar: tuple, qatorlar: List[tuple]) -> str:
    # ⚠️ BOM (﻿) ATAYLAB: usiz Excel faylni ANSI deb o'qiydi va
    # o'zbekcha «o'», «g'» hamda @username'lardagi harflar buziladi.
    # LibreOffice va Google Sheets BOM bilan ham to'g'ri ochadi.
    satrlar = [";".join(sarlavhalar)]
    satrlar += [";".join(csv_katak(k) for k in q) for q in qatorlar]
    return "﻿" + "\r\n".join(satrlar) + "\r\n"
