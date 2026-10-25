"""Status emojilarini (assets/status_*.webm) Vexon «V» belgisidan yasaydi.

    python assets/status_yasash.py            # hammasi
    python assets/status_yasash.py search pro # faqat shular

Nega repo'da: oldingi animatsiyalarning skriptlari sessiya papkasida
qolib yo'qolgan edi — logo o'zgarganda 16 tasini noldan chizishga to'g'ri
keldi. Endi keyingi o'zgarish shu faylni tahrirlash bilan tugaydi.

Telegram video emoji talablari: 100x100, ≤3 s, ≤30 fps, ovozsiz, VP9 alfa
bilan, **≤64 KB** (207 KB jonli rad etilgan). Har fayl `crf` oshirib shu
chegaraga sig'diriladi.

⚠️ Animatsiya o'zgardimi — `handlers/messages.py::_LOGO_BELGI` dagi
emojini ham o'zgartiring: bot to'plamdagi stikerni faqat emoji farq
qilganda yangilaydi (replaceStickerInSet). `_LOGO_TOPLAM` ni OSHIRMANG.

Manba: `assets/vexon_v.png` — logodan ajratilgan shaffof «V».
"""
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

PAPKA = os.path.dirname(os.path.abspath(__file__))
K = 4                      # 4x chizib, 100 ga kichraytiriladi — silliq qirralar
N = 400                    # chizish o'lchami
KADR, FPS = 60, 20         # 3 soniya
MAX_BAYT = 60 * 1024       # 64 KB dan biroz past — zaxira

V = Image.open(os.path.join(PAPKA, "vexon_v.png")).convert("RGBA")

# Brend gradienti (logodagi ranglar): moviy-binafsha -> ko'k -> zangori
_G = np.array([[150, 90, 255], [70, 95, 255], [40, 205, 255]], np.float32)


def _gradient() -> Image.Image:
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    t = ((xx + (N - yy)) / (2 * N)).clip(0, 1)[..., None]
    a = np.where(t < 0.5, _G[0] + (_G[1] - _G[0]) * (t * 2), _G[1] + (_G[2] - _G[1]) * (t * 2 - 1))
    return Image.fromarray(np.dstack([a, np.full((N, N), 255, np.float32)]).astype(np.uint8))


GRAD = _gradient()


def s(x: float) -> float:
    """100-lik koordinata -> chizish koordinatasi."""
    return x * K


def yangi() -> Image.Image:
    return Image.new("RGBA", (N, N), (0, 0, 0, 0))


def niqob() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    m = Image.new("L", (N, N), 0)
    return m, ImageDraw.Draw(m)


def boya(kadr: Image.Image, m: Image.Image, shaffoflik: float = 1.0) -> None:
    """Niqob shaklini brend gradienti bilan bo'yab qo'yadi."""
    if shaffoflik < 1:
        m = m.point(lambda p: int(p * shaffoflik))
    q = GRAD.copy()
    q.putalpha(m)
    kadr.alpha_composite(q)


def oq(kadr: Image.Image, m: Image.Image, shaffoflik: float) -> None:
    q = Image.new("RGBA", (N, N), (255, 255, 255, 0))
    q.putalpha(m.point(lambda p: int(p * shaffoflik)))
    kadr.alpha_composite(q)


def v(kadr: Image.Image, cx: float, cy: float, en: float, aylan: float = 0,
      shaffoflik: float = 1.0, ochiq_x: float | None = None) -> None:
    """«V» ni markazi (cx, cy), eni `en` (100-lik) qilib qo'yadi.
    `ochiq_x` — chapdan shu nisbatgacha ko'rinadi (chizilish effekti)."""
    w = round(s(en))
    h = round(w * V.height / V.width)
    b = V.resize((w, h), Image.LANCZOS)
    if ochiq_x is not None:
        m = Image.new("L", b.size, 0)
        ImageDraw.Draw(m).rectangle([0, 0, int(w * ochiq_x), h], fill=255)
        b.putalpha(Image.fromarray((np.asarray(b.getchannel("A"), np.float32)
                                    * np.asarray(m, np.float32) / 255).astype(np.uint8)))
    if shaffoflik < 1:
        b.putalpha(b.getchannel("A").point(lambda p: int(p * shaffoflik)))
    if aylan:
        b = b.rotate(aylan, resample=Image.BICUBIC, expand=True)
    kadr.alpha_composite(b, (round(s(cx) - b.width / 2), round(s(cy) - b.height / 2)))


