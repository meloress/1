"""Oylik obuna (Stars, `subscription_period`) va javobdagi sana-vaqt.

Ishga tushirish: python tests/test_pro_obuna.py

Bazaga ham, Telegram'ga ham tegmaydi: `database.*` va `pro.bot` soxta.
Eng qimmatli tekshiruvlar:
  [3] boshqaning obuna havolasini to'lab bo'lmaydi (unga yashirin oylik
      to'lovchi bo'lib qolardi);
  [6] ikkinchi parallel obuna o'chiriladi (aks holda har oy ikki marta yechiladi);
  [8] obuna Pro'ni keyingi yechishdan + zaxiragacha cho'zadi — yangilanish
      kechiksa Pro uzilmaydi;
  [9] faol obunachiga «tugayapti, uzaytiring» ketmaydi (ikkinchi xaridga undardi).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

from handlers import pro
from db import database
from core.config import OBUNA_NARX, OBUNA_KUN, OBUNA_ZAXIRA_SOAT, PRO_PLANS_BY_DAYS
from tests._manba import kod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAQIRUV = []          # soxta bot/baza nima chaqirilganini yozadi
HOLAT = {"obuna": None, "ban": False}


class FakeBot:
    def __init__(self, rad=()):
        self.rad = set(rad)

    async def edit_user_star_subscription(self, **kw):
        CHAQIRUV.append(("edit_sub", kw))
        if kw["telegram_payment_charge_id"] in self.rad:
            raise RuntimeError("SUBSCRIPTION_NOT_FOUND")
        return True

    async def send_message(self, chat_id, text, **kw):
        CHAQIRUV.append(("send", chat_id, text))

    async def create_invoice_link(self, **kw):
        CHAQIRUV.append(("link", kw))
        return "https://t.me/$obuna"


class FakeMessage:
    def __init__(self, uid=5, sp=None):
        self.from_user = NS(id=uid, username="ali")
        self.successful_payment = sp
        self.chat = NS(id=uid)
        self.javoblar = []

    async def answer(self, text, **kw):
        self.javoblar.append((text, kw))

    async def delete(self):
        pass


def soxta_baza():
    async def grant_paid_pro(**kw):
        CHAQIRUV.append(("grant", kw))
        return True

    async def pro_obuna_ol(uid):
        return HOLAT["obuna"]

    async def pro_obuna_holat(uid, holat):
        CHAQIRUV.append(("holat", uid, holat))

    async def is_banned(uid):
        return HOLAT["ban"]

    async def get_superadmin_id():
        return 1

    async def get_full_user_profile(uid):
        return {"plan_type": "pro", "premium_until": datetime.now(timezone.utc) + timedelta(days=20),
                "username": "ali"}

    async def karta_ol():
        return None

    async def karta_faol_sorov(uid, oyna):
        return None

    for nom, fn in list(locals().items()):
        setattr(database, nom, fn)

    async def sync_commands(*a, **k):
        pass
    pro.menu_module.sync_commands = sync_commands


def sp(payload, amount=OBUNA_NARX, charge="ch1", birinchi=True, exp=None):
    return NS(telegram_payment_charge_id=charge, invoice_payload=payload, currency="XTR",
              total_amount=amount, is_recurring=True, is_first_recurring=birinchi,
              subscription_expiration_date=exp)


def grantlar():
    return [c[1] for c in CHAQIRUV if c[0] == "grant"]


async def main():
    soxta_baza()
    pro.bot = FakeBot()
    P = pro.build_obuna_payload(5, OBUNA_NARX)

    # [1] payload: faqat bot yasagani; bir martalik yo'l uni qabul qilmaydi
    assert pro.parse_obuna_payload(P) == (5, OBUNA_NARX)
    for yomon in ("prosub:v1:0:100", "prosub:v1:5:0", "prosub:v1:5:10001",
                  "prosub:v0:5:100", "prosub:v1:5", "pro:v1:30:5", "prosub:v1:x:100", ""):
        assert pro.parse_obuna_payload(yomon) is None, yomon
    assert pro.parse_payload(P) is None, "obuna payloadi bir martalik xarid bo'lib o'tib ketdi"
    print("[1] obuna payloadi va rad etiladiganlar OK")

    # [2] ikkala to'lov turi bitta shartdan
    assert pro.tolov_shartlari(P) == (OBUNA_KUN, 5, OBUNA_NARX, True)
    assert pro.tolov_shartlari("pro:v1:90:7") == (90, 7, PRO_PLANS_BY_DAYS[90][0], False)
    assert pro.tolov_shartlari("axlat") is None
    # Narx payloadda: keyin OBUNA_NARX o'zgarsa ham eski obunachi o'z narxida
    assert pro.tolov_shartlari(pro.build_obuna_payload(5, 77))[2] == 77
    print("[2] tolov_shartlari OK")

    # [3] pre_checkout
    async def checkout(uid, payload, amount):
        javob = {}

        async def answer(ok, error_message=None):
            javob.update(ok=ok, xato=error_message)
        await pro.handle_pre_checkout(NS(from_user=NS(id=uid), invoice_payload=payload,
                                         total_amount=amount, answer=answer))
        return javob

    assert (await checkout(5, P, OBUNA_NARX))["ok"] is True
    j = await checkout(6, P, OBUNA_NARX)
    assert j["ok"] is False and "sizniki emas" in j["xato"], j
    assert (await checkout(5, P, OBUNA_NARX + 1))["ok"] is False
    HOLAT["ban"] = True
    assert (await checkout(5, P, OBUNA_NARX))["ok"] is False
    HOLAT["ban"] = False
    print("[3] pre_checkout: o'ziga ok, boshqaga/narx/blok — rad OK")

    # [4] birinchi to'lov: grant obuna bilan, bayram xabari, sana <tg-time>
    exp = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    CHAQIRUV.clear()
    m = FakeMessage(sp=sp(P, exp=exp))
    await pro.handle_successful_payment(m)
    g = grantlar()
    assert len(g) == 1 and g[0]["days"] == OBUNA_KUN and g[0]["beneficiary_id"] == 5, g
    ob = g[0]["obuna"]
    assert ob["yangi"] is True and ob["ikkinchi"] is False, ob
    assert int(ob["gacha"].timestamp()) == exp and ob["gacha"].tzinfo is not None
    matn = m.javoblar[-1][0]
    assert "OYLIK OBUNA FAOLLASHTIRILDI" in matn and f'<tg-time unix="{exp}"' in matn, matn
    print("[4] birinchi to'lov: grant + keyingi sana <tg-time> OK")

    # [5] har oylik yangilanish — qisqa satr, effektsiz
    CHAQIRUV.clear()
    m = FakeMessage(sp=sp(P, charge="ch2", birinchi=False, exp=exp))
    await pro.handle_successful_payment(m)
    assert grantlar()[0]["obuna"]["yangi"] is False
    matn, kw = m.javoblar[-1]
    assert "yangilandi" in matn and "FAOLLASHTIRILDI" not in matn, matn
    assert not kw.get("message_effect_id"), "har oy 🎉 effekti bezovta qiladi"
    print("[5] yangilanish xabari qisqa OK")

    # [6] ikkinchi parallel obuna — Pro beriladi, obunaning o'zi o'chiriladi
    HOLAT["obuna"] = {"charge_id": "eski", "oxirgi_charge": "eski", "holat": "faol",
                      "keyingi": datetime.now(timezone.utc) + timedelta(days=9), "narx": OBUNA_NARX}
    CHAQIRUV.clear()
    m = FakeMessage(sp=sp(P, charge="yangi1", exp=exp))
    await pro.handle_successful_payment(m)
    assert grantlar()[0]["obuna"]["ikkinchi"] is True
    edit = [c[1] for c in CHAQIRUV if c[0] == "edit_sub"]
    assert edit == [{"user_id": 5, "telegram_payment_charge_id": "yangi1", "is_canceled": True}], edit
    assert "allaqachon bor edi" in m.javoblar[-1][0]
    # Eski obunaning yangilanishi esa — ikkinchi EMAS
    CHAQIRUV.clear()
    await pro.handle_successful_payment(FakeMessage(sp=sp(P, charge="eski2", birinchi=False, exp=exp)))
    assert grantlar()[0]["obuna"]["ikkinchi"] is False
    assert not [c for c in CHAQIRUV if c[0] == "edit_sub"]
    HOLAT["obuna"] = None
    print("[6] ikkinchi parallel obuna o'chiriladi OK")

    # [7] boshqaning obuna payloadi successful_payment'da — grant YO'Q, admin xabardor
    CHAQIRUV.clear()
    m = FakeMessage(uid=6, sp=sp(P, exp=exp))
    await pro.handle_successful_payment(m)
    assert not grantlar(), "boshqaning obunasi to'lovchiga Pro berdi"
    assert any(c[0] == "send" and c[1] == 1 for c in CHAQIRUV), "admin xabardor qilinmadi"
    print("[7] begona obuna payloadi — grant yo'q, admin xabardor OK")

    # [8] grant_paid_pro SQL: zaxira GREATEST + holat upsert; ikkinchida upsert yo'q
    class FakeConn:
        def __init__(self):
            self.executed = []

        async def fetchrow(self, q, *a):
            return {"id": 1}

        async def execute(self, q, *a):
            self.executed.append((q, a))

        @asynccontextmanager
        async def transaction(self):
            yield

    class FakePool:
        def __init__(self):
            self.conn = FakeConn()

        @asynccontextmanager
        async def acquire(self):
            yield self.conn

    from importlib import reload
    import db.database as dbm
    dbm = reload(dbm)               # soxta funksiyalar emas, haqiqiy SQL
    gacha = datetime(2026, 12, 3, 10, 0, tzinfo=timezone.utc)

    async def grant(obuna):
        dbm.pool = FakePool()
        assert await dbm.grant_paid_pro(charge_id="c", payer_id=5, beneficiary_id=5, stars=100,
                                        days=30, payload=P, obuna=obuna)
        return dbm.pool.conn.executed

    ex = await grant({"gacha": gacha, "yangi": True, "ikkinchi": False})
    zaxira = [a for q, a in ex if "GREATEST(premium_until, $2)" in q]
    assert zaxira == [(5, gacha + timedelta(hours=OBUNA_ZAXIRA_SOAT))], ex
    upsert = [a for q, a in ex if "INSERT INTO pro_obuna" in q]
    assert upsert == [(5, "c", gacha, 100, True)], upsert
    assert "ON CONFLICT (user_id)" in dbm._OBUNA_YOZ_SQL
    ex = await grant({"gacha": gacha, "yangi": True, "ikkinchi": True})
    assert not [q for q, _ in ex if "INSERT INTO pro_obuna" in q], "ikkinchi obuna holatni bosdi"
    ex = await grant(None)
    assert [q for q, _ in ex if "UPDATE users" in q] == [dbm._EXTEND_PLAN_SQL], \
        "obunasiz xarid o'zgarib ketdi"
    print("[8] grant: zaxira + upsert, ikkinchida upsert yo'q OK")

    # [9] «tugayapti» eslatmasi faol obunachiga ketmaydi
    src = kod(os.path.join(ROOT, "db", "database.py"))
    eslat = src[src.index("async def take_expiry_reminders"):]
    eslat = eslat[:eslat.index("\n\n\n")]
    assert "NOT EXISTS (SELECT 1 FROM pro_obuna" in eslat and "o.holat = 'faol'" in eslat
    print("[9] faol obunachiga «tugayapti» yo'q OK")

    # [10] Update.subscription: holat va xabar
    soxta_baza()
    CHAQIRUV.clear()
    await pro.handle_obuna_ozgardi(NS(user=NS(id=5), invoice_payload=P, state="canceled"))
    assert ("holat", 5, "bekor") in CHAQIRUV
    assert any(c[0] == "send" and "o'chirildi" in c[2] and "<tg-time" in c[2] for c in CHAQIRUV)
    CHAQIRUV.clear()
    await pro.handle_obuna_ozgardi(NS(user=NS(id=5), invoice_payload=P, state="failed"))
    assert ("holat", 5, "xato") in CHAQIRUV
    CHAQIRUV.clear()
    await pro.handle_obuna_ozgardi(NS(user=NS(id=5), invoice_payload="pro:v1:30:5", state="canceled"))
    await pro.handle_obuna_ozgardi(NS(user=NS(id=5), invoice_payload=P, state="boshqa"))
    assert not CHAQIRUV, CHAQIRUV
    print("[10] subscription update: bekor / xato / begona OK")

    # [11] obuna_toxtat: birinchi chek rad etsa — oxirgisi; holat bot_bekor
    pro.bot = FakeBot(rad={"birinchi"})
    HOLAT["obuna"] = {"charge_id": "birinchi", "oxirgi_charge": "oxirgi", "holat": "faol",
                      "keyingi": None, "narx": 100}
    CHAQIRUV.clear()
    assert await pro.obuna_toxtat(5) is True
    assert [c[1]["telegram_payment_charge_id"] for c in CHAQIRUV if c[0] == "edit_sub"] == \
        ["birinchi", "oxirgi"]
    assert ("holat", 5, "bot_bekor") in CHAQIRUV
    HOLAT["obuna"]["holat"] = "bot_bekor"
    CHAQIRUV.clear()
    assert await pro.obuna_toxtat(5) is False and not CHAQIRUV
    HOLAT["obuna"] = None
    assert await pro.obuna_toxtat(5) is False
    pro.bot = FakeBot()
    print("[11] obuna_toxtat OK")

    # [12] /pro ekrani
    HOLAT["obuna"] = {"charge_id": "a", "oxirgi_charge": "a", "holat": "faol",
                      "keyingi": datetime.now(timezone.utc) + timedelta(days=19), "narx": 100}
    matn, kb = await pro._render_pro_screen(5)
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "pro:obuna_bekor" in data and not any(d and d.startswith("pro:buy") for d in data), data
    assert "uzaytiring" not in matn.lower() and "<tg-time" in matn, matn
    HOLAT["obuna"] = None
    _, kb = await pro._render_pro_screen(5)
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert data[0] == "pro:obuna", data
    sovga = [b.callback_data for row in pro._buy_buttons(777, obuna=True) for b in row]
    assert "pro:obuna" not in sovga, "sovg'a obuna bo'lib qoldi"
    print("[12] /pro: obunachiga o'chirish, boshqaga obuna tugmasi, sovg'ada yo'q OK")

    # [13] obuna havolasi: subscription_period va payload to'g'ri
    CHAQIRUV.clear()
    q = NS(message=FakeMessage())
    await pro._obuna_taklif(q, 5)
    link = [c[1] for c in CHAQIRUV if c[0] == "link"][0]
    assert link["subscription_period"] == 2592000 and link["currency"] == "XTR"
    assert link["payload"] == P and link["prices"][0].amount == OBUNA_NARX
    kb = q.message.javoblar[-1][1]["reply_markup"]
    assert kb.inline_keyboard[0][0].url == "https://t.me/$obuna"
    print("[13] obuna havolasi OK")

    # [14] eslatma: modelga aniq sana shakli; javobda u <tg-time> bo'ladi
    from services import ai

    async def create_scheduled_task(*a, **k):
        return "qo'yildi: 2026-11-04 18:00"
    ai.create_scheduled_task = create_scheduled_task
    r = await ai._run_reminder_task(5, {"action": "create", "text": "x", "when": "2026-11-04 18:00"})
    assert "«04.11.2026 18:00»" in r, r
    html = ai._replace_dates("ertaga, 04.11.2026 18:00 da")
    assert 'format="wDt"' in html and "<tg-time" in html, html
    print("[14] eslatma vaqti <tg-time> ga tushadi OK")

    print("\nHammasi o'tdi: 14/14")


if __name__ == "__main__":
    asyncio.run(main())
