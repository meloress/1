"""Uzoq ko'rinmagan foydalanuvchiga xabar uchun tekshiruv.
Ishga tushirish: python tests/test_inactive.py

HAQIQIY NOSOZLIK: funksiya umuman ishlamay qolgan edi. Ikkita sabab:
  1) `await asyncio.sleep(7 kun)` sikldan OLDIN turardi. Railway'da har
     deploy konteynerni qayta ishga tushiradi, ya'ni bot yetti kun
     uzluksiz ishlamaydi va funksiya bir marta ham chaqirilmasdi;
  2) xabar yuborilgach `last_seen = NOW()` yozilardi — haqiqiy faollik
     ma'lumoti buzilardi va odam "hozir kirgan" bo'lib qolardi.

Shuning uchun bu yerda aynan shu ikki xato va bosqichlar mantiqi
qo'riqlanadi.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import inspect

from core.config import INACTIVE_STEPS, INACTIVE_BATCH, INACTIVE_TICK
from db import database
from handlers import helpers


def test_steps():
    assert list(INACTIVE_STEPS) == [7, 15, 30], INACTIVE_STEPS
    # Oraliqlar O'SIB borishi kerak — javob bermayotgan odamni bir xil
    # tezlikda turtish spam bo'ladi.
    assert all(a < b for a, b in zip(INACTIVE_STEPS, INACTIVE_STEPS[1:]))
    assert 0 < INACTIVE_BATCH <= 200, "bitta tsiklda juda ko'p model chaqiruvi"
    assert INACTIVE_TICK <= 24 * 3600, "tekshiruv juda siyrak"
    print("[1] bosqichlar 7 -> 15 -> 30 va o'sib boradi OK")

    # Oxirgi bosqichdan keyin BOSHIGA qaytish: (stage + 1) % 3.
    stage = 0
    kutilgan = [1, 2, 0, 1, 2, 0]
    natija = []
    for _ in range(6):
        stage = (stage + 1) % len(INACTIVE_STEPS)
        natija.append(stage)
    assert natija == kutilgan, natija
    print("[2] uchinchi xabardan keyin sikl boshidan boshlanadi OK")


def _kod(fn) -> str:
    """Funksiya manbasi, IZOHSIZ va docstringsiz.

    Izohlarda eski xato tushuntirilgan, ya'ni "last_seen = NOW()" satri
    u yerda ATAYLAB turadi — tekshiruv unga ilinib qolmasin.
    """
    src = inspect.getsource(fn)
    qismlar = src.split('"""')
    if len(qismlar) >= 3:
        src = qismlar[0] + "".join(qismlar[2:])
    return "\n".join(q.split("#")[0] for q in src.split("\n"))


def test_watcher_fixed():
    src = _kod(helpers.notify_inactive_users)

    # 1) Uzun sleep sikldan OLDIN turmasligi kerak.
    assert "3600 * 24 * 7" not in src, "yetti kunlik sleep qaytib kelgan"
    kutish = src.index("await asyncio.sleep(90)")
    sikl = src.index("while True:")
    assert kutish < sikl, "boshlang'ich kutish sikl ichida qolib ketgan"
    print("[3] deploy'dan keyin ishga tushadi (uzun sleep yo'q) OK")

    # 2) last_seen'ga TEGILMASLIGI kerak.
    assert "last_seen = NOW()" not in src, \
        "KRITIK: xabar yuborish haqiqiy faollik ma'lumotini buzyapti"
    take = _kod(database.take_inactive_users)
    assert "last_seen = NOW()" not in take, \
        "KRITIK: SQL last_seen ni o'zgartiryapti"
    print("[4] last_seen faqat haqiqiy faollikda o'zgaradi OK")

    # 3) Belgilash va olish BITTA so'rovda — ikki nusxa ishlasa ham
    #    bitta odamga ikkita xabar ketmasin.
    assert "RETURNING" in take and "FOR UPDATE SKIP LOCKED" in take
    assert "inactive_notified_at = NOW()" in take
    print("[5] olish va belgilash atomik OK")

    # 4) Foydalanuvchi qaytsa bosqich nolga tushsin.
    save = inspect.getsource(database.save_user)
    assert "inactive_stage = 0" in save and "inactive_notified_at = NULL" in save, \
        "qaytgan foydalanuvchiga baribir 15/30 kunlik xabarlar ketaveradi"
    print("[6] foydalanuvchi qaytsa sanoq noldan boshlanadi OK")


