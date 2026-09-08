"""QO'RIQCHI: promptdan biror QOIDA yo'qolib qolmasin.

Prompt har bir so'rovda to'liq yuboriladi, ya'ni undagi har token kunlik
bepul grantdan yeyiladi. Shuning uchun undan takror qismlar olib
tashlanadi — LEKIN bitta ham qoida yo'qolmasligi SHART. Bu test aynan
shuni qo'riqlaydi: har bir qoida yakuniy `instructions` satrida
qolganini tekshiradi, qaysi bo'limda turishidan qat'i nazar.

Yangi qoida qo'shsangiz — shu ro'yxatga ham qo'shing. Qoidani ATAYLAB
olib tashlasangiz — shu yerdan ham o'chiring va NEGA ekanini yozing.

Ishga tushirish:  PYTHONIOENCODING=utf-8 python tests/test_prompt_rules.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config as c  # noqa: E402


def check(n, nom, shart):
    assert shart, f"[{n}] {nom} — YIQILDI"
    print(f"[{n}] {nom} OK")


# Modelga haqiqatan boradigan matn (services/ai.py: get_openai_reply).
INSTRUCTIONS = "\n\n".join([
    c.build_system_prompt(), c.CONCISE_INSTRUCTION, c.IMAGE_CAPABILITY_NOTE,
])
DUZ = " ".join(INSTRUCTIONS.split()).lower()


def bor(*parchalar):
    """Ro'yxatdagi parchalarning KAMIDA BITTASI matnda bormi."""
    return any(" ".join(p.split()).lower() in DUZ for p in parchalar)


# ── Matematika: har bir qoida alohida ────────────────────────────
# Bu bo'lim ikki joyda takrorlangan edi (prompt ichida + alohida
# STRICT_MATH_RULES). Takror olib tashlanganda birorta qoida
# tushib qolmasligi kerak — quyida har biri alohida tekshiriladi.
MATEMATIKA = [
    ("hamma formula LaTeX bo'lishi shart",
     ("must be latex", "must be in latex")),
    ("oddiy matnli formula qabul qilinmaydi",
     ('plain-text math (e.g. "e = m * c^2") is not acceptable',
      'plain-text math ("e = m * c^2") is not acceptable')),
    ("bu qat'iy talab ekani aytilgan",
     ("hard requirement", "is not acceptable")),
    ("qator ichida bitta dollar", ("inline", )),
    ("blok uchun ikkita dollar", ("double dollars", )),
    ("faqat $ va $$ amal qiladi", ("only $ and $$", )),
    ("\\[ \\] va \\( \\) qat'iy taqiqlangan",
     ("\\[ \\] and \\( \\) are strictly forbidden", )),
    ("boshqa ajratgich yo'qligi aytilgan",
     ("no other acceptable delimiters", "only $ and $$ are valid")),
    ("ular Telegram renderini buzishi aytilgan",
     ("crash telegram's renderer", "crashes the parser")),
    ("ASCII emas, haqiqiy LaTeX buyruqlari",
     ("not ascii", )),
    ("\\frac buyrug'i misolda bor", ("\\frac", )),
    ("\\sqrt \\sum \\int misolda bor",
     ("\\sqrt", )),
    ("yechim tuzilishi: berilgan -> formula -> hisob -> javob",
     ("given", )),
    ("bosqichlar orasida izoh bo'lishi kerak",
     ("prose", )),
    ("yalang tenglamalarni ketma-ket yozmaslik",
     ("never chain bare equations", )),
    ("matematikani kod bilan yechmaslik",
     ("code to solve math", "python or any code to solve math")),
    ("yolg'iz $100 renderni buzadi",
     ("100 dollars", )),
]

for i, (nom, parchalar) in enumerate(MATEMATIKA, 1):
    check(i, f"matematika: {nom}", bor(*parchalar))

n = len(MATEMATIKA)

# ── Boshqa bo'limlar: har biri joyida turibdimi ──────────────────
BOLIMLAR = [
    ("vazifa (MISSION)", "mission"),
    ("til ko'zgusi", "dynamic mirroring"),
    ("kim yaratgani", "og'abek jumayev"),
    ("maxfiylik", "never disclose the internals"),
    ("shaxsiyat", "be someone, not something"),
    ("jalb qilish dvigateli", "engagement engine"),
    ("chiqish shartnomasi", "output contract"),
    ("kod uchun", "for code"),
    ("maxsus kirishlar", "special inputs"),
    ("halollik", "honesty & care"),
    ("fishing", "phishing & social engineering"),
    ("bo'sh gap yo'q", "no filler"),
    ("matematika bo'limi", "latex"),
    ("telegram formatlash", "telegram formatting"),
    ("jadval", "never a fake one"),
    ("yig'iladigan bo'lim", "[batafsil"),
    ("iqtibos", "[iqtibos"),
    ("tugma", "[tugma"),
    ("xarita", "[xarita"),
    ("javob hajmini moslash", "response adaptation"),
    ("rasm yuborish imkoniyati", "images — you can send them"),
]
for nom, kalit in BOLIMLAR:
    n += 1
    check(n, f"bo'lim joyida: {nom}", kalit in DUZ)

# ── Yo'qolishi eng qimmatga tushadigan alohida qoidalar ──────────
MUHIM = [
    ("qisqalik aniqlik hisobiga bo'lmaydi",
     ("brevity never comes at the cost of accuracy", )),
    ("bo'sh gap bilan boshlamaslik (uch tilda)",
     ("men sun'iy intellekt sifatida", )),
    ("ruscha bo'sh gap ham taqiqlangan", ("как ии, я", )),
    ("sarlavha (#) taqiqlangan", ("use **bold** instead", )),
    ("pastki chiziq kursiv parserni buzadi", ("crashes the parser", )),
    ("rasm o'rniga havola berish — yiqilgan javob",
     ("is a failed answer", )),
    ("har bir rasm so'roviga alohida chaqiruv",
     ("own tool call", )),
    ("fishing: tayyor xabar yozilmaydi",
     ("ready-to-send message", )),
    ("fishing: ortiqcha rad etmaslik", ("do not over-refuse", )),
    ("fishing: simulyatsiya yorlig'i", ("simulyatsiya", )),
    ("xarita: noto'g'ri koordinata aniqlanmaydi",
     ("41.9/12.5 is rome", )),
    ("jadval: ajratuvchi qator majburiy", ("separator row", )),
    ("checklist: bajariladigan qadamlar uchun", ("- [ ]", )),
    ("izoh (footnote) ta'rifi shu javobda bo'lishi shart",
     ("must have its definition", )),
    ("==marked== javobda bittadan ko'p emas",
     ("at most one per reply", )),
]
for nom, parchalar in MUHIM:
    n += 1
    check(n, f"muhim qoida: {nom}", bor(*parchalar))

# ── O'lcham: prompt sezilmasdan shishib ketmasin ─────────────────
belgilar = len(INSTRUCTIONS)
n += 1
check(n, f"instructions o'lchami nazoratda ({belgilar} belgi)",
      belgilar < 24000)

print(f"\nHammasi o'tdi: {n}/{n}")
