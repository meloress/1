"""Web panel darvozasi uchun qo'lda ishga tushiriladigan tekshiruv.
Ishga tushirish: python tests/test_web_auth.py

Tarmoq ham, baza ham kerak emas: soxta BOT_TOKEN qo'yiladi va
`huquq_bormi` (yagona DB tegadigan nuqta) almashtiriladi.

Nimani qo'riqlaydi — panel internetda OCHIQ turadi, ya'ni bu fayl
buzilsa butun admin paneli begonaga ochiladi:
  1) soxta imzo o'tmaydi;
  2) o'g'irlangan `initData` abadiy amal qilmaydi (5 daqiqa);
  3) imzo to'g'ri, lekin admin bo'lmagan odam kirolmaydi;
  4) cookie imzosi qalbakilashtirilganda sessiya tan olinmaydi.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ⚠️ Import'dan OLDIN: core.config tokenni modul yuklanganda o'qiydi.
os.environ["BOT_TOKEN"] = "123456:TEST-TOKEN-FOR-WEB-AUTH"

import asyncio
import hashlib
import hmac
import time
from urllib.parse import urlencode

from aiohttp.test_utils import TestClient, TestServer

import web
from web import auth

TOKEN = os.environ["BOT_TOKEN"]


def init_data_yasa(user_id: int, auth_date: int | None = None,
                   buzuq: bool = False) -> str:
    """Telegram qanday imzolasa — shunday. (Mini App tomonini taqlid qiladi.)"""
    user = '{"id":%d,"first_name":"Test"}' % user_id
    maydonlar = {"auth_date": str(auth_date or int(time.time())), "user": user}
    check = "\n".join(f"{k}={maydonlar[k]}" for k in sorted(maydonlar))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    imzo = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if buzuq:
        imzo = "0" * 64
    return urlencode({**maydonlar, "hash": imzo})


async def sorov(client, init_data):
    return await client.post("/api/session", json={"init_data": init_data})


async def main():
    # Bazaga tegadigan hamma joy almashtiriladi, ya'ni tekshiruv
    # Postgres'siz ishlaydi.
    #
    # ⚠️ `is_superadmin` / `get_admin_meta` ataylab XATO qaytaradi: ular
    # faqat chap kartochkadagi ism va rolni beradi, ya'ni baza uzilganda
    # ham kirish ISHLASHI kerak. Ilgari bu yerda haqiqiy chaqiruv
    # qolib ketgan edi va test mahalliy `.env` dagi jonli bazaga
    # jimgina bog'lanib, "tarmoqsiz" degan va'dasini buzgan edi.
    ruxsat = {"qiymat": True}

    async def soxta_huquq(user_id: int) -> bool:
        return ruxsat["qiymat"]

    async def baza_yiqilgan(*a, **k):
        raise RuntimeError("bu testda bazaga murojaat qilinmasin")

    web.huquq_bormi = soxta_huquq
    auth.huquq_bormi = soxta_huquq
    web.database_module.is_superadmin = baza_yiqilgan
    web.database_module.get_admin_meta = baza_yiqilgan
    # Chastota chegarasi testdagi ketma-ket so'rovlarni bo'g'masin.
    auth.SESSION_RATE_LIMIT = 1000

    async with TestClient(TestServer(web.build_app())) as client:
        r = await sorov(client, init_data_yasa(1, buzuq=True))
        assert r.status == 401, f"soxta imzo o'tib ketdi: {r.status}"
        print("[1] soxta imzoli initData rad etiladi OK")

        eski = int(time.time()) - auth.INIT_DATA_MAX_AGE - 10
        r = await sorov(client, init_data_yasa(1, auth_date=eski))
        assert r.status == 401, f"eski initData qabul qilindi: {r.status}"
        # Imzo o'zi TO'G'RI edi — ya'ni rad etilishiga faqat yosh sabab.
        r = await sorov(client, init_data_yasa(1))
        assert r.status == 200, f"yangi initData rad etildi: {r.status}"
        print("[2] auth_date 5 daqiqadan eski bo'lsa rad etiladi OK")

        ruxsat["qiymat"] = False
        r = await sorov(client, init_data_yasa(1))
        assert r.status == 403, f"admin bo'lmagan kirdi: {r.status}"
        ruxsat["qiymat"] = True
        print("[3] imzosi to'g'ri, lekin admin bo'lmagan foydalanuvchi rad etiladi OK")

        haqiqiy = auth.sessiya_yasa(1)
        buzuq = haqiqiy[:-1] + ("a" if haqiqiy[-1] != "a" else "b")
        r = await client.get("/api/me", headers={"Cookie": f"{auth.COOKIE_NAME}={buzuq}"})
        assert r.status == 401, f"buzuq cookie qabul qilindi: {r.status}"
        r = await client.get("/api/me")
        assert r.status == 401, "cookie'siz kirish ochiq"
        print("[4] cookie imzosi buzilsa rad etiladi OK")

        # Muddati o'tgan cookie — `sessiya_ochi` toza funksiya, shu yerda.
        eski_payload = f"1.{int(time.time()) - 5}"
        eski_imzo = hmac.new(auth._kalit(), eski_payload.encode(),
                             hashlib.sha256).hexdigest()
        assert auth.sessiya_ochi(f"{eski_payload}.{eski_imzo}") is None
        assert auth.sessiya_ochi(haqiqiy) == 1, "to'g'ri cookie o'qilmadi"
        print("[5] muddati o'tgan cookie rad etiladi, to'g'risi o'qiladi OK")

        r = await sorov(client, init_data_yasa(1))
        assert r.status == 200
        assert auth.COOKIE_NAME in r.cookies, "sessiya cookie'si qo'yilmadi"
        qiymat = r.cookies[auth.COOKIE_NAME]
        assert qiymat["httponly"], "cookie HttpOnly emas — JS o'qiy oladi"
        assert qiymat["secure"], "cookie Secure emas — http orqali ketadi"
        print("[6] muvaffaqiyatli kirish HttpOnly+Secure cookie qo'yadi OK")

        # Yuqoridagi so'rov baza YIQILGAN holatda 200 qaytardi — demak
        # ism/rol o'qilmasa ham admin panelga kira oladi. Javobda
        # ikkala maydon ham bo'lishi shart: panel ularni o'qiydi.
        ma = await r.json()
        assert ma.get("ism") and ma.get("rol"), ma
        assert ma["rol"] == "Admin", "baza yo'qda rol bezak qiymatiga tushsin"
        c = await client.get("/api/me", headers={"Cookie": f"{auth.COOKIE_NAME}={haqiqiy}"})
        assert c.status == 200 and (await c.json()).get("ism"), "cookie bilan kirish ishlamadi"
        print("[7] baza javob bermasa ham kirish ishlaydi (ism/rol — bezak) OK")

    print("\nweb auth: barcha tekshiruvlar o'tdi (7/7).")


if __name__ == "__main__":
    asyncio.run(main())
