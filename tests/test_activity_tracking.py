"""Admin statistikasi barcha faollik turlarini ko'rsatishini tekshiradi.
Ishga tushirish: python tests/test_activity_tracking.py

Nega kerak: guest mode'da ball yechilardi, lekin track_user_activity()
umuman chaqirilmasdi — admin panelda foydalanuvchi hech narsa qilmagandek
ko'rinardi. Fayl yaratish esa yozilsa ham admin'ning turlar ro'yxatida
yo'q edi. Bu test o'sha sinf xatoni qaytib kelishidan qo'riqlaydi: kod
yozadigan HAR BIR faollik turi statistikada ko'rinishi shart.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

from handlers import messages as hm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Statistikada ko'rinishi SHART bo'lmagan turlar: bular AI chaqiruvi emas.
IGNORED = {"start"}

# guest.py dagi f"guest_{content_type}_message" shu turlarga yoyiladi.
GUEST_CONTENT_TYPES = ("text", "photo", "document", "voice")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def written_activity_types() -> set:
    """Kod haqiqatda yozadigan barcha faollik turlari."""
    names = set()
    for rel in (("handlers", "messages.py"), ("handlers", "guest.py"),
                ("handlers", "biznes.py")):
        src = read(*rel)
        # "def track_user_activity(" — bu ta'rif, chaqiruv emas
        for raw in re.findall(r'(?<!def )track_user_activity\(.*?f?"([^"]+)"\s*,?\s*\)',
                              src, re.S):
            if "{" in raw:
                # f"guest_{content_type}_message"
                prefix, _, suffix = raw.partition("{")
                suffix = suffix.split("}", 1)[1]
                names |= {f"{prefix}{ct}{suffix}" for ct in GUEST_CONTENT_TYPES}
            else:
                names.add(raw)
    return names - IGNORED


def main():
    # ⚠️ MANBA KO'CHDI (3-bosqich). Ilgari SQL filtri va `type_labels`
    # `handlers/admin/stats.py` da qo'lda ikki marta yozilgan edi va bu
    # test o'sha faylni MATN sifatida o'qirdi. Web panel qo'shilganda
    # uchinchi nusxa paydo bo'lardi, shuning uchun ro'yxat
    # `core/config.py::ACTIVITY_TYPES` ga yig'ildi — endi uni import
    # qilib o'qiymiz, ya'ni test kodning joylashuviga bog'liq emas.
    from core.config import ACTIVITY_TYPES

    # 1) Kod yozadigan turlar aniqlandimi
    types = written_activity_types()
    assert "text_message" in types and "file_task" in types, types
    assert "guest_text_message" in types and "guest_voice_message" in types, types
    print(f"[1] kod {len(types)} ta faollik turi yozadi OK")

    # 2) Guest mode faolligi UMUMAN yoziladimi (asosiy nuqson shu edi)
    guest_src = read("handlers", "guest.py")
    assert "track_user_activity(" in guest_src, \
        "guest mode faollikni yozmaydi — statistika kam ko'rsatadi"
    # Faqat kvota RUXSAT bergan tarmoqda yozilishi kerak: bloklangan
    # so'rovda AI chaqirilmaydi, demak u faollik ham emas.
    allowed_branch = guest_src.split('if quota.get("allowed", True):', 1)
    assert len(allowed_branch) == 2, "guest kvota tarmog'i topilmadi"
    denied = allowed_branch[1].split("else:", 1)[1][:400]
    assert "track_user_activity" in allowed_branch[1][:600], "ruxsat tarmog'ida yozilmagan"
    assert "track_user_activity" not in denied, "limit tugaganda ham yozilyapti"
    print("[2] guest faolligi faqat AI chaqirilganda yoziladi OK")

    # 3) Kod yozadigan har bir tur ro'yxatda bormi. Ro'yxat bir vaqtda
    #    SQL filtri ham (`activity_stats()` unga `= ANY($1)` qiladi),
    #    ko'rinadigan nom ham — ya'ni tushib qolgan tur ikkalasidan
    #    birdan emas, IKKALASIDAN ham yo'qoladi.
    missing = types - set(ACTIVITY_TYPES)
    assert not missing, f"ACTIVITY_TYPES dan tushib qolgan turlar: {missing}"
    print(f"[3] {len(ACTIVITY_TYPES)} ta tur yagona ro'yxatda, biri ham tushib qolmagan OK")

    # 4) Har bir yozuvning shakli to'g'rimi: (emoji, nom, ball).
    #    Nom bo'sh qolsa admin'ga 'guest_text_message' degan xom satr
    #    chiqardi; ball son bo'lmasa taxminiy xarajat hisoblanmasdi.
    for tur, qiymat in ACTIVITY_TYPES.items():
        assert isinstance(qiymat, tuple) and len(qiymat) == 3, (tur, qiymat)
        emoji, nom, ball = qiymat
        assert nom and not nom.startswith(tur[:4]), f"{tur}: ko'rinadigan nom yo'q"
        assert isinstance(ball, int) and ball >= 0, f"{tur}: ball bahosi son emas"
    # SQL filtri va ko'rinish AYNAN shu dict'dan o'qishi shart — nusxa
    # paydo bo'lmasin (ilgari stats.py da qo'lda ikki marta yozilgandi).
    # ⚠️ `handlers/admin/stats.py` ro'yxatdan CHIQDI: 7-bosqichda o'sha
    # ekran webga ko'chib, fayl o'chirildi. Iste'molchilar endi uchta:
    # SQL filtri, kunlik hisobot va panel.
    for fayl in (("db", "database.py"), ("handlers", "admin", "daily.py"),
                 ("web", "api.py")):
        assert "ACTIVITY_TYPES" in read(*fayl), f"{fayl[-1]} yagona ro'yxatdan o'qimaydi"
    # Qo'lda yozilgan nusxalar qaytib kelmasin. `ACTIVITY_LABELS`
    # aynan shunday nusxa edi va unda `location_message` YO'Q edi —
    # kunlik hisobot uni xom satr qilib ko'rsatib yurgan.
    assert "ACTIVITY_LABELS = {" not in read("handlers", "admin", "daily.py"), \
        "daily.py da turlar ro'yxatining nusxasi qaytib kelgan"
    assert "type_labels" not in read("web", "api.py"), \
        "web/api.py da turlar ro'yxatining nusxasi paydo bo'lgan"
    print(f"[4] {len(ACTIVITY_TYPES)} ta turning nomi va ball bahosi joyida OK")

    # 5) Fayl vazifasi faqat fayl CHIQQANDA yoziladi
    logged = []
    real = hm.track_user_activity
    hm.track_user_activity = lambda uid, un, ev: logged.append(ev)
    try:
        asyncio.run(hm._after_file_task(FakeMsg(), [FakeQuota()], True))
        assert logged == ["file_task"], logged
        logged.clear()
        asyncio.run(hm._after_file_task(FakeMsg(), [FakeQuota()], False))
        assert logged == [], "fayl chiqmasa yozilmasligi kerak"
        logged.clear()
        asyncio.run(hm._after_file_task(FakeMsg(), [], True))
        assert logged == [], "fayl vazifasi bo'lmasa yozilmasligi kerak"

        # Faqat RASM chizilgan holat: fayl sanog'i umuman yechilmagan.
        # Ilgari bu yerda "oxirgi bepul faylingiz" xabari yolg'on ishga
        # tushib, Pro foydalanuvchiga bepul tarif haqida yozib yuborardi.
        logged.clear()
        asyncio.run(hm._after_file_task(FakeMsg(), [FakeUnchargedQuota()], True))
        assert logged == [], (
            "ishlatilmagan sanoq bo'yicha faollik yozilmasligi kerak"
        )
    finally:
        hm.track_user_activity = real
    print("[5] fayl yaratish faqat fayl chiqqanda yoziladi OK")

    # 6) Ishlatilmagan sanoq bo'yicha limit XABARI ham chiqmasligi kerak
    sent = []
    real_answer = hm._answer_with_pro_button
    hm._answer_with_pro_button = lambda msg, text, offer: sent.append(text)
    try:
        asyncio.run(hm._after_file_task(FakeMsg(), [FakeUnchargedQuota()], True))
        assert sent == [], (
            "KRITIK: tegilmagan sanoq bo'yicha limit xabari yuborildi — "
            "Pro foydalanuvchi 'oxirgi bepul faylingiz' xabarini olardi"
        )
    finally:
        hm._answer_with_pro_button = real_answer
    print("[6] tegilmagan sanoq bo'yicha noto'g'ri xabar chiqmaydi OK")

    print("\nactivity_tracking: barcha tekshiruvlar o'tdi (6/6).")


class FakeQuota:
    """services.file_task_quota.DailyQuota ning soxta nusxasi.

    `charged` va `kind` HAQIQIY sinfda bor va _after_file_task ularga
    tayanadi — soxta obyekt ham ularni berishi shart.
    """
    limit_hit = False
    limit = 2
    remaining = 1
    charged = True
    kind = "files"


class FakeUnchargedQuota(FakeQuota):
    """Umuman ishlatilmagan sanoq (masalan faqat rasm chizilgan holat)."""
    charged = False


class FakeUser:
    id = 42
    username = "test"


class FakeMsg:
    from_user = FakeUser()

    async def answer(self, text, parse_mode=None):
        pass


if __name__ == "__main__":
    main()
