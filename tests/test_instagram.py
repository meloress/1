# -*- coding: utf-8 -*-
"""Instagram poydevori — Telegram'ga tegmaslik qo'riqchisi.

Shakl: mustaqil assert-skript, `PYTHONIOENCODING=utf-8 python tests/test_instagram.py`.
"""
import asyncio
import hashlib
import hmac
import json
import sys
from pathlib import Path

ILDIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ILDIZ))

from tests._manba import kod
from web import instagram as ig


def _soxta_sorov(query=None, headers=None, tana=b""):
    class Q:
        def __init__(self, q):
            self._q = q or {}

        def get(self, k, d=""):
            return self._q.get(k, d)

    class R:
        def __init__(self):
            self.query = Q(query)
            self.headers = headers or {}

        async def read(self):
            return tana

    return R()


def main():
    n = 0

    def ok(shart, izoh):
        nonlocal_n = [0]
        assert shart, izoh
        print(f"[{izoh}] OK")

    # 1 — to'g'ri imzo o'tadi
    n += 1
    sir = "sinov-siri"
    tana = json.dumps({"object": "instagram"}).encode()
    imzo = "sha256=" + hmac.new(sir.encode(), tana, hashlib.sha256).hexdigest()
    ok(ig.imzo_togri(tana, imzo, sir) is True, f"{n}")

    # 2 — noto'g'ri imzo o'tmaydi
    n += 1
    ok(ig.imzo_togri(tana, "sha256=0" * 11, sir) is False, f"{n}")

    # 3 — bo'sh kirishlar o'tmaydi
    n += 1
    ok(ig.imzo_togri(b"", imzo, sir) is False, f"{n}")
    n += 1
    ok(ig.imzo_togri(tana, imzo, "") is False, f"{n}")
    n += 1
    ok(ig.imzo_togri(tana, "md5=abc", sir) is False, f"{n}")

    # 4 — sir sozlanmagan bo'lsa POST 404 (Meta tekshiruvi ham topmaydi)
    n += 1
    import os
    os.environ.pop("IG_APP_SECRET", None)
    try:
        from core import config as cfg
        eski = getattr(cfg, "IG_APP_SECRET", "")
        cfg.IG_APP_SECRET = ""
    except Exception:
        eski = None
    javob = asyncio.run(ig.qabul(_soxta_sorov(tana=tana)))
    ok(javob.status == 404, f"{n}")
    if eski is not None:
        cfg.IG_APP_SECRET = eski

    # 5 — sir bor, imzo noto'g'ri bo'lsa 403
    n += 1
    os.environ["IG_APP_SECRET"] = sir
    javob = asyncio.run(ig.qabul(
        _soxta_sorov(headers={"X-Hub-Signature-256": "sha256=yolgon"}, tana=tana)))
    ok(javob.status == 403, f"{n}")

    # 6 — to'g'ri imzo + instagram object → ok
    n += 1
    javob = asyncio.run(ig.qabul(
        _soxta_sorov(headers={"X-Hub-Signature-256": imzo}, tana=tana)))
    ok(javob.status == 200, f"{n}")
    os.environ.pop("IG_APP_SECRET", None)

    # 7 — instagram bo'lmagan object → 404 (begona event javobsiz)
    n += 1
    os.environ["IG_APP_SECRET"] = sir
    begona = json.dumps({"object": "page"}).encode()
    bimzo = "sha256=" + hmac.new(sir.encode(), begona, hashlib.sha256).hexdigest()
    javob = asyncio.run(ig.qabul(
        _soxta_sorov(headers={"X-Hub-Signature-256": bimzo}, tana=begona)))
    ok(javob.status == 404, f"{n}")
    os.environ.pop("IG_APP_SECRET", None)

    # 8 — web/instagram.py da SQL yo'q (panel qoidasi: SQL faqat db/database.py)
    n += 1
    matn = kod(ILDIZ / "web" / "instagram.py").upper()
    ok("SELECT" not in matn and "INSERT" not in matn and "UPDATE" not in matn, f"{n}")

    # 9 — instagram_* SQL larda owner_id filtri bor
    n += 1
    dbkod = kod(ILDIZ / "db" / "database.py")
    import ast
    daraxt = ast.parse(dbkod)
    muammo = []
    for tug in ast.walk(daraxt):
        if isinstance(tug, (ast.FunctionDef, ast.AsyncFunctionDef)) and tug.name.startswith("instagram_"):
            parch = ast.get_source_segment(dbkod, tug) or ""
            if "owner_id" not in parch:
                muammo.append(tug.name)
    ok(not muammo, f"{n} {muammo}")

    # 10 — konfig standartlari bor
    n += 1
    from core import config as cfg2
    ok(hasattr(cfg2, "IG_VERIFY_TOKEN") and hasattr(cfg2, "IG_APP_SECRET")
       and hasattr(cfg2, "IG_MATN_MAX"), f"{n}")

    # 11 — event parse: matnli o'tadi, echo/bo'sh/matnsiz tushadi
    n += 1
    from handlers import instagram as hi
    hodisa = {"object": "instagram", "entry": [
        {"messaging": [
            {"sender": {"id": "111"}, "message": {"mid": "m1", "text": "  Salom  "}},
            {"sender": {"id": "111"}, "message": {"mid": "m2", "text": "   "}},
            {"sender": {"id": "222"}, "message": {"mid": "m3", "is_echo": True, "text": "o'zim"}},
            {"sender": {"id": ""}, "message": {"mid": "m4", "text": "kimsasiz"}},
            {"sender": {"id": "333"}, "message": {"mid": "m5"}},
        ]},
        "not-a-dict",
    ]}
    xabarlar = hi.hodisadan_xabarlar(hodisa)
    ok(len(xabarlar) == 1 and xabarlar[0]["sender"] == "111"
       and xabarlar[0]["matn"] == "Salom", f"{n}")

    # 12 — matn kesiladi (IG plain kanal)
    n += 1
    ok(len(hi.matn_tozala("a " * 2000)) <= cfg2.IG_MATN_MAX, f"{n}")

    # 13 — yuborish: bo'sh kirish hech qayerga bormaydi
    n += 1
    ok(asyncio.run(hi.yubor("", "111", "salom")) == (False, "bo'sh"), f"{n}")

    # 14 — yuborish: fake post orqali ok va xato yo'llari
    n += 1
    async def _ok(url, yuk, sar):
        assert "/me/messages" in url
        assert yuk["recipient"] == {"id": "111"}
        assert "TOKEN" not in str(sar), "token test sarlavhasiga chiqmasin"
        return {"message_id": "mid-1"}
    ok(asyncio.run(hi.yubor("TOKEN", "111", "salom", _post=_ok)) == (True, ""), f"{n}")
    n += 1
    async def _xato(url, yuk, sar):
        return {"error": {"message": "oyna yopiq"}}
    nat = asyncio.run(hi.yubor("TOKEN", "111", "salom", _post=_xato))
    ok(nat[0] is False and "oyna" in nat[1], f"{n}")

    # 15 — handlers/instagram.py da SQL yo'q
    n += 1
    hkod = kod(ILDIZ / "handlers" / "instagram.py").upper()
    ok("SELECT" not in hkod and "INSERT" not in hkod and "UPDATE" not in hkod, f"{n}")

    # 16 — web/instagram.py da SQL yo'q (qabul faqat db modulini chaqiradi)
    n += 1
    wkod = kod(ILDIZ / "web" / "instagram.py").upper()
    ok("SELECT" not in wkod and "INSERT" not in wkod and "UPDATE" not in wkod, f"{n}")

    # 17 — ID tekshiruvi (faqat raqam, 5-25)
    n += 1
    ok(hi._raqam_mi("123456") is True and hi._raqam_mi("abc") is False
       and hi._raqam_mi("1234") is False and hi._raqam_mi("12 34") is False, f"{n}")

    # 18 — ulash ekrani: ulanmaganga 3 qadam, ulanganga IG ID
    n += 1
    ulanmagan = hi.ekran_matni(None)
    ulangan = hi.ekran_matni({"yoqilgan": True, "ig_id": "999"})
    ok("IG ID" in ulanmagan and "Professional" in ulanmagan
       and "999" in ulangan and "Ulanmagan" not in ulangan, f"{n}")

    # 19 — qoralama matni mijoz HTML'ini qochiradi (mijoz matni — ishonchsiz)
    n += 1
    qm = hi.qoralama_matni("1", "<b>salom</b>")
    ok("<b>salom</b>" not in qm and "&lt;b&gt;salom&lt;/b&gt;" in qm, f"{n}")

    # 20 — karta tugmalari `bz:` ichida (alohida buyruq/namespace yo'q)
    n += 1
    bkod = kod(ILDIZ / "handlers" / "instagram.py")
    ok("bz:igj:" in bkod and "bz:igx:" in bkod
       and "ig:y:" not in bkod and "ig:ulash" not in bkod, f"{n}")

    # 21 — javob yuborish: ulanishsiz hech narsa ketmaydi
    n += 1
    import db.database as db
    _orig_ol = db.instagram_ulanish_ol

    async def _yoq(oid):
        return None
    db.instagram_ulanish_ol = _yoq
    nat = asyncio.run(hi.javob_yubor(1, "111", "salom"))
    ok(nat == (False, "Instagram uzilgan."), f"{n} {nat}")

    # 22 — javob yuborish: fake ulanish + fake post → tarixga yozadi
    n += 1
    yozilgan = []

    async def _bor(oid):
        return {"owner_id": oid, "ig_id": "9", "page_id": "8",
                "sahifa_token": "TOK", "yoqilgan": True}

    async def _yoz(oid, sid, rol, matn):
        yozilgan.append((oid, sid, rol, matn))
    _orig_yoz = db.instagram_xabar_yoz
    db.instagram_ulanish_ol = _bor
    db.instagram_xabar_yoz = _yoz

    async def _ok2(url, yuk, sar):
        return {"message_id": "mid-1"}
    _orig_yubor = hi.yubor

    async def _yubor_ok(tok, sid, matn, _post=None):
        assert tok == "TOK" and sid == "111" and matn == "salom"
        return True, ""
    hi.yubor = _yubor_ok
    nat = asyncio.run(hi.javob_yubor(1, "111", "  salom  "))
    ok(nat == (True, "IG'ga yuborildi")
       and yozilgan == [(1, "111", "assistent", "salom")], f"{n} {nat}")
    db.instagram_ulanish_ol = _orig_ol
    db.instagram_xabar_yoz = _orig_yoz
    hi.yubor = _orig_yubor

    # 21 — Sozlamalarda Instagram tugmasi bor (`/biznes` → Sozlamalar)
    n += 1
    mkod = kod(ILDIZ / "handlers" / "biznes.py")
    ok('"bz:ig"' in mkod and "bz:igu" in mkod and "bz:iguz" in mkod
       and "process_ig_token" in mkod, f"{n}")

    # 22 — alohida /instagram buyrug'i yo'q (ega qarori: Sozlamalar ichida)
    n += 1
    akod = kod(ILDIZ / "main.py")
    ok('Command("instagram")' not in akod and "instagram_module" not in akod, f"{n}")

    print(f"JAMI: {n} tekshiruv — hammasi OK")


if __name__ == "__main__":
    main()
