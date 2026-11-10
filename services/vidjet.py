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
    html = _TEST_SHABLON.replace("@@Q@@", _json(savollar))
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
    html = _KARTOCHKA_SHABLON.replace("@@K@@", _json(k))
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


# ── Jonli limit kartasi (/profile) ────────────────────────────────
# Holat `chat_data` da, birinchi chizish shundan. Keyin vidjet o'zi
# ekranga chiqqanda va har 15 soniyada botdan "y" so'raydi
# (`widget_query`, faqat shaxsiy chatda, faqat KO'RINIB turganda) va bot
# yangi raqamlarni javobda qaytaradi. Shuning uchun ball yechiladigan
# hech bir joyga "kartani yangila" chaqiruvi kerak emas.
# Kalitlar: b — ball, f — fayl, r — rasm, t — tadqiqot; [ishlatilgan,
# chegara], chegara null — cheksiz, kalit yo'q — tarifda yo'q.
_KARTA_SHABLON = """<style>
body{margin:0;padding:8px 12px 14px}
.k{margin:0 0 12px}
.w{display:flex;justify-content:space-between;gap:8px}
.l{font-weight:600}
.t{height:8px;border-radius:4px;background:var(--tg-theme-secondary-bg-color);overflow:hidden;margin:6px 0 3px}
.f{height:100%;border-radius:4px;background:var(--tg-theme-button-color);transition:width .4s}
.z{background:#d9534f}
.u{color:var(--tg-theme-hint-color);font-size:.82em}
</style>
<div id="a"></div>
<script>
var W=window.TelegramWidget,L=[["b","🔋 AI Creditlar","ball"],["f","📄 Fayllar","ta"],["r","🖼 Rasm chizish","ta"],["t","🔎 Chuqur tadqiqot","ta"]];
function d(s){try{return JSON.parse(s)}catch(e){return null}}
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function r(x){
if(!x)return;var a=document.getElementById("a");a.innerHTML="";
L.forEach(function(l){
var v=x[l[0]];if(!v)return;
var k=el("div","k"),w=el("div","w"),c=v[1]==null;
w.appendChild(el("span","l",l[1]));
w.appendChild(el("span",0,c?"cheksiz":Math.max(0,v[1]-v[0])+" "+l[2]+" qoldi"));
k.appendChild(w);
if(!c){var t=el("div","t"),f=el("div","f"+(v[0]>=v[1]?" z":""));
f.style.width=(v[1]>0?Math.min(100,v[0]/v[1]*100):100)+"%";
t.appendChild(f);k.appendChild(t);k.appendChild(el("div","u",v[0]+" / "+v[1]+" ishlatildi"))}
a.appendChild(k)});
a.appendChild(el("div","u","🕛 Har kuni 00:00 da yangilanadi"))}
r(d(W&&W.chatData));
function y(){if(W&&W.request)W.request("y").then(function(o){r(d(o.result))},function(){})}
y();
document.addEventListener("visibilitychange",function(){if(!document.hidden)y()});
setInterval(y,15000);
</script>"""

KARTA_SOROVI = "y"


def karta_html() -> str:
    return _KARTA_SHABLON


def karta_holati(raqamlar: dict) -> str:
    """`chat_data` va so'rov javobi — bitta format (1024 baytdan ancha kichik)."""
    return _json(raqamlar)


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
    return _OBHAVO_SHABLON


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
    return _VALYUTA_SHABLON


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
.j{font-weight:600}.n{font-size:.8em;opacity:.85}
.k{margin-top:10px;font-size:.85em;opacity:.9}
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
    return _NAMOZ_SHABLON


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
.h{font-size:.85em;opacity:.85}
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
    return _ESLATMA_SHABLON


def eslatma_holati(d: dict) -> str:
    return _json(d)


def eslatma_izohi(d: dict) -> str:
    return f"⏰ Eslatma: {d['m']}"[:CAPTION_MAX]


def _eslatma_zaxirasi(d: dict) -> str:
    # Karta rad etilsa matn kerak emas: model javobi vaqtni allaqachon aytgan.
    return ""


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
