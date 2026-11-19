"""Panelning iPhone uchun zamonaviy qismlari (2026-11-19) — qo'riqchi.
Ishga tushirish: PYTHONIOENCODING=utf-8 python tests/test_panel_iphone.py

Tarmoq, baza va Telegram kerak emas. Telegram'ga bog'liq oqimlar (Face ID,
CloudStorage, tebranish) lokal stendda soxta WebApp bilan brauzerda bosib
chiqilgan; bu fayl o'sha oqimlarning QOIDALARINI qadaydi — ular buzilsa
hech narsa yiqilmaydi, panel shunchaki himoyasiz yoki noqulay bo'lib qoladi.

  1-to'plam:
    [1]  P3 ranglar: ikki shart ostida, yorqinlik va kontrast asl hex bilan bir xil
    [2]  P3: ikkala yorug' blok bir xil, SVG gradiyenti va grafik nuqtalari ham
    [3]  KPI: daromadning 7 kunlik qatori va kechagi summasi (foiz emas)
    [4]  KPI mini-grafik: oxirgi bo'lak uzuq, gradiyent userSpaceOnUse, «0%» strelkasiz
    [5]  Face ID: faqat telefonda; ma'lumot qulfdan KEYIN; o'rnatilgan qulfni
         chetlab o'tib bo'lmaydi; birinchi rad etish panelni yopib qo'ymaydi
    [6]  Face ID: o'chirish ham biometriya bilan; 1 daqiqadan keyin qayta qulf

  2-to'plam:
    [7]  bo'lim almashishi View Transitions bilan; rad etilgan va'da ushlanadi
    [8]  katta sarlavha: yashirin paytda o'lchanmaydi, ikkala nusxa bitta funksiyadan
    [9]  profil telefonda — varaq: ro'yxat joyi saqlanadi, tortib yopish, burilish
    [10] pastga tortib yangilash: faqat o'qiladigan bo'limlarda, .wrap'da transform qolmaydi
    [11] bosib turish menyusi: faqat xavfsiz amallar, barmoq uzilishi profilni ochmaydi
    [12] tebranish: tab, chip va grafikda selectionChanged

  3-to'plam:
    [13] faollik xaritasi: Toshkent soati, 7×24, so'rov yiqilsa ekran yashaydi
    [14] asosiy ekran ikonkasi: faqat qo'llaydigan mijozda
    [15] tizim shrifti (SF Pro), tashqi shrift yo'q, yaroqsiz `font:` qisqa yozuvi yo'q
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ⚠️ `test_web_stats` BIRINCHI: u BOT_TOKEN ni `web` import qilinishidan
# oldin qo'yadi va soxta bazani beradi — nusxasini yozmaymiz.
import test_web_stats as tws          # noqa: E402
from _manba import css_kod, js_kod    # noqa: E402

import asyncio                        # noqa: E402
import datetime                       # noqa: E402
import pathlib                        # noqa: E402
import re                             # noqa: E402

from aiohttp.test_utils import TestClient, TestServer   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "web" / "static"
HTML = (STATIC / "panel.html").read_text(encoding="utf-8")
CSS = re.sub(r"/\*.*?\*/", "", css_kod((STATIC / "panel.css").read_text(encoding="utf-8")), flags=re.S)
JS = js_kod((STATIC / "panel.js").read_text(encoding="utf-8"))
SOZ = re.sub(r"/\*.*?\*/", "", (STATIC / "soz.js").read_text(encoding="utf-8"), flags=re.S)

OK = 0


def check(n, nom, shart):
    global OK
    assert shart, f"[{n}] YIQILDI: {nom}"
    OK += 1
    print(f"[{n}] {nom} OK")


def funksiya(matn, nom):
    """`function nom(` dan keyingi `function` gacha (taxminiy tana)."""
    i = matn.index(f"function {nom}(")
    j = re.search(r"\n  (async )?function ", matn[i + 10:])
    return matn[i:i + 10 + j.start()] if j else matn[i:]


def blok(matn, bosh):
    """`bosh` dan boshlanib, qavslari yopilgan blok."""
    i = matn.index(bosh)
    k = matn.index("{", i)
    chuq = 0
    for j in range(k, len(matn)):
        chuq += {"{": 1, "}": -1}.get(matn[j], 0)
        if chuq == 0:
            return matn[i:j + 1]
    raise AssertionError(f"yopilmagan blok: {bosh}")


# ── WCAG yorqinligi: sRGB hex va Display P3 ─────────────────────────
def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def y_hex(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def y_p3(s):
    r, g, b = (float(x) for x in re.match(r"color\(display-p3 ([\d.]+) ([\d.]+) ([\d.]+)\)", s).groups())
    # Display P3 → XYZ (D65) matritsasining Y qatori.
    return 0.2289746 * _lin(r) + 0.6917385 * _lin(g) + 0.0792869 * _lin(b)


def kontrast(a, b):
    a, b = max(a, b), min(a, b)
    return (a + 0.05) / (b + 0.05)


def tokenlar(tana):
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", tana))


def p3_va_asl():
    """1-2: P3 bloklar — tuzilma, yorqinlik, kontrast."""
    asos = tokenlar(blok(CSS, ":root{"))
    yorug = tokenlar(blok(CSS, ':root[data-tema="light"]{'))

    i = CSS.index("@media (color-gamut:p3){")
    p3 = blok(CSS, "@media (color-gamut:p3){")
    # ⚠️ IKKI shart: ekran (media) va brauzer (`@supports`). Ikkinchisisiz
    # eski brauzerda `--ok: color(...)` baribir yoziladi va rang yo'qoladi.
    check(1, "P3 bloki `@supports (color:color(display-p3 …))` ichida",
          "@supports (color:color(display-p3 1 1 1)){" in p3
          and i > CSS.index(':root[data-tema="light"]{'))
    p3_qorongi = tokenlar(blok(p3, ":root{"))
    p3_yorug = tokenlar(blok(p3, ':root[data-tema="light"]{'))
    p3_brauzer = tokenlar(blok(blok(CSS, "@media (color-gamut:p3) and (prefers-color-scheme:light){"),
                               ':root:not([data-tema="dark"]){'))

    # Har P3 token asl hex tokenning O'ZI (yangi nom paydo bo'lmasin) va
    # yorqinligi asliga 2% gacha yaqin: kontrast o'zgarmaydi, faqat to'yinish.
    farqlar = []
    for jadval, asl in ((p3_qorongi, asos), (p3_yorug, yorug)):
        for t, v in jadval.items():
            if t == "--grad":
                continue
            assert t in asl and asl[t].startswith("#"), f"P3 da notanish token {t}"
            farq = abs(y_p3(v) - y_hex(asl[t])) / y_hex(asl[t])
            farqlar.append((t, round(farq, 3)))
            assert farq < 0.02, f"{t}: P3 yorqinligi asldan {farq:.1%} farq qiladi"
    # Matn rangi bo'lib ishlatiladigan `--azure` — ikkala temada AA.
    for jadval, yuza in ((p3_qorongi, asos["--panel"]), (p3_yorug, yorug["--panel"])):
        assert kontrast(y_p3(jadval["--azure"]), y_hex(yuza)) >= 4.5, "P3 --azure kontrasti < 4.5"
    check(1, f"{len(farqlar)} ta P3 token: yorqinlik asldan <2%, --azure AA", True)

    check(2, "brauzerdagi yorug' P3 = Telegram yorug' P3 (bir xil qiymatlar)",
          p3_brauzer == p3_yorug and set(p3_yorug) <= set(p3_qorongi))
    check(2, "SVG gradiyent to'xtashlari va grafik nuqtalari P3 da qayta bo'yaladi",
          all(f"stop.{g}{{stop-color:color(display-p3" in p3 for g in ("g1", "g2", "g3"))
          and ".chart .nuqta.oxirgi{fill:color(display-p3" in p3
          and HTML.count('class="g1"') >= 3 and 'class="kesim" id="chart-cross"' in HTML
          and 'class="nuqta' in JS)


async def kpi_api():
    """3: daromad mini-grafigi va kechagi summa — serverdan."""
    bugun = datetime.datetime.now(tws.TASHKENT).date()
    kecha = bugun - datetime.timedelta(days=1)

    async def daromad():
        d = dict(tws.SOXTA_DAROMAD)
        d["daily"] = [{"kun": kecha, "stars": 777, "soni": 3},
                      {"kun": bugun - datetime.timedelta(days=5), "stars": 50, "soni": 1},
                      # 7 kunlik oynadan TASHQARIDA — mini-grafikka tushmasin.
                      {"kun": bugun - datetime.timedelta(days=9), "stars": 9999, "soni": 9}]
        return d

    tws.soxta_bazani_qoy(tws.api, revenue_stats=daromad)
    async with TestClient(TestServer(tws.web.build_app())) as c:
        h = await tws.kir(c)
        pul = (await (await c.get("/api/overview", headers=h)).json())["kpi"]["daromad"]
        tws.soxta_bazani_qoy(tws.api)          # `daily` umuman yo'q (eski shakl)
        pul0 = (await (await c.get("/api/overview", headers=h)).json())["kpi"]["daromad"]
    sonlar = [k["soni"] for k in pul["kunlar"]]
    check(3, "daromad mini-grafigi: 7 kun, Toshkent kunlari, bo'sh kun 0, oynadan tashqarisi yo'q",
          len(sonlar) == 7 and sonlar[-2] == 777 and sonlar[1] == 50 and sum(sonlar) == 827
          and pul["kunlar"][-1]["kun"] == bugun.isoformat())
    # ⚠️ Foiz EMAS: bugun tugamagan kun, ertalab «−90%» yolg'on bo'lardi.
    check(3, "«kecha» — summa (777), foiz kaliti yo'q; `daily` bo'lmasa ham 0, yiqilmaydi",
          pul["kecha"] == 777 and "ozgarish" not in pul
          and pul0["kecha"] == 0 and len(pul0["kunlar"]) == 7)


def mini_grafik():
    """4: KPI mini-grafigi va «▲ 12%» yorlig'i."""
    m = funksiya(JS, "mini")
    check(4, "oxirgi bo'lak (bugun) alohida, uzuq chiziq bilan",
          "p.slice(n - 2)" in m and "m-bugun" in m and "p.slice(0, n - 1)" in m
          and re.search(r"\.spark \.m-bugun\{[^}]*stroke-dasharray", CSS))
    # objectBoundingBox tekis (hammasi 0) chiziqni CHIZMAYDI.
    check(4, "chiziq gradiyenti `userSpaceOnUse` (tekis chiziq ham ko'rinadi)",
          re.search(r'id="sparkLine" gradientUnits="userSpaceOnUse"', HTML)
          and "stroke:url(#sparkLine)" in CSS)
    for kpi in ("k-sorov-sp", "k-faol-sp", "k-pul-sp"):
        assert f'id="{kpi}"' in HTML and f'mini("{kpi}"' in JS, kpi
    t = funksiya(JS, "trend")
    check(4, "uchta KPI'da mini-grafik; «0%» strelkasiz va neytral; mini-grafik doim 7 kun",
          '"teng"' in t and ".slice(-7)" in funksiya(JS, "boshqaruv")
          and all(k in SOZ for k in ("sorov:", "faol:", "pul:")))


