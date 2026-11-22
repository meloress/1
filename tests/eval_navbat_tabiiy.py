# -*- coding: utf-8 -*-
"""Navbatchi — TABIIYLIK baholash (jonli model, qo'lda). `eval_tabiiy.py` ning
guruh varianti: guruhdagilar javobni o'qib «Jasur o'zi yozdi» deydimi?

  1. Izlar (regex) — AI matnining belgilari: uzun tire, yordamchi iboralari,
     ro'yxat, savolni qaytarish, guruh suhbatidan ko'p marta uzun javob …
  2. Hakam (boshqa model, ko'r) — «Jasur telefonida o'zi yozgan» ehtimoli 1-10.

Faqat MATN baholanadi. Vaqt, reply'siz yozish, xabarni o'tkazib yuborish —
kodda (`handlers/navbatchi.py`), ularni `test_navbatchi.py` tekshiradi.
Reaksiya (matnsiz) va «-» (jim) — alohida sanaladi, hakamga bormaydi.

Ishga tushirish — PowerShell'dan, C:\\Users\\Acer\\Desktop\\123 da:
    railway run python tests/eval_navbat_tabiiy.py [--takror N] [id...]
⚠️ Bazaga yozmaydi (`_log_token_usage` o'chirilgan), Telegram'ga chiqmaydi.
"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import ai                  # noqa: E402
from core.loader import openai_client    # noqa: E402

ai._log_token_usage = lambda *a, **k: None       # ⛔️ production bazaga yozilmasin
HAKAM_MODEL = "gpt-5.4"

QIZIT = "guruhni qizitib tur, maksimal hazillash, qora yumor ham bo'ladi, kerak bo'lsa jiddiy"
DASTUR = "men kelgunimcha dasturlash savollariga javob berib tur"
USLUB = ("[EGASINING USLUBI — xabarlaridan o'rganilgan]\n"
         "- hamma narsani kichik harf bilan yozadi\n- juda qisqa, 2-8 so'z\n"
         "- «bro», «xullas», «e» deydi\n- emoji kam, ko'pincha 😂\n"
         "- namunalar: «ha bro», «xullas ertaga ko'ramiz», «e qo'ysang-chi 😂», "
         "«kim bor kechqurun»")

# (id, vazifa, guruh suhbati, javob beriladigan xabar, menga)
S = [
    ("zerikish", QIZIT, "Sardor: hamma ishdami\nBekzod: guruh o'likku bugun",
     "Bekzod: kimdir tirikmi o'zi", False),
    ("dushanba", QIZIT, "Ali: yana dushanba",
     "Bekzod: dushanba yana keldi, yashashdan charchadim 😩", False),
    ("maosh", QIZIT, "Sardor: bugun 25-sana", "Bekzod: maosh tushishini kutib o'tiribman, "
     "telefonni 5 minutda bir tekshiryapman", False),
    ("futbol", QIZIT, "Vali: kecha o'yinni ko'rdinglarmi", "Vali: Real yana yutqazdi, "
     "hammasi tugadi", False),
    ("yangi_odam", QIZIT, "Ali: kim qo'shdi buni", "Malika: salom hammaga, yangi qo'shildim", False),
    ("qayerdasan", QIZIT, "Sardor: Jasur ko'rinmay ketdi", "Sardor: Jasur aka qayerdasiz, "
     "yo'qolib qoldingiz", True),
    ("bot_hazil", QIZIT, "Ali: jasur bugun juda faol-ku", "Dilshod: Jasur bot qo'ydimi "
     "o'zi 😂 bunaqa tez yozmasdi", True),
    ("begona_toxta", QIZIT, "Bekzod: kuldirding", "Sardor: vexon to'xta endi", False),
    ("list_tuple", DASTUR, "Vali: kim python biladi", "Ali: python'da list bilan tuple "
     "farqi nima?", False),
    ("useeffect", DASTUR, "Ali: react o'rganyapman", "Ali: useEffect nega ikki marta "
     "ishlayapti, hech tushunmadim", False),
    ("kechqurun", QIZIT, "Vali: ishdan keyin nima qilamiz", "Ali: kim kechqurun "
     "futbolga boradi?", False),
    ("rahmat", DASTUR, "Ali: tuple nima\nJasur (sen): o'zgarmaydigan list, xullas",
     "Ali: rahmat aka, tushundim", True),
    ("provokatsiya", QIZIT, "Bekzod: jasur bugun jim-ku", "Sardor: jasur sen eshak, "
     "javob ber-chi qo'rqoq", True),
    ("tentak_kim", QIZIT, "Ali: zerikdik", "Bekzod: bu guruhda eng tentak kim o'zi?", False),
    ("kinoya", QIZIT, "Vali: men bugun 5 da turdim", "Ali: voy-bo'y, endi seni olimpiadaga "
     "yuboramiz, chempion 😂", False),
    # Egasining xabariga reaksiya — kod shu satrni yasaydi (navbatchi.reaksiya_keldi).
    ("rk_masxara", QIZIT, "Jasur (sen): bugun hammaga choy mendan",
     "[REAKSIYA] Sardor sening «bugun hammaga choy mendan» degan xabaringga 🤡 bosdi", True),
    ("rk_najas", QIZIT, "Jasur (sen): men eng zo'r futbolchiman bu guruhda",
     "[REAKSIYA] Bekzod sening «men eng zo'r futbolchiman bu guruhda» degan xabaringga 💩 bosdi", True),
    ("rk_yurak", "qizlarga xushomad qilib, guruhni jonlantirib tur",
     "Jasur (sen): bugun guruh gullab ketdi",
     "[REAKSIYA] Malika sening «bugun guruh gullab ketdi» degan xabaringga ❤ bosdi", True),
    ("rk_layk", DASTUR, "Jasur (sen): list o'zgaradi, tuple yo'q",
     "[REAKSIYA] Ali sening «list o'zgaradi, tuple yo'q» degan xabaringga 👍 bosdi", True),
    ("rk_yigi", QIZIT, "Jasur (sen): dushanba ham bizdan charchagan",
     "[REAKSIYA] Vali sening «dushanba ham bizdan charchagan» degan xabaringga 😭 bosdi", True),
]

IZLAR = [
    (r"[—–]", "uzun tire"),
    (r"(?i)\balbatta\b", "«albatta»"),
    (r"(?i)zo'r savol|ajoyib savol|savolingiz", "savolni maqtash"),
    (r"(?i)yordam bera|xizmat|xursandman|murojaat", "yordamchi ohangi"),
    (r"(?i)kelinglar,? (birga|hammamiz)", "boshlovchi ibora"),
    (r"(?m)^\s*(\d+[.)]|[-•])\s", "ro'yxat"),
    (r";", "nuqtali vergul"),
    (r"!.*!", "ko'p undov"),
]


def izlar(xabar: str, matn: str) -> list:
    topildi = [nom for rx, nom in IZLAR if re.search(rx, matn)]
    if len(matn) > max(90, 4 * len(xabar)):
        topildi.append(f"uzun ({len(matn)} belgi)")
    return topildi


HAKAM = (
    "You judge an Uzbek Telegram group chat. The LAST message was sent from member "
    "JASUR's account. Decide whether Jasur typed it himself on his phone, or an AI/bot "
    "wrote it for him. Real friends in Uzbek groups write casually: short, often "
    "lowercase, slang, few emoji, sometimes several short messages, no assistant "
    "phrases, no lecturing, no perfectly balanced jokes. Reply ONLY JSON: "
    "{\"ball\": 1-10 (10 = certainly Jasur himself), \"izlar\": [short reasons it "
    "looks like a bot, in Uzbek]}.")


async def hakam(suhbat: str, xabar: str, matn: str) -> tuple:
    r = await openai_client.responses.create(
        model=HAKAM_MODEL, instructions=HAKAM, store=False,
        input=f"{suhbat}\n{xabar}\nJASUR (baholanadigan xabar): {matn}")
    try:
        d = json.loads(re.search(r"\{.*\}", r.output_text, re.S).group(0))
        return int(d.get("ball", 0)), d.get("izlar") or []
    except Exception:
        return 0, ["hakam javobi o'qilmadi"]


async def main():
    takror = int(sys.argv[sys.argv.index("--takror") + 1]) if "--takror" in sys.argv else 1
    qiymat = {sys.argv.index("--takror") + 1} if "--takror" in sys.argv else set()
    arg = [a for i, a in enumerate(sys.argv) if i and not a.startswith("--") and i not in qiymat]
    holatlar = [s for s in S if not arg or any(a in s[0] for a in arg)]
    jami, natija = {}, []
    for nom_u, uslub in (("uslubsiz", ""), ("uslubli", USLUB)):
        ballar, izli, jim, reaksiya = [], 0, 0, 0
        for hid, vazifa, suhbat, xabar, menga in holatlar:
            for _ in range(takror):
                r = await ai.navbat_javobi(vazifa, suhbat, xabar, egasi="Jasur",
                                           oldingi=[], menga=menga, uslub=uslub)
                matn, rk = r[0], (r[2] if len(r) > 2 else "")
                if not matn:
                    jim += not rk
                    reaksiya += bool(rk)
                    print(f"{nom_u:8} {hid:13}   -    {'[' + rk + ']' if rk else '(jim)'}")
                    continue
                iz = izlar(xabar, matn)
                ball, sabab = await hakam(suhbat, xabar, matn)
                ballar.append(ball)
                izli += bool(iz)
                natija.append({"uslub": nom_u, "id": hid, "matn": matn, "reaksiya": rk,
                               "izlar": iz, "ball": ball, "hakam": sabab})
                print(f"{nom_u:8} {hid:13} {ball:>2}/10 {('[' + rk + '] ') if rk else ''}"
                      f"{matn[:110]!r}" + (f"  ← {', '.join(iz)}" if iz else "")
                      + (f"  | hakam: {'; '.join(sabab)[:140]}" if ball < 7 else ""))
        jami[nom_u] = (sum(ballar) / max(1, len(ballar)), izli, len(ballar), jim, reaksiya)
    print()
    for nom_u, (ort, izli, n, jim, rk) in jami.items():
        print(f"{nom_u}: hakam o'rtacha {ort:.1f}/10, izli {izli}/{n}, jim {jim}, faqat reaksiya {rk}")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           ".eval_navbat_tabiiy_oxirgi.json"), "w", encoding="utf-8") as f:
        json.dump(natija, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
