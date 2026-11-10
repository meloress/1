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
aylanadi: `test_matnga()`.
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
_TEST_RE = re.compile(r"\[\s*test\s*\]\s*\n?(.*?)(?:\[\s*/\s*test\s*\]|\Z)", re.S | re.I)
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


def test_ajrat(matn: str) -> tuple:
    """(bloklarsiz matn, [savollar ro'yxati, …]). Bitta ham to'g'ri savoli
    yo'q blok AJRATILMAYDI — u `test_matnga()` orqali matn bo'lib qoladi."""
    testlar = []

    def bir(m):
        s = test_oqi(m.group(1))
        if not s:
            return m.group(0)
        testlar.append(s)
        return ""

    qolgan = _TEST_RE.sub(bir, matn or "")
    return re.sub(r"\n{3,}", "\n\n", qolgan).strip(), testlar


def test_matni(savollar: list) -> str:
    qismlar, javoblar = ["📝 **Test**"], []
    for n, (s, v, t, iz) in enumerate(savollar, 1):
        qismlar.append(f"**{n}. {s}**\n" + "\n".join(f"{_HARF[i]}) {x}" for i, x in enumerate(v)))
        javoblar.append(f"{n} — {_HARF[t]}" + (f". {iz}" if iz else ""))
    # Javoblar yig'iladigan bo'limda: rich xabarda yopiq turadi, oddiy
    # matnda esa sarlavha bo'lib oxirida (strip_rich_tokens).
    qismlar.append("[batafsil: ✅ Javoblar]\n" + "\n".join(javoblar) + "\n[/batafsil]")
    return "\n\n".join(qismlar)


def test_matnga(matn: str, qoralama: bool = False) -> str:
    """Vidjet chizilmaydigan joy uchun: blok → oddiy matnli test.

    `qoralama=True` — oqim paytidagi draft: blok o'rniga faqat "tayyorlanmoqda".
    Aks holda `+` belgili qatorlar javobni test tugashidan OLDIN ochib qo'yardi."""
    if not matn or "test" not in matn.lower():
        return matn

    def bir(m):
        if qoralama:
            return "📝 _Test tayyorlanmoqda…_"
        s = test_oqi(m.group(1))
        # Hech narsa o'qilmadi — belgilarsiz xom matn qoladi, ma'lumot yo'qolmasin.
        return test_matni(s) if s else m.group(1).strip()

    return _TEST_RE.sub(bir, matn)


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