def face_id():
    """5-6: Face ID qulfi qoidalari."""
    # Faqat telefonda — kompyuterda biometriya yo'q, Bot API 7.2+.
    m = re.search(r"var TELEFON = (\[[^\]]*\])", JS)
    bm = funksiya(JS, "bmTayyor")
    check(5, "qulf faqat ios/android va Bot API 7.2+ da",
          m and set(re.findall(r'"(\w+)"', m.group(1))) == {"ios", "android"}
          and 'isVersionAtLeast("7.2")' in bm)

    # ⛔️ Ma'lumot QULFDAN KEYIN: na ism, na /api/meta qulf ochilmasdan.
    ich = funksiya(JS, "ichkariga")
    check(5, "ichkariga(): avval qulf, keyin ism, korsat(shell) va /api/meta",
          ich.index("await qulfKut(qulfBoshla)") < ich.index('korsat("shell")')
          < ich.index('ol("/api/meta")')
          and ich.index("await qulfKut(qulfBoshla)") < ich.index('$("who-ism")'))
    ek = funksiya(JS, "ekranYukla")
    check(5, "qulf ostida ekran yuklanmaydi", "qulfYopiq) return" in ek)

    # Holat CloudStorage'da — localStorage'ni WebView bilan tozalab yuborish mumkin.
    check(5, "holat Telegram CloudStorage'da, localStorage'da emas",
          "cs.getItem(kalit" in funksiya(JS, "bulut") and "localStorage" not in JS)

    # ⛔️ O'rnatilgan qulf ("1") + biometriya o'chirilgan → panel OCHILMAYDI.
    b = funksiya(JS, "qulfBoshla")
    check(5, "o'rnatilgan qulfni telefon sozlamasida biometriyani o'chirib chetlab o'tib bo'lmaydi",
          '!BM.isBiometricAvailable && qulfHolati !== "1"' in b
          and 'if (!BM.isBiometricAvailable) return qulfKorsat("yoq")' in funksiya(JS, "qulfUrin"))
    # Birinchi rad etish (qulf hali o'rnatilmagan: "") — panel ochiladi, "0".
    # O'rnatilgan qulfda rad etish — «ruxsat» ekrani, ochilmaydi.
    u = funksiya(JS, "qulfUrin")
    check(5, "rad etilgan ruxsat: o'rnatilmagan qulfda — voz kechish, o'rnatilganda — qulf",
          'if (qulfHolati === "") return qulfVoz();' in u
          and u.index('qulfHolati === ""') < u.index('return qulfKorsat("ruxsat")', u.index('qulfHolati === ""'))
          and 'javob || ""' in funksiya(JS, "bulut"))

    # O'chirish ham biometriya bilan — telefon qo'lidagi boshqa odam qulfni
    # bir bosishda o'chira olmasin. Saqlash Face ID'dan KEYIN.
    h = funksiya(JS, "qulfHodisalari")
    check(6, "Sozlamalardagi kalitcha: tasdiq → biometriya → keyin CloudStorage",
          h.index("ochirSavol") < h.index("await bmTasdiqla()") < h.index('bulut("yoz"')
          and "if (!ok) return" in h)
    q = funksiya(JS, "qulfQaytdi")
    check(6, "1 daqiqadan ko'p chetda — qayta qulf; qulf ostida MainButton yashirin",
          "var QULF_MUDDAT = 60000;" in JS and "> QULF_MUDDAT" in q and "asosiyTugma(null)" in q
          and 'tg.onEvent("deactivated", qulfChetda)' in JS and 'tg.onEvent("activated", qulfQaytdi)' in JS
          and "visibilitychange" in funksiya(JS, "telegram"))
    check(6, "qulf ekrani HTML'da yashirin boshlanadi va korsat() uni biladi",
          '<div class="gate" id="qulf" hidden>' in HTML
          and '["yuklash", "xato", "qulf", "shell"]' in JS)


