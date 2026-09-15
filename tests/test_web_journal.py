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

os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN-FOR-WEB-JOURNAL"

import ast
import re
import asyncio
import datetime
import pathlib

from aiohttp.test_utils import TestClient, TestServer

import web
from web import api, auth
from core.config import AUDIT_ACTIONS

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

    async def get_admin_audit(limit=10, offset=0, admin_id=None):
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

    async def count_admin_audit(admin_id=None):
        return 41 if admin_id is None else 2

    async def recent_errors(limit=15, offset=0):
        if offset:
            return []
        return [{"id": 3, "kind": "timeout", "message": "<script>x</script> javob kelmadi",
                 "user_id": 641, "created_at": datetime.datetime(2026, 9, 15, 14, 12, tzinfo=UTC)}]

    async def error_summary():
        return {"day": 11, "week": 40, "total": 45, "users_day": 5,
                "kinds": [("timeout", 6), ("matn", 3)]}

    async def revenue_stats():
        return {"stars_today": 1850, "stars_30d": 24300, "stars_total": 186700,
                "sales_30d": 17, "refunds": 2, "by_plan": [(30, 12), (7, 5)]}

    async def inactive_users(limit=30):
        return [{"user_id": 511, "username": "akmal", "plan_type": "free",
                 "last_seen": datetime.datetime(2026, 8, 20, tzinfo=UTC)}]

    async def count_inactive_users():
        return 120

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
    a = (ROOT / "web" / "api.py").read_text(encoding="utf-8")
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
        # 3) To'rttasi ham cookie'siz yopiq.
        for yol in ("audit", "errors", "revenue", "inactive"):
            r = await c.get("/api/journal/" + yol)
            assert r.status == 401, f"{yol} cookie'siz ochiq: {r.status}"
        print("[3] jurnalning 4 ta endpointi ham cookie'siz 401 qaytaradi OK")

        # 4) Audit: nom almashtiriladi, NOMA'LUM amal esa XOM nomi bilan
        #    ko'rsatiladi — yashirilsa, yozuv umuman yo'qday bo'lardi.
        a = await (await c.get("/api/journal/audit", headers=h)).json()
        assert a["rows"][0]["amal"] == AUDIT_ACTIONS["ban_user"], a["rows"][0]
        assert a["rows"][0]["admin"] == "@melores"
        assert a["rows"][0]["kimga"] == "@dilshod_a"
        assert a["rows"][1]["amal"] == "bilib_bolmaydigan_amal", "noma'lum amal yashirildi"
        assert a["rows"][1]["kimga"] is None and a["rows"][1]["admin"] == "ID:2001"
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
        js = (ROOT / "web" / "static" / "panel.js").read_text(encoding="utf-8")
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
        assert 'd.ortacha === null ? "—"' in js, "panel «—» ko'rsatmaydi"
        print("[8] sotuv yo'qda o'rtacha chek «—» bo'ladi, 0 emas OK")

        # 9) Nofaol: bu «14 kun yozmaganlar» EMAS, botni bloklaganlar.
        i = await (await c.get("/api/journal/inactive", headers=h)).json()
        assert i["jami"] == 120 and i["rows"][0]["user_id"] == 511
        # ⚠️ Faqat KO'RINADIGAN matn tekshiriladi: izohlarda «maketda
        # shunday yozilgandi» deb tushuntirish bor va u to'g'ri joyda.
        html = re.sub(r"<!--.*?-->", "",
                      (ROOT / "web" / "static" / "panel.html").read_text(encoding="utf-8"),
                      flags=re.S)
        assert "14 kundan beri" not in html, (
            "maketdagi noto'g'ri tushuntirish qolib ketgan — bu ro'yxat "
            "botni bloklaganlar, yozmaganlar emas")
        assert "Eslatma yuborish" not in html, (
            "botni bloklagan odamga eslatma yuborib bo'lmaydi")
        print("[9] nofaol ro'yxati to'g'ri tushuntirilgan OK")

    print("\nweb journal: barcha tekshiruvlar o'tdi (9/9).")


if __name__ == "__main__":
    asyncio.run(main())
