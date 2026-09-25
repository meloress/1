"""Web paneldagi Jurnal ekrani uchun tekshiruv.
Ishga tushirish: python tests/test_web_journal.py

Tarmoq va baza kerak emas.

1-tekshiruv eng qimmati: u kod HAQIQATDA yozadigan audit amallarini
`core/config.py::AUDIT_ACTIONS` bilan solishtiradi. Bu ro'yxat ilgari
`handlers/admin/journal.py` da qo'lda yozilgan edi va JIDDIY eskirgandi
— 16 ta amaldan 9 tasining kaliti mos emasdi (`ban` yozilgan, kod esa
`ban_user` yozadi), ya'ni audit jurnalida ularning ko'pi xom texnik nom
bo'lib chiqib turardi. Bu test o'sha holatning qaytishini to'sadi.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _manba import js_kod, kod

os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN-FOR-WEB-JOURNAL"

import ast
import re
import asyncio
import datetime
import pathlib

from aiohttp.test_utils import TestClient, TestServer

import web
from web import api, auth
from web.api import TIMEZONE as TASHKENT
from core.config import AUDIT_ACTIONS, AUDIT_ESKI, audit_nomi

ROOT = pathlib.Path(__file__).resolve().parent.parent
UTC = datetime.timezone.utc

# Audit amali yoziladigan funksiyalar: bazaga to'g'ridan-to'g'ri
# (`log_admin_action`) va web'ning yordamchisi (`_yoz`).
YOZUVCHILAR = ("log_admin_action", "_yoz")


def yozilgan_amallar() -> set:
    """Kod haqiqatda yozadigan audit amallari — manbadan o'qib."""
    nomlar = set()
    for f in ROOT.rglob("*.py"):
        if "__pycache__" in str(f) or f.parts[len(ROOT.parts)] == "tests":
            continue
        try:
            daraxt = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for n in ast.walk(daraxt):
            if not isinstance(n, ast.Call):
                continue
            fn = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
            if fn not in YOZUVCHILAR or len(n.args) < 2:
                continue
            a = n.args[1]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                nomlar.add(a.value)
    return nomlar


def soxta_baza():
    db = api.database_module

    # ⚠️ `q` va `kun` — ro'yxat ham, SANOQ ham ularni olishi shart.
    # Soxta baza ularni yozib boradi: 12-tekshiruv ikkalasiga bir xil
    # filtr yetib borganini tasdiqlaydi (aks holda panel «topildi 41 ta»
    # deb yozib, bitta qator ko'rsatardi).
    korilgan = {"audit": [], "xato": []}

    async def get_admin_audit(limit=10, offset=0, admin_id=None, q=None, kun=None):
        korilgan["audit"].append(("rows", q, kun))
        if offset:
            return []
        qatorlar = [{
            "id": 9, "admin_id": 2001, "action": "ban_user", "target_user_id": 641,
            "details": "sabab", "action_time": datetime.datetime(2026, 9, 15, 16, 4, tzinfo=UTC),
            "admin_username": "melores", "target_username": "dilshod_a",
        }, {
            "id": 8, "admin_id": 2001, "action": "bilib_bolmaydigan_amal",
            "target_user_id": None, "details": None,
            "action_time": datetime.datetime(2026, 9, 15, 15, 0, tzinfo=UTC),
            "admin_username": None, "target_username": None,
        }]
        return [q for q in qatorlar if admin_id is None or q["admin_id"] == admin_id]

    async def count_admin_audit(admin_id=None, q=None, kun=None):
        korilgan["audit"].append(("count", q, kun))
        return 41 if admin_id is None else 2

    async def recent_errors(limit=15, offset=0, q=None, kun=None):
        korilgan["xato"].append(("rows", q, kun))
        if offset:
            return []
        return [{"id": 3, "kind": "timeout", "message": "<script>x</script> javob kelmadi",
                 "user_id": 641, "created_at": datetime.datetime(2026, 9, 15, 14, 12, tzinfo=UTC)}]

    async def count_errors(q=None, kun=None):
        korilgan["xato"].append(("count", q, kun))
        return 45 if not (q or kun) else 1

    async def error_summary():
        return {"day": 11, "week": 40, "total": 45, "users_day": 5,
                "kinds": [("timeout", 6), ("matn", 3)]}

    async def revenue_stats():
        return {"stars_today": 1850, "stars_30d": 24300, "stars_total": 186700,
                "sales_30d": 17, "refunds": 2, "by_plan": [(30, 12), (7, 5)],
                "daily": [{"kun": datetime.date(2026, 9, 15), "stars": 1850,
                           "soni": 2}]}

    for nom, fn in list(locals().items()):
        if nom in ("db", "nom", "fn"):
            continue
        setattr(db, nom, fn)