def otish_va_sarlavha():
    """7-8: silliq o'tish va katta sarlavha."""
    o = funksiya(JS, "otish")
    check(7, "View Transitions: «kamroq harakat»da va eski brauzerda darhol; rad etilgan va'da ushlanadi",
          "document.startViewTransition(fn)" in o and "prefers-reduced-motion: reduce" in o
          and "|| !kirdi) return fn();" in o
          and '"finished"' in o and ".catch(function () {})" in o)
    check(7, "o'tish bor joyda eski `rise` o'chadi; tab-panel va sarlavha joyida turadi",
          re.search(r"@supports \(view-transition-name:none\)\{section\[data-screen\]\.on\{animation:none\}\}", CSS)
          and ".tabbar{view-transition-name:tabbar}" in CSS)

    s = funksiya(JS, "sarlavhaHolati")
    ich = funksiya(JS, "ichkariga")
    # ⚠️ Panel yashirin paytda o'lcham 0 — ikkala sarlavha birga ko'rinardi.
    check(8, "katta sarlavha: o'lchami 0 bo'lsa ixcham emas; panel ko'ringach qayta hisoblanadi",
          "k.offsetHeight > 0" in s and ich.index('korsat("shell")') < ich.index("sarlavhaHolati()")
          and "sarlavhaHolati()" in funksiya(JS, "qulfQaytdi"))
    check(8, "sarlavha yagona funksiyadan ikkala joyga yoziladi, katta sarlavha faqat telefonda",
          '"katta-sarlavha"' in funksiya(JS, "sarlavhaYoz") and ".katta{display:none}" in CSS
          and 'id="katta" aria-hidden="true"' in HTML
          and 'ttl.textContent' not in JS)