def yoy(d, cx, cy, r, bosh, oxir, qalin):
    d.arc([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], bosh, oxir, fill=255, width=round(s(qalin)))


def halqa(d, cx, cy, r, qalin):
    yoy(d, cx, cy, r, 0, 360, qalin)


def yulduz(d, cx, cy, r):
    """To'rt qirrali uchqun."""
    i = r * 0.28
    d.polygon([(s(cx), s(cy - r)), (s(cx + i), s(cy - i)), (s(cx + r), s(cy)), (s(cx + i), s(cy + i)),
               (s(cx), s(cy + r)), (s(cx - i), s(cy + i)), (s(cx - r), s(cy)), (s(cx - i), s(cy - i))],
              fill=255)


def doira(d, cx, cy, r, fill=255):
    d.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], fill=fill)


def silliq(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def tolqin(t: float, faza: float = 0) -> float:
    """0..1 oralig'ida, t=0 va t=1 da bir xil — halqa (loop) uziluvsiz."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * (t + faza))


# ---------------------------------------------------------------- turlar

def emoji(t):  # «o'ylayapman» — V atrofida aylanuvchi yoy
    k = yangi()
    m, d = niqob()
    halqa(d, 50, 50, 43, 3)
    boya(k, m, 0.22)
    m, d = niqob()
    bosh = t * 720
    yoy(d, 50, 50, 43, bosh, bosh + 70 + 60 * tolqin(t * 2), 5)
    boya(k, m)
    v(k, 50, 52, 60)
    return k


def search(t):  # lupa V ustida aylanib yuradi
    k = yangi()
    v(k, 50, 52, 60)
    a = 2 * math.pi * t
    cx, cy = 50 + 13 * math.cos(a), 46 + 10 * math.sin(a)
    m, d = niqob()
    doira(d, cx, cy, 15)
    oq(k, m, 0.28)
    m, d = niqob()
    halqa(d, cx, cy, 15, 4.5)
    d.line([s(cx + 10.5), s(cy + 10.5), s(cx + 24), s(cy + 24)], fill=255, width=round(s(6)))
    boya(k, m)
    return k


def document(t):  # varaqda satrlar birin-ketin yoziladi
    k = yangi()
    m, d = niqob()
    d.rounded_rectangle([s(16), s(10), s(64), s(78)], radius=s(7), outline=255, width=round(s(4)))
    boya(k, m)
    m, d = niqob()
    for i in range(5):
        p = silliq((t * 1.25 - i * 0.14) / 0.14)
        if p > 0:
            uz = (36 if i < 4 else 22) * p
            d.rounded_rectangle([s(24), s(22 + i * 10), s(24 + uz), s(26 + i * 10)], radius=s(2), fill=255)
    boya(k, m)
    v(k, 72, 76, 40)
    return k


def photo(t):  # vizir burchaklari nafas oladi, uchqun yonadi
    k = yangi()
    v(k, 50, 52, 54)
    q = 1 - 0.07 * tolqin(t)
    m, d = niqob()
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        x, y = 50 + sx * 42 * q, 50 + sy * 42 * q
        d.line([s(x), s(y), s(x - sx * 14), s(y)], fill=255, width=round(s(5)))
        d.line([s(x), s(y), s(x), s(y - sy * 14)], fill=255, width=round(s(5)))
    boya(k, m)
    m, d = niqob()
    yulduz(d, 78, 22, 4 + 5 * tolqin(t, 0.25))
    yulduz(d, 22, 80, 2 + 3 * tolqin(t, 0.75))
    boya(k, m)
    return k


def voice(t):  # ikki tomonda tovush ustunlari
    k = yangi()
    m, d = niqob()
    for i, x in enumerate((6, 14, 22, 78, 86, 94)):
        h = 6 + 26 * tolqin(t * 2, i * 0.17)
        d.rounded_rectangle([s(x - 2.5), s(50 - h / 2), s(x + 2.5), s(50 + h / 2)], radius=s(2.5), fill=255)
    boya(k, m)
    v(k, 50, 51, 48)
    return k


def image(t):  # qalam V ni chizadi
    k = yangi()
    p = silliq(t / 0.65)
    sh = 1 - silliq((t - 0.88) / 0.12)
    v(k, 50, 52, 64, ochiq_x=p, shaffoflik=sh)
    if t < 0.7:
        x = 50 - 32 + 64 * p
        y = 30 + 40 * abs(2 * p - 1)
        m, d = niqob()
        d.polygon([(s(x), s(y)), (s(x + 5), s(y - 13)), (s(x + 13), s(y - 21)), (s(x + 21), s(y - 13)),
                   (s(x + 13), s(y - 5))], fill=255)
        boya(k, m)
    return k


def reminder(t):  # soat halqasi to'ladi, qo'ng'iroqchalar silkinadi
    k = yangi()
    m, d = niqob()
    halqa(d, 50, 54, 36, 4)
    boya(k, m, 0.25)
    m, d = niqob()
    yoy(d, 50, 54, 36, -90, -90 + 360 * silliq(t / 0.9), 5)
    boya(k, m)
    # Qo'ng'iroqchalar — budilnik «quloqlari», jiringlaganda silkinadi
    ay = 12 * math.sin(2 * math.pi * t * 4)
    for sx in (-1, 1):
        q = yangi()
        mm, dd = niqob()
        cx, cy = 50 + sx * 27, 20
        dd.pieslice([s(cx - 11), s(cy - 11), s(cx + 11), s(cy + 11)], 180, 360, fill=255)
        boya(q, mm)
        k.alpha_composite(q.rotate(sx * 35 + ay, center=(s(cx), s(cy)), resample=Image.BICUBIC))
    v(k, 50, 55, 44)
    return k


def memory(t):  # nuqtalar V ga uchib kiradi
    k = yangi()
    v(k, 50, 52, 54)
    m, d = niqob()
    for i in range(6):
        f = (t + i / 6) % 1
        a = 2 * math.pi * i / 6 + 0.6
        r = 46 * (1 - silliq(f))
        x, y = 50 + r * math.cos(a), 50 + r * math.sin(a)
        doira(d, x, y, 4.5 * (1 - f * 0.7), fill=int(255 * (1 - silliq((f - 0.75) / 0.25))))
    boya(k, m)
    return k


def kichik(t):  # Business «avtojavob» belgisi — kadrning ~46%i, yaltiroq o'tadi
    k = yangi()
    v(k, 50, 51, 46)
    x = -30 + 160 * silliq(t / 0.6)
    yal = Image.new("L", (N, N), 0)
    ImageDraw.Draw(yal).polygon([(s(x), 0), (s(x + 12), 0), (s(x - 18), N), (s(x - 30), N)], fill=150)
    alfa = np.asarray(k.getchannel("A"), np.float32) / 255
    yal = Image.fromarray((np.asarray(yal, np.float32) * alfa).astype(np.uint8))
    oq(k, yal, 1.0)
    return k


def wave(t):  # V qo'l silkitadi
    k = yangi()
    ay = 12 * math.sin(2 * math.pi * t * 2)
    v(k, 46, 54, 56, aylan=ay)
    m, d = niqob()
    for i, r in enumerate((10, 18)):
        sh = tolqin(t * 2, -i * 0.15)
        mm, dd = niqob()
        yoy(dd, 76, 26, r, 280, 350, 4)
        boya(k, mm, sh)
    return k


def broom(t):  # supurgi chang nuqtalarini supuradi
    k = yangi()
    v(k, 50, 40, 52)
    x = 30 + 40 * tolqin(t * 2)
    m, d = niqob()
    d.line([s(x + 10), s(52), s(x), s(80)], fill=255, width=round(s(4)))
    d.polygon([(s(x - 9), s(80)), (s(x + 8), s(80)), (s(x + 12), s(94)), (s(x - 13), s(94))], fill=255)
    boya(k, m)
    m, d = niqob()
    for i in range(4):
        f = (t * 2 + i / 4) % 1
        doira(d, 10 + 80 * f, 92 - 4 * math.sin(math.pi * f), 2.5, fill=int(255 * (1 - f)))
    yulduz(d, 82, 18, 3 + 4 * tolqin(t, 0.3))
    boya(k, m)
    return k


def chat(t):  # pufakchada «yozmoqda» nuqtalari
    k = yangi()
    m, d = niqob()
    d.rounded_rectangle([s(8), s(12), s(84), s(60)], radius=s(12), outline=255, width=round(s(4)))
    d.polygon([(s(20), s(58)), (s(34), s(58)), (s(18), s(72))], fill=255)
    for i in range(3):
        y = 36 - 6 * max(0.0, math.sin(2 * math.pi * (t * 2 - i * 0.15)))
        doira(d, 30 + i * 16, y, 5)
    boya(k, m)
    v(k, 74, 78, 38)
    return k


def build(t):  # kalit buraladi
    k = yangi()
    ay = 25 * math.sin(2 * math.pi * t)
    kalit = yangi()
    m, d = niqob()
    d.line([s(30), s(70), s(62), s(38)], fill=255, width=round(s(9)))
    doira(d, 66, 34, 13)
    d.polygon([(s(66), s(34)), (s(80), s(14)), (s(86), s(26)), (s(74), s(40))], fill=0)
    boya(kalit, m)
    kalit = kalit.rotate(ay, center=(s(48), s(52)), resample=Image.BICUBIC)
    k.alpha_composite(kalit)
    m, d = niqob()
    yulduz(d, 16, 18, 3 + 4 * tolqin(t, 0.2))
    yulduz(d, 88, 46, 2 + 3 * tolqin(t, 0.7))
    boya(k, m)
    v(k, 72, 78, 40)
    return k


def pro(t):  # olmos va uchqunlar
    k = yangi()
    m, d = niqob()
    q = 1 + 0.04 * tolqin(t)
    pts = [(14, 30), (28, 14), (68, 14), (82, 30), (48, 74)]
    c = (48, 40)
    pts = [(c[0] + (x - c[0]) * q, c[1] + (y - c[1]) * q) for x, y in pts]
    d.polygon([(s(x), s(y)) for x, y in pts], outline=255, width=round(s(4)))
    d.line([s(pts[0][0]), s(pts[0][1]), s(pts[3][0]), s(pts[3][1])], fill=255, width=round(s(3)))
    for x in (38, 58):
        d.line([s(c[0] + (x - c[0]) * q), s(c[1] + (14 - c[1]) * q), s(pts[4][0]), s(pts[4][1])],
               fill=255, width=round(s(2.5)))
    boya(k, m)
    m, d = niqob()
    yulduz(d, 86, 10, 3 + 5 * tolqin(t, 0.1))
    yulduz(d, 8, 60, 2 + 3 * tolqin(t, 0.6))
    boya(k, m)
    v(k, 74, 78, 40)
    return k


def limits(t):  # ikki halqa — sarflangan ulush to'lib-qaytadi
    k = yangi()
    m, d = niqob()
    halqa(d, 50, 50, 44, 5)
    halqa(d, 50, 50, 34, 5)
    boya(k, m, 0.2)
    m, d = niqob()
    yoy(d, 50, 50, 44, -90, -90 + 290 * silliq(tolqin(t) * 1.1), 5)
    yoy(d, 50, 50, 34, -90, -90 + 200 * silliq(tolqin(t, 0.15) * 1.1), 5)
    boya(k, m)
    v(k, 50, 51, 44)
    return k


def capabilities(t):  # nishon halqalari tashqariga tarqaladi
    k = yangi()
    m, d = niqob()
    for i in range(2):
        f = (t + i / 2) % 1
        mm, dd = niqob()
        halqa(dd, 50, 50, 22 + 26 * f, 4)
        boya(k, mm, 1 - f)
    v(k, 50, 51, 50)
    return k


TURLAR = {"emoji": emoji, "search": search, "document": document, "photo": photo,
          "voice": voice, "image": image, "reminder": reminder, "memory": memory,
          "kichik": kichik, "wave": wave, "broom": broom, "chat": chat, "build": build,
          "pro": pro, "limits": limits, "capabilities": capabilities}


def yasash(nom: str) -> int:
    fn = TURLAR[nom]
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(KADR):
            fn(i / KADR).resize((100, 100), Image.LANCZOS).save(os.path.join(tmp, f"{i:03d}.png"))
        chiq = os.path.join(PAPKA, f"status_{nom}.webm")
        for crf in range(28, 64, 3):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
                            "-i", os.path.join(tmp, "%03d.png"), "-c:v", "libvpx-vp9",
                            "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", str(crf), "-an",
                            "-t", "3", chiq], check=True)
            if os.path.getsize(chiq) <= MAX_BAYT:
                return os.path.getsize(chiq)
    raise RuntimeError(f"{nom}: 64 KB ga sig'madi")


if __name__ == "__main__":
    for nom in sys.argv[1:] or TURLAR:
        print(f"{nom}: {yasash(nom) // 1024} KB")
