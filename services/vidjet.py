"""Bot API 10.4 vidjetlari — interaktiv test va jonli limit kartasi.

Vidjet — xabar ichida ishlaydigan HTML (https://core.telegram.org/bots/widgets).
Bu modulda faqat SOF funksiyalar: belgini o'qish, oddiy matnga o'girish,
HTML yasash. Yuborish `handlers/` da.

⛔️ MODEL HTML YOZMAYDI. Xarita va tugmadagi qoida: model faqat MA'LUMOT
beradi (`[test] … [/test]` belgisi), HTML shu yerdagi tayyor shablondan
yasaladi. Model yozgan HTML — ishonchsiz kod, va u 4 KB siqilgan
chegaraga baribir sig'masdi. Model matni JSON bo'lib skriptga tushadi va
ekranga FAQAT `textContent` orqali chiqadi — `innerHTML` ga hech qachon.

⚠️ Production'da vidjet FAQAT shaxsiy chatda ishlaydi (2026-11). Boshqa
hamma joyda — guruh, guest, draft, oddiy zaxira — belgi oddiy matnga
aylanadi: `bloklar_matnga()`.
"""
import html
import json
import random
import re
import zlib

# ── Chegaralar (Telegram'niki: https://core.telegram.org/bots/widgets#limits)
HTML_MAX = 32768          # UTF-8 bayt
SIQILGAN_MAX = 4096       # zlib, 9-daraja — server shunday sanaydi
SIQILGAN_ZAXIRA = 3900    # serverning sanashidan ozgina farq — rad etilmasin
CAPTION_MAX = 1024

TEST_SAVOL_MAX = 10       # promptda ham shu son
TEST_VARIANT_MIN, TEST_VARIANT_MAX = 2, 6
_SAVOL_UZUN, _VARIANT_UZUN, _IZOH_UZUN = 300, 150, 300

# `[test]` … `[/test]`. Yopilmagani matn OXIRIGACHA blok hisoblanadi: model
# yopishni unutsa ham test yo'qolmasin.
# `[kartochka]` — xuddi shu yo'l (lug'at/atama kartochkalari).
_BLOK_RE = re.compile(
    r"\[\s*(test|kartochka)\s*\]\s*\n?(.*?)(?:\[\s*/\s*\1\s*\]|\Z)", re.S | re.I)
KARTOCHKA_MAX = 30
_KARTA_UZUN = 120
_HARF = "ABCDEF"


# ── LaTeX va markdown → o'qiladigan matn ─────────────────────────
# ⛔️ JONLI (2026-11-10): vidjetda «$7 \times 8$ nechaga teng?» chiqdi.
# Prompt matematikani LaTeX'da yozdiradi va oddiy javobda Telegram uni
# formula qilib chizadi — vidjetda esa matn faqat textContent, ya'ni xom
# `\times` o'quvchiga ko'rinadi. Prompt qoidasi kafolat emas, shuning uchun
# KOD tozalaydi: `\times` → ×, `\frac{1}{2}` → 1/2, `x^2` → x², `**a**` → a.
# `$` ham formula, ham dollar: Pandoc qoidasi — ochuvchidan keyin va
# yopuvchidan oldin bo'sh joy yo'q, yopuvchidan keyin raqam yo'q — va ichi
# formulaga o'xshashi shart. Shunda «$5 va $10» narx bo'lib qoladi.
_BUYRUQ = {
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "approx": "≈", "equiv": "≡", "sim": "~", "infty": "∞", "circ": "°", "degree": "°",
    "to": "→", "rightarrow": "→", "Rightarrow": "⇒", "leftarrow": "←", "Leftrightarrow": "⇔",
    "in": "∈", "notin": "∉", "subset": "⊂", "cup": "∪", "cap": "∩", "emptyset": "∅",
    "angle": "∠", "perp": "⊥", "parallel": "∥", "triangle": "△", "sum": "Σ", "prod": "∏",
    "int": "∫", "partial": "∂", "nabla": "∇", "forall": "∀", "exists": "∃", "sqrt": "√",
    "ldots": "…", "cdots": "⋯", "dots": "…",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "Delta": "Δ", "epsilon": "ε",
    "theta": "θ", "lambda": "λ", "mu": "μ", "pi": "π", "rho": "ρ", "sigma": "σ",
    "Sigma": "Σ", "tau": "τ", "phi": "φ", "omega": "ω", "Omega": "Ω",
    "quad": " ", "qquad": " ", "left": "", "right": "", "displaystyle": "",
    "sin": "sin", "cos": "cos", "tan": "tan", "log": "log", "ln": "ln", "lim": "lim",
}
_USTKI_HARF = "0123456789+-=()n"
_USTKI = str.maketrans(_USTKI_HARF, "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_OSTKI = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_FORMULA_RE = re.compile(
    r"\$\$(.+?)\$\$|\\\((.+?)\\\)|\\\[(.+?)\\\]|\$(?=\S)([^$\n]*?\S)\$(?!\d)", re.S)
_FORMULAGA_OXSHAYDI = re.compile(r"\\[A-Za-z%]|[\^_{}=+\-*/<>×÷]")


def _daraja(x: str, jadval, belgi: str) -> str:
    x = x.strip()
    if x and all(ch in _USTKI_HARF for ch in x) and (belgi == "^" or "n" not in x):
        return x.translate(jadval)
    return f"{belgi}{x}" if len(x) == 1 else f"{belgi}({x})"


def _qavsla(x: str) -> str:
    """Kasr surat/maxraji: bitta son yoki so'z — qavssiz, aks holda qavsda
    (`\\frac{a+b}{2}` → `(a+b)/2`, `a+b/2` emas — ma'nosi o'zgarmasin)."""
    x = x.strip()
    return x if re.fullmatch(r"[\w.,°√π⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ₀-₉]+", x) else f"({x})"


def _latex(t: str) -> str:
    t = t.replace("\\\\", " ")
    t = re.sub(r"\\[,;:! ]", " ", t).replace("\\%", "%")
    # Gradus — darajaning maxsus holati: `30^{\circ}` → 30°, `30^(°)` emas.
    t = re.sub(r"\^\s*\{?\s*\\circ\s*\}?", "°", t)
    for _ in range(10):                      # ichma-ich {} — ichidan tashqariga
        oldin = t
        t = re.sub(r"\^\{([^{}]*)\}", lambda m: _daraja(m[1], _USTKI, "^"), t)
        t = re.sub(r"_\{([^{}]*)\}", lambda m: _daraja(m[1], _OSTKI, "_"), t)
        t = re.sub(r"\^([0-9n+\-])", lambda m: m[1].translate(_USTKI), t)
        t = re.sub(r"(?<=[A-Za-z)])_([0-9])", lambda m: m[1].translate(_OSTKI), t)
        t = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
                   lambda m: f"{_qavsla(m[1])}/{_qavsla(m[2])}", t)
        t = re.sub(r"\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}",
                   lambda m: f"{m[1].strip().translate(_USTKI)}√{_qavsla(m[2])}", t)
        t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", lambda m: f"√{_qavsla(m[1])}", t)
        t = re.sub(r"\\(?:text|textbf|mathrm|mathbf|mathit|operatorname|mbox)\s*\{([^{}]*)\}",
                   r"\1", t)
        if t == oldin:
            break
    t = re.sub(r"\\([A-Za-z]+)", lambda m: _BUYRUQ.get(m[1], m[1]), t)
    t = t.replace("{", "").replace("}", "")
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def oddiy_matn(matn: str) -> str:
    """Vidjetga tushadigan model matni: LaTeX va markdown belgilarisiz."""
    if not matn:
        return matn

    def formula(m):
        ichi = next(g for g in m.groups() if g is not None)
        # `$56$`, `$x$` — operatorsiz, lekin baribir formula (javob varianti
        # shunday keladi). Narx esa `$56` — yopuvchi `$` siz, bu yerga tushmaydi.
        if _FORMULAGA_OXSHAYDI.search(ichi) or re.fullmatch(r"-?[\w.,]+", ichi):
            return _latex(ichi)
        return m.group(0)

    t = _FORMULA_RE.sub(formula, matn)
    # `$` siz yozilgan buyruq ham (model ba'zan delimitersiz yozadi) —
    # faqat MA'LUM buyruqlar, notanish `\foo` tegilmaydi.
    t = re.sub(r"\\([A-Za-z]+)", lambda m: _BUYRUQ.get(m[1], m.group(0)), t)
    t = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m[1] or m[2], t)
    # Prompt `==belgilash==` ga ruxsat beradi; ~~, || ham uchraydi.
    t = re.sub(r"==(.+?)==|~~(.+?)~~|\|\|(.+?)\|\|", lambda m: m[1] or m[2] or m[3], t)
    # Yakka `*kursiv*` — faqat so'z ichida emas: `2*3*4` ko'paytma bo'lib qoladi.
    t = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]*?\S)\*(?![\w*])", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t).replace("\\%", "%")
    t = re.sub(r"\[([^\]]+)\]\(https?://[^)\s]+\)", r"\1", t)
    t = html.unescape(re.sub(r"</?(?:b|i|u|s|em|strong|code|mark|sub|sup)\s*>", "", t, flags=re.I))
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def test_oqi(blok: str) -> list:
    """Blok matnidan savollar: [[savol, [variantlar], togri_index, izoh], …].

    Buzuq savol (to'g'ri javobi yo'q, bittadan ko'p, variant yetmaydi)
    TASHLANADI — model xatosi butun testni o'ldirmasin. Variantlar
    aralashtiriladi: model to'g'ri javobni deyarli har doim birinchi yozadi."""
    savollar, joriy = [], None

    def yop():
        if not joriy:
            return
        togrilar = [i for i, (_, t) in enumerate(joriy["v"]) if t]
        if len(togrilar) == 1 and TEST_VARIANT_MIN <= len(joriy["v"]) <= TEST_VARIANT_MAX:
            v = joriy["v"][:]
            random.shuffle(v)
            savollar.append([joriy["s"], [m for m, _ in v],
                             next(i for i, (_, t) in enumerate(v) if t), joriy["iz"]])

    for qator in blok.splitlines():
        q = qator.strip()
        if len(q) < 2:
            continue
        belgi, matn = q[0], oddiy_matn(q[1:].strip())
        if not matn:
            continue
        if belgi == "?":
            yop()
            joriy = {"s": matn[:_SAVOL_UZUN], "v": [], "iz": ""}
        elif joriy is None:
            continue
        elif belgi in "+-":
            joriy["v"].append((matn[:_VARIANT_UZUN], belgi == "+"))
        elif belgi == "!":
            joriy["iz"] = matn[:_IZOH_UZUN]
    yop()
    return savollar[:TEST_SAVOL_MAX]


def kartochka_oqi(blok: str) -> list:
    """`old — orqa` qatorlari: [[old, orqa], …]. Ajratgichi yo'q qator
    tashlanadi. Ajratgich: ` — `, ` – `, ` - `, `=`, `: ` (model har xil
    yozadi). Ikki nuqta faqat bo'sh joy bilan — "10:30" bo'linmasin; so'z
    ichidagi chiziqcha ("well-known") ham ajratgich emas."""
    out = []
    for qator in blok.splitlines():
        q = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", qator).strip()
        qism = re.split(r"\s+[—–-]\s+|\s*=\s*|:\s+", q, maxsplit=1)
        if len(qism) == 2:
            old, orqa = (oddiy_matn(x.strip())[:_KARTA_UZUN] for x in qism)
            if old and orqa:
                out.append([old, orqa])
    return out[:KARTOCHKA_MAX]


def bloklar_ajrat(matn: str) -> tuple:
    """(bloklarsiz matn, [(tur, ma'lumot), …]). Bitta ham to'g'ri qatori
    yo'q blok AJRATILMAYDI — u `bloklar_matnga()` orqali matn bo'lib qoladi."""
    bloklar = []

    def bir(m):
        tur = m.group(1).lower()
        d = BLOK_TURLARI[tur][0](m.group(2))
        if not d:
            return m.group(0)
        bloklar.append((tur, d))
        return ""

    qolgan = _BLOK_RE.sub(bir, matn or "")
    return re.sub(r"\n{3,}", "\n\n", qolgan).strip(), bloklar


def test_matni(savollar: list) -> str:
    qismlar, javoblar = ["📝 **Test**"], []
    for n, (s, v, t, iz) in enumerate(savollar, 1):
        qismlar.append(f"**{n}. {s}**\n" + "\n".join(f"{_HARF[i]}) {x}" for i, x in enumerate(v)))
        javoblar.append(f"{n} — {_HARF[t]}" + (f". {iz}" if iz else ""))
    # Javoblar yig'iladigan bo'limda: rich xabarda yopiq turadi, oddiy
    # matnda esa sarlavha bo'lib oxirida (strip_rich_tokens).
    qismlar.append("[batafsil: ✅ Javoblar]\n" + "\n".join(javoblar) + "\n[/batafsil]")
    return "\n\n".join(qismlar)


def kartochka_matni(k: list) -> str:
    return "🗂 **Kartochkalar**\n\n" + "\n".join(
        f"{n}. **{a}** — {b}" for n, (a, b) in enumerate(k, 1))