def varaq_va_tortish():
    """9-10: profil varag'i va pastga tortib yangilash."""
    g = funksiya(JS, "go")
    gi = funksiya(JS, "goIchki")
    # Varaq ochiq turib boshqa bo'limga — avval varaq pastga tushadi.
    check(9, "varaq ochiq bo'lsa go() avval uni yopadi; ostida o'z ro'yxati qoladi",
          "if (varaq && name !== \"profil\")" in g and "varaqYop(" in g
          and "(varaqqa && s.dataset.screen === orqa)" in gi)
    # ⭐ Ro'yxat joyi saqlanadi — ilgari «Orqaga» uni tepaga qaytarardi.
    check(9, "varaqni ochish/yopish ro'yxatni tepaga qaytarmaydi; varaqda sarlavha o'zgarmaydi",
          "if (!varaqqa && !varaqdan) window.scrollTo" in gi and "if (!varaqqa) {" in gi)
    v = funksiya(JS, "varaqSurish")
    check(9, "tortib yopish: faqat varaq tepada bo'lsa, kiritish maydonida emas, `passive:false`",
          "sec.scrollTop > 0) return" in v and 'closest("input, textarea, select")' in v
          and "{ passive: false }" in v and "e.preventDefault()" in v)
    m = funksiya(JS, "maketAlmashdi")
    check(9, "burilishda varaq ↔ ichki sahifa almashadi (resize va media-so'rov)",
          "!tel && varaq" in m and "tel && !varaq" in m
          and 'addEventListener("resize", maketAlmashdi)' in JS
          and 'addEventListener("change", maketAlmashdi)' in JS)

    t = funksiya(JS, "tortibYangilash")
    # ⛔️ Formali bo'limlarda yo'q — yozilgan qiymat o'chib ketardi.
    check(10, "tortib yangilash faqat `YANGILANADI` bo'limlarida, varaq/menyu/qulf ostida emas",
          "!YANGILANADI[hozir]" in t and "varaq ||" in t and "menyuOchiq" in t and "qulfYopiq" in t)
    check(10, "`.wrap` da transform qolmaydi (ichidagi fixed varaqni sindirardi); belgi yuklash tugashini kutadi",
          'wrap.style.transform = "";' in funksiya(JS, "joyiga") if "function joyiga(" in JS else False)
    check(10, "ekranYukla() va'da qaytaradi (yuklanmasa ham)",
          "return fn().catch(" in funksiya(JS, "ekranYukla")
          and funksiya(JS, "ekranYukla").count("return Promise.resolve();") == 2)


