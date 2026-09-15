"""Web panel maketining tuzilmasi uchun qo'lda ishga tushiriladigan tekshiruv.
Ishga tushirish: python tests/test_web_panel.py

Tarmoq, baza va brauzer kerak emas — faqat uchta statik fayl o'qiladi.

Bu fayldagi hamma tekshiruv BITTA turdagi nosozlikni qo'riqlaydi:
**jim o'lgan tugma**. Panel — bitta sahifa, hamma narsa `data-*`
atributlari orqali bog'langan, ya'ni nomi bir harfga o'zgargan tugma
bosilganda hech narsa bo'lmaydi: xato yo'q, log yo'q, foydalanuvchi
esa «panel buzilibdi» deydi. Keyingi bosqichlarda bu fayllar qayta-qayta
tahrirlanadi, shuning uchun qamrov shu yerda qadab qo'yiladi.
"""

import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pathlib

STATIC = pathlib.Path(__file__).resolve().parent.parent / "web" / "static"
HTML = (STATIC / "panel.html").read_text(encoding="utf-8")
CSS = (STATIC / "panel.css").read_text(encoding="utf-8")
JS = (STATIC / "panel.js").read_text(encoding="utf-8")

# Ekran bo'laklari: <section data-screen="x" ...> ... </section>
SECTIONS = dict(re.findall(
    r'<section data-screen="(\w+)"[^>]*>(.*?)</section>', HTML, re.S))


def test_ekranlar():
    """Har bir `data-go` haqiqiy ekranga olib boradimi."""
    assert SECTIONS, "bironta <section data-screen> topilmadi"
    yollar = set(re.findall(r'data-go="(\w+)"', HTML))
    yoq = yollar - set(SECTIONS)
    assert not yoq, f"tugma bor, ekran yo'q: {yoq}"

    # Boshlang'ich ekran ANIQ BITTA bo'lishi kerak: ikkitasi bir vaqtda
    # ochilsa ikkala ekran ustma-ust chiziladi, bittasi ham bo'lmasa
    # panel bo'sh ochiladi.
    ochiq = re.findall(r'<section data-screen="(\w+)" class="on"', HTML)
    assert len(ochiq) == 1, f"boshlang'ich ekran aniq bitta bo'lsin: {ochiq}"
    assert ochiq[0] == "dash", ochiq
    assert 'var BOSH_EKRAN = "dash"' in JS, "panel.js dagi bosh ekran HTML bilan mos emas"
    print("[1] har bir data-go haqiqiy ekranga olib boradi, bosh ekran bitta OK")


def test_telefonda_qamrov():
    """⚠️ ENG MUHIMI: Mini App TELEFONDA ochiladi, chap menyu esa u yerda
    yashiringan. Ya'ni ekranga yo'l faqat pastki tab-panel va bosh ekran
    ichidagi tugmalardan qoladi. Maketda tab-panelda 5 ta joy bor,
    ekran esa 7 ta — qolgan ikkitasi bosh ekrandagi «Boshqa bo'limlar»
    kartochkasidan ochiladi. Shu kartochka o'chsa, Statistika va
    Tarqatma telefonda BUTUNLAY yo'qoladi va buni hech narsa aytmaydi.
    """
    tabbar = re.search(r'<nav class="tabbar".*?</nav>', HTML, re.S)
    assert tabbar, "pastki tab-panel yo'q"
    telefonda = set(re.findall(r'data-go="(\w+)"', tabbar.group(0)))
    telefonda |= set(re.findall(r'data-go="(\w+)"', SECTIONS["dash"]))

    yetmaydi = set(SECTIONS) - telefonda
    assert not yetmaydi, f"telefonda ochib bo'lmaydigan ekran: {yetmaydi}"

    # Kompyuterda esa chap menyuda HAMMASI turishi kerak.
    nav = re.search(r'<nav class="nav" id="nav">.*?</nav>', HTML, re.S)
    assert nav, "chap menyu yo'q"
    railda = set(re.findall(r'data-go="(\w+)"', nav.group(0)))
    assert railda == set(SECTIONS), f"chap menyu to'liq emas: {set(SECTIONS) - railda}"

    # «Boshqa bo'limlar» kartochkasi faqat tor ekranda ko'rinadi.
    assert ".faqat-tel{display:none}" in CSS.replace(" ", "")
    assert ".faqat-tel{display:block}" in CSS.replace(" ", ""), \
        "faqat-tel telefon media-so'rovida yoqilmagan"
    print("[2] har bir ekran telefonda ham, kompyuterda ham ochiladi OK")


def test_sub_tablar():
    """Sub-tab bosilganda ochiladigan panel haqiqatan bormi."""
    topildi = 0
    for nom, ichi in SECTIONS.items():
        bar = re.search(r'<div class="subtabs"[^>]*>(.*?)</div>', ichi, re.S)
        if not bar:
            continue
        topildi += 1
        tugmalar = re.findall(r'data-pane="([\w-]+)"', bar.group(1))
        panellar = re.findall(r'<div class="pane[^"]*" data-pane="([\w-]+)"', ichi)
        assert tugmalar, f"{nom}: sub-tab tugmalari yo'q"
        assert set(tugmalar) == set(panellar), \
            f"{nom}: tugma va panel mos emas — {set(tugmalar) ^ set(panellar)}"

        ochiq = re.findall(r'<div class="pane on" data-pane="([\w-]+)"', ichi)
        assert len(ochiq) == 1, f"{nom}: ochiq panel aniq bitta bo'lsin — {ochiq}"
        joriy = re.findall(r'aria-current="true" data-pane="([\w-]+)"', bar.group(1))
        assert joriy == ochiq, f"{nom}: belgilangan tab ochiq panelga mos emas"
    assert topildi == 3, f"sub-tabli ekranlar soni kutilgandan boshqa: {topildi}"

    # Boshqa ekrandan sub-tab bilan chaqirish: data-go + data-pane juftligi.
    for ekran, pane in re.findall(r'data-go="(\w+)" data-pane="([\w-]+)"', HTML):
        assert f'data-pane="{pane}"' in SECTIONS[ekran], \
            f"{ekran} ichida '{pane}' paneli yo'q"
    print("[3] sub-tab tugmalari mavjud panellarga bog'langan OK")


