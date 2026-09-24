"""Panelning KO'RINISHI uchun tuzilma tekshiruvlari.

Bu fayl ham jonli shikoyatdan tug'ildi — telefondagi olti ekrandan.
Muammolarning hammasi bitta turkumda edi: panel kompyuterda yasalgan va
telefonda sinalmagan. Jadvalning oxirgi ustuni ekrandan chiqib ketardi,
«Saqlash» tugmalari o'ng chetda kesilardi, pastki navigatsiya oxirgi
kartochkani yopib turardi, kulrang izohlar esa o'qilmas darajada xira
edi.

Brauzer va skrinshot bu yerda yo'q, shuning uchun tekshiriladigan narsa
— QOIDANING O'ZI: jadval yo'qmi, `--nav-h` hisobga olinganmi, rang
tokenlari ikkala temada ham to'liqmi, kontrast yetarlimi. Bular
«chiroyli ko'rinadimi» degan savolga javob bermaydi, lekin aynan
yuqoridagi oltita xatoning qaytishini to'sadi.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_panel_korinish.py
"""

import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-PANEL-LOOK")

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "web" / "static"
HTML = (STATIC / "panel.html").read_text(encoding="utf-8")
CSS = (STATIC / "panel.css").read_text(encoding="utf-8")
JS = (STATIC / "panel.js").read_text(encoding="utf-8")
SOZ = (STATIC / "soz.js").read_text(encoding="utf-8")

# Izohsiz HTML — tekshiriladigan narsa EKRANDA ko'rinadigani.
KORINADIGAN = re.sub(r"<!--.*?-->", "", HTML, flags=re.S)
# Izohsiz CSS — xuddi shu sabab: izohda «#FFFFFF» yozilgan bo'lishi mumkin.
CSS_SOF = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def _blok(nom: str) -> str:
    """CSS selektorining tanasi."""
    i = CSS_SOF.index(nom)
    return CSS_SOF[i:CSS_SOF.index("}", i)]


def _rang(blok: str, token: str):
    m = re.search(re.escape(token) + r"\s*:\s*(#[0-9A-Fa-f]{6})", blok)
    return m.group(1) if m else None