def menyu_va_titroq():
    """11-12: bosib turish menyusi va tebranish."""
    keys = re.findall(r"^\s{4}(\w+):\s+'<", JS.split("var MENYU_IKON = {", 1)[1].split("};", 1)[0], re.M)
    # ⛔️ Bloklash / Pro bu yerda YO'Q — bitta noto'g'ri barmoq harakati.
    check(11, "menyuda faqat xavfsiz amallar: profil, ID, Telegram, kuzatuv (tasdiq bilan)",
          keys == ["och", "id", "tg", "kuzat"]
          and "await tasdiq(S.savol.kuzat(nom))" in funksiya(JS, "menyuAmal"))
    b = funksiya(JS, "bosibTurish")
    check(11, "bosib turish 480 ms; 8px siljish — aylantirish; barmoq uzilishi profilni ochmaydi",
          "}, 480);" in b and "> 8" in b
          and "if (uzoq && e.cancelable) e.preventDefault();" in b
          and JS.count("Date.now() - menyuVaqt < 700") == 2)
    check(11, "o'ng tugma / Android: menyu ikki marta ochilmaydi; Escape va parda yopadi",
          '"contextmenu"' in b and "menyuQator === row) return" in b
          and '"Escape"' in b and "menyuYop()" in b)
    check(11, "qatorlarda `data-un` (xavfsiz()dan o'tgan); matnlar lug'atda",
          JS.count('data-un="\' +') == 2 and JS.count('xavfsiz(u.username || "")') == 2
          and all(k in SOZ for k in ("och:", "kuzat:", "tglinkKetdi:")))

    t = funksiya(JS, "titroq")
    check(12, "«tanlov» = selectionChanged: tablarda, filtr chiplarida, grafikda kun almashganda",
          '"tanlov") return tg.HapticFeedback.selectionChanged()' in t
          and 'titroq("tanlov");\n        showPane(bar.dataset.tabs' in JS
          and "if (e.touches && i !== oldingi) titroq(\"tanlov\")" in JS
          and JS.count('titroq("tanlov")') >= 7)


