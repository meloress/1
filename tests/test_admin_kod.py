"""`/kod` — promokod va referal taklifini odamga yuborish oqimi.

⚠️ Bu oqim 7-bosqichda BOTDA qoldi, qolgan hamma admin ekrani esa webga
ko'chdi. Sabab tarqatmanikiga aynan o'xshash (REJA 2): `send_promo_gift()`
tayyor tugmali xabar jo'natadi, `send_referral_invite()` esa har kimga
o'zining shaxsiy havolasini yasaydi — webda qayta yig'ilgan xabar
ikkalasini ham yo'qotardi.

Shu sababli u endi web testlari qoplamaydigan YAGONA admin oqimi, va
bu fayl uning yagona qo'riqchisi. Tekshiriladigan narsa aniq: menyudan
ikkita YUBORISH amali chiqsin (yaratish emas — u panelda), kod tanlash
holatni to'g'ri qo'ysin, va kod yo'q bo'lganda admin panelga
yo'naltirilsin (ilgari bu yerda «yangi kod yaratish» tugmasi bor edi va
u endi mavjud emas — o'sha matn qolib ketsa, admin yo'q tugmani
qidirardi).

Tarmoq, baza va Telegram kerak emas.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_admin_kod.py
"""
import asyncio
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-ADMIN-KOD")

from handlers.admin import promo  # noqa: E402

YUBORILGAN = []
UTC = datetime.timezone.utc


class FakeUser:
    id = 1
    username = "admin"


class FakeMsg:
    from_user = FakeUser()

    async def answer(self, text, parse_mode=None, reply_markup=None):
        YUBORILGAN.append((text, reply_markup))


class FakeState:
    def __init__(self):
        self.s = None
        self.d = {}

    async def clear(self):
        self.s = None

    async def set_state(self, s):
        self.s = s

    async def update_data(self, **kw):
        self.d.update(kw)

    async def get_data(self):
        return self.d


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.message = FakeMsg()
        self.from_user = FakeUser()

    async def answer(self, *a, **k):
        pass


def _q(v):
    async def i():
        return v
    return i()


def tugmalar(kb):
    return [b.callback_data for row in kb.inline_keyboard for b in row]


async def main():
    promo.require_admin_or_deny = lambda m: _q(True)
    promo.require_admin_or_deny_query = lambda q: _q(True)

    kelajak = datetime.datetime.now(UTC) + datetime.timedelta(days=9)

    async def kodlar(limit=30):
        return [
            {"code": "SENTABR30", "days": 30, "used_count": 1, "max_uses": 100,
             "expires_at": kelajak, "revoked": False},
            # Ishlatib bo'lingan va bekor qilingan kodlar yuborish
            # ro'yxatiga TUSHMASLIGI kerak: adminning ularni yuborishi —
            # odamga ishlamaydigan sovg'a jo'natish demakdir.
            {"code": "TUGAGAN", "days": 7, "used_count": 5, "max_uses": 5,
             "expires_at": None, "revoked": False},
            {"code": "BEKOR", "days": 7, "used_count": 0, "max_uses": 5,
             "expires_at": None, "revoked": True},
        ]
    promo.database_module.list_promo_codes = kodlar

    st = FakeState()

    # 1) Menyuda FAQAT yuborish amallari.
    await promo.show_giveaway_menu(FakeMsg(), st)
    matn, kb = YUBORILGAN[-1]
    assert tugmalar(kb) == ["gv:sendpromo", "gv:sendref", "gv:close"], tugmalar(kb)
    # ⚠️ Yaratish va ro'yxat panelda — bu yerda qolsa ikki joyda ikki
    # xil holat bo'lardi (kod panelda bekor qilinadi, botda esa hali
    # «faol» ko'rinib turadi).
    assert "gv:new" not in tugmalar(kb) and "gv:list" not in tugmalar(kb)
    assert "panel" in matn.lower(), "admin yaratishni qayerdan topishini bilmaydi"
    print("[1] /kod menyusi: ikkita yuborish amali, yaratish panelga yo'naltirilgan OK")

    # 2) Kod tanlash — faqat ISHLATSA BO'LADIGANLARI.
    await promo.giveaway_callback(FakeQuery("gv:sendpromo"), st)
    matn, kb = YUBORILGAN[-1]
    t = tugmalar(kb)
    assert "gv:pick:SENTABR30" in t, t
    assert "gv:pick:TUGAGAN" not in t, "limiti to'lgan kod yuborish ro'yxatida"
    assert "gv:pick:BEKOR" not in t, "bekor qilingan kod yuborish ro'yxatida"
    print("[2] tanlash ro'yxatida faqat ishlatsa bo'ladigan kodlar OK")

    # 3) Kod tanlanganda holat va kod SAQLANADI — aks holda oluvchilar
    #    yozilgach «kod yo'qoldi» chiqardi.
    await promo.giveaway_callback(FakeQuery("gv:pick:SENTABR30"), st)
    assert st.s == promo.GiveawayStates.waiting_promo_recipients
    assert st.d.get("promo_code") == "SENTABR30"
    print("[3] kod tanlanadi, holat va kod saqlanadi OK")

    # 4) Referal taklifi — kod tanlashsiz, to'g'ridan-to'g'ri.
    await promo.giveaway_callback(FakeQuery("gv:sendref"), st)
    assert st.s == promo.GiveawayStates.waiting_ref_recipients
    print("[4] referal taklifi oqimi ishlaydi OK")

    # 5) Kod umuman yo'q bo'lsa — PANELGA yo'naltiriladi.
    #    ⚠️ Ilgari bu matn «🎟 Yangi promokod yaratish tugmasini bosing»
    #    derdi. O'sha tugma 7-bosqichda o'chdi, ya'ni matn qolib ketsa
    #    admin mavjud bo'lmagan tugmani qidirib yurardi.
    async def bosh(limit=30):
        return []
    promo.database_module.list_promo_codes = bosh
    await promo.giveaway_callback(FakeQuery("gv:sendpromo"), st)
    matn, _ = YUBORILGAN[-1]
    assert "panelda" in matn, matn
    assert "tugmasini bosing" not in matn, "o'chirilgan tugmaga havola qolib ketgan"
    print("[5] kod yo'qda panelga yo'naltiradi, o'lik tugmaga havola yo'q OK")

    # 6) Noma'lum callback YIQITMAYDI — eski xabardagi tugma bosilishi
    #    mumkin (`gv:new` allaqachon yo'q).
    await promo.giveaway_callback(FakeQuery("gv:new"), st)
    await promo.giveaway_callback(FakeQuery("gv:"), st)
    await promo.giveaway_callback(FakeQuery("gv:pick"), st)
    print("[6] eski/noto'g'ri callback yiqitmaydi OK")

    print("\n/kod oqimi: barcha tekshiruvlar o'tdi (6/6).")


if __name__ == "__main__":
    asyncio.run(main())