def bloklar_matnga(matn: str, qoralama: bool = False) -> str:
    """Vidjet chizilmaydigan joy uchun: blok → oddiy matn (test, kartochka).

    `qoralama=True` — oqim paytidagi draft: blok o'rniga faqat "tayyorlanmoqda".
    Aks holda `+` belgili qatorlar javobni test tugashidan OLDIN ochib qo'yardi."""
    if not matn or "[" not in matn:
        return matn

    def bir(m):
        tur = m.group(1).lower()
        oqi, matni, _, _, kutish = BLOK_TURLARI[tur]
        if qoralama:
            return kutish
        d = oqi(m.group(2))
        # Hech narsa o'qilmadi — belgilarsiz xom matn qoladi, ma'lumot yo'qolmasin.
        return matni(d) if d else m.group(2).strip()

    return _BLOK_RE.sub(bir, matn)


def _json(qiymat) -> str:
    # `<` qochiriladi: savol ichidagi "</script>" skriptni yopib qo'ymasin.
    return (json.dumps(qiymat, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace("\x00", ""))


def sigadimi(html: str) -> bool:
    b = html.encode("utf-8")
    return len(b) <= HTML_MAX and len(zlib.compress(b, 9)) <= SIQILGAN_ZAXIRA


# ── Interaktiv test ───────────────────────────────────────────────
# Botga so'rov YO'Q (allow_queries yo'q): hammasi telefonda. Javoblar shu
# xabarning localStorage'ida — qayta ochilganda test o'sha joyida turadi.
# Variant — oddiy <button>: vidjetda input umuman yo'q.
_TEST_SHABLON = """<style>
body{margin:0;padding:8px 12px 14px}
.n{color:var(--tg-theme-hint-color);font-size:.85em}
.q{font-weight:600;margin:4px 0 10px}
.v{display:block;width:100%;text-align:left;white-space:normal;margin:0 0 6px}
.ok{background:#2e9e4f;color:#fff}
.no{background:#d9534f;color:#fff}
.iz{color:var(--tg-theme-hint-color);font-size:.9em;margin:4px 0 10px}
.r{font-size:1.6em;font-weight:700;margin:4px 0 12px}
</style>
<div id="a"></div>
<script>
var Q=@@Q@@,S;
try{S=JSON.parse(localStorage.getItem("s"))}catch(e){}
if(!S||!S.j)S={i:0,j:[]};
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function go(x){S=x;try{localStorage.setItem("s",JSON.stringify(S))}catch(e){}r()}
function r(){
var a=document.getElementById("a"),i=S.i,k=0,n,b;a.innerHTML="";
if(i>=Q.length){
for(n=0;n<Q.length;n++)if(S.j[n]===Q[n][2])k++;
a.appendChild(el("div","n","Natija"));
a.appendChild(el("div","r",k+" / "+Q.length));
b=el("button",0,"↻ Qaytadan");b.onclick=function(){go({i:0,j:[]})};a.appendChild(b);return}
var q=Q[i],t=S.j[i];
a.appendChild(el("div","n",(i+1)+" / "+Q.length));
a.appendChild(el("div","q",q[0]));
q[1].forEach(function(v,m){
var c=el("button","v"+(t==null?"":m===q[2]?" ok":m===t?" no":""),v);
if(t==null)c.onclick=function(){S.j[i]=m;go(S)};
a.appendChild(c)});
if(t!=null){
if(q[3])a.appendChild(el("div","iz",q[3]));
b=el("button",0,i+1<Q.length?"Keyingi →":"Natijani ko'rish");
b.onclick=function(){S.i=i+1;go(S)};a.appendChild(b)}
}
r();
</script>"""


def test_html(savollar: list) -> str | None:
    """Tayyor HTML yoki None — 4 KB'ga sig'masa. None bo'lsa chaqiruvchi
    testni matn bilan yuboradi: savollarni jimgina kesib tashlash —
    foydalanuvchidan yarim testni yashirish bo'lardi."""
    html = _imzoli(_TEST_SHABLON).replace("@@Q@@", _json(savollar))
    return html if sigadimi(html) else None


def test_izohi(savollar: list) -> str:
    """Vidjetni qo'llamaydigan ilova FAQAT shuni ko'radi (va chat ro'yxati)."""
    return f"📝 Test · {len(savollar)} ta savol"


# ── Lug'at kartochkalari ──────────────────────────────────────────
# Bosilsa aylanadi (old ↔ orqa), ← → bilan o'tiladi, «Aralash» tartibni
# o'zgartiradi. Holat (joriy kartochka, tomoni, tartib) — localStorage'da.
# Model matni faqat textContent orqali. 3D aylantirish profilda yo'q —
# tomon rangi va matni almashadi.
_KARTOCHKA_SHABLON = """<style>
body{margin:0;padding:10px 12px 12px;font-family:system-ui,sans-serif}
.n{color:var(--tg-theme-hint-color);font-size:.85em}
.k{margin:8px 0 10px;min-height:120px;border-radius:14px;background:var(--tg-theme-secondary-bg-color);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:16px}
.k b{font-size:1.35em}
.k span{color:var(--tg-theme-hint-color);font-size:.78em;margin-top:10px}
.o{background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color)}
.o span{color:var(--tg-theme-button-text-color)}
.t{display:flex;gap:6px}.t button{flex:1}
</style>
<div id="a"></div>
<script>
var K=@@K@@,S;try{S=JSON.parse(localStorage.getItem("s"))}catch(e){}
if(!S||!S.p||S.p.length!=K.length)S={i:0,o:0,p:K.map(function(x,i){return i})};
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function go(){try{localStorage.setItem("s",JSON.stringify(S))}catch(e){}r()}
function r(){var a=document.getElementById("a"),c=K[S.p[S.i]],k=el("div","k"+(S.o?" o":"")),t=el("div","t"),p=el("button",0,"←"),q=el("button",0,"Aralash"),x=el("button",0,"→");a.innerHTML="";
a.appendChild(el("div","n","Kartochka "+(S.i+1)+" / "+K.length));
k.appendChild(el("b",0,c[S.o]));k.appendChild(el("span",0,S.o?"Bosing — orqaga":"Bosing — javobi"));
k.onclick=function(){S.o=S.o?0:1;go()};a.appendChild(k);
p.onclick=function(){S.i=(S.i+K.length-1)%K.length;S.o=0;go()};
x.onclick=function(){S.i=(S.i+1)%K.length;S.o=0;go()};
q.onclick=function(){for(var i=S.p.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),z=S.p[i];S.p[i]=S.p[j];S.p[j]=z}S.i=0;S.o=0;go()};
t.appendChild(p);t.appendChild(q);t.appendChild(x);a.appendChild(t)}
r();
</script>"""


def kartochka_html(k: list) -> str | None:
    html = _imzoli(_KARTOCHKA_SHABLON).replace("@@K@@", _json(k))
    return html if sigadimi(html) else None


def kartochka_izohi(k: list) -> str:
    return f"🗂 Kartochkalar · {len(k)} ta"


# tur → (o'qish, matn shakli, HTML yoki None, izoh, draftdagi o'rinbosar).
# Yangi blok turi — shu yerga bitta qator va _BLOK_RE ga nomi.
BLOK_TURLARI = {
    "test": (test_oqi, test_matni, test_html, test_izohi, "📝 _Test tayyorlanmoqda…_"),
    "kartochka": (kartochka_oqi, kartochka_matni, kartochka_html, kartochka_izohi,
                  "🗂 _Kartochkalar tayyorlanmoqda…_"),
}


# ── Ob-havo kartasi ───────────────────────────────────────────────
# Holat (`chat_data`) — services/obhavo.py::prognoz() qaytargan lug'at.
# Shahar nomi tashqi API'dan keladi — u ham faqat textContent orqali chiqadi;
# innerHTML ga faqat shu yerdagi O'ZIMIZNING ikonka satrlari tushadi.
# Yangilash: karta ko'ringanda ma'lumot 15 daqiqadan eski bo'lsa botdan
# "w:lat,lon" so'raydi; yangisi shu xabarning localStorage'ida qoladi.
# ⚠️ Animatsiya faqat transform bilan: opacity/blur vidjet profilida "og'ir"
# element, 16 tadan oshsa vidjet to'xtatiladi.
OBHAVO_SOROVI = "w:"
_OBHAVO_SHABLON = """<style>
body{margin:0;padding:14px 16px 16px;font-family:system-ui,sans-serif;color:#fff;background:linear-gradient(165deg,#4f9be6,#2a62b8)}
body.b{background:linear-gradient(165deg,#8494a8,#4d5b6e)}
body.n{background:linear-gradient(165deg,#24335c,#0e1530)}
.u{display:flex;justify-content:space-between;align-items:flex-start}
.c{font-weight:600}
.h{font-size:3.4em;font-weight:300;line-height:1.05;margin:2px 0}
.s{font-size:.92em}
.m{font-size:.8em;color:rgba(255,255,255,.82);margin-top:8px}
.r{display:flex;margin-top:10px;padding:8px 4px;border-radius:14px;background:rgba(255,255,255,.16)}
.r div{flex:1;text-align:center;font-size:.75em;color:rgba(255,255,255,.85)}
.r b{display:block;font-size:1.25em;color:#fff;font-weight:600}
.r svg{margin:3px auto}
@keyframes a{to{transform:rotate(360deg)}}
@keyframes d{0%,100%{transform:translateX(0)}50%{transform:translateX(1.5px)}}
@keyframes y{from{transform:translateY(-2px)}to{transform:translateY(2px)}}
.a .ry{transform-origin:12px 12px;animation:a 14s linear infinite}
.a .cl{animation:d 4s ease-in-out infinite}
.a .dr{animation:y .8s linear infinite alternate}
</style>
<div id="a"></div>
<script>
var W=window.TelegramWidget,D,
SN='<g class="ry" stroke="#FFD54A" stroke-width="1.6" stroke-linecap="round"><path d="M12 1.5v2.4M12 20.1v2.4M1.5 12h2.4M20.1 12h2.4M4.6 4.6l1.7 1.7M17.7 17.7l1.7 1.7M4.6 19.4l1.7-1.7M17.7 6.3l1.7-1.7"/></g><circle cx="12" cy="12" r="4.6" fill="#FFD54A"/>',
MN='<path fill="#F3E3A1" d="M15 3a8.8 8.8 0 1 0 6 15.2A7.2 7.2 0 0 1 15 3z"/>',
CL='<path class="cl" fill="#fff" d="M7 18.5h10.6a4 4 0 0 0 .3-8 5.6 5.6 0 0 0-10.8 1.6A3.2 3.2 0 0 0 7 18.5z"/>',
CU='<path class="cl" fill="#fff" d="M7 15.5h10.6a4 4 0 0 0 .3-8 5.6 5.6 0 0 0-10.8 1.6A3.2 3.2 0 0 0 7 15.5z"/>',
G={q:SN,qb:'<g transform="translate(-4 -4) scale(.8)">'+SN+'</g>'+CL,b:CL,
t:'<path stroke="#fff" stroke-width="1.8" stroke-linecap="round" d="M4 8h16M2.5 12h19M5 16h14"/>',
y:CU+'<path class="dr" stroke="#9fd3ff" stroke-width="1.6" stroke-linecap="round" d="M9 18l-1 3M13 18l-1 3M17 18l-1 3"/>',
qr:CU+'<g class="dr" fill="#fff"><circle cx="8.5" cy="19.5" r="1.1"/><circle cx="12.5" cy="21" r="1.1"/><circle cx="16.5" cy="19.5" r="1.1"/></g>',
m:CU+'<path fill="#FFD54A" d="M12.8 15l-3 4.6h2.3l-1 3.9 4-5.6h-2.3l1.6-2.9z"/>'};
function p(s){try{return JSON.parse(s)}catch(e){return null}}
function ic(k,n,tun,a){var g=G[k]||CL;if(tun&&k=="q")g=MN;if(tun&&k=="qb")g='<g transform="translate(-4 -4) scale(.8)">'+MN+'</g>'+CL;
return '<svg'+(a?' class="a"':'')+' width="'+n+'" height="'+n+'" viewBox="0 0 24 24">'+g+'</svg>'}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function qator(v,f){var r=el("div","r");v.forEach(function(x){var c=el("div");f(c,x);r.appendChild(c)});return r}
function r(d){if(!d)return;D=d;var a=document.getElementById("a"),u=el("div","u"),l=el("div"),i=el("div");
document.body.className=d.tun?"n":/^(b|t|y|qr|m)$/.test(d.k)?"b":"";
a.innerHTML="";l.appendChild(el("div","c",d.j));l.appendChild(el("div","h",d.h+"°"));l.appendChild(el("div","s",d.s));
i.innerHTML=ic(d.k,78,d.tun,1);u.appendChild(l);u.appendChild(i);a.appendChild(u);
a.appendChild(el("div","m","His qilinadi "+d.f+"° · Shamol "+d.w+" km/soat · Namlik "+d.nm+"%"));
a.appendChild(qator(d.s2,function(c,x){c.appendChild(el("span",0,x[0]));var s=el("div");s.innerHTML=ic(x[1],22,x[3]);c.appendChild(s);c.appendChild(el("b",0,x[2]+"°"))}));
a.appendChild(qator(d.k3,function(c,x){c.appendChild(el("span",0,x[0]));var s=el("div");s.innerHTML=ic(x[1],22,0);c.appendChild(s);c.appendChild(el("b",0,x[2]+"°"));c.appendChild(el("span",0,x[3]+"°"))}));
a.appendChild(el("div","m",d.v+" holatiga · Open-Meteo"))}
var S=p(W&&W.chatData),L;try{L=p(localStorage.getItem("d"))}catch(e){}
r(L&&S&&L.t>S.t?L:S);
function y(){if(!W||!W.request||!D||!D.c||Date.now()/1e3-D.t<900)return;
W.request("w:"+D.c[0]+","+D.c[1]).then(function(o){var x=p(o.result);if(x&&x.s2){x.j=D.j;r(x);try{localStorage.setItem("d",JSON.stringify(x))}catch(e){}}},function(){})}
y();document.addEventListener("visibilitychange",function(){if(!document.hidden)y()});setInterval(y,60000);
</script>"""


def obhavo_html() -> str:
    return _imzoli(_OBHAVO_SHABLON, "#ffffffd9")


def obhavo_holati(d: dict) -> str:
    return _json(d)


def obhavo_izohi(d: dict) -> str:
    return f"🌤 {d['j']}: {d['h']}°, {d['s'].lower()}"


# ── Valyuta kartasi ───────────────────────────────────────────────
# Holat — services/valyuta.py::holat(): {"d": sana, "r": [[kod, nom,
# 1 birlik so'mda, kunlik farq], ...], "t": vaqt}. Konvertor klaviaturasiz:
# qatorni bosib valyuta, tugmani bosib summa tanlanadi (vidjetda input yo'q).
# ⚠️ `f()` — Python'dagi `valyuta.son()` ning AYNAN o'zi (2 xona, 1 dan
# kichikda 4, oxirgi nollarsiz, minglik bo'sh joy, vergul): javob matni va
# karta bitta summani ikki xil yozmasin.
# Yangilash: 1 soatdan eski bo'lsa "v:USD,EUR" so'raydi (kurs kuniga bir).
VALYUTA_SOROVI = "v:"
_VALYUTA_SHABLON = r"""<style>
body{margin:0;padding:12px 14px 14px;font-family:system-ui,sans-serif}
.h{font-weight:600}
.n{color:var(--tg-theme-hint-color);font-size:.8em;margin:2px 0 8px}
.r{display:flex;align-items:center;gap:10px;padding:5px 10px;border-radius:12px;margin:0 0 2px}
.s{background:var(--tg-theme-secondary-bg-color)}
.f{font-size:1.4em;line-height:1}
.k{flex:1;min-width:0}
.k b,.v b{display:block}
.k span{display:block;color:var(--tg-theme-hint-color);font-size:.78em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.v{text-align:right;font-variant-numeric:tabular-nums}
.up{color:#2e9e4f;font-size:.8em}.dn{color:#d9534f;font-size:.8em}.eq{color:var(--tg-theme-hint-color);font-size:.8em}
.c{display:flex;gap:6px;margin:10px 0 8px}
.c button{flex:1;padding:6px 0}
.c .on{background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color)}
.o{font-size:1.15em;font-weight:600;text-align:center;font-variant-numeric:tabular-nums}
</style>
<div id="a"></div>
<script>
var W=window.TelegramWidget,D,I=0,M=100,X=[1,10,100,1000];
function p(s){try{return JSON.parse(s)}catch(e){return null}}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function f(x){var s=x.toFixed(Math.abs(x)>=1?2:4);if(s.indexOf(".")>=0)s=s.replace(/0+$/,"").replace(/\.$/,"");var q=s.split(".");return q[0].replace(/\B(?=(\d{3})+(?!\d))/g," ")+(q[1]?","+q[1]:"")}
function fl(c){return c=="XDR"?"🌐":String.fromCodePoint(127397+c.charCodeAt(0),127397+c.charCodeAt(1))}
function r(){var a=document.getElementById("a"),d=D;if(!d||!d.r||!d.r.length)return;if(I>=d.r.length)I=0;a.innerHTML="";
a.appendChild(el("div","h","💱 Valyuta kursi"));a.appendChild(el("div","n","Markaziy bank · "+d.d));
d.r.forEach(function(x,i){var q=el("div","r"+(i==I?" s":"")),k=el("div","k"),v=el("div","v"),o=f(Math.abs(x[3]));
q.appendChild(el("span","f",fl(x[0])));k.appendChild(el("b",0,x[0]));k.appendChild(el("span",0,x[1]));q.appendChild(k);
v.appendChild(el("b",0,f(x[2])+" so'm"));v.appendChild(el("span",o=="0"?"eq":x[3]>0?"up":"dn",o=="0"?"o'zgarmagan":(x[3]>0?"▲ ":"▼ ")+o));
q.appendChild(v);q.onclick=function(){I=i;r()};a.appendChild(q)});
var c=el("div","c");X.forEach(function(m){var b=el("button",m==M?"on":0,f(m));b.onclick=function(){M=m;r()};c.appendChild(b)});a.appendChild(c);
var x=d.r[I];a.appendChild(el("div","o",f(M)+" "+x[0]+" = "+f(M*x[2])+" so'm"))}
var S=p(W&&W.chatData),L;try{L=p(localStorage.getItem("d"))}catch(e){}
D=L&&S&&L.t>S.t?L:S;r();
function y(){if(!W||!W.request||!D||!D.r||Date.now()/1e3-D.t<3600)return;
W.request("v:"+D.r.map(function(x){return x[0]}).join(",")).then(function(o){var x=p(o.result);if(x&&x.r&&x.r.length){D=x;r();try{localStorage.setItem("d",JSON.stringify(x))}catch(e){}}},function(){})}
y();document.addEventListener("visibilitychange",function(){if(!document.hidden)y()});setInterval(y,300000);
</script>"""


def valyuta_html() -> str:
    return _imzoli(_VALYUTA_SHABLON)


def valyuta_holati(d: dict) -> str:
    return _json(d)


def valyuta_izohi(d: dict) -> str:
    """Vidjetsiz ilova ko'radigan yagona matn — birinchi kurs shu yerda ham."""
    from services.valyuta import son
    x = d["r"][0]
    return f"💱 Markaziy bank kursi ({d['d']}): 1 {x[0]} = {son(x[2])} so'm"


def valyuta_matni(d: dict) -> str:
    """Karta rad etilganda — o'sha raqamlar matn bilan."""
    from services.valyuta import son
    return "\n".join([f"💱 Markaziy bank kursi ({d['d']}):"]
                     + [f"1 {x[0]} ({x[1]}) = {son(x[2])} so'm" for x in d["r"]])


# ── Namoz vaqtlari kartasi ────────────────────────────────────────
# Holat — services/namoz.py::holat(): {"j", "d": sana, "v": [6 vaqt],
# "e": ertangi Bomdod, "u": shahar UTC farqi (daqiqa), "m": manba, "q"}.
# Sanoq SHAHAR soati bilan (`u`), telefon soati bilan emas: Toshkentdagi
# odam Makka vaqtini so'rasa ham "Asrgacha" to'g'ri chiqsin. Kun almashsa
# (shahar sanasi `d` dan boshqa) botdan "n:"+q so'raydi, 5 daqiqada bir.
NAMOZ_SOROVI = "n:"
_NAMOZ_SHABLON = """<style>
body{margin:0;padding:12px 14px 14px;font-family:system-ui,sans-serif}
.b{border-radius:16px;padding:12px 14px;color:#fff;background:linear-gradient(160deg,#1f7a5a,#0f4a3a)}
.j{font-weight:600}.n{font-size:.8em;color:#ffffffd9}
.k{margin-top:10px;font-size:.85em;color:#ffffffe6}
.s{font-size:2.3em;font-weight:300;line-height:1.1;font-variant-numeric:tabular-nums}
.r{display:flex;justify-content:space-between;padding:7px 12px;border-radius:12px;margin-top:3px;font-variant-numeric:tabular-nums}
.o{color:var(--tg-theme-hint-color)}
.x{background:var(--tg-theme-secondary-bg-color);font-weight:600}
.u{color:var(--tg-theme-hint-color);font-size:.78em;margin-top:8px;text-align:center}
</style>
<div id="a"></div>
<script>
var W=window.TelegramWidget,D,N=["🌙 Bomdod","🌅 Quyosh","☀️ Peshin","🌤 Asr","🌇 Shom","🌌 Xufton"],
M={r:"Rasmiy jadval",t:"Taxminiy: Toshkent jadvali + uzunlik farqi",h:"Hisoblangan (±1 daqiqa)",a:"Astronomik hisob · Asr Hanafiy"},S,I=-1,Q=0;
function p(s){try{return JSON.parse(s)}catch(e){return null}}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function m(s){var a=s.split(":");return a[0]*60+ +a[1]}
function z(n){return(n<10?"0":"")+n}
function sh(){var t=new Date(Date.now()+D.u*6e4);return{d:z(t.getUTCDate())+"."+z(t.getUTCMonth()+1)+"."+t.getUTCFullYear(),n:t.getUTCHours()*60+t.getUTCMinutes()+t.getUTCSeconds()/60}}
function k(){var h=sh(),i=0;while(i<6&&m(D.v[i])<=h.n)i++;return{i:i,q:(i<6?m(D.v[i]):m(D.e)+1440)-h.n}}
function r(){var a=document.getElementById("a"),x=k(),b=el("div","b");I=x.i;a.innerHTML="";
b.appendChild(el("div","j","🕌 "+D.j));b.appendChild(el("div","n",D.d));
b.appendChild(el("div","k",I==1?"Quyosh chiqishiga":(I<6?N[I].split(" ")[1]:"Bomdod")+" namozigacha"));
S=el("div","s");b.appendChild(S);a.appendChild(b);
D.v.forEach(function(v,i){var q=el("div","r"+(i==I||(I==6&&i==0)?" x":i<I?" o":""));q.appendChild(el("span",0,N[i]));q.appendChild(el("b",0,v));a.appendChild(q)});
a.appendChild(el("div","u",M[D.m]||""));t()}
function t(){var x=k(),s=Math.max(0,Math.round(x.q*60));if(x.i!=I)return r();
S.textContent=Math.floor(s/3600)+":"+z(Math.floor(s/60)%60)+":"+z(s%60)}
var C=p(W&&W.chatData),L;try{L=p(localStorage.getItem("d"))}catch(e){}
D=L&&C&&L.t>C.t?L:C;if(D&&D.v)r();
function y(){if(!W||!W.request||!D||sh().d==D.d||Date.now()-Q<3e5)return;Q=Date.now();
W.request("n:"+D.q).then(function(o){var x=p(o.result);if(x&&x.v){x.j=D.j;D=x;r();try{localStorage.setItem("d",JSON.stringify(x))}catch(e){}}},function(){})}
y();document.addEventListener("visibilitychange",function(){if(!document.hidden)y()});
setInterval(function(){if(D&&D.v){t();y()}},1000);
</script>"""


def namoz_html() -> str:
    return _imzoli(_NAMOZ_SHABLON)


def namoz_holati(d: dict) -> str:
    return _json(d)


def namoz_izohi(d: dict) -> str:
    """Vidjetsiz ilova ko'radigan yagona matn — vaqtlarning hammasi shu yerda."""
    from services.namoz import NOMLAR
    return f"🕌 {d['j']}, {d['d']}\n" + " · ".join(
        f"{n} {t}" for n, t in zip(NOMLAR, d["v"]))


def namoz_matni(d: dict) -> str:
    """Karta rad etilganda. ⚠️ `namoz.matn()` EMAS — u modelga yozilgan
    (ichida "tekshirishni ayting" kabi ko'rsatma bor)."""
    from services.namoz import NOMLAR
    manba = {"t": "\n⚠️ Taxminiy (±2 daqiqa)", "a": "\nAstronomik hisob, Asr Hanafiy"}
    return (f"🕌 {d['j']} — {d['d']}\n"
            + "\n".join(f"{n}: {t}" for n, t in zip(NOMLAR, d["v"]))
            + manba.get(d.get("m"), ""))


# ── Eslatma kartasi ───────────────────────────────────────────────
# Holat: {"m": matn, "at": epoch, "r": takror, "id": eslatma id}.
# Sanoq telefonda; "e:<id>" so'rovi eslatma hali faolmi va keyingi vaqti
# qachonligini so'raydi — bekor qilingan eslatma sanalib turmasin, takroriy
# eslatma esa keyingi vaqtga o'tsin. Javob {"at": …} yoki {"x": 1} (yo'q).
# Vaqt Toshkentda ko'rsatiladi: eslatma vaqti Toshkent bo'yicha qo'yiladi.
ESLATMA_SOROVI = "e:"
_ESLATMA_SHABLON = """<style>
body{margin:0;padding:12px 14px 14px;font-family:system-ui,sans-serif}
.b{border-radius:16px;padding:14px;color:#fff;background:linear-gradient(160deg,#6a4fd6,#3d2a8f)}
.h{font-size:.85em;color:#ffffffd9}
.m{font-weight:600;font-size:1.1em;margin:6px 0 2px;overflow-wrap:anywhere}
.s{font-size:2.2em;font-weight:300;line-height:1.15;margin-top:10px;font-variant-numeric:tabular-nums}
.u{color:var(--tg-theme-hint-color);font-size:.8em;margin-top:8px;text-align:center}
</style>
<div id="a"></div>
<script>
var W=window.TelegramWidget,D,S,Q=0,R={daily:"🔁 Har kuni",weekly:"🔁 Har hafta",monthly:"🔁 Har oy"};
function p(s){try{return JSON.parse(s)}catch(e){return null}}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function z(n){return(n<10?"0":"")+n}
function v(at){var t=new Date((at+18e3)*1e3);return z(t.getUTCDate())+"."+z(t.getUTCMonth()+1)+"."+t.getUTCFullYear()+", "+z(t.getUTCHours())+":"+z(t.getUTCMinutes())}
function r(){var a=document.getElementById("a"),b=el("div","b");a.innerHTML="";
b.appendChild(el("div","h","⏰ Eslatma"+(R[D.r]?" · "+R[D.r]:"")));b.appendChild(el("div","m",D.m));
b.appendChild(el("div","h","📅 "+v(D.at)));S=el("div","s");b.appendChild(S);a.appendChild(b);
if(!D.x)a.appendChild(el("div","u","Vaqti kelganda shu chatga yozaman"));t()}
function t(){if(D.x){S.textContent=D.at*1e3<=Date.now()?"✅ Yuborildi":"🚫 Bekor qilingan";return}
var s=Math.round(D.at-Date.now()/1e3);if(s<=0){S.textContent="⏳ Vaqti keldi";y(30);return}
var k=Math.floor(s/86400);S.textContent=(k?k+" kun ":"")+Math.floor(s/3600)%24+":"+z(Math.floor(s/60)%60)+":"+z(s%60)}
function y(n){if(!W||!W.request||!D||Date.now()-Q<(n||300)*1e3)return;Q=Date.now();
W.request("e:"+D.id).then(function(o){var x=p(o.result);if(x&&(x.at||x.x)){if(x.at){D.at=x.at;D.x=0}else D.x=1;r();try{localStorage.setItem("d",JSON.stringify(D))}catch(e){}}},function(){})}
var C=p(W&&W.chatData),L;try{L=p(localStorage.getItem("d"))}catch(e){}
D=L&&C&&L.id==C.id?L:C;if(D&&D.at){r();Q=0;y(1)}
document.addEventListener("visibilitychange",function(){if(!document.hidden)y(20)});
setInterval(function(){if(D&&D.at){t();y()}},1000);
</script>"""


def eslatma_html() -> str:
    return _imzoli(_ESLATMA_SHABLON)


def eslatma_holati(d: dict) -> str:
    return _json(d)


def eslatma_izohi(d: dict) -> str:
    return f"⏰ Eslatma: {d['m']}"[:CAPTION_MAX]


def _eslatma_zaxirasi(d: dict) -> str:
    # Karta rad etilsa matn kerak emas: model javobi vaqtni allaqachon aytgan.
    return ""


# ── Brend: Vexon «V» logosi (SVG) ─────────────────────────────────
# Vidjet tashqi rasm yuklay olmaydi (tarmoq yo'q), JPEG/PNG esa siqilgan
# 4 KB ga sig'maydi — logo vektorda: assets/vexon_v.png dagi ikki lenta va
# logodagi halqa. ⚠️ `opacity`/`filter` YO'Q (vidjet ularni "og'ir" deb
# sanaydi) — shaffoflik faqat `fill-opacity` va gradient bilan. Halqa
# aylanadi (`.rg`), ya'ni faqat transform.
_LOGO = (
    '<svg class="lg" viewBox="0 0 100 100"><defs>'
    '<linearGradient id="la" x1="0" y1="0" x2=".7" y2="1"><stop offset="0" stop-color="#6a9bff"/>'
    '<stop offset=".5" stop-color="#3442ff"/><stop offset=".82" stop-color="#4a3cf0"/>'
    '<stop offset="1" stop-color="#b07cff"/></linearGradient>'
    '<linearGradient id="lb" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d792ff"/>'
    '<stop offset=".4" stop-color="#3fdcff"/><stop offset="1" stop-color="#3d55ff"/></linearGradient>'
    '<linearGradient id="lc" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7fd8ff"/>'
    '<stop offset="1" stop-color="#e2a6ff"/></linearGradient>'
    '<radialGradient id="ld"><stop offset="0" stop-color="#3b5bff" stop-opacity=".45"/>'
    '<stop offset="1" stop-color="#3b5bff" stop-opacity="0"/></radialGradient></defs>'
    '<circle cx="50" cy="50" r="50" fill="url(#ld)"/>'
    '<circle class="rg" cx="50" cy="50" r="46" fill="none" stroke="#5a6dff" stroke-width="1.3" '
    'stroke-dasharray="190 99" stroke-linecap="round"/>'
    '<path fill="url(#la)" d="M6 22C22 20 34 26 42 38L60 72C64 80 61 90 52 90C46 90 43 86 41 81L19 38C15 30 11 25 6 22Z"/>'
    '<path fill="url(#lb)" d="M95 18C84 19 73 25 66 35L47 65C57 68 64 62 69 54L86 29C89 24 92 20 95 18Z"/>'
    '<path fill="url(#lc)" fill-opacity=".85" d="M6 22C22 20 34 26 42 38L49 51C40 38 28 28 6 22Z"/></svg>')
_BREND_CSS = (
    "body{margin:0;padding:10px;font-family:system-ui,sans-serif}"
    ".hd{display:flex;align-items:center;gap:12px;padding:14px 16px;border-radius:18px;color:#fff;"
    "background:radial-gradient(130% 160% at 0% 0%,#22309a 0,#0b1033 50%,#05060f 100%)}"
    ".hd .lg{width:56px;height:56px;flex:none}"
    ".rg{transform-origin:50px 50px;animation:rg 10s linear infinite}"
    "@keyframes rg{to{transform:rotate(360deg)}}"
    # ⛔️ `background-clip:text` YO'Q: Telegram vidjeti uni qo'llamaydi — jonli
    # (2026-11-10) matn shaffof qolib, o'rnida gradient to'rtburchak chiqdi.
    # Rang — oddiy `color`; "AI" logo rangida (`.ai`).
    ".wm{font-weight:800;letter-spacing:.16em;color:#fff}"
    ".ai{color:#9fb0ff}"
    ".vk{font-size:.62em;font-weight:800;letter-spacing:.22em;color:#dfe3ff;margin-bottom:3px}"
    ".st{font-size:.82em;color:#aab3d9;margin-top:2px}"
    ".pr{display:inline-block;margin-left:7px;padding:1px 8px;border-radius:9px;font-size:.72em;"
    "letter-spacing:.06em;color:#fff;background:linear-gradient(90deg,#3f6bff,#b25cff);vertical-align:2px}"
    ".wm{white-space:nowrap}"
    # Telefonda xabar pufagi kompyuterdagidan tor (~290 px): sarlavha bir
    # qatorda qolsin, «PRO» belgisi pastga tushmasin. `.hd .wm` — shablonning
    # o'z `.wm{font-size}` qoidasidan kuchliroq (u _BREND_CSS dan keyin keladi).
    "@media (max-width:340px){.hd{padding:12px;gap:10px}.hd .lg{width:46px;height:46px}"
    ".hd .wm{font-size:.98em;letter-spacing:.05em}.pr{margin-left:5px;padding:1px 6px}}")
_JS_ASOS = ("var W=window.TelegramWidget;"
            "function p(s){try{return JSON.parse(s)}catch(e){return null}}"
            "function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;"
            "if(x!=null)e.textContent=x;return e}"
            "function z(n){return(n<10?'0':'')+n}")


# Kichik logo + nom — brend sarlavhasi yo'q kartalar (ob-havo, valyuta,
# namoz, eslatma, test, kartochka) pastida. Gradient id'lari `_LOGO` nikidan
# boshqa (`va`/`vb`), zaxira rang bilan — gradient chiqmasa ham logo ko'rinsin.
_MINI_LOGO = (
    '<svg width="18" height="16" viewBox="4 14 92 78"><defs>'
    '<linearGradient id="va" x1="0" y1="0" x2=".7" y2="1"><stop offset="0" stop-color="#6a9bff"/>'
    '<stop offset=".55" stop-color="#3442ff"/><stop offset="1" stop-color="#b07cff"/></linearGradient>'
    '<linearGradient id="vb" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d792ff"/>'
    '<stop offset=".4" stop-color="#3fdcff"/><stop offset="1" stop-color="#3d55ff"/></linearGradient></defs>'
    '<path fill="url(#va) #4a5cff" d="M6 22C22 20 34 26 42 38L60 72C64 80 61 90 52 90C46 90 43 86 41 81L19 38C15 30 11 25 6 22Z"/>'
    '<path fill="url(#vb) #3fb8ff" d="M95 18C84 19 73 25 66 35L47 65C57 68 64 62 69 54L86 29C89 24 92 20 95 18Z"/></svg>')


def _imzoli(shablon: str, rang: str = "var(--tg-theme-hint-color)") -> str:
    """Kartaning pastiga «logo VEXON AI» imzosi (`<div id="a">` dan keyin)."""
    imzo = ('<div style="display:flex;align-items:center;justify-content:center;gap:6px;'
            'margin-top:12px;font:800 .68em/1 system-ui,sans-serif;letter-spacing:.2em;color:'
            + rang + '">' + _MINI_LOGO + 'VEXON AI</div>')
    return shablon.replace('<div id="a"></div>', '<div id="a"></div>' + imzo, 1)


# Karta ichidagi tugma: "c:<callback_data>" — bot uni xabar ostidagi o'sha
# tugma kabi bajaradi (`profile.vidjet_amali`). Javob {"ok", "t": xabar}.
# ⚠️ `request` tap ichida SINXRON chaqiriladi (Telegram taymer/promise'dan
# kelganini tap deb sanamaydi). Natija — pastda toast (`tt`), bosilgan
# tugma kutish paytida ramka oladi (`.bz`; opacity emas — u "og'ir" element).
AMAL_SOROVI = "c:"
_AMAL_CSS = (
    ".ab{display:flex;gap:6px;margin-top:10px}"
    ".ab button{flex:1;min-width:0;border:0;border-radius:12px;padding:10px 6px;"
    "font:600 .86em system-ui,sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
    "color:var(--tg-theme-button-text-color);background:var(--tg-theme-button-color)}"
    ".ab .ik{color:var(--tg-theme-text-color);background:var(--tg-theme-secondary-bg-color)}"
    ".ab .xv{color:#fff;background:#e5484d}"
    ".bz{box-shadow:inset 0 0 0 2px #29d0ff!important}"
    ".tp:active,.ab button:active{transform:scale(.97)}"
    ".tt{position:fixed;left:10px;right:10px;bottom:10px;padding:10px 12px;border-radius:12px;"
    "font-size:.84em;text-align:center;color:#fff;background:#1b2150;box-shadow:0 0 0 1px #3d4aa8;"
    "transform:translateY(170%);transition:transform .3s}.tt.on{transform:none}")
_JS_AMAL = """
function tt(s){var t=document.getElementById("tt");if(!t){t=el("div","tt");t.id="tt";document.body.appendChild(t)}
t.textContent=s;t.className="tt on";clearTimeout(t.k);t.k=setTimeout(function(){t.className="tt"},3600)}
function A(c,b,ok){if(!W||!W.request){tt("Pastdagi tugmadan foydalaning");return}
try{if(W.HapticFeedback)W.HapticFeedback.selectionChanged()}catch(e){}
if(b)b.classList.add("bz");
W.request("c:"+c).then(function(o){if(b)b.classList.remove("bz");var x=p(o.result)||{};if(x.t)tt(x.t);else if(ok&&x.ok)tt(ok)},
function(e){if(b)b.classList.remove("bz");tt(e&&e.code=="BUSY"?"⏳ Bajarilmoqda…":"⚠️ Bo'lmadi — pastdagi tugmadan urinib ko'ring")})}
function bn(t,c,k,ok){var b=el("button",k||0,t);b.onclick=function(){A(c,b,ok)};return b}
"""


def _sarlavha(nom: str, izoh_id: str = "st", pro: bool = False) -> str:
    # Nomi «VEXON AI» bo'lmagan kartada brend nomi tepada kichik satr (`.vk`).
    vk = "" if "VEXON" in nom else '<div class="vk">VEXON <span class="ai">AI</span></div>'
    return ('<div class="hd">' + _LOGO + '<div>' + vk + '<div class="wm">' + nom
            + ('<span class="pr">PRO</span>' if pro else "") + '</div><div class="st" id="'
            + izoh_id + '"></div></div></div>')


# ── /start: kutib olish kartasi ───────────────────────────────────
# Ma'lumotsiz, so'rovsiz: logo, nom va o'zi almashadigan imkoniyatlar.
# Slaydlar — `_greeting_text()` dagi va'dalarning O'ZI (u izohda turadi):
# karta botda yo'q narsani va'da qilmasin (rasm chizish — Pro, shu yerda yo'q).
# Birinchi maydon — `_IKONKA` kaliti: oddiy emoji emas, logo gradientidagi
# SVG ikonka. Logo emojilarimiz (custom emoji, stiker) vidjet ichida
# CHIQMAYDI — vidjet tarmoqsiz, stikerni yuklay olmaydi.
START_SLAYDLAR = (
    ("c", "Istalgan savol", "Kerak bo'lsa internetdan qidiraman va manbasini ko'rsataman"),
    ("d", "Hujjatlar", "PDF, Word, Excel yoki TXT yuboring — o'qib, tahlil qilaman"),
    ("f", "Rasmlar", "Rasm yuboring — xuddi insondek ko'rib tushuntiraman"),
    ("m", "Ovozli xabar", "Gapirib so'rang — ovozli javob qaytaraman"),
    ("b", "Fayl yarataman", "Taqdimot, PDF, Word va Excel tayyorlab beraman"),
    ("w", "Har kungi yordam", "Ob-havo, valyuta kursi, namoz vaqtlari va eslatmalar"),
)
# Ikonkalar (24×24, chiziqli, logo gradienti). ⛔️ Gradient har ikonkaning
# O'Z <defs>'ida va `stroke` ATRIBUTIDA, zaxira rang bilan (`url(#gN) #6fa8ff`):
# CSS `stroke:url(#ig)` boshqa SVG'dagi gradientga iPhone Telegram'ida (WebKit)
# ishlamadi — jonli (2026-11-10) ikonkalar bo'm-bo'sh doira bo'lib chiqdi,
# Chrome'da esa hammasi joyida edi. Va `scale`/animatsiya logoda YO'Q: iOS
# animatsiyadagi elementni past aniqlikda rasterlaydi — logo xira chiqdi. Har biri faol
# slaydda o'z harakatini qiladi; hammasi faqat transform (`.bo` sakraydi,
# `.sx` cho'ziladi, `.ro` aylanadi, `.pu` uradi). O'zimizning satrlar —
# innerHTML'ga faqat shular tushadi, model/foydalanuvchi matni emas.
_IKONKA = {
    "c": '<path d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8l-5 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/>'
         '<g fill="#4fb8ff" stroke="none"><circle class="bo" cx="8" cy="10.5" r="1.3"/>'
         '<circle class="bo b2" cx="12" cy="10.5" r="1.3"/><circle class="bo b3" cx="16" cy="10.5" r="1.3"/></g>',
    "d": '<path d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><path d="M14 2v5h5"/>'
         '<path class="sx" d="M8 12h8"/><path class="sx b2" d="M8 15.5h8"/><path class="sx b3" d="M8 19h5"/>',
    "f": '<rect x="3" y="4" width="18" height="16" rx="3"/><circle class="pu" cx="9" cy="9.5" r="1.8"/>'
         '<path d="M21 15.5l-4.5-4.5L6 20"/>',
    "m": '<rect class="pu" x="9" y="2.5" width="6" height="11.5" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/>',
    "b": '<path class="ro" d="M12 2.5l2.1 5.6 5.9 2.1-5.9 2.1L12 18l-2.1-5.7L4 10.2l5.9-2.1z"/>'
         '<path class="pu" d="M19 15.5l.9 2.2 2.1.8-2.1.8-.9 2.2-.9-2.2-2.1-.8 2.1-.8z"/>',
    "w": '<g class="ro"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22'
         'M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></g>',
}
# «Orbita»: logo markazda, imkoniyatlar uning halqasida aylanadi — faoli
# tepaga chiqadi, matni pastda almashadi. Karusel = logo orbitasi (nuqtalar
# kerak emas, joyni orbita ko'rsatadi). Hammasi transform: halqa `.o`
# −60°·I ga buriladi, har tugun `.n` +60°·I ga — ikonka doim tik turadi.
_START_SHABLON = ("<style>" + _BREND_CSS + """
.c{border-radius:22px;padding:6px 16px 18px;color:#eef1ff;overflow:hidden;background:radial-gradient(90% 60% at 50% 34%,#1d2a8c 0,#0e1440 48%,#070b24 100%)}
.or{position:relative;width:250px;height:250px;margin:14px auto 0}
.or>svg,.o,.lc{position:absolute;left:0;top:0;width:250px;height:250px}
.hl{transform-origin:125px 125px;animation:rg 14s linear infinite}
.o{transition:transform .9s cubic-bezier(.6,-.2,.25,1.25)}
.n{position:absolute;width:46px;height:46px;margin:-23px 0 0 -23px;transition:transform .9s cubic-bezier(.6,-.2,.25,1.25)}
.i{width:46px;height:46px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#121a52;box-shadow:inset 0 0 0 1px #34409e;transition:transform .5s,box-shadow .5s,background .5s}
.n.on .i{background:#18237a;box-shadow:inset 0 0 0 2px #5b8cff,0 0 0 7px #4f7bff30}
.i svg{width:24px;height:24px;overflow:visible;transition:width .4s,height .4s}
.n.on .i svg{width:29px;height:29px}
.lc{display:flex;align-items:center;justify-content:center;pointer-events:none}
.lc .lg{width:108px;height:108px}
.lc .rg{display:none}
.wm{font-size:1.65em;letter-spacing:-.01em;text-align:center;margin-top:8px}
.ai{color:#9fb0ff}
.tg{text-align:center;color:#9aa3d6;font-size:.86em;margin:2px 0 16px}
.f{border-radius:16px;padding:14px 16px;background:#0b1035;box-shadow:inset 0 0 0 1px #222b74;min-height:62px}
.f b{display:block;font-size:1.08em;margin-bottom:4px}
.f span{color:#c3c9ee;font-size:.9em;line-height:1.4}
.f.v{animation:kr .45s ease-out}
@keyframes kr{from{transform:translateY(7px)}}
.on .bo{animation:bo 1.2s ease-in-out infinite}
@keyframes bo{30%{transform:translateY(-2px)}}
.on .sx{transform-origin:8px 0;animation:sx 1.6s ease-in-out infinite}
@keyframes sx{0%{transform:scaleX(.2)}60%,100%{transform:scaleX(1)}}
.on .ro{transform-origin:12px 12px;animation:rg 8s linear infinite}
.on .pu{transform-origin:12px 12px;animation:pu 1.4s ease-in-out infinite}
@keyframes pu{50%{transform:scale(1.12)}}
.b2{animation-delay:.15s!important}.b3{animation-delay:.3s!important}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
<div class="c"><div class="or" id="or"><svg viewBox="0 0 250 250"><defs><linearGradient id="ig" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5b8cff"/><stop offset=".5" stop-color="#29d0ff"/><stop offset="1" stop-color="#c77dff"/></linearGradient></defs>
<circle cx="125" cy="125" r="103" fill="none" stroke="#28318a" stroke-width="1.2"/>
<circle class="hl" cx="125" cy="125" r="103" fill="none" stroke="url(#ig) #4f7bff" stroke-width="2" stroke-dasharray="70 577" stroke-linecap="round"/>
<circle cx="125" cy="125" r="78" fill="none" stroke="#1f2770" stroke-width="1" stroke-dasharray="2 7"/></svg>
<div class="o" id="o"></div><div class="lc">""" + _LOGO + """</div></div>
<div class="wm">Vexon <span class="ai">AI</span></div><div class="tg">Shaxsiy AI yordamchingiz</div>
<div class="f" id="f"></div></div>
<script>""" + _JS_ASOS + """
var S=@@S@@,IK=@@I@@,o=document.getElementById("o"),f=document.getElementById("f"),N=[],I=-1,A=0,L=S.length,T;
S.forEach(function(x,i){var a=(i/S.length*360-90)*Math.PI/180,n=el("div","n"),c=el("div","i");n.style.left=125+103*Math.cos(a)+"px";n.style.top=125+103*Math.sin(a)+"px";
c.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="url(#g'+i+') #6fa8ff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><defs><linearGradient id="g'+i+'" gradientUnits="userSpaceOnUse" x1="2" y1="2" x2="22" y2="22"><stop offset="0" stop-color="#6b95ff"/><stop offset=".5" stop-color="#2fd2ff"/><stop offset="1" stop-color="#cf8bff"/></linearGradient></defs>'+(IK[x[0]]||"")+"</svg>";n.appendChild(c);n.onclick=function(e){e.stopPropagation();g(i);R()};o.appendChild(n);N.push(n)});
function g(i){i=(i+L)%L;if(i==I)return;var d=I<0?i:((i-I)%L+L)%L;if(d>L/2)d-=L;A+=d;I=i;var r=-360/L*A;o.style.transform="rotate("+r+"deg)";
N.forEach(function(n,j){n.style.transform="rotate("+(-r)+"deg)";n.className=j==I?"n on":"n"});
f.className="f";f.innerHTML="";f.appendChild(el("b",0,S[I][1]));f.appendChild(el("span",0,S[I][2]));void f.offsetWidth;f.className="f v"}
function R(){clearInterval(T);T=setInterval(function(){g(I+1)},4200)}
g(0);R();document.getElementById("or").onclick=f.onclick=function(){g(I+1);R()};
</script>""")


def start_html() -> str:
    return (_START_SHABLON.replace("@@S@@", _json([list(s) for s in START_SLAYDLAR]))
            .replace("@@I@@", _json(_IKONKA)))


# ── /pro: tariflar kartasi (va sovg'a kartasi) ────────────────────
# Holat (handlers/pro.py::pro_kartasi) — `"e"` qaysi EKRAN:
#   ""  asosiy: "h" f bepul | p Pro | m muddatsiz, "r": [[belgi, nom, bepul,
#       pro], ...] (PLAN_LIMITS dan), "k" qolgan kun, "o" obuna, "n" sana;
#   "s" / "k" Stars / karta tariflari: "t": [[nom, narx, izoh, chegirma,
#       eng foydali, kun], ...] (`pro.tarif_plitkalari` — tugmalar bilan BIR
#       manba), "ob" oylik obuna narxi (taklif qilinsa);
#   "kb" — karta sozlangan (kartada «💳» tugmasi).
# Sovg'a kartasi (`sovga_html`) — o'sha plitkalar + "gf" oluvchi nomi, "rid"
# uning id'si (tugmalar `pro:buy:<kun>:<id>`), "e": "g" — «kimga?» so'rovi.
# Ikki shablon, chunki bittasi 4 KB (siqilgan) ga sig'madi; sovg'a xabari
# asosiy ekranga hech qachon o'tmaydi, Pro xabari — sovg'a so'roviga.
# Kartadagi plitka va tugma BOSILADI: "c:<callback>" — xabar ostidagi tugmaning
# o'zi (`profile.vidjet_amali`), ya'ni pul yo'li va tekshiruvlar o'sha.
# Ekran almashganda bot `editMessageWidgetData` yuboradi → `chatDataChanged`.
# ⚠️ «Eng foydali» belgisi plitka ICHIDA, nom yonida: `position:absolute` bilan
# plitka tepasiga chiqarilgani iPhone Telegram'ida (2026-11-11) ingichka chiziq
# va ramka ortida xira matn bo'lib chiqdi; kompyuterda joyida edi.
_PLITKA_CSS = """
.wm{font-size:1.2em}
.u{color:var(--tg-theme-hint-color);font-size:.85em;margin-top:8px}
.pt{display:flex;align-items:center;gap:10px;margin-top:8px;padding:11px 14px;border-radius:14px;background:var(--tg-theme-secondary-bg-color)}
.pt.bs{box-shadow:inset 0 0 0 2px #6b72ff}
.pt.ob{color:#fff;background:linear-gradient(110deg,#2c3bc4,#7b3fd6)}
.pn{flex:1;min-width:0}.pn b{display:block}.pn span{font-size:.78em;color:var(--tg-theme-hint-color)}
.ob .pn span{color:#dfe3ff}
.pp{text-align:right;white-space:nowrap}.pp b{font-size:1.08em;font-variant-numeric:tabular-nums}
.pp i{display:block;font-style:normal;font-size:.72em;font-weight:700;color:#2fbf71}
.pt em{display:inline-block;margin-left:7px;padding:2px 8px;border-radius:8px;font-size:.66em;font-style:normal;font-weight:700;vertical-align:2px;white-space:nowrap;color:#fff;background:linear-gradient(90deg,#3f6bff,#b25cff)}
"""
_PLITKA_JS = """
var D,a=document.getElementById("a"),S=document.getElementById("st");
function pt(x,c,cb,ok){var q=el("div","pt tp"+(x[4]?" bs":"")+(c?" "+c:"")),l=el("div","pn"),r=el("div","pp"),n=el("b",0,x[0]);if(x[4])n.appendChild(el("em",0,"Eng foydali"));l.appendChild(n);l.appendChild(el("span",0,x[2]));q.appendChild(l);
if(x[3])r.appendChild(el("i",0,x[3]));r.appendChild(el("b",0,x[1]));q.appendChild(r);q.onclick=function(){A(cb,q,ok)};a.appendChild(q)}
function pl(){var g=D.gf,k=D.e=="k",Z=D.rid?":"+D.rid:"",r=el("div","ab");S.textContent=g?"🎁 Sovg'a: "+g:(k?"💳 Karta orqali · ":"⭐️ Telegram Stars · ")+(D.h=="f"?"muddatni tanlang":"uzaytirish");
if(D.ob)pt(["♻️ Har oy avtomatik",D.ob+" ⭐/oy","Pro uzilmaydi · istalgan payt o'chirasiz","",0],"ob","pro:obuna","♻️ Obuna havolasi pastda");
(D.t||[]).forEach(function(x){pt(x,0,(k?"pro:karta:":"pro:buy:")+x[5]+Z,k?"💳 Karta raqami va summa pastda":"⭐️ To'lov oynasi pastda")});
if(!g)r.appendChild(bn("⬅️ Orqaga","pro:usul","ik"));if(D.kb||k)r.appendChild(k?bn("⭐️ Stars bilan","pro:stars"+Z,"ik"):bn("💳 Karta bilan","pro:kartalar"+Z,"ik"));a.appendChild(r);
a.appendChild(el("div","u",(k?"Keyingi qadamda karta raqami va aniq summa chiqadi. ":"")+(D.h=="p"&&!g?"Yangi kunlar qolgan muddatga qo'shiladi. ":"")+"👆 Muddatni bosing"))}
"""
_PRO_SHABLON = ("<style>" + _BREND_CSS + _AMAL_CSS + _PLITKA_CSS + """
.tb{margin-top:8px}
.r{display:flex;align-items:center;padding:5px 4px;border-bottom:1px solid var(--tg-theme-secondary-bg-color)}
.r:last-child{border:0}
.n{flex:1;min-width:0}
.v{width:64px;text-align:center;font-variant-numeric:tabular-nums}
.f{color:var(--tg-theme-hint-color)}
.p{font-weight:700;color:var(--tg-theme-button-color)}
.hr{border:0;padding-bottom:2px}
.hr .v{font-size:.78em;font-weight:600}
.hr .p{color:#fff;border-radius:8px;padding:3px 0;background:linear-gradient(90deg,#3f6bff,#8a5cff)}
.rn{display:flex;align-items:center;gap:16px;margin-top:8px;padding:2px 6px}
.rn svg{width:86px;height:86px;flex:none}
.tr{stroke:var(--tg-theme-secondary-bg-color)}.ht{fill:var(--tg-theme-hint-color)}
.k{font-size:1.15em;font-weight:700}
.b{display:inline-block;margin-top:6px;padding:3px 10px;border-radius:10px;font-size:.8em;background:var(--tg-theme-secondary-bg-color)}
</style>
""" + _sarlavha('VEXON <span class="ai">AI</span>', pro=True) + """<div id="a"></div>
<script>""" + _JS_ASOS + _JS_AMAL + _PLITKA_JS + """
function tb(r,b){var t=el("div","tb"),h=el("div","r hr");h.appendChild(el("span","n",""));if(!b)h.appendChild(el("span","v f","Bepul"));h.appendChild(el("span","v p",b?"Sizda":"Pro"));t.appendChild(h);
r.forEach(function(x){var q=el("div","r");q.appendChild(el("span","n",x[0]+" "+x[1]));if(!b)q.appendChild(el("span","v f",x[2]));q.appendChild(el("span","v p",x[3]));t.appendChild(q)});a.appendChild(t)}
function ab(){var r=el("div","ab");if(D.h=="f"||(D.h=="p"&&!D.o)){r.appendChild(bn("⭐️ Stars","pro:stars"));if(D.kb)r.appendChild(bn("💳 Karta","pro:kartalar"))}
if(D.o)r.appendChild(bn("🔕 Avto to'lov","pro:obuna_bekor","ik","👇 Pastda tasdiqlang"));r.appendChild(bn("🎁 Sovg'a","pro:gift","ik","🎁 Pastda — kimga sovg'a qilishni yozing"));a.appendChild(r)}
function mn(){if(D.h=="f"){S.textContent="Ko'proq imkoniyat, kamroq cheklov";tb(D.r||[]);ab();return}
S.textContent="Pro tarifingiz faol";
var m=D.h=="m",k=D.k||0,o=m?0:251.3*(1-Math.min(k,30)/30),q=el("div","rn"),i=el("div"),c=k<=3&&!m&&!D.o?"#e5484d":"url(#rq) #5b6bff";
q.innerHTML='<svg viewBox="0 0 100 100"><defs><linearGradient id="rq"><stop offset="0" stop-color="#3f6bff"/><stop offset="1" stop-color="#b25cff"/></linearGradient></defs><circle class="tr" cx="50" cy="50" r="40" fill="none" stroke-width="9"/><circle cx="50" cy="50" r="40" fill="none" stroke="'+c+'" stroke-width="9" stroke-linecap="round" stroke-dasharray="251.3" stroke-dashoffset="'+o+'" transform="rotate(-90 50 50)"/><text x="50" y="50" text-anchor="middle" font-size="22" font-weight="700" fill="currentColor"></text><text class="ht" x="50" y="66" text-anchor="middle" font-size="10"></text></svg>';
var x=q.getElementsByTagName("text");x[0].textContent=m?"∞":k;x[1].textContent=m?"muddatsiz":"kun qoldi";
i.appendChild(el("div","k",m?"Muddatsiz tarif":"Pro faol"));
if(D.o)i.appendChild(el("div","b","♻️ Har oy o'zi uzayadi"));
if(D.n)i.appendChild(el("div","u",(D.o?"Keyingi to'lov: ":"Tugaydi: ")+D.n));
q.appendChild(i);a.appendChild(q);tb((D.r||[]).filter(function(x){return x[3]!="✓"}),1);
var h=(D.r||[]).filter(function(x){return x[3]=="✓"}).map(function(x){return x[0]+" "+x[1]});if(h.length)a.appendChild(el("div","u","Yana: "+h.join(" · ")));ab()}
function R(){D=p(W&&W.chatData)||{};a.innerHTML="";if(D.e=="s"||D.e=="k")pl();else mn()}
R();if(W&&W.onEvent)W.onEvent("chatDataChanged",R);
</script>""")
_SOVGA_SHABLON = ("<style>" + _BREND_CSS + _AMAL_CSS + _PLITKA_CSS + """
.gx{display:block;margin:12px auto 2px}
.sg{display:flex;align-items:center;gap:10px;margin-top:8px;padding:9px 12px;border-radius:12px;background:var(--tg-theme-secondary-bg-color)}
.sg i{flex:none;width:24px;height:24px;border-radius:50%;text-align:center;line-height:24px;font-style:normal;font-weight:700;font-size:.8em;color:#fff;background:linear-gradient(135deg,#3f6bff,#b25cff)}
.nt{margin:10px 2px 0;font-size:.85em}
</style>
""" + _sarlavha('VEXON <span class="ai">AI</span>', pro=True) + """<div id="a"></div>
<script>""" + _JS_ASOS + _JS_AMAL + _PLITKA_JS + """
function gf(){S.textContent="Do'stingizga Pro sovg'a qiling";var b=el("div");
b.innerHTML='<svg class="gx" width="76" height="76" viewBox="0 0 64 64"><defs><linearGradient id="gb" gradientUnits="userSpaceOnUse" x1="8" y1="20" x2="56" y2="58"><stop offset="0" stop-color="#4f7bff"/><stop offset="1" stop-color="#b25cff"/></linearGradient></defs><path d="M32 19C27 9 16 8 16 14c0 4 8 5 16 5zm0 0c5-10 16-11 16-5 0 4-8 5-16 5z" fill="none" stroke="#ffcf4a" stroke-width="3" stroke-linejoin="round"/><rect x="9" y="27" width="46" height="30" rx="5" fill="url(#gb) #6a6bff"/><rect x="6" y="19" width="52" height="10" rx="4" fill="#8fa4ff"/><rect x="28.5" y="19" width="7" height="38" fill="#ffcf4a"/></svg>';a.appendChild(b);
[["1","@username yozing"],["2","yoki ID raqamini yuboring"],["3","yoki uning xabarini forward qiling"]].forEach(function(x){var q=el("div","sg");q.appendChild(el("i",0,x[0]));q.appendChild(el("span",0,x[1]));a.appendChild(q)});
a.appendChild(el("div","nt","❗️ Oluvchi avval botga /start bergan bo'lishi kerak. Stars yoki karta bilan to'laysiz — unga sovg'a kartasi boradi."));
a.appendChild(el("div","u","✍️ Javobni shu chatga yozing"))}
function R(){D=p(W&&W.chatData)||{};a.innerHTML="";if(D.e=="s"||D.e=="k")pl();else gf()}
R();if(W&&W.onEvent)W.onEvent("chatDataChanged",R);
</script>""")


def pro_html() -> str:
    return _PRO_SHABLON


def sovga_html() -> str:
    return _SOVGA_SHABLON


def pro_holati(d: dict) -> str:
    return _json(d)


# ── /kunlik: daydjest kartasi ─────────────────────────────────────
# Holat (handlers/digest.py::kunlik_holati): {"l": 1 — bepul (panjara
# qulf), "h": [soatlar], "m": mavzular, "t"}. Sanoq Toshkent soati (UTC+5,
# yozgi vaqt yo'q) bilan: keyingisi — `keyingi_vaqt()` qoidasi (joriy soat
# "yuborilgan"). Soat tugmasi bosilsa bot yangi holatni o'zi yuboradi
# (`editMessageWidgetData` → `chatDataChanged`); mavzu yozilganda esa xabar
# noma'lum — karta "k" bilan holatni 6 soniyada bir so'raydi (ko'rinib turganda).
KUNLIK_SOROVI = "k"
_KUNLIK_SHABLON = ("<style>" + _BREND_CSS + _AMAL_CSS + """
.wm{font-size:1.05em;letter-spacing:.1em}
.dl{display:block;width:230px;height:230px;margin:6px auto 0}
.m{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin:4px 0 2px}
.m span{padding:4px 10px;border-radius:12px;font-size:.82em;background:var(--tg-theme-secondary-bg-color)}
.u{color:var(--tg-theme-hint-color);font-size:.8em;text-align:center;margin-top:6px}
.x{color:#e5484d;font-weight:600}
.hz{cursor:pointer}
</style>
""" + _sarlavha("KUNLIK DAYDJEST") + """<div id="a"></div>
<script>""" + _JS_ASOS + _JS_AMAL + """
var D,NS="http://www.w3.org/2000/svg",a=document.getElementById("a"),SV,Q=0;
function s(t,o,x){var e=document.createElementNS(NS,t);for(var k in o)e.setAttribute(k,o[k]);if(x!=null)e.textContent=x;return e}
function hz(){var t=new Date(Date.now()+18e6);return{h:t.getUTCHours(),m:t.getUTCMinutes(),s:t.getUTCSeconds()}}
function nx(){var h=D.h||[],n=hz(),b=h.filter(function(x){return x>n.h});if(!h.length)return null;var x=b.length?b[0]:h[0]+24;return{h:x%24,q:x*3600-(n.h*3600+n.m*60+n.s)}}
function r(){if(!D)return;a.innerHTML="";var e=D.l,h=D.h||[],n=hz(),T=nx();
document.getElementById("st").textContent=e?"💎 Pro imkoniyati":h.length?(D.m?"✅ Faol · har kuni "+h.length+" marta":"❗ Mavzu yozilmagan"):"🔕 O'chirilgan";
SV=s("svg",{viewBox:"0 0 200 200","class":"dl"});
SV.appendChild(s("defs")).innerHTML='<linearGradient id="kg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3f6bff"/><stop offset="1" stop-color="#b25cff"/></linearGradient>';
SV.appendChild(s("circle",{cx:100,cy:100,r:84,fill:"none",style:"stroke:var(--tg-theme-secondary-bg-color)","stroke-width":2}));
var f=(n.h+n.m/60)/24,w=(f*360-90)*Math.PI/180;SV.appendChild(s("path",{d:"M100 16A84 84 0 "+(f>.5?1:0)+" 1 "+(100+84*Math.cos(w))+" "+(100+84*Math.sin(w)),fill:"none",stroke:"url(#kg) #6b72ff","stroke-width":3,"stroke-linecap":"round"}));
for(var i=0;i<24;i++){var g=(i/24*360-90)*Math.PI/180,on=h.indexOf(i)>=0,X=100+84*Math.cos(g),Y=100+84*Math.sin(g);
SV.appendChild(s("circle",on&&!e?{cx:X,cy:Y,r:8,fill:"url(#kg) #6b72ff"}:{cx:X,cy:Y,r:on?8:2.6,style:"fill:var(--tg-theme-hint-color)"}));
if(on)SV.appendChild(s("text",{x:X,y:Y+3.2,"text-anchor":"middle","font-size":8,"font-weight":700,fill:"#fff"},z(i)));
else if(i%6==0)SV.appendChild(s("text",{x:100+68*Math.cos(g),y:100+68*Math.sin(g)+3,"text-anchor":"middle","font-size":9,style:"fill:var(--tg-theme-hint-color)"},z(i)));
var H=s("circle",{cx:X,cy:Y,r:11,fill:"#000","fill-opacity":0,"class":"hz"});H.onclick=tp(i);SV.appendChild(H)}
SV.appendChild(s("circle",{cx:100+84*Math.cos(w),cy:100+84*Math.sin(w),r:4.5,fill:"#fff",stroke:"url(#kg) #6b72ff","stroke-width":2.5}));
var ok=!e&&T&&D.m;SV.appendChild(s("text",{x:100,y:88,"text-anchor":"middle","font-size":10,style:"fill:var(--tg-theme-hint-color)"},e?"Pro tarif":ok?"Keyingisi":T?"Mavzu kerak":"Soat tanlang"));
SV.appendChild(s("text",{x:100,y:114,"text-anchor":"middle","font-size":24,"font-weight":700,fill:"currentColor"},ok?z(T.h)+":00":"—"));
SV.appendChild(s("text",{id:"cd",x:100,y:132,"text-anchor":"middle","font-size":10,style:"fill:var(--tg-theme-hint-color)"}));
a.appendChild(SV);var m=el("div","m");(D.m||"").split(/[,;\\n]+/).forEach(function(x){x=x.trim();if(x&&m.childNodes.length<8)m.appendChild(el("span",0,x.length>28?x.slice(0,27)+"…":x))});
if(D.m)a.appendChild(m);else if(h.length&&!e)a.appendChild(el("div","u x","Mavzu yozilmaguncha daydjest kelmaydi"));
var B=el("div","ab");if(e)B.appendChild(bn("💎 Pro'ga o'tish","pro:open",0,"💎 Pro kartasi pastda"));
else{B.appendChild(bn("✏️ Mavzular","dg:topics","ik","✏️ Pastda mavzularni yozing"));if(h.length)B.appendChild(bn("🔕 O'chirish","dg:off","ik"))}a.appendChild(B);
a.appendChild(el("div","u",e?"Har kuni tanlagan soatingizda tayyor xulosa":"👆 Soatni siferblatda bosing · Toshkent vaqti"));c()}
function tp(i){return function(){if(D.l){A("pro:open",0,"💎 Pro kartasi pastda");return}Q=Date.now()+4e3;A("dg:h:"+i)}}
function c(){var T=nx(),k=document.getElementById("cd");if(!k||!T||D.l||!D.m)return;var q=T.q;k.textContent=Math.floor(q/3600)+":"+z(Math.floor(q/60)%60)+":"+z(q%60)+" qoldi";if(q<=0)r()}
function y(){if(!W||!W.request||Date.now()-Q<5500)return;Q=Date.now();W.request("k").then(function(o){var x=p(o.result);if(x&&x.h){D=x;r()}},function(){})}
D=p(W&&W.chatData);r();y();document.addEventListener("visibilitychange",function(){if(!document.hidden)y()});
if(W&&W.onEvent)W.onEvent("chatDataChanged",function(){var x=p(W.chatData);if(x&&x.h){D=x;r()}});
setInterval(function(){c();y()},1000);var L=-1;setInterval(function(){var n=hz();if(n.m!=L){L=n.m;r()}},5000);
</script>""")


def kunlik_html() -> str:
    return _KUNLIK_SHABLON


def kunlik_holati(d: dict) -> str:
    return _json(d)


# ── /research: jarayon kartasi ────────────────────────────────────
# Holat (handlers/messages.py::_tadqiqot_ochiq): {"id", "m": mavzu, "b":
# bosqich q qidiruv / p PDF / x xulosa / t tayyor / e to'xtadi, "q": oxirgi
# qidiruvlar, "s": manba (noyob havola) soni, "t0": boshlanish, "d": tugash,
# "f": fayl soni}. Karta "r:<id>" bilan 5 s da bir so'raydi (Telegram'ning
# fon so'rovi chegarasi), tugagach to'xtaydi. Bot qayta ishga tushsa RAM
# bo'sh — javob {x:1}, karta "uzildi" deydi (javob o'zi «Qayta so'rash» oladi).
TADQIQOT_SOROVI = "r:"
_TADQIQOT_SHABLON = ("<style>" + _BREND_CSS + """
.wm{font-size:1.05em;letter-spacing:.1em}
.m{font-weight:600;margin:12px 4px 10px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.sp{display:flex;gap:4px;margin:0 2px}
.sp div{flex:1;text-align:center;font-size:.72em;color:var(--tg-theme-hint-color)}
.sp i{display:block;height:5px;border-radius:3px;margin-bottom:6px;background:var(--tg-theme-secondary-bg-color);font-style:normal}
.sp .ok i{background:linear-gradient(90deg,#3f6bff,#8a5cff)}
.sp .on i{background:linear-gradient(90deg,#3f6bff,#29d0ff);animation:pl 1s ease-in-out infinite alternate;transform-origin:left}
@keyframes pl{from{transform:scaleX(.35)}to{transform:scaleX(1)}}
.sp .ok,.sp .on{color:inherit;font-weight:600}
.k{display:flex;justify-content:space-between;margin:12px 4px 6px;font-size:.88em}
.q{font-size:.84em;color:var(--tg-theme-hint-color);margin:3px 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.z{font-weight:700;text-align:center;margin-top:10px}
</style>
""" + _sarlavha("CHUQUR TADQIQOT") + """<div id="a"></div>
<script>""" + _JS_ASOS + """
var D,Q=0,a=document.getElementById("a"),B=[["Qidiruv"],["Manbalar"],["PDF"],["Xulosa"]];
function ix(){return D.b=="t"?4:D.b=="x"?3:D.b=="p"?2:(D.q&&D.q.length?1:0)}
function v(){var e=(D.d||Date.now()/1e3)-D.t0;e=Math.max(0,Math.round(e));return Math.floor(e/60)+":"+z(e%60)}
function r(){a.innerHTML="";var i=ix(),u=D.b=="t"||D.b=="e";
document.getElementById("st").textContent=D.b=="t"?"✅ Tayyor":D.b=="e"?"⚠️ "+(D.x?"Jarayon uzildi":"To'xtadi"):"Ishlayapman…";
document.querySelector(".rg").style.animationDuration=u?"10s":"1.6s";
a.appendChild(el("div","m",D.m));var s=el("div","sp");
B.forEach(function(x,j){var c=el("div",j<i?"ok":j==i&&!u?"on":"");c.appendChild(el("i"));c.appendChild(document.createTextNode((j<i?"✓ ":"")+x[0]));s.appendChild(c)});a.appendChild(s);
var k=el("div","k");k.appendChild(el("span",0,"🔎 "+(D.q||[]).length+" qidiruv · 🔗 "+(D.s||0)+" manba"));k.appendChild(el("span",0,"⏱ "+v()));a.appendChild(k);
(D.q||[]).slice(-4).forEach(function(x){a.appendChild(el("div","q","✓ «"+x+"»"))});
if(D.b=="t")a.appendChild(el("div","z",D.f?"📄 PDF hisobot va xulosa pastda":"Xulosa pastda"))}
function y(){if(!W||!W.request||!D||D.b=="t"||D.b=="e"||Date.now()-Q<5e3)return;Q=Date.now();
W.request("r:"+D.id).then(function(o){var x=p(o.result);if(!x)return;if(x.x){D.b="e";D.x=1;D.d=Date.now()/1e3}else D=x;r();try{localStorage.setItem("d",JSON.stringify(D))}catch(e){}},function(){})}
var C=p(W&&W.chatData),L;try{L=p(localStorage.getItem("d"))}catch(e){}D=L&&C&&L.id==C.id?L:C;
if(D){r();y();document.addEventListener("visibilitychange",function(){if(!document.hidden)y()});setInterval(function(){if(D.b!="t"&&D.b!="e")r();y()},1000)}
</script>""")


def tadqiqot_html() -> str:
    return _TADQIQOT_SHABLON


def tadqiqot_holati(d: dict) -> str:
    """Kartaga faqat ochiq kalitlar: `_u` (havolalar to'plami) — ichki."""
    return _json({k: v for k, v in d.items() if not k.startswith("_")})


# ── Karta orqali to'lov kartasi ───────────────────────────────────
# Holat (handlers/pro.py::tolov_kartasi): {"id", "t": tarif nomi, "n": karta
# raqami, "nf": guruhlangan, "o": egasi, "s": summa, "sf": guruhlangan,
# "w": oxiridagi tanish so'mlar, "x": so'rov yopiladigan vaqt (epoch), "h":
# holat k kutmoqda | t tekshirilmoqda | r rad | a tasdiqlandi | b bekor |
# e eskirdi, "z": rad sababi, "g": Pro tugash sanasi}.
# Holat bazada o'zgaradi (chek, superadmin qarori, watcher) — karta "t:<id>"
# bilan 15 s da bir so'raydi (k/t/r da — rad etilgach chek qayta yuboriladi;
# ko'rinib turganda); bekor
# qilinganda bot `editMessageWidgetData` bilan o'zi yuboradi. Nusxa —
# `TelegramWidget.copyText` (tap ichida). ⛔️ Pul tugmalari xabar ostida, karta
# faqat ko'rsatadi; egasi ismi — textContent.
TOLOV_SOROVI = "t:"
_TOLOV_SHABLON = ("<style>" + _BREND_CSS + _AMAL_CSS + """
.wm{font-size:1.05em;letter-spacing:.1em}
.bc{margin-top:10px;padding:14px 16px 12px;border-radius:18px;color:#fff;background:linear-gradient(135deg,#2335a8,#5b2fc0 58%,#141a5c)}
.bt{display:flex;justify-content:space-between;align-items:center;font-size:.66em;font-weight:800;letter-spacing:.2em;color:#dfe3ff}
.bn{font-size:1.32em;font-weight:600;letter-spacing:.08em;margin:18px 0 12px;font-variant-numeric:tabular-nums;white-space:nowrap}
@media (max-width:340px){.bn{font-size:1.12em;letter-spacing:.03em}.bc{padding:12px 13px 11px}.sm b{font-size:1.25em}.sm{padding:11px 12px}}
.bo{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:.82em;color:#dfe3ff}
.bo span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cp{flex:none;border:0;border-radius:10px;padding:6px 11px;font:600 .82em system-ui,sans-serif;color:#fff;background:#ffffff33}
.cp.l{color:var(--tg-theme-button-text-color);background:var(--tg-theme-button-color)}
.sm{display:flex;align-items:center;gap:10px;margin-top:10px;padding:12px 14px;border-radius:16px;background:var(--tg-theme-secondary-bg-color)}
.sm div{flex:1;min-width:0}
.sm small{display:block;font-size:.76em;color:var(--tg-theme-hint-color)}
.sm b{font-size:1.45em;font-variant-numeric:tabular-nums;white-space:nowrap}
.sm i{font-style:normal;color:#7d8bff}
.w{font-size:.76em;color:var(--tg-theme-hint-color);margin:6px 4px 0}
.sp{display:flex;gap:4px;margin:14px 2px 0}
.sp div{flex:1;text-align:center;font-size:.72em;color:var(--tg-theme-hint-color)}
.sp u{display:block;height:5px;border-radius:3px;margin-bottom:6px;background:var(--tg-theme-secondary-bg-color)}
.sp .ok u{background:linear-gradient(90deg,#3f6bff,#8a5cff)}
.sp .on u{background:linear-gradient(90deg,#3f6bff,#29d0ff);transform-origin:left;animation:pl 1s ease-in-out infinite alternate}
.sp .er u{background:#e5484d}
@keyframes pl{from{transform:scaleX(.35)}to{transform:scaleX(1)}}
.sp .ok,.sp .on,.sp .er{color:inherit;font-weight:600}
.zt{margin:12px 4px 0;font-size:.9em;font-weight:600;text-align:center}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
""" + _sarlavha("KARTA TO'LOVI") + """<div id="a"></div>
<script>""" + _JS_ASOS + _JS_AMAL + """
var D,Q=0,Z,a=document.getElementById("a");
function cp(x,b){try{W.copyText(String(x));b.textContent="✓ Nusxalandi";if(W.HapticFeedback)W.HapticFeedback.notificationOccurred("success")}catch(e){}}
function bt(x,c){var b=el("button","cp"+(c?" "+c:""),"📋 Nusxa");b.onclick=function(){cp(x,b)};return b}
function ql(){var k=D.h,s=Math.round(D.x-Date.now()/1e3);if(k=="k"&&s<=0)k="e";
if(k=="k")return"⏱ "+Math.floor(s/3600)+":"+z(Math.floor(s/60)%60)+":"+z(s%60)+" ichida to'lang va chekni yuboring";
return{t:"⏳ Chek tekshirilmoqda — odatda bir necha soat, eng ko'pi 24 soat",a:D.gf?"🎁 Sovg'a yetkazildi"+(D.g?" · "+D.g+" gacha":""):"🎉 Pro faollashdi"+(D.g?" · "+D.g+" gacha":""),r:"❌ Tasdiqlanmadi: "+(D.z||"")+". To'g'ri chekni yuboring",b:"✖️ To'lov so'rovi bekor qilindi",e:"⌛️ Vaqt tugadi. To'lagan bo'lsangiz — adminga chek bilan yozing"}[k]||""}
function r(){a.innerHTML="";var h=D.h,f=h=="k"||h=="r",c=el("div","bc"),t=el("div","bt"),o=el("div","bo");
document.getElementById("st").textContent=(D.gf?"🎁 "+D.gf+" · ":"")+"Pro "+D.t+" · #"+D.id;
t.appendChild(el("span",0,"BANK KARTASI"));t.appendChild(el("span",0,"VEXON AI"));c.appendChild(t);c.appendChild(el("div","bn",D.nf));
o.appendChild(el("span",0,D.o||""));if(f)o.appendChild(bt(D.n));c.appendChild(o);a.appendChild(c);
var m=el("div","sm"),d=el("div"),b=el("b");d.appendChild(el("small",0,"Aynan shu summani o'tkazing"));
b.appendChild(document.createTextNode(D.sf.slice(0,-3)));b.appendChild(el("i",0,D.sf.slice(-3)));b.appendChild(document.createTextNode(" so'm"));d.appendChild(b);m.appendChild(d);if(f)m.appendChild(bt(D.s,"l"));a.appendChild(m);
if(D.w)a.appendChild(el("div","w","Oxiridagi "+D.w+" so'm — to'lovingizni tanib olishimiz uchun"));
var i={k:0,r:1,t:2,a:4}[h],p=el("div","sp");if(i==null)i=-1;
["O'tkazing","Chek yuboring","Tekshiruv","Pro ✓"].forEach(function(x,j){var q=el("div",j<i?"ok":j==i?(h=="r"?"er":"on"):"");q.appendChild(el("u"));q.appendChild(document.createTextNode(x));p.appendChild(q)});
a.appendChild(p);Z=el("div","zt",ql());a.appendChild(Z);
var r=el("div","ab"),E=h=="k"&&D.x<=Date.now()/1e3;
if((h=="k"&&!E)||h=="r")r.appendChild(bn("📎 Chek yuborish","pro:chek:"+D.id,0,"📎 Endi chek rasmini shu chatga yuboring"));
if(h=="k"&&!E)r.appendChild(bn("✖️ Bekor qilish","pro:kb:"+D.id,"ik"));
if(h=="b"||h=="e"||E)r.appendChild(bn(D.gf?"🎁 Qaytadan":"💳 Yangi to'lov","pro:qayta:"+D.id));
if(h=="a")r.appendChild(bn(D.gf?"🎁 Yana sovg'a":"👤 Profilim",D.gf?"pro:gift":"pro:profile"));
if(r.childNodes.length)a.appendChild(r)}
function y(){if(!W||!W.request||!D||"ktr".indexOf(D.h)<0||Date.now()-Q<15e3)return;Q=Date.now();
W.request("t:"+D.id).then(function(o){var x=p(o.result);if(x&&x.h&&x.h!="x"){var u=x.h!=D.h;D.h=x.h;D.z=x.z;D.g=x.g;if(u)r()}},function(){})}
function R(){var x=p(W&&W.chatData);if(x&&x.id){D=x;r();y()}}
R();if(W&&W.onEvent)W.onEvent("chatDataChanged",R);
document.addEventListener("visibilitychange",function(){if(!document.hidden)y()});
setInterval(function(){if(D){if(D.h=="k"&&D.x<=Date.now()/1e3&&!D.E){D.E=1;r()}else if(Z)Z.textContent=ql();y()}},1000);
</script>""")


def tolov_html() -> str:
    return _TOLOV_SHABLON


def tolov_holati(d: dict) -> str:
    return _json(d)


# ── Bayram kartasi: Pro yoqildi / sovg'a ──────────────────────────
# Holat (handlers/pro.py::tabrik_kartasi): {"a": sarlavha, "b": izoh satri,
# "l": [[belgi, imkoniyat], ...] — PLAN_LIMITS dan, "u": pastki satr,
# "k": [[yozuv, callback, toast], ...] — kartadagi tugmalar (`vidjet_amali`)}.
# Matnlar Python'da yig'iladi (testda tekshiriladi), karta faqat chizadi;
# hammasi textContent. Konfetti — faqat transform, 3 marta, faqat BIRINCHI
# ochilishda (xabarning localStorage'i), qayta ko'rilganda yo'q;
# logoda animatsiya yo'q (iOS animatsiyadagi elementni xira chizadi).
_TABRIK_SHABLON = ("<style>" + _BREND_CSS + _AMAL_CSS + """
.cb{position:relative;overflow:hidden;padding:18px 16px 20px;border-radius:22px;text-align:center;color:#eef1ff;background:radial-gradient(90% 70% at 50% 30%,#2a3aa8 0,#101650 52%,#070b24 100%)}
.cb .lg{width:96px;height:96px}
.cb .rg{display:none}
.wm{font-size:1.05em;letter-spacing:.16em;margin-top:4px}
.h1{font-size:1.5em;font-weight:800;margin-top:12px}
.sb{color:#c3c9ee;font-size:.92em;margin-top:4px;overflow-wrap:anywhere}
#cf i{position:absolute;top:-14px;width:7px;height:12px;border-radius:2px;animation:cf 2.6s ease-in 3 both}
@keyframes cf{from{transform:translateY(0) rotate(0)}to{transform:translateY(340px) rotate(560deg)}}
.pk{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.pk div{width:calc(50% - 3px);box-sizing:border-box;padding:9px 10px;border-radius:12px;font-size:.84em;background:var(--tg-theme-secondary-bg-color)}
.u{color:var(--tg-theme-hint-color);font-size:.84em;text-align:center;margin-top:12px}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
<div class="cb"><div id="cf"></div>""" + _LOGO + """<div class="wm">VEXON <span class="ai">AI</span><span class="pr">PRO</span></div><div class="h1" id="h"></div><div class="sb" id="s"></div></div><div class="pk" id="k"></div><div class="ab" id="b"></div><div class="u" id="u"></div>
<script>""" + _JS_ASOS + _JS_AMAL + """
var D=p(W&&W.chatData)||{},C=["#ffcf4a","#5b8cff","#29d0ff","#c77dff","#ff6fa8","#7dffb2"],f=document.getElementById("cf"),Y=1;
document.getElementById("h").textContent=D.a||"";document.getElementById("s").textContent=D.b||"";document.getElementById("u").textContent=D.u||"";
(D.l||[]).forEach(function(x){document.getElementById("k").appendChild(el("div",0,x[0]+" "+x[1]))});
(D.k||[]).forEach(function(x,j){document.getElementById("b").appendChild(bn(x[0],x[1],j?"ik":0,x[2]))});
try{Y=!localStorage.getItem("c");localStorage.setItem("c","1")}catch(e){}
if(Y)for(var i=0;i<14;i++){var c=el("i");c.style.left=(4+i*6.8)+"%";c.style.background=C[i%6];c.style.animationDelay=(i%5)*.35+(i%3)*.2+"s";f.appendChild(c)}
</script>""")


def tabrik_html() -> str:
    return _TABRIK_SHABLON


def tabrik_holati(d: dict) -> str:
    return _json(d)


# ── /profile: shaxsiy kabinet kartasi ─────────────────────────────
# Holat (handlers/profile.py::profil_holati): "b"/"f"/"r"/"t" — [ishlatilgan,
# chegara] (chegara null — cheksiz, kalit yo'q — tarifda yo'q), "p": f bepul
# | p Pro | m muddatsiz, "e"/"k": tugash sanasi va qolgan kun, "i": ID,
# "u": username, "n": ism, "m": xabarlar, "o": a'zo bo'lgan sana, "g": model,
# "x": [matn, rasm, ovoz, hujjat] narxi (config'dagi MESSAGE_COST_*).
# Karta ko'ringanda va har 15 s da "y" so'raydi — ball yechiladigan joyga
# "kartani yangila" chaqiruvi kerak emas. Javobda ism yo'q (bazada yo'q),
# shuning uchun eski ism saqlanadi. Ism/username — faqat textContent.
KARTA_SOROVI = "y"
_KARTA_SHABLON = ("<style>" + _BREND_CSS + _AMAL_CSS + """
.hi{flex:1;min-width:0}
.nm{font-weight:700;font-size:1.2em;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pl{flex:none;align-self:flex-start;padding:3px 10px;border-radius:10px;font-size:.74em;font-weight:800;letter-spacing:.06em;color:#c9d0ff;box-shadow:inset 0 0 0 1px #4a55b0}
.pl.pp{color:#fff;box-shadow:none;background:linear-gradient(90deg,#3f6bff,#b25cff)}
.pd{margin:10px 4px 0;font-size:.86em;color:var(--tg-theme-hint-color)}
.cr{display:flex;align-items:center;gap:14px;margin:10px 2px 0}
.cr svg{width:96px;height:96px;flex:none}
.tr{stroke:var(--tg-theme-secondary-bg-color)}.ht{fill:var(--tg-theme-hint-color)}
.ar{animation:ar 1.2s ease-out}
@keyframes ar{from{stroke-dashoffset:263.9}}
.cl{font-weight:700}
.u{color:var(--tg-theme-hint-color);font-size:.8em;margin-top:3px}
.ch{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}
.ch span{padding:3px 8px;border-radius:9px;font-size:.78em;background:var(--tg-theme-secondary-bg-color)}
.bk{margin:9px 4px 0}
.bw{display:flex;justify-content:space-between;font-size:.9em}
.bw b{font-variant-numeric:tabular-nums}
.bt{height:6px;border-radius:3px;margin-top:5px;overflow:hidden;background:var(--tg-theme-secondary-bg-color)}
.bt i{display:block;height:100%;border-radius:3px;background:linear-gradient(90deg,#3f6bff,#29d0ff)}
.bt .z{background:#e5484d}
.gr{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.gr div{flex:1 1 28%;min-width:0;padding:9px 6px;border-radius:12px;text-align:center;background:var(--tg-theme-secondary-bg-color)}
.gr b{display:block;font-size:.94em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gr span{font-size:.72em;color:var(--tg-theme-hint-color)}
.pl{cursor:pointer}
@media (max-width:340px){.gr div{padding:8px 4px}.gr b{font-size:.82em;white-space:normal}.cr{gap:10px}.cr svg{width:86px;height:86px}}
</style>
<div class="hd">""" + _LOGO + """<div class="hi"><div class="vk">VEXON <span class="ai">AI</span></div><div class="nm" id="nm"></div><div class="st" id="st"></div></div><div class="pl" id="pl"></div></div><div id="a"></div>
<script>""" + _JS_ASOS + _JS_AMAL + """
var D,F=1,a=document.getElementById("a"),K=["✉️","🖼","🎤","📄"];
function $(i){return document.getElementById(i)}
function r(x){if(!x||!x.b)return;if(D&&D.n&&!x.n)x.n=D.n;D=x;
$("nm").textContent=x.n||(x.u?"@"+x.u:"Foydalanuvchi");$("st").textContent=(x.u?"@"+x.u+" · ":"")+"ID "+x.i;
var P=$("pl");P.className=x.p=="f"?"pl":"pl pp";P.textContent=x.p=="f"?"FREE":x.p=="m"?"PRO ∞":"PRO";P.onclick=function(){A("pro:open",P,"💎 Pro kartasi pastda")};a.innerHTML="";
if(x.p=="p")a.appendChild(el("div","pd","💎 Pro tarif · "+x.e+" gacha · "+x.k+" kun qoldi"));else if(x.p=="m")a.appendChild(el("div","pd","💎 Muddatsiz tarif"));
var b=x.b,L=b[1],q=L==null?0:Math.max(0,L-b[0]),C=263.9,o=L==null||L<=0?0:C*(1-q/L),c=el("div","cr"),i=el("div");
c.innerHTML='<svg viewBox="0 0 100 100"><defs><linearGradient id="pq" gradientUnits="userSpaceOnUse" x1="8" y1="8" x2="92" y2="92"><stop offset="0" stop-color="#4f7bff"/><stop offset=".5" stop-color="#29d0ff"/><stop offset="1" stop-color="#b77dff"/></linearGradient></defs><circle class="tr" cx="50" cy="50" r="42" fill="none" stroke-width="8"/><circle'+(F?' class="ar"':'')+' cx="50" cy="50" r="42" fill="none" stroke="'+(L!=null&&q<=L*.1?'#e5484d':'url(#pq) #4f7bff')+'" stroke-width="8" stroke-linecap="round" stroke-dasharray="263.9" stroke-dashoffset="'+o+'" transform="rotate(-90 50 50)"/><text x="50" y="54" text-anchor="middle" font-size="21" font-weight="700" fill="currentColor"></text><text class="ht" x="50" y="68" text-anchor="middle" font-size="9.5"></text></svg>';
var t=c.getElementsByTagName("text");t[0].textContent=L==null?"∞":q;t[1].textContent=L==null?"cheksiz":"ball qoldi";
i.appendChild(el("div","cl","🔋 Bugungi AI Creditlar"));i.appendChild(el("div","u",L==null?"Kunlik limit qo'llanilmaydi":b[0]+" / "+L+" ishlatildi"));
if(L!=null){if(q>0){var h=el("div","ch");K.forEach(function(k,j){var n=Math.floor(q/(x.x||[])[j]);if(n>0)h.appendChild(el("span",0,k+" "+n+" ta"))});
if(h.childNodes.length){i.appendChild(el("div","u","00:00 gacha yana:"));i.appendChild(h)}else i.appendChild(el("div","u","⚠️ Birorta amal uchun yetmaydi"))}else i.appendChild(el("div","u","⏳ Limit tugadi — 00:00 da yangilanadi"))}
c.appendChild(i);a.appendChild(c);
[["f","📄 Fayl yaratish"],["r","🖼 Rasm chizish"],["t","🔎 Chuqur tadqiqot"]].forEach(function(l){var v=x[l[0]];if(!v)return;
var k=el("div","bk"),w=el("div","bw");w.appendChild(el("span",0,l[1]));w.appendChild(el("b",0,v[1]==null?"cheksiz":v[0]+" / "+v[1]));k.appendChild(w);
if(v[1]!=null){var s=el("div","bt"),f=el("i",v[0]>=v[1]?"z":0);f.style.width=(v[1]>0?Math.min(100,v[0]/v[1]*100):100)+"%";s.appendChild(f);k.appendChild(s)}a.appendChild(k)});
var g=el("div","gr");[[x.m,"Xabarlar"],[x.o,"A'zo bo'lgan"],[x.g,"Model"]].forEach(function(s){var d=el("div");d.appendChild(el("b",0,s[0]));d.appendChild(el("span",0,s[1]));g.appendChild(d)});
a.appendChild(g);var B=el("div","ab");if(x.p!="m")B.appendChild(bn(x.p=="f"?"💎 Pro'ga o'tish":"➕ Uzaytirish","pro:open",0,"💎 Pro kartasi pastda"));
B.appendChild(bn("🎁 Sovg'a qilish","pro:gift","ik","🎁 Pastda — kimga sovg'a qilishni yozing"));a.appendChild(B);F=0}
r(p(W&&W.chatData));
function y(){if(W&&W.request)W.request("y").then(function(o){r(p(o.result))},function(){})}
y();document.addEventListener("visibilitychange",function(){if(!document.hidden)y()});setInterval(y,15000);
</script>""")


def karta_html() -> str:
    return _KARTA_SHABLON


def karta_holati(raqamlar: dict) -> str:
    """`chat_data` va so'rov javobi — bitta format (1024 baytdan ancha kichik)."""
    return _json(raqamlar)


def turi(tur: str):
    """(html, holat, izoh, zaxira matn) — asbob navbatga qo'ygan vidjet turi
    bo'yicha. Yangi kartani qo'shish — shu yerga bitta qator."""
    from services import namoz, obhavo
    return {
        "obhavo": (obhavo_html, obhavo_holati, obhavo_izohi, obhavo.matn),
        "valyuta": (valyuta_html, valyuta_holati, valyuta_izohi, valyuta_matni),
        "namoz": (namoz_html, namoz_holati, namoz_izohi, namoz_matni),
        "eslatma": (eslatma_html, eslatma_holati, eslatma_izohi, _eslatma_zaxirasi),
    }.get(tur)
