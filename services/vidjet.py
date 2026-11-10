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
        belgi, matn = q[0], q[1:].strip()
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
