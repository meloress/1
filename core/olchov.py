"""Business oqimlari o'lchovi — strukturali JSON log (AUDIT.md, 2-bosqich).

Har oqim (kiruvchi xabar, qoralama, avtojavob, buyruq, ...) oxirida BITTA
qator yoziladi:

    OLCHOV {"oqim": "loyiha", "id": "3f2a9c1b", "jami_ms": 2140,
            "bosqichlar": {"kvota": 12, "bilim_uslub": 9, "model": 2050},
            "ttft_ms": 830, "llm": 1, "kirish": 3120, "keshdan": 0,
            "chiqish": 42, "egasi": 7001, "natija": "tugadi"}

⛔️ Logga faqat son, id va nom tushadi — xabar matni, token (API kalit)
yoki model javobi HECH QACHON. `yoz()` qiymat turini tekshiradi: satr
faqat qisqa identifikator bo'lsa o'tadi.

Xulqqa ta'sir yo'q: o'lchov hech narsani ushlamaydi va hech narsani
yutmaydi — dekorator istisnoni o'z holicha qayta ko'taradi, log yozilmasa
ham (JSON xatosi) oqim davom etadi.
"""
import functools
import json
import logging
import secrets
import time
from contextvars import ContextVar

logger = logging.getLogger("olchov")

_joriy: ContextVar = ContextVar("olchov_joriy", default=None)
# Bitta business update'ning korrelyatsiya id'si — debounce taymeri
# `create_task` bilan konteksni nusxalaydi, shuning uchun qoralama oqimi
# uni keltirib chiqargan xabarning id'sini oladi.
_sorov_id: ContextVar = ContextVar("olchov_sorov_id", default=None)

# Satr maydoni shu uzunlikdan oshsa — tashlanadi (matn sizib chiqmasin).
_SATR_MAX = 32


def _xavfsiz(qiymat):
    if qiymat is None or isinstance(qiymat, (bool, int, float)):
        return qiymat
    if isinstance(qiymat, str) and len(qiymat) <= _SATR_MAX and "\n" not in qiymat:
        return qiymat
    return None


class _Oqim:
    __slots__ = ("nom", "t0", "oxirgi", "bosqichlar", "maydon")

    def __init__(self, nom: str):
        self.nom = nom
        self.t0 = self.oxirgi = time.perf_counter()
        self.bosqichlar: dict = {}
        self.maydon: dict = {"llm": 0, "kirish": 0, "keshdan": 0, "chiqish": 0}


def yangi_sorov() -> str:
    """Business update kirishida — korrelyatsiya id'si."""
    sid = secrets.token_hex(4)
    _sorov_id.set(sid)
    return sid


def belgi(nom: str) -> None:
    """Oldingi belgidan beri o'tgan vaqt `nom` bosqichiga yoziladi.
    Joriy oqim bo'lmasa — hech narsa."""
    o = _joriy.get()
    if o is None:
        return
    hozir = time.perf_counter()
    o.bosqichlar[nom] = o.bosqichlar.get(nom, 0) + round((hozir - o.oxirgi) * 1000)
    o.oxirgi = hozir


def qosh(**maydon) -> None:
    """Joriy oqimga maydon (natija, ttft_ms, egasi, rejim, ...)."""
    o = _joriy.get()
    if o is not None:
        o.maydon.update(maydon)


def token(kirish: int, keshdan: int, chiqish: int, model: str | None = None) -> None:
    """`services.ai._log_token_usage` dan — har LLM raundi. Narx logga
    yozilmaydi: model narxlari kodda yo'q (bepul grant + ortig'i billing),
    uni tokenlardan tashqarida hisoblash to'g'riroq."""
    o = _joriy.get()
    if o is None:
        return
    if model:
        o.maydon["model"] = model
    o.maydon["llm"] += 1
    o.maydon["kirish"] += int(kirish or 0)
    o.maydon["keshdan"] += int(keshdan or 0)
    o.maydon["chiqish"] += int(chiqish or 0)


def yoz(**maydon) -> None:
    try:
        toza = {k: _xavfsiz(v) if not isinstance(v, dict) else
                {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float))}
                for k, v in maydon.items()}
        logger.info("OLCHOV " + json.dumps(toza, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        pass


def oqim(nom: str):
    """Dekorator: async funksiya — bitta oqim. Tugaganda (istisno bilan
    ham) bitta JSON qator yoziladi; istisno o'zgarishsiz qayta ko'tariladi."""
    def dek(fn):
        @functools.wraps(fn)
        async def ichki(*a, **k):
            o = _Oqim(nom)
            belgi_ = _joriy.set(o)
            natija = "tugadi"
            try:
                return await fn(*a, **k)
            except BaseException as e:
                natija = type(e).__name__
                raise
            finally:
                _joriy.reset(belgi_)
                o.maydon.setdefault("natija", natija)
                yoz(oqim=nom, id=_sorov_id.get(),
                    jami_ms=round((time.perf_counter() - o.t0) * 1000),
                    bosqichlar=o.bosqichlar, **o.maydon)
        return ichki
    return dek