async def xarita_api():
    """13: faollik xaritasi — SQL qoidasi, 7×24 jadval, yiqilsa ekran yashaydi."""
    from _manba import kod
    db = kod(ROOT / "db" / "database.py")
    i = db.index("async def faollik_xaritasi(")
    sql = db[i:db.index("\nasync def ", i + 10)]
    # ⚠️ Soat Toshkent bo'yicha (server UTC), adminlar sanalmaydi, oyna parametr.
    check(13, "SQL: Toshkent soati, ISODOW, adminlarsiz, oyna parametr bilan",
          sql.count("AT TIME ZONE 'Asia/Tashkent'") == 2 and "ISODOW" in sql
          and "{_ODDIY_USER}" in sql and "make_interval(days => $1::int)" in sql)

    x = tws.api._xarita([{"hafta_kuni": 3, "soat": 5, "soni": 7},
                         {"hafta_kuni": 1, "soat": 23, "soni": 7},
                         {"hafta_kuni": 9, "soat": 1, "soni": 99},     # yaroqsiz — tashlanadi
                         {"hafta_kuni": 2, "soat": 24, "soni": 99}])
    check(13, "7×24 jadval, bo'sh katak 0, yaroqsiz qator tashlanadi, tenglikda eng erta kun",
          len(x["kataklar"]) == 7 and all(len(q) == 24 for q in x["kataklar"])
          and x["kataklar"][2][5] == 7 and x["jami"] == 14 and x["eng"] == 7
          and x["eng_payt"] == {"kun": 0, "soat": 23}
          and tws.api._xarita([])["eng_payt"] is None and tws.api._xarita(None) is None)

    async def yiqiladi(kunlar=30):
        raise RuntimeError("baza uzildi")

    tws.soxta_bazani_qoy(tws.api)
    async with TestClient(TestServer(tws.web.build_app())) as c:
        h = await tws.kir(c)
        bor = await (await c.get("/api/stats", headers=h)).json()
        tws.soxta_bazani_qoy(tws.api, faollik_xaritasi=yiqiladi)
        r = await c.get("/api/stats", headers=h)
        yoq = await r.json()
        tws.soxta_bazani_qoy(tws.api)
    check(13, "/api/stats xaritani beradi; xarita so'rovi yiqilsa — 200 va `xarita: null`",
          bor["xarita"]["kataklar"][1][21] == 34 and bor["xarita"]["eng_payt"] == {"kun": 1, "soat": 21}
          and r.status == 200 and yoq["xarita"] is None and yoq["kpi"]["jami"] == bor["kpi"]["jami"])
    xc = funksiya(JS, "xaritaChiz")
    check(13, "panel: √ shkala, karta `null` da yashirin, kun nomlari lug'atda (7 ta)",
          "Math.sqrt(v / x.eng)" in xc and "karta.hidden = !x;" in xc
          and len(re.findall(r'"\w+"', SOZ.split("haftaTola:", 1)[1].split("]", 1)[0])) == 7)


def uy_va_shrift():
    """14-15: asosiy ekran ikonkasi va tizim shrifti."""
    u = funksiya(JS, "uyTekshir")
    q = funksiya(JS, "qurilmaKartasi")
    check(14, "ikonka: Bot API 8.0, avval holat so'raladi, «unsupported»da qator yo'q",
          'isVersionAtLeast("8.0")' in u and "tg.checkHomeScreenStatus(" in u
          and 'uyHolati !== "unsupported"' in q and '$("uy-qosh").hidden = uyHolati === "added"' in q
          and "k.hidden = !face && !uy;" in q)
    check(14, "qo'shilgani Telegram hodisasidan (`homeScreenAdded`), tugma — `addToHomeScreen()`",
          'tg.onEvent("homeScreenAdded"' in JS and "tg.addToHomeScreen()" in funksiya(JS, "uyHodisalari"))

    # ⚠️ `blok(CSS, "body{")` emas: birinchi «body{» — `html,body{touch-action…}`.
    body = blok(CSS, "\nbody{")
    check(15, "tizim shrifti (iPhone'da SF Pro), tashqi shrift yo'q",
          re.search(r"font:400 var\(--f-l\)/1\.5 -apple-system,", body) is not None
          and "IBM Plex" not in CSS and "googleapis" not in HTML)
    # `font:600 12px/1 inherit` — yaroqsiz qisqa yozuv, butun qator tashlanardi.
    check(15, "shrift qisqa yozuvida `inherit` yo'q (brauzer butun qatorni tashlardi)",
          # `font:inherit` YOLG'IZ — to'g'ri; boshqa qiymat bilan aralashi — yo'q.
          not re.search(r"font:\s*(?!inherit\s*[;}])[^;}]*\binherit\b", CSS)
          and "font:inherit;" in CSS)


def main():
    p3_va_asl()
    asyncio.run(kpi_api())
    mini_grafik()
    face_id()
    otish_va_sarlavha()
    varaq_va_tortish()
    menyu_va_titroq()
    asyncio.run(xarita_api())
    uy_va_shrift()
    print(f"\npanel iPhone: barcha tekshiruvlar o'tdi ({OK}/{OK}).")


if __name__ == "__main__":
    main()