async def test_text():
    """Tayyor matn — model chaqirilmaydi (ilgari har xabar ~6 300 token edi)."""
    from core.config import INACTIVE_MATNLAR

    # 21 ta = 7/15/30 sikli bilan taxminan bir yil; hammasi har xil.
    assert len(INACTIVE_MATNLAR) == 21, len(INACTIVE_MATNLAR)
    assert len(set(INACTIVE_MATNLAR)) == len(INACTIVE_MATNLAR), "takror matn bor"
    kunlar, kun = [], 0
    for i in range(len(INACTIVE_MATNLAR)):
        kun += INACTIVE_STEPS[i % len(INACTIVE_STEPS)]
        kunlar.append(kun)
    assert 330 <= kunlar[-1] <= 400, f"oxirgi xabar {kunlar[-1]}-kunda — bir yil emas"
    for m in INACTIVE_MATNLAR:
        assert m.count("{ism}") == 1, m
        assert len(m.format(ism=", Abdurahmonbek")) <= 300, m
    print(f"[7] 21 ta har xil tayyor matn, oxirgisi {kunlar[-1]}-kunda OK")

    # Model UMUMAN chaqirilmasin — butun tejash shunda.
    import services.ai as ai_mod
    real = ai_mod.get_gpt_reply

    def chaqirilmasin(*a, **k):
        raise AssertionError("sog'indik model chaqirdi — token sarflanyapti")
    ai_mod.get_gpt_reply = chaqirilmasin
    yuborilgan = []

    async def fake_rich(user_id, markdown=None, **k):
        yuborilgan.append(markdown)
        return 1
    import handlers.messages as msg_mod
    real_rich = msg_mod._send_rich_message
    msg_mod._send_rich_message = fake_rich
    try:
        for n in range(1, len(INACTIVE_MATNLAR) + 1):
            await helpers._send_miss_you(7, n, None)
    finally:
        ai_mod.get_gpt_reply = real
        msg_mod._send_rich_message = real_rich
    assert len(set(yuborilgan)) == len(INACTIVE_MATNLAR), "N-xabar N-matnni olmadi"
    print("[8] model chaqirilmaydi, N-xabar N-matnni oladi OK")

    # Ism: to'liq ismning birinchi so'zi; markdown belgilari tushadi; yo'q bo'lsa — usiz.
    assert helpers._miss_you_text(1, "Og'abek Karimov").startswith("👋 Salom, Og'abek!")
    assert helpers._miss_you_text(1, "*Ali_*").startswith("👋 Salom, Ali!")
    assert helpers._miss_you_text(1, None).startswith("👋 Salom!")
    assert helpers._miss_you_text(1, "🔥🔥").startswith("👋 Salom!")
    print("[9] ism birinchi so'zdan, belgilarsiz; ism yo'q bo'lsa — usiz OK")

    # Rich yetmasa — oddiy xabar, HTML ekranlangan.
    oddiy = {}

    async def rad(*a, **k):
        return None

    async def fake_dm(user_id, text, kb=None):
        oddiy["text"] = text
    real_dm = helpers._dm_or_deactivate
    msg_mod._send_rich_message, helpers._dm_or_deactivate = rad, fake_dm
    try:
        await helpers._send_miss_you(7, 1, "Ali<b>")
    finally:
        msg_mod._send_rich_message, helpers._dm_or_deactivate = real_rich, real_dm
    assert oddiy["text"].startswith("👋 Salom, Alib!") and "<" not in oddiy["text"], oddiy
    print("[10] rich rad etilsa oddiy xabar ketadi OK")

    # 21-xabardan keyin TO'XTAYDI, qaytgan odamda sanoq noldan.
    take = _kod(database.take_inactive_users)
    assert "COALESCE(inactive_sent, 0) < $2" in take and "len(INACTIVE_MATNLAR)" in take, \
        "hamma matn ketgach ham yozaveradi — yil bo'yi javob bermaganga spam"
    assert "inactive_sent = COALESCE(u.inactive_sent, 0) + 1" in take
    assert "inactive_sent = 0" in inspect.getsource(database.save_user), \
        "qaytgan odamga keyingi safar xabarlar umuman ketmaydi"
    print("[11] 21-xabardan keyin to'xtaydi, qaytsa sanoq noldan OK")


async def main():
    test_steps()
    test_watcher_fixed()
    await test_text()
    print("\nsog'indik: barcha tekshiruvlar o'tdi (11/11).")


if __name__ == "__main__":
    asyncio.run(main())