def test_logo():
    """REJA 3.2.1 — panelning YAGONA rasmi `/static/logo.jpg`.

    Boshqa rasm yoki tashqi havola qo'shilsa, logo ikki joyda ikki xil
    bo'lib qoladi va yangilanganda bittasi eskiligicha qolaveradi.
    """
    LOGO = "/static/logo.jpg"
    rasmlar = re.findall(r'<img[^>]*src="([^"]+)"', HTML)
    assert rasmlar, "panelda logo umuman yo'q"
    assert set(rasmlar) == {LOGO}, f"begona rasm: {set(rasmlar) - {LOGO}}"
    assert f'<link rel="icon" href="{LOGO}">' in HTML, "favicon logodan olinmagan"
    # CSS ichida rasm chaqirig'i bo'lmasin (gradient url() emas).
    assert not re.search(r"url\(\s*['\"]?[^)]*\.(png|jpe?g|gif|svg|webp)", CSS), \
        "panel.css ichida begona rasm bor"
    assert len(rasmlar) >= 3, "logo kutilgan joylarda ishlatilmagan"
    print(f"[4] logo faqat {LOGO} dan olinadi ({len(rasmlar)} joyda) OK")


def test_id_lar():
    """panel.js murojaat qiladigan har bir ID panel.html da bormi.

    Bitta yo'q ID butun IIFE'ni yiqitardi — shuning uchun kod `qism()`
    ichida bo'laklarga ajratilgan, lekin baribir o'sha bo'lak jim
    ishlamay qoladi. Test uni deploydan OLDIN ushlaydi.
    """
    bor = set(re.findall(r'\sid="([\w-]+)"', HTML))
    kerak = set(re.findall(r'\$\("([\w-]+)"\)', JS))
    kerak |= set(re.findall(r'getElementById\("([\w-]+)"\)', JS))
    # `korsat()` ichidagilar o'zgaruvchi orqali uzatiladi — qo'lda.
    kerak |= {"yuklash", "xato", "shell", "tabbar"}
    yoq = kerak - bor
    assert not yoq, f"panel.js mavjud bo'lmagan ID ga murojaat qiladi: {yoq}"
    print(f"[5] panel.js chaqirgan {len(kerak)} ta ID panel.html da bor OK")


def test_fayllar_ulangan():
    assert '<link rel="stylesheet" href="/static/panel.css">' in HTML
    assert '<script src="/static/panel.js"></script>' in HTML
    assert "telegram-web-app.js" in HTML, "Telegram WebApp kutubxonasi ulanmagan"
    print("[6] panel.html css, js va Telegram kutubxonasini ulaydi OK")


def test_telegram_ulanishi():
    """2-bosqichning «tayyor» mezoni: to'liq balandlik va tab-panel.

    Har biri bir marta yozilib, keyin tasodifan o'chib ketishi mumkin
    bo'lgan chaqiruvlar — o'chsa panel ishlaydi, lekin noto'g'ri
    ko'rinadi va sababi ko'rinmaydi.
    """
    for chaqiruv in ("tg.ready()", "tg.expand()", "setHeaderColor",
                     "disableVerticalSwipes", "viewportStableHeight",
                     "BackButton", "HapticFeedback", "viewportChanged"):
        assert chaqiruv in JS, f"panel.js da '{chaqiruv}' yo'q"

    # Balandlik CSS o'zgaruvchisi orqali ulanadi — ikkala tomon ham kerak.
    assert '--vh' in CSS and 'setProperty("--vh"' in JS
    assert "min-height:var(--vh)" in CSS.replace(" ", "")
    # Orqaga tugmasi bosh ekranda yashirilishi kerak.
    assert "BackButton.hide()" in JS and "BackButton.show()" in JS
    print("[7] Telegram WebApp ulanishi to'liq (balandlik, orqaga, titroq) OK")


def test_darvoza():
    """Panel ma'lumoti FAQAT kirishdan keyin ko'rsatiladi."""
    # Uchala ekran ham bor va ikkitasi boshidan yopiq.
    assert '<div class="shell" id="shell" hidden>' in HTML
    assert '<div class="gate" id="xato" hidden>' in HTML
    assert '<div class="gate" id="yuklash">' in HTML, "yuklash ekrani boshida ochiq bo'lsin"
    assert '<nav class="tabbar" id="tabbar" hidden>' in HTML, \
        "tab-panel kirishdan oldin ko'rinmasligi kerak"
    # Kirish `/api/session` dan boshlanadi, cookie esa zaxira.
    assert '"/api/session"' in JS and '"/api/me"' in JS
    assert JS.index('"/api/session"') < JS.index('"/api/me"'), \
        "avval yangi imzo, keyin cookie — tartib teskari"
    print("[8] panel ma'lumoti faqat kirishdan keyin ko'rsatiladi OK")


if __name__ == "__main__":
    test_ekranlar()
    test_telefonda_qamrov()
    test_sub_tablar()
    test_logo()
    test_id_lar()
    test_fayllar_ulangan()
    test_telegram_ulanishi()
    test_darvoza()
    print("\nweb panel: barcha tekshiruvlar o'tdi (8/8).")