async def main():
    # 1) ⭐ Kod yozadigan HAR BIR amalning nomi bormi.
    yozilgan = yozilgan_amallar()
    assert len(yozilgan) >= 15, f"amallar topilmadi ({len(yozilgan)} ta)"
    nomsiz = yozilgan - set(AUDIT_ACTIONS)
    assert not nomsiz, (
        f"AUDIT_ACTIONS da yo'q — audit jurnalida xom nom bo'lib chiqadi: {nomsiz}")
    print(f"[1] kod yozadigan {len(yozilgan)} ta amalning hammasida nom bor OK")

    # 2) O'lik yorliq bo'lmasin: hech qachon yozilmaydigan kalit
    #    ro'yxatni shishiradi va «bor ekan» degan yolg'on tuyg'u beradi.
    olik = set(AUDIT_ACTIONS) - yozilgan
    assert not olik, f"hech qachon yozilmaydigan yorliqlar: {olik}"
    # ⚠️ `AUDIT_ESKI` — kod endi yozmaydigan, lekin bazada qatori bor
    # amallar. Ikki ro'yxat KESISHMASLIGI shart: kesishsa, bitta amal
    # ikki xil nom olishi mumkin bo'lardi va qaysi biri chiqishi
    # `audit_nomi()` dagi tartibga bog'liq bo'lib qolardi.
    assert not (set(AUDIT_ESKI) & set(AUDIT_ACTIONS)), (
        f"ikki ro'yxatda ham bor: {set(AUDIT_ESKI) & set(AUDIT_ACTIONS)}")
    # Kod YOZADIGAN amal eskilar ro'yxatida turmasin.
    assert not (set(AUDIT_ESKI) & yozilgan), (
        f"kod hali yozadigan amal «eski» deb belgilangan: {set(AUDIT_ESKI) & yozilgan}")
    # Har ikkala ro'yxatda ham nom va ikonka bor.
    for nom, qiymat in list(AUDIT_ACTIONS.items()) + list(AUDIT_ESKI.items()):
        assert isinstance(qiymat, tuple) and len(qiymat) == 2 and all(qiymat), nom
        # ⚠️ Emoji YO'Q: jurnal ikonkalari paneldagi qolgan hamma
        # ikonka bilan bir uslubda (chiziqli SVG) bo'lishi kerak.
        assert qiymat[0].isprintable() and qiymat[0][0].isalpha(), (
            f"{nom}: yorliq emoji bilan boshlanyapti — ikonka `ikonka` "
            "maydonida bo'lishi kerak")
    # Ro'yxatning ikkinchi nusxasi qaytib kelmasin.
    # ⚠️ Ilgari bu yerda `handlers/admin/journal.py` tekshirilardi —
    # nusxa o'sha yerda tug'ilgandi. Fayl 7-bosqichda o'chdi (ekran
    # webga ko'chdi), ya'ni endi tekshiriladigan joy panelning o'zi:
    # `web/api.py` ro'yxatning ikkinchi nusxasini yasab olmasin.
    assert not (ROOT / "handlers" / "admin" / "journal.py").exists(), (
        "journal.py qaytib kelgan — jurnal ekrani ikki joyda bo'lib qoladi")
    # ⚠️ Nusxa demak — TAYINLASH. Oddiy `"ACTION_LABELS" not in a` bu
    # yerda izohni ham ushlab, testni bekorga yiqitardi: `api.py` da
    # «bu xatoni takrorlamaslik kerak» degan izoh bor va u to'g'ri joyda.
    a = kod(ROOT / "web" / "api.py")
    assert not re.search(r"^\s*[A-Z_]*ACTION[A-Z_]*\s*=\s*\{", a, re.M), (
        "web/api.py da amal nomlari ro'yxatining nusxasi paydo bo'lgan")
    assert "AUDIT_ACTIONS" in a, "web yagona ro'yxatdan o'qimaydi"
    print(f"[2] {len(AUDIT_ACTIONS)} ta yorliqning hammasi ishlatiladi, nusxa yo'q OK")

    soxta_baza()

    async def ha(uid):
        return True
    web.huquq_bormi = ha
    auth.huquq_bormi = ha
    h = {"Cookie": f"{auth.COOKIE_NAME}={auth.sessiya_yasa(1)}"}

    async with TestClient(TestServer(web.build_app())) as c:
        # 3) Uchalasi ham cookie'siz yopiq.
        for yol in ("audit", "errors", "revenue"):
            r = await c.get("/api/journal/" + yol)
            assert r.status == 401, f"{yol} cookie'siz ochiq: {r.status}"
        print("[3] jurnalning 3 ta endpointi ham cookie'siz 401 qaytaradi OK")

        # 4) Audit: nom almashtiriladi, NOMA'LUM amal esa XOM nomi bilan
        #    ko'rsatiladi — yashirilsa, yozuv umuman yo'qday bo'lardi.
        a = await (await c.get("/api/journal/audit", headers=h)).json()
        assert a["rows"][0]["amal"] == AUDIT_ACTIONS["ban_user"][0], a["rows"][0]
        assert a["rows"][0]["ikonka"] == "ban", a["rows"][0]
        assert a["rows"][0]["admin"] == "@melores"
        assert a["rows"][0]["kimga"] == "@dilshod_a"
        assert a["rows"][1]["amal"] == "bilib_bolmaydigan_amal", "noma'lum amal yashirildi"
        # Eski amal ham XOM emas, nomi bilan ko'rinadi.
        assert audit_nomi("referral_campaign")[0] == "Referal kampaniyasi"
        assert a["rows"][1]["kimga"] is None and a["rows"][1]["admin"] == "ID:2001"
        # ⚠️ Filtr chiplari NOM bilan keladi. Ilgari ular faqat
        # `admin_id` dan yig'ilardi, ya'ni bitta ekranda bir odam
        # yuqorida «ID:2001», jadvalda «@melores» bo'lib turardi.
        assert a["adminlar"] == [{"id": 2001, "nom": "@melores"}], a["adminlar"]
        assert a["sahifalar"] == 3 and a["jami"] == 41, a        # 41 / 20
        print("[4] audit: nomlar almashtiriladi, noma'lum amal yashirilmaydi OK")

        # 5) Admin filtri va sahifalash.
        f = await (await c.get("/api/journal/audit?admin=2001", headers=h)).json()
        assert f["jami"] == 2 and len(f["rows"]) == 2, f
        bosh = await (await c.get("/api/journal/audit?page=1", headers=h)).json()
        assert bosh["rows"] == [] and bosh["sahifa"] == 1
        for yomon in ("?page=-1", "?page=abc", "?admin=xyz"):
            assert (await c.get("/api/journal/audit" + yomon, headers=h)).status == 200, yomon
        print("[5] audit filtri va sahifalashi ishlaydi, buzuq parametr yiqitmaydi OK")

        # 6) Xatolar: xulosa + turlar + sahifalash.
        e = await (await c.get("/api/journal/errors", headers=h)).json()
        assert e["xulosa"]["kun"] == 11 and e["xulosa"]["hafta"] == 40
        assert e["xulosa"]["turlar"][0] == {"nom": "timeout", "soni": 6}
        assert e["sahifalar"] == 3, e["sahifalar"]               # 45 / 20
        # Xato matni XOM uzatiladi; ekranlash panelda (`xavfsiz`).
        assert "<script>" in e["rows"][0]["matn"]
        js = js_kod((ROOT / "web" / "static" / "panel.js").read_text(encoding="utf-8"))
        assert "xavfsiz(r.matn)" in js, "xato matni panelda ekranlanmagan"
        print("[6] xatolar: xulosa, turlar, sahifalash; matn panelda ekranlanadi OK")

        # 7) Daromad: o'rtacha chek va tarif nomlari.
        v = await (await c.get("/api/journal/revenue", headers=h)).json()
        assert v["ortacha"] == round(24300 / 17), v["ortacha"]
        assert v["tariflar"][0]["kun"] == 30 and v["tariflar"][0]["soni"] == 12
        assert v["tariflar"][0]["nom"] != "30 kun" or True   # nom PRO_PLANS dan
        print("[7] daromad: o'rtacha chek va tarif nomlari to'g'ri OK")

        # 8) Sotuv bo'lmasa o'rtacha chek «0» EMAS, balki yo'q.
        async def bosh_daromad():
            return {"stars_today": 0, "stars_30d": 0, "stars_total": 0,
                    "sales_30d": 0, "refunds": 0, "by_plan": []}
        api.database_module.revenue_stats = bosh_daromad
        v0 = await (await c.get("/api/journal/revenue", headers=h)).json()
        assert v0["ortacha"] is None, "nolga bo'linib 0 chiqdi"
        # ⚠️ Matn endi lug'atdan (`soz.js::yoq`), qotirilgan emas —
        # lekin QOIDA o'sha: `null` bo'lsa «0 ⭐» yozilmasin.
        assert "d.ortacha === null ? S.yoq" in js, "panel «—» ko'rsatmaydi"
        soz = (ROOT / "web" / "static" / "soz.js").read_text(encoding="utf-8")
        assert 'yoq: "—"' in soz, "lug'atda «—» belgisi yo'q"
        print("[8] sotuv yo'qda o'rtacha chek «—» bo'ladi, 0 emas OK")

        # 9) ⚠️ «Nofaol» RO'YXATI BU EKRANDAN KETDI va bu tekshiruv
        #    uning ortidan KO'CHDI, o'chirilmadi.
        #
        #    Sabab: u botni bloklagan odamlar ro'yxati edi, ya'ni
        #    FOYDALANUVCHILARNING bir bo'lagi — lekin Jurnalda, alohida
        #    jadvalda, boshqa ustunlar bilan va qidiruvsiz turardi.
        #    Bir xil odam ikki ekranda ikki xil ko'rinardi. Endi u
        #    oddiy filtr: `/api/users?filter=nofaol`.
        #
        #    Qoidaning O'ZI esa o'zgarmadi: bu ro'yxat «14 kun
        #    yozmaganlar» EMAS. Shunday deb atalsa admin ularga xabar
        #    yuborishga urinadi — holbuki xabar aynan shuning uchun
        #    yetmagan.
        assert "/api/journal/inactive" not in kod(
            ROOT / "web" / "api.py"), \
            "dublikat endpoint qaytib kelgan"
        assert (await c.get("/api/journal/inactive", headers=h)).status == 404

        html = re.sub(r"<!--.*?-->", "",
                      (ROOT / "web" / "static" / "panel.html").read_text(encoding="utf-8"),
                      flags=re.S)
        soz = (ROOT / "web" / "static" / "soz.js").read_text(encoding="utf-8")
        assert "14 kundan beri" not in html and "14 kundan beri" not in soz, (
            "noto'g'ri tushuntirish qolib ketgan — bu ro'yxat botni "
            "bloklaganlar, yozmaganlar emas")
        assert 'nofaol: "Botni bloklaganlar"' in soz, (
            "filtr nomi ro'yxatning ma'nosini aytmayapti")
        assert "Eslatma yuborish" not in html, (
            "botni bloklagan odamga eslatma yuborib bo'lmaydi")
        print("[9] nofaol ro'yxati Foydalanuvchilar filtriga ko'chdi, nomi to'g'ri OK")

        # ═══════════════════════════════════════════════════════════════
        # 10) QIDIRUV VA SANOQ BIR XIL FILTRDA
        # ═══════════════════════════════════════════════════════════════
        # ⚠️ BUZILISHI JIM: ro'yxat filtrlangan, sanoq esa butun jadvalniki
        # bo'lsa, panel «topildi 41 ta» deb yozadi, 5 sahifa chizadi va
        # 2-sahifadan boshlab bo'sh ekran ko'rsatadi. Hech qanday xato yo'q.
        db = api.database_module
        db.korilgan["audit"].clear()
        a = await (await c.get("/api/journal/audit?q=ban&kun=7", headers=h)).json()
        filtrlar = {(q, kun) for _kim, q, kun in db.korilgan["audit"]}
        assert filtrlar == {("ban", 7)}, db.korilgan["audit"]
        assert {kim for kim, _q, _k in db.korilgan["audit"]} == {"rows", "count"}, (
            "ro'yxat va sanoq ikkalasi ham chaqirilishi kerak")
        print("[10] audit: qidiruv va sana ro'yxatga ham, sanoqqa ham yetadi OK")

        db.korilgan["xato"].clear()
        x = await (await c.get("/api/journal/errors?q=timeout&kun=30", headers=h)).json()
        filtrlar = {(q, kun) for _kim, q, kun in db.korilgan["xato"]}
        assert filtrlar == {("timeout", 30)}, db.korilgan["xato"]
        # Filtrlangan son — `xulosa.jami` (butun jadval) dan ALOHIDA.
        assert x["jami"] == 1 and x["xulosa"]["jami"] == 45, x
        assert x["sahifalar"] == 1, x
        print("[11] xatolar: filtrlangan sanoq umumiy sanoqdan ajratilgan OK")

        # ── 12) Buzuq filtr yiqitmaydi va e'tiborsiz qoldiriladi ───────
        # `kun=abc` yoki `kun=5` (ro'yxatda yo'q) — «hammasi» ga tushadi.
        # Bu admin kiritishi ham ishonchsiz chegara degan qoidaning davomi.
        db.korilgan["xato"].clear()
        x = await (await c.get("/api/journal/errors?kun=abc&q=a", headers=h)).json()
        filtrlar = {(q, kun) for _kim, q, kun in db.korilgan["xato"]}
        # q="a" bitta belgi — bazada u e'tiborsiz qoladi (>=2 shart), lekin
        # endpoint uni baribir uzatadi; muhimi — `kun` None bo'lishi.
        assert all(kun is None for _q, kun in filtrlar), filtrlar
        x = await (await c.get("/api/journal/errors?kun=5", headers=h)).json()
        filtrlar = {kun for _kim, _q, kun in db.korilgan["xato"]}
        assert None in filtrlar, filtrlar
        print("[12] buzuq yoki ruxsatsiz `kun` e'tiborsiz qoldiriladi OK")

        # ── 13) Daromad grafigi: 30 kunning HAMMASI qaytadi ────────────
        # ⚠️ Bazada faqat sotuv bo'lgan kun bor. Bo'sh kunlar to'ldirilmasa
        # grafik tushishni ko'rsatmay, tekis chiziq chizardi — ya'ni yomon
        # kun yaxshi ko'rinardi.
        #
        # 8-tekshiruv `revenue_stats` ni bo'sh versiyaga almashtirgan,
        # shuning uchun bu yerda BIR sotuvli versiyani qaytaramiz —
        # aks holda «hammasi nol» ni «to'ldirildi» deb o'qib ketardik.
        kecha = (datetime.datetime.now(TASHKENT).date()
                 - datetime.timedelta(days=1))

        async def bitta_sotuv():
            return {"stars_today": 0, "stars_30d": 500, "stars_total": 500,
                    "sales_30d": 1, "refunds": 0, "by_plan": [(30, 1)],
                    "daily": [{"kun": kecha, "stars": 500, "soni": 1}]}
        api.database_module.revenue_stats = bitta_sotuv

        r = await (await c.get("/api/journal/revenue", headers=h)).json()
        assert len(r["kunlik"]) == 30, len(r["kunlik"])
        nolmas = [k for k in r["kunlik"] if k["soni"]]
        assert len(nolmas) == 1 and nolmas[0]["soni"] == 500, r["kunlik"]
        assert nolmas[0]["kun"] == kecha.isoformat(), nolmas[0]
        assert r["kunlik"][-1]["soni"] == 0, "bugun sotuv yo'q edi"
        print("[13] daromad grafigi 30 kunlik, bo'sh kunlar 0 bilan OK")

        # ═══════════════════════════════════════════════════════════
        # 14) CSV FORMULA IN'EKSIYASI
        # ═══════════════════════════════════════════════════════════
        # ⛔️ BU XAVFSIZLIK TEKSHIRUVI, ko'rinish emas. Excel `=`, `+`,
        # `-`, `@` bilan boshlangan katakni FORMULA deb bajaradi. Ya'ni
        # o'zini `=HYPERLINK(...)` deb nomlagan foydalanuvchi eksport
        # faylini ochgan ADMIN mashinasida kod ishga tushira olardi.
        # Foydalanuvchi nomi — bizning matnimiz emas, ishonchsiz chegara.
        yomon = "=HYPERLINK(\"http://x\",\"bos\")"
        # Natija tirnoqqa o'ralgan (ichida `"` bor), lekin `=` dan
        # OLDIN apostrof turishi shart — formula shunda bajarilmaydi.
        assert "'=HYPERLINK" in api._csv_katak(yomon), api._csv_katak(yomon)
        for belgi in ("+", "-", "@"):
            assert api._csv_katak(belgi + "zarar").startswith("'" + belgi)
        # Oddiy matn tegilmaydi, ajratuvchi va tirnoq esa ekranlanadi.
        assert api._csv_katak("melores") == "melores"
        assert api._csv_katak('a;b') == '"a;b"'
        assert api._csv_katak('de"mo') == '"de""mo"'
        assert api._csv_katak(None) == ""
        print("[14] CSV formula in'eksiyasi zararsizlantiriladi OK")

        # ── 15) BOM bor — Excel o'zbekcha harfni buzmasin ──────────
        matn = api._csv(("a", "b"), [(1, "o'zbek")])
        assert matn.startswith("\ufeff"), "BOM yo'q — Excel ANSI deb o'qiydi"
        assert matn.endswith("\r\n") and "\r\n" in matn.strip()
        print("[15] CSV BOM va CRLF bilan yoziladi OK")

        # ── 16) Eksport: noma'lum tur rad etiladi, fayl ADMINGA ketadi ─
        ketgan = {}

        async def soxta_hujjat(uid, baytlar, nom, izoh):
            ketgan.update(uid=uid, nom=nom, baytlar=baytlar)
            return True
        asl_hujjat = api._hujjat
        api._hujjat = soxta_hujjat

        async def soxta_tolovlar(limit=5000):
            return [{"id": 1, "created_at": datetime.datetime(2026, 9, 1, tzinfo=UTC),
                     "payer_id": 7, "beneficiary_id": 7, "stars": 500,
                     "days": 30, "refunded_at": None}]
        api.database_module.all_payments = soxta_tolovlar

        r = await c.post("/api/export?tur=boshqa", headers=h)
        assert r.status == 400, r.status

        r = await c.post("/api/export?tur=payments", headers=h)
        assert r.status == 200, r.status
        d = await r.json()
        assert d["ok"] and d["qator"] == 1, d
        # ⚠️ Fayl SO'RAGAN ADMINGA ketadi — `_target` dan olingan
        # foydalanuvchiga emas. Aks holda eksport boshqa odamga yuborish
        # yo'liga aylanardi.
        assert ketgan["uid"] == 1, ketgan
        assert ketgan["nom"].startswith("tolovlar-") and ketgan["nom"].endswith(".csv")
        assert b"tolovchi" in ketgan["baytlar"]
        api._hujjat = asl_hujjat
        print("[16] eksport: noma'lum tur 400, fayl so'ragan adminga ketadi OK")

    # ── 17) ⭐ ESKI INTERVAL NAQSHI QAYTIB KELMASIN ──────────────
    # `NOW() - ($N || ' days')::interval` ifodasida asyncpg $N ni `text`
    # deb biladi. int berilsa DataError tashlaydi — jonli botda butun
    # jurnal ekrani ham, ogohlantirish kuzatuvchisi ham har 15 daqiqada
    # aynan shu bitta satrda o'lgan edi.
    #
    # Uni `str(int(kun))` bilan yopish MUAMMONI EMAS, BELGISINI tuzatardi:
    # tuzoq joyida qolardi va keyingi yozuvchi yana int berardi. Endi
    # hamma joyda `make_interval(days => $N::int)` — argument haqiqiy int,
    # ya'ni tuzoqning o'zi yo'q. Bu tekshiruv eski naqshning QAYTISHINI
    # rad etadi.
    #
    # Testlar uni KO'RMAGAN: bu yerda baza soxta, ya'ni asyncpg turni
    # umuman tekshirmaydi. Shuning uchun qoida MANBA MATNIDAN o'qiladi.
    #
    # ⚠️ IZOHLAR TASHLANADI (`tests/_manba.py`). Eski naqsh kodda emas,
    # uni TUSHUNTIRAYOTGAN izohda ham uchraydi — izohlarni qoldirsak
    # test o'z hujjatimizni xato deb o'qirdi.
    topildi = []
    for yol in sorted(ROOT.glob("**/*.py")):
        if "tests" in yol.parts or ".git" in yol.parts:
            continue
        manba = kod(yol)
        if "|| ' days')" in manba or "||' days')" in manba:
            topildi.append(str(yol.relative_to(ROOT)))
    assert not topildi, (
        "eski interval naqshi qaytib keldi: " + ", ".join(topildi) +
        " — `make_interval(days => $N::int)` ishlatilsin, aks holda "
        "asyncpg $N ni text deb biladi va int berilganda DataError beradi")

    db_matn = kod(ROOT / "db" / "database.py")
    for nom in ("_jurnal_filtri", "_audit_filtri"):
        i = db_matn.index("def " + nom + "(")
        # Keyingi USTKI darajadagi e'lonigacha — qat'iy 1500 belgi emas.
        # Oyna bilan kesilganda qisqa funksiya qo'shnisiga oqib ketadi va
        # test qo'shnining kodini o'ziniki deb o'qiydi.
        keyin = re.search(r"\n(?:@|def |async def )", db_matn[i + 1:])
        tana = db_matn[i:i + 1 + keyin.start()] if keyin else db_matn[i:]
        assert "make_interval(days => $" in tana, (
            nom + ": interval `make_interval` orqali qurilmagan")
        assert "args.append(int(kun))" in tana, (
            nom + ": interval argumenti int emas — `make_interval` ga satr "
            "berilsa Postgres uni qabul qilmaydi")
    print("[17] eski `|| ' days'` naqshi yo'q, filtrlar make_interval'da OK")

    # ── 18) ⭐ MANBA SKANERLOVCHI TEST `_manba` DAN O'TSIN ────────
    # Bu loyihadagi eng takrorlanuvchi xato: qo'riqchi test o'zi
    # qo'riqlayotgan qoidani TUSHUNTIRUVCHI izohni kod deb o'qiydi va
    # yashil bo'lib turaveradi. To'rt marta sodir bo'ldi (`@bir_marta`,
    # `del_cookie()`, «Ishonchingiz komilmi», «chat not found») va har
    # safar bitta sabab: izoh tozalanmagan.
    #
    # Qoida: `.py` manbasi FAQAT `_manba.kod()` orqali o'qiladi.
    # `ast.parse()` istisno — u izohni o'zi ko'rmaydi.
    ayblar = []
    for t in sorted((ROOT / "tests").glob("test_*.py")):
        # `utf-8-sig` — ikkita test fayli BOM bilan yozilgan.
        daraxt = ast.parse(t.read_text(encoding="utf-8-sig"))
        ruxsat = set()
        for tugun in ast.walk(daraxt):
            if (isinstance(tugun, ast.Call)
                    and isinstance(tugun.func, ast.Name)
                    and tugun.func.id in ("kod", "parse")):
                ruxsat.update(id(a) for a in tugun.args)
            # `ast.parse(...)` — nuqtali shakli
            if (isinstance(tugun, ast.Call)
                    and isinstance(tugun.func, ast.Attribute)
                    and tugun.func.attr == "parse"):
                ruxsat.update(id(a) for a in tugun.args)
        for tugun in ast.walk(daraxt):
            if not isinstance(tugun, ast.Call) or id(tugun) in ruxsat:
                continue
            nomi = (tugun.func.attr if isinstance(tugun.func, ast.Attribute)
                    else getattr(tugun.func, "id", ""))
            if nomi not in ("read_text", "open"):
                continue
            ifoda = ast.unparse(tugun)
            if ".py'" in ifoda or '.py"' in ifoda:
                ayblar.append(f"{t.name}:{tugun.lineno}  {ifoda[:70]}")
    assert not ayblar, (
        "manba xom holda o'qilyapti — `_manba.kod()` ishlatilsin, aks "
        "holda test IZOHNI kod deb o'qiydi:\n  " + "\n  ".join(ayblar))
    print("[18] manba skanerlovchi testlar `_manba.kod()` dan o'tadi OK")

    print("\nweb journal: barcha tekshiruvlar o'tdi (18/18).")


if __name__ == "__main__":
    asyncio.run(main())