def _yorqinlik(hex_rang: str) -> float:
    """WCAG nisbiy yorqinligi."""
    def kanal(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r = int(hex_rang[1:3], 16), int(hex_rang[3:5], 16), int(hex_rang[5:7], 16)
    return 0.2126 * kanal(r[0]) + 0.7152 * kanal(r[1]) + 0.0722 * kanal(r[2])


def _kontrast(a: str, b: str) -> float:
    la, lb = _yorqinlik(a), _yorqinlik(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def main() -> None:
    # ── 1) JADVAL YO'Q ──────────────────────────────────────────
    # ⚠️ Har ro'yxat `<table>` ichida, `overflow-x:auto` bilan turardi.
    # Telefonda bu — oxirgi ustun ekrandan tashqarida degani: «Oxirgi
    # faollik» ham, «Saqlash» tugmalari ham. Admin u yerda nimadir
    # borligini bilmasdi ham.
    assert "<table" not in KORINADIGAN, "jadval qaytib kelgan — telefonda ustun kesiladi"
    assert "tbl-wrap" not in CSS_SOF and "tbl-wrap" not in KORINADIGAN, \
        "gorizontal siljitadigan o'ram qaytib kelgan"
    assert ".rows" in CSS_SOF and "--ust" in CSS_SOF, "ro'yxat tuzilmasi yo'q"
    # Faqat sub-tablar siljiy oladi (ular ataylab yonga siljiydi).
    siljish = re.findall(r"([.#][\w-]+)\{[^}]*overflow-x:auto", CSS_SOF)
    assert set(siljish) <= {".subtabs"}, f"gorizontal siljiydigan blok: {siljish}"
    print("[1] jadval yo'q, gorizontal siljish faqat sub-tablarda OK")

    # ── 2) PASTKI NAVIGATSIYA KONTENTNI YOPMAYDI ────────────────
    # §2.6: nav `position:fixed`, ya'ni kontent uning balandligi
    # + qurilma chekkasi qadar pastdan bo'shatilishi SHART.
    assert "--nav-h:" in CSS_SOF, "navigatsiya balandligi token emas"
    wrap = re.search(r"\.wrap\{[^}]*padding:[^;]*calc\(var\(--nav-h\)[^;]*var\(--past\)", CSS_SOF)
    assert wrap, "kontent pastdan nav balandligicha bo'shatilmagan"
    assert "env(safe-area-inset-bottom" in CSS_SOF and "env(safe-area-inset-top" in CSS_SOF, \
        "qurilma xavfsiz chekkalari hisobga olinmagan"
    assert "calc(6px + var(--past))" in CSS_SOF, "nav o'zi xavfsiz chekkani hisobga olmayapti"
    print("[2] kontent pastki navigatsiya + xavfsiz chekka qadar bo'shatilgan OK")

    # ── 3) IKKALA TEMA HAM TO'LIQ ───────────────────────────────
    # ⚠️ Qoida: hech bir rang FAQAT media-so'rov ichida ta'riflanmasin.
    # Aks holda `data-tema` qo'yilgan mijozda o'sha rang umuman yo'q
    # bo'lib qoladi va element bo'yalmagan holda chiqadi.
    qorongi = _blok(":root{")
    yorug = _blok(':root[data-tema="light"]{')
    tokenlar = set(re.findall(r"(--[a-z0-9-]+)\s*:", qorongi))
    ranglar = {t for t in tokenlar if _rang(qorongi, t)}
    yetmaydi = {t for t in ranglar if not re.search(re.escape(t) + r"\s*:", yorug)}
    assert not yetmaydi, f"yorug' temada ta'riflanmagan rang: {yetmaydi}"
    assert "@media (prefers-color-scheme:light)" in CSS_SOF, \
        "brauzerda tema tanlanmaydi (Telegramdan tashqarida ochilishi mumkin)"
    assert 'tg.onEvent("themeChanged", tema)' in JS, "tema o'zgarishiga obuna yo'q"
    assert 'setAttribute("data-tema", t)' in JS, "Telegram temasi qo'llanmaydi"
    print(f"[3] {len(ranglar)} ta rang ikkala temada ham ta'riflangan OK")

    # ── 4) ⭐ KONTRAST — WCAG AA (4.5:1) ─────────────────────────
    # ⚠️ Eski `--ink-3` (#6E6A8A) kartochka fonida 3.7:1 edi, ya'ni AA
    # dan past. Bu paneldagi HAMMA izohga tegishli edi: «so'nggi 24
    # soat», «yoqilgan bo'lsa bot javob bermaydi», jadval sarlavhalari.
    for tema_nomi, blok in (("qorong'i", qorongi), ("yorug'", yorug)):
        yuza = _rang(blok, "--panel")
        # `--azure` matn rangi sifatida ham ishlatiladi (toastdagi
        # «Bekor qilish»), ya'ni u ham AA dan o'tishi kerak.
        for token, chegara in (("--ink-3", 4.5), ("--ink-2", 4.5),
                               ("--ink", 4.5), ("--azure", 4.5)):
            k = _kontrast(_rang(blok, token), yuza)
            assert k >= chegara, f"{tema_nomi} temada {token} kontrasti {k:.2f}:1 (< {chegara})"
    print("[4] izoh matnlari ikkala temada ham WCAG AA dan o'tadi OK")

    # ── 5) QOTIRILGAN RANG YO'Q ─────────────────────────────────
    # Token blokidan tashqarida `#rrggbb` qolmasin — aks holda u
    # yorug' temada o'zgarmaydi va qora fonda qora matn chiqadi.
    tashqari = CSS_SOF
    for b in (qorongi, yorug, _blok("@media (prefers-color-scheme:light)")):
        tashqari = tashqari.replace(b, "")
    # `--grad` va SVG gradienti ataylab literal — ular brend rangi va
    # ikkala temada ham bir xil turadi.
    qolgan = [h for h in re.findall(r"#[0-9A-Fa-f]{6}", tashqari)
              if h.upper() not in ("#C724FF", "#7B5CFF", "#2BB3FF", "#FFFFFF")]
    assert not qolgan, f"token bo'lmagan rang: {set(qolgan)}"

    # ⚠️ Server ham rang EMAS, token nomi yuboradi (`TARIF_RANGI`).
    # O'sha tokenlar CSS da haqiqatan bor bo'lishi kerak: bo'lmasa
    # tarif doirasi umuman bo'yalmay qoladi va buni hech narsa
    # aytmaydi — `background:var(--yo-q)` jimgina o'tib ketadi.
    from core.config import TARIF_RANGI
    for kalit, qiymat in TARIF_RANGI.items():
        assert qiymat.startswith("var(--"), f"{kalit}: serverda qotirilgan rang {qiymat}"
        token = qiymat[4:-1]
        assert _rang(qorongi, token), f"{token} qorong'i temada yo'q"
        assert _rang(yorug, token), f"{token} yorug' temada yo'q"
    print("[5] ranglar faqat tokenlarda, server ham token nomi yuboradi OK")

    # ── 6) LUG'AT ───────────────────────────────────────────────
    # §5: matnlar bitta faylda. Ro'yxatlar esa SERVERDAN — ular botga
    # ham tegishli va ikkinchi nusxa bo'lishi mumkin emas.
    assert '<script src="/static/soz.js"></script>' in HTML, "lug'at ulanmagan"
    assert HTML.index("soz.js") < HTML.index("panel.js"), \
        "lug'at panel.js dan KEYIN ulangan — u yuklanmasdan ishlatiladi"
    assert "window.SOZ" in SOZ and "var S = window.SOZ;" in JS
    # Panel tarif nomlarini O'YLAB TOPMASIN.
    assert 'ol("/api/meta")' in JS, "panel yagona ro'yxatni serverdan olmayapti"
    assert not re.search(r'PLAN\s*=\s*\{', JS), "tarif nomlarining nusxasi qaytib kelgan"
    for eski in ("guest", "Userlar"):
        assert eski not in KORINADIGAN, f"aralash so'z ekranda qolgan: {eski}"
    # Nav va sahifa sarlavhasi bir xil so'zni ishlatsin.
    assert "Sozlama<" not in KORINADIGAN, "nav «Sozlama», sahifa «Sozlamalar» — bir xil qilinsin"
    print("[6] matnlar lug'atda, ro'yxatlar serverdan, so'zlar bir xil OK")

    # ── 7) CHIP VA YORLIQ QATOR O'RTASIDA BO'LINMAYDI ───────────
    # §2.4: «BEHRUZ -> 1 ta» ikki qatorga bo'linib, chetlari singan
    # ko'rinardi.
    tag = _blok(".tag{")
    assert "white-space:nowrap" in tag, "yorliq bo'linib ketishi mumkin"
    chip = _blok(".chip{")
    assert "white-space:nowrap" in chip, "chip bo'linib ketishi mumkin"
    assert "flex-wrap:wrap" in _blok(".chips{"), "chiplar o'ramaydi — kesiladi"
    assert "flex-wrap:wrap" in _blok(".row{"), "qator o'ramaydi — ustun kesiladi"
    print("[7] chip va yorliqlar butunligicha yangi qatorga o'tadi OK")

    # ── 8) SANA — QISQA VA NISBIY ───────────────────────────────
    # §2.7: to'liq sana telefonda ikki qatorga bo'linib, qatorni ikki
    # barobar baland qilardi.
    for fn in ("function nisbiy(", "function qisqa(", "function kunNomi("):
        assert fn in JS, f"sana formatlagichi yo'q: {fn}"
    assert "toLocaleString" not in JS.split("function son(")[1].split("}")[0].replace(
        'toLocaleString("ru-RU")', ""), "raqam formati o'zgarib ketgan"
    # Server tayyor satr EMAS, ISO yubormoqda.
    api = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
    assert "isoformat(timespec=" in api, "server hali ham tayyor sana satrini yuborayapti"
    assert '%d.%m.%Y %H:%M' not in api, "serverda sana formati qolgan"
    print("[8] sanalar serverda ISO, panelda qisqa/nisbiy shaklda OK")

    # ── 9) TELEGRAM: IMZO, MAINBUTTON, SWIPE ────────────────────
    assert '"X-Telegram-Init-Data"' in JS, "so'rovlarda Telegram imzosi yo'q"
    # Har bir `fetch` imzoni olib ketsin.
    # ⚠️ Sarlavha chaqiruvning O'Z qatorida bo'lishi shart emas
    # (`so_rov()` uni yuqorida `cfg` ichiga yig'adi), shuning uchun
    # atrofdagi bir necha qator ko'riladi. `/api/session` — yagona
    # istisno: u imzoni tanada yuboradi, chunki cookie hali yo'q.
    qatorlar = JS.splitlines()
    for n, qator in enumerate(qatorlar, 1):
        if "fetch(" not in qator or "/api/session" in qator:
            continue
        atrof = "\n".join(qatorlar[max(0, n - 7):n + 1])
        assert "imzo(" in atrof, f"panel.js:{n} — imzosiz so'rov: {qator.strip()}"
    assert "disableVerticalSwipes" in JS, "ro'yxatni siljitganda ilova yopiladi"
    assert "safeAreaInset" in JS and "contentSafeAreaInset" in JS
    assert "tg.MainButton" in JS and "asosiyTugma(" in JS, "pastdagi Saqlash tugmasi yo'q"
    # §3.4: muvaffaqiyatdan keyin haptik + toast + bekor qilish.
    assert "notificationOccurred" in JS, "haptik javob yo'q"
    assert "function toast(" in JS and "bekorFn" in JS, "«Bekor qilish» yo'q"
    print("[9] har so'rovda imzo, MainButton, swipe va safe-area joyida OK")

    # ── 10) SKELET, BO'SH VA XATO HOLATLARI ─────────────────────
    assert "function skelet(" in JS and ".skelet" in CSS_SOF, "yuklanish skeleti yo'q"
    assert "function boshHolat(" in JS, "bo'sh holat matni yo'q"
    assert "function xatoHolat(" in JS and "S.qaytaUrinish" in JS, \
        "xato holatida «Qayta urinish» tugmasi yo'q"
    assert "function yangilandiBelgisi(" in JS, "«Yangilandi: HH:MM» yo'q"
    # Bo'sh holat matnlari lug'atda va hammasi to'ldirilgan.
    ishlatilgan = set(re.findall(r"S\.bosh\.(\w+)", JS))
    borlar = set(re.findall(r"^\s{4}(\w+):", SOZ.split("bosh: {", 1)[1].split("},", 1)[0], re.M))
    assert ishlatilgan <= borlar, f"lug'atda yo'q bo'sh holat: {ishlatilgan - borlar}"
    print("[10] skelet, bo'sh holat, xato + «Qayta urinish», «Yangilandi» bor OK")

    # ── 11) SENSORLI EKRAN QOIDALARI ─────────────────────
    # Uchalasi ham JONLI SHIKOYATDAN keyin yozilgan va uchalasi ham
    # ko'zga tashlanmay yo'qolib ketishi mumkin: hech narsa yiqilmaydi,
    # panel shunchaki «g'alati» bo'lib qoladi.

    # ⛔️ `user-scalable=no` QO'SHILMASIN — iOS uni e'tiborga olmaydi,
    # olganda ham ko'zi ojiz odam uchun zoom'ni butunlay o'ldirardi.
    # To'g'ri yechim `touch-action`, va u TUGMAGA emas, `html`/`body`
    # ga: shikoyat aynan MATN va BO'SH JOY ustida edi.
    assert "user-scalable" not in HTML, "viewport zoom'ni o'chirgan"
    assert re.search(r"html,\s*body\{[^}]*touch-action:\s*manipulation", CSS_SOF), (
        "touch-action html/body da emas — matn ustida double-tap zoom qoladi")

    # iOS fokusda zoom: 16px dan kichik maydon butun sahifani
    # kattalashtiradi va ORTGA QAYTARMAYDI.
    for sel in ("input,textarea,select{", ".field input{", ".kiritish{"):
        assert "max(16px" in _blok(sel), f"{sel} — iOS fokusda zoom qiladi"

    # Telefonda `:hover` bosilgandan KEYIN ham qolib ketadi — qator
    # rangli bo'lib turadi va odam uni «tanlangan» deb o'qiydi.
    tashqarida = re.findall(r"^[^@\s][^\r\n]*:hover", CSS_SOF, re.M)
    assert not tashqarida, f"hover media query TASHQARISIDA: {tashqarida}"
    assert "@media (hover:hover) and (pointer:fine)" in CSS_SOF, "hover bloki yo'q"

    # Ro'yxat oxirida siljish Telegram OYNASIGA o'tmasin.
    assert "overscroll-behavior-y:contain" in CSS_SOF, "overscroll ochiq"
    print("[11] touch-action, 16px input, hover media, overscroll OK")

    # ── 12) KOMPYUTERDA TO'LIQ EKRAN ─────────────────────
    # ⚠️ «web» DEGAN PLATFORMA QIYMATI YO'Q — Telegram Web ikkita:
    # `weba` va `webk`. «web» deb yozilsa shart HECH QACHON bajarilmaydi
    # va bag jimgina qoladi — buni faqat shunday tekshiruv tutadi.
    m = re.search(r"KENG_EKRAN = (\[[^\]]*\])", JS)
    assert m, "KENG_EKRAN ro'yxati yo'q"
    assert set(re.findall(r'"(\w+)"', m.group(1))) == {
        "tdesktop", "macos", "weba", "webk"}, m.group(1)
    assert "requestFullscreen" in JS and 'isVersionAtLeast("8.0")' in JS, (
        "to'liq ekran versiya tekshiruvisiz chaqirilyapti")
    print("[12] desktop/web mijozda to'liq ekran so'raladi OK")

    # ── 13) ⭐ XATO HOLATI KO'RINADIGAN JOYDA ─────────────
    # JONLI BAG: `/api/overview` 500 qaytarganda ekranda beshta statik
    # «—» qolardi va hech narsa «yuklanmadi» demasdi. Ikki sabab bor
    # edi va ikkalasi ham shu yerda qo'riqlanadi.

    # (a) Xato xabari BIRINCHI `.card` ichiga emas, `section` tepasiga.
    # Oltita ekranda birinchi `.card` KPI qatoridan KEYIN turadi, ya'ni
    # telefonda xabar ekrandan pastda qolardi.
    i = JS.index("function xatoQatori(")
    tana = JS[i:i + 700]
    # `"] .card` — aynan «section ichidagi birinchi .card ni top» degan
    # selektor. Element o'ziga `card` sinfini olishi mumkin, bu boshqa narsa.
    assert '"] .card' not in tana, (
        "xato xabari yana birinchi .card ichiga qo'yilyapti — u KPI "
        "qatoridan keyin turadi va telefonda ko'rinmaydi")
    assert "insertBefore" in tana or "prepend" in tana, (
        "xato xabari ekran TEPASIGA qo'yilmayapti")

    # (b) KPI raqamlari yuklanishdan oldin skelet ko'rsatadi — statik
    # «—» «hali kelmadi» va «yiqildi» ni FARQLAMAYDI.
    assert "function kpiSkelet(" in JS and ".skelet-kpi" in CSS_SOF, (
        "KPI skeleti yo'q")
    for ekran in ("boshqaruv", "statistika"):
        j = JS.index(f"async function {ekran}()")
        assert "kpiSkelet(" in JS[j:j + 300], f"{ekran}: KPI skeleti chaqirilmagan"
    print("[13] xato xabari ekran tepasida, KPI skeleti bor OK")

    print("\npanel ko'rinishi: barcha tekshiruvlar o'tdi (13/13).")


if __name__ == "__main__":
    main()
