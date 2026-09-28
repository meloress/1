"""GPT yozgan Python kodini izolyatsiya qilingan holda bajaradi.

Bu modul FAQAT kod bajarish bilan shug'ullanadi — Telegram yoki OpenAI
haqida hech narsa bilmaydi. Chaqiruvchi (services/ai.py) kodni va (bo'lsa)
kirish faylini beradi, natijada muvaffaqiyat/xato va yaratilgan fayllar
ro'yxatini oladi.

IZOLYATSIYA (nima himoyalangan va nima yo'q — ochiq-oydin):
  ✓ Muhit o'zgaruvchilari TOZALANADI — bola-jarayon BOT_TOKEN,
    OPENAI_API_KEY, DATABASE_URL kabi sirlarni umuman ko'rmaydi.
  ✓ Vaqtinchalik papka — har bajarilishda yangi, oxirida butunlay
    o'chiriladi. Kod faqat shu papka ichida ishlaydi (cwd).
  ✓ 60 soniya timeout — cheksiz sikl butun jarayon guruhi bilan
    o'ldiriladi.
  ✓ CPU / xotira / fayl hajmi / jarayon soni chegaralari (Linux'da
    RLIMIT orqali; Windows'da bu chegaralar ishlamaydi, faqat timeout).
  ✓ `python -s -E` — PYTHONPATH va foydalanuvchi site-packages
    e'tiborga olinmaydi.
  ✓ Tarmoq YOPIQ (2026-09-29). Sabab: shu Railway loyihasida ichki
    tarmoqda Postgres, Web-panel va boshqa botlar turibdi — model yozgan
    kod (prompt-injection bilan) ularga ulana olardi. Ikki qatlam:
      1) Linux: bo'sh tarmoq nomlar maydoni (`unshare` USER+NET) — haqiqiy
         izolyatsiya. Konteyner ruxsat bermasa — 2-qatlam qoladi.
      2) `_qoriqchi.py`: socket ulanishi va DNS Python darajasida taqiqlanadi.
    ponytail: 2-qatlam `_socket`/ctypes orqali aylanib o'tiladi — 1-qatlam
    ishlamasa bu to'liq himoya EMAS; ishga tushishda logda qaysi biri
    ishlagani yoziladi (`tarmoq_tekshir`).
"""
import asyncio
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

SANDBOX_TIMEOUT = 60           # soniya — kod bajarilishining qattiq chegarasi
MAX_OUTPUT_FILES = 10          # bittada qaytariladigan fayllar soni chegarasi
MAX_OUTPUT_FILE_SIZE = 45 * 1024 * 1024   # Telegram 50 MB — biroz zaxira bilan

# Har bajarilishda ish papkasiga ko'chiriladigan yordamchi modullar.
# GPT yozgan kod ularni `import docgen` kabi to'g'ridan-to'g'ri ishlatadi.
# Sabab: matn kengligini o'lchash/o'rash kabi ishlarni modelga qoldirsak,
# u koordinatalarni taxminan qo'yadi va matn sahifadan chiqib ketadi yoki
# boshqa blok ustiga tushadi. Bu yerda esa sinovdan o'tgan kod ishlaydi.
_HELPERS_DIR = Path(__file__).parent / "sandbox_helpers"

try:
    import resource  # POSIX-only (Railway = Linux). Windows'da yo'q.
    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False


@dataclass
class SandboxResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    traceback: str = ""
    output_files: List[Tuple[str, bytes]] = field(default_factory=list)


def _build_child_env(work_dir: Path) -> dict:
    """Bola-jarayon uchun MINIMAL muhit — barcha sirlar olib tashlanadi.

    Bu eng muhim himoya qatlami: BOT_TOKEN / OPENAI_API_KEY /
    DATABASE_URL kabi qiymatlar bola-jarayonga umuman uzatilmaydi,
    shuning uchun GPT yozgan kod (hatto prompt-injection natijasida
    ataylab yomon niyat bilan yozilgan bo'lsa ham) ularni o'qiy olmaydi.

    HOME/MPLCONFIGDIR vaqtinchalik papkaga yo'naltiriladi: matplotlib va
    boshqa kutubxonalar ishga tushganda yoziladigan config/kesh papkasini
    talab qiladi, uni tashqarida emas, shu yerda ushlab turamiz (papka
    oxirida butunlay o'chiriladi).
    """
    cache_dir = work_dir / ".cache"
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "MPLBACKEND": "Agg",   # matplotlib ekransiz (headless) muhitda ishlashi uchun
        # ⚠️ HISOB OQIMLARI SONI — 1 ta. Konteyner ichida `nproc` HOST
        # yadrolarini ko'rsatadi (Railway'da o'nlab), OpenBLAS esa har bir
        # oqim uchun katta bufer ajratadi va "Memory allocation still
        # failed after 10 retries" bilan yiqiladi — `import pandas` ning
        # o'zi ham o'tmaydi. Sandbox kodi bir martalik hisob, undan
        # parallellikdan foyda yo'q. Bu o'zgaruvchilar PYTHON* emas,
        # shuning uchun `-E` ularni bosmaydi.
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "MPLCONFIGDIR": str(cache_dir / "mpl"),
        "XDG_CACHE_HOME": str(cache_dir),
        "XDG_CONFIG_HOME": str(cache_dir),
        "HOME": str(work_dir),
        "TMPDIR": str(work_dir),
    }
    if os.name == "nt":  # mahalliy Windows'da sinash uchun
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env["USERPROFILE"] = str(work_dir)
        env["TEMP"] = str(work_dir)
        env["TMP"] = str(work_dir)
    return env


# 1-qatlam yoqilganmi. `tarmoq_tekshir()` uni o'chiradi, agar nomlar
# maydoni ichida fayl yozish buzilsa (sandbox ishlamay qolgandan ko'ra
# faqat 2-qatlam yaxshi).
_NETNS = True
_CLONE_NEWUSER, _CLONE_NEWNET = 0x10000000, 0x40000000


def _tarmoqni_yop() -> None:
    """Bola-jarayonni tarmoq interfeysi yo'q nomlar maydoniga o'tkazadi.
    Yiqilsa jim — 2-qatlam (`_qoriqchi.py`) baribir ishlaydi."""
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        uid, gid = os.getuid(), os.getgid()
        if libc.unshare(_CLONE_NEWUSER | _CLONE_NEWNET) != 0:
            return
        # Xaritasiz foydalanuvchi fayl yarata olmaydi (EOVERFLOW) — o'zini
        # o'ziga moslaymiz.
        for yol, matn in (("/proc/self/setgroups", "deny"),
                          ("/proc/self/uid_map", f"{uid} {uid} 1"),
                          ("/proc/self/gid_map", f"{gid} {gid} 1")):
            with open(yol, "w") as f:
                f.write(matn)
    except Exception:
        pass


# 2-qatlam: skriptdan OLDIN ishlaydi, keyin `script.py` ni `__main__`
# sifatida bajaradi — traceback'dagi qator raqamlari o'zgarmaydi (model
# xatosini aynan o'sha qatordan tuzatadi).
_QORIQCHI = '''import socket, _socket, runpy, sys
def _yopiq(*a, **k):
    raise PermissionError("Sandbox: internet yopiq. Kerakli fayllar oldindan berilgan.")
for _n in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
    setattr(socket, _n, _yopiq)
for _n in ("getaddrinfo", "gethostbyname", "gethostbyname_ex"):
    setattr(_socket, _n, _yopiq)
socket.socket.connect = socket.socket.connect_ex = _yopiq
sys.argv = ["script.py"]
runpy.run_path("script.py", run_name="__main__")
'''


def _apply_limits() -> None:
    """Bola-jarayonda exec'dan OLDIN chaqiriladi (faqat POSIX)."""
    if _NETNS:
        _tarmoqni_yop()
    # CPU: 55s yumshoq / 60s qattiq — timeout bilan bir xil tartibda.
    resource.setrlimit(resource.RLIMIT_CPU, (55, 60))
    # ⚠️ XOTIRA: RLIMIT_AS ISHLATILMAYDI, RLIMIT_DATA ishlatiladi.
    #
    # `AS` — VIRTUAL manzil maydoni. numpy/pandas/matplotlib/pptx uni
    # ishlatmasa ham gigabaytlab band qiladi (arena, thread stek,
    # mmap zaxirasi). 2 GB chegara serverda `import pandas` ni ham
    # MemoryError bilan yiqitardi — va har safar boshqa kutubxonani,
    # ya'ni nosozlik "goh bor, goh yo'q" bo'lib ko'rinardi.
    #
    # Windowsda RLIMIT umuman qo'llanmaydi (`_HAS_RESOURCE` False),
    # shuning uchun mahalliy sinovda hammasi ishlardi va nosozlik FAQAT
    # Railway'da chiqardi: model `import deck` yiqilgach jimgina PDF ga
    # o'tib ketardi, foydalanuvchi esa taqdimot so'rab PDF olardi.
    #
    # `DATA` esa HAQIQIY uyumni cheklaydi (Linux 4.7+ da anonim mmap ham
    # kiradi), ya'ni himoya saqlanadi, bekorga band qilingan manzil
    # maydoni esa hisoblanmaydi.
    try:
        resource.setrlimit(resource.RLIMIT_DATA,
                           (1536 * 1024 * 1024, 1536 * 1024 * 1024))
    except (ValueError, OSError):
        pass
    # Yaratiladigan fayl hajmi: 100 MB.
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))
    # Fork bombasidan himoya.
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
    except (ValueError, OSError):
        pass
    # Yangi jarayon guruhi — timeoutda butun daraxtni o'ldirish uchun.
    os.setsid()


def _collect_output_files(output_dir: Path) -> Tuple[List[Tuple[str, bytes]], List[str]]:
    """output/ papkasidagi fayllarni o'qiydi.

    Qaytaradi: (fayllar, ogohlantirishlar). Ogohlantirishlar GPT'ga
    qaytariladi, shunda u masalan faylni kichraytirishga urinishi mumkin.
    """
    files: List[Tuple[str, bytes]] = []
    warnings: List[str] = []

    if not output_dir.is_dir():
        return files, warnings

    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        if len(files) >= MAX_OUTPUT_FILES:
            warnings.append(f"{MAX_OUTPUT_FILES} tadan ortiq fayl yaratildi — qolganlari tashlab yuborildi.")
            break
        size = path.stat().st_size
        if size > MAX_OUTPUT_FILE_SIZE:
            warnings.append(f"'{path.name}' juda katta ({size // (1024 * 1024)} MB) — yuborilmadi.")
            continue
        try:
            files.append((path.name, path.read_bytes()))
        except Exception as e:
            warnings.append(f"'{path.name}' o'qib bo'lmadi: {e}")

    return files, warnings


def _safe_extra_name(name: str) -> str:
    """Qo'shimcha fayl nomini xavfsiz holatga keltiradi.

    ⚠️ Bu nomlar model chaqirig'idan kelib chiqadi (u qancha rasm
    so'raganiga qarab), shuning uchun ular ISHONCHSIZ chegara: `..` yoki
    `/` ish papkasidan tashqariga yozib yuborishi mumkin edi. Faqat
    fayl nomining o'zi olinadi va ruxsat etilgan belgilar qoldiriladi.
    """
    base = os.path.basename(name.replace("\\", "/"))
    cleaned = "".join(c for c in base if c.isalnum() or c in "._-")[:64]
    return cleaned or "file.bin"


async def run_in_sandbox(
    code: str,
    input_file_bytes: Optional[bytes] = None,
    input_filename: Optional[str] = None,
    extra_files: Optional[dict] = None,
) -> SandboxResult:
    """Kodni vaqtinchalik, tozalangan muhitda bajaradi.

    Kirish fayli (bo'lsa) ish papkasida `input.<kengaytma>` nomi bilan
    turadi. Kod `output/` papkasiga yozgan barcha fayllar o'qib
    qaytariladi. Papka har qanday holatda (xato/timeout ham) o'chiriladi.

    `extra_files` — {nom: baytlar}: ish papkasiga oldindan qo'yiladigan
    qo'shimcha fayllar (masalan internetdan yuklab olingan `rasm1.jpg`).
    Bu tarmoqqa chiqmasdan rasm ishlatishning yagona yo'li: sandbox'ga
    "internetga chiqmang" deb aytilgan, shuning uchun kerakli fayllar
    unga TAYYOR holda beriladi.
    """
    if not code or not code.strip():
        return SandboxResult(success=False, traceback="Bo'sh kod yuborildi.")

    tmp_dir = tempfile.mkdtemp(prefix="filetask_")
    work_dir = Path(tmp_dir)
    output_dir = work_dir / "output"

    try:
        output_dir.mkdir(exist_ok=True)
        (work_dir / ".cache").mkdir(exist_ok=True)

        if _HELPERS_DIR.is_dir():
            for helper in _HELPERS_DIR.glob("*.py"):
                shutil.copy2(helper, work_dir / helper.name)

        if input_file_bytes is not None and input_filename:
            ext = input_filename.rsplit(".", 1)[-1].lower() if "." in input_filename else "bin"
            # Kengaytmani tozalaymiz — yo'l bilan o'ynashning oldini olish uchun.
            ext = "".join(c for c in ext if c.isalnum())[:10] or "bin"
            (work_dir / f"input.{ext}").write_bytes(input_file_bytes)

        for raw_name, content in (extra_files or {}).items():
            if not content:
                continue
            (work_dir / _safe_extra_name(raw_name)).write_bytes(content)

        (work_dir / "script.py").write_text(code, encoding="utf-8")
        (work_dir / "_qoriqchi.py").write_text(_QORIQCHI, encoding="utf-8")

        # `-s -E`: foydalanuvchi site-packages va muhit o'zgaruvchilari
        # e'tiborga olinmaydi. `-I` ISHLATILMAYDI, chunki u skript papkasini
        # ham sys.path'dan olib tashlaydi va yordamchi `docgen` moduli
        # import qilinmay qoladi.
        #
        # `-X utf8` MAJBURIY: `-E` barcha PYTHON* o'zgaruvchilarini,
        # jumladan yuqorida qo'yilgan PYTHONIOENCODING'ni ham e'tiborsiz
        # qoldiradi. Linuxda LANG=C.UTF-8 qutqaradi, Windowsda esa bola
        # jarayon ANSI kod sahifasiga (cp1251) tushib qoladi va o'zbekcha
        # `ʻ` yoki emoji chop etilishi UnicodeEncodeError bilan yiqiladi —
        # model esa buni o'z kodining xatosi deb o'ylab, fayl yaratish
        # raundlarini behuda sarflaydi. Bu bayroq env emas, shuning uchun
        # `-E` uni bosa olmaydi.
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-s", "-E", "-X", "utf8", "_qoriqchi.py",
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_child_env(work_dir),
            preexec_fn=_apply_limits if _HAS_RESOURCE else None,
        )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=SANDBOX_TIMEOUT)
        except asyncio.TimeoutError:
            _kill_process_tree(proc)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass
            return SandboxResult(
                success=False,
                traceback=(
                    f"TIMEOUT: kod {SANDBOX_TIMEOUT} soniyada tugamadi va to'xtatildi. "
                    "Kodni sezilarli tezlashtiring (masalan butun faylni emas, "
                    "faqat kerakli qismini qayta ishlang)."
                ),
            )

        stdout = (stdout_b or b"").decode("utf-8", errors="replace")
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")

        if proc.returncode != 0:
            logger.info(f"[Sandbox] kod xato bilan tugadi (exit={proc.returncode})")
            return SandboxResult(
                success=False,
                stdout=stdout[:2000],
                # OXIRI qoldiriladi: xatoning o'zi traceback'ning oxirgi
                # qatorida. Boshidan kesilganda model "nima yiqildi"ni
                # ko'rmay, kodni ko'r-ko'rona qayta yozardi.
                stderr=stderr[-3000:],
                traceback=(stderr or stdout or "Noma'lum xatolik")[-3000:],
            )

        files, warnings = _collect_output_files(output_dir)
        combined_stdout = stdout[:2000]
        if warnings:
            combined_stdout += "\n[OGOHLANTIRISH] " + " ".join(warnings)

        logger.info(f"[Sandbox] muvaffaqiyat, {len(files)} ta fayl yaratildi")
        return SandboxResult(success=True, stdout=combined_stdout, output_files=files)

    except Exception as e:
        logger.error(f"[Sandbox] kutilmagan xatolik: {e}")
        return SandboxResult(success=False, traceback=f"Sandbox xatosi: {e}"[:2000])

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# Sandbox ichida GPT yozgan kod tayanadigan kutubxonalar. Ro'yxat
# `run_python_sandbox` tool tavsifidagi va'da bilan bir xil bo'lishi kerak.
SANDBOX_LIBRARIES = (
    "pptx", "docx", "openpyxl", "xlrd", "xlwt", "reportlab", "pypdf",
    "matplotlib", "PIL", "pandas", "fitz", "bs4", "lxml",
)


async def check_libraries() -> list[str]:
    """Kutubxonalar HAQIQATDA import bo'ladimi. Muammolar ro'yxatini qaytaradi.

    ⚠️ Ota jarayonda `import pptx` qilib tekshirish YETARLI EMAS: sandbox
    bola jarayoni `-s -E -X utf8` bilan, tozalangan muhitda va boshqa
    ish papkasida ishlaydi.

    NEGA KERAK: `python-pptx` serverda import bo'lmay qolgan edi va buni
    hech narsa bildirmadi — model jimgina PDF ga o'tib ketdi, ya'ni
    foydalanuvchi taqdimot so'rab PDF olardi. Endi bu ishga tushishda
    logda ko'rinadi.
    """
    kod = (
        "import importlib\n"
        f"for m in {list(SANDBOX_LIBRARIES)!r}:\n"
        "    try:\n"
        "        importlib.import_module(m)\n"
        "    except Exception as e:\n"
        "        print(f'{m}: {type(e).__name__}: {e}')\n"
    )
    result = await run_in_sandbox(kod)
    if not result.success:
        return [f"tekshiruvning o'zi yiqildi: {result.traceback[:300]}"]
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


_TARMOQ_SINOV = (
    "import _socket\n"
    "open('output/ok.txt', 'w').write('ok')\n"
    "s = _socket.socket(); s.settimeout(3)\n"
    "try:\n"
    "    s.connect(('1.1.1.1', 53)); print('OCHIQ')\n"
    "except Exception as e:\n"
    "    print('YOPIQ', type(e).__name__)\n"
)


async def tarmoq_tekshir() -> str:
    """Ishga tushishda: 1-qatlam (nomlar maydoni) HAQIQATDA ishlayaptimi.

    `_socket` 2-qatlamni chetlab o'tadi — shuning uchun bu sinov faqat
    1-qatlamni o'lchaydi. Nomlar maydonida fayl yozish buzilsa, 1-qatlam
    o'chiriladi: tarmoqsiz sandbox'dan ko'ra ishlamaydigan sandbox yomonroq.
    """
    global _NETNS
    r = await run_in_sandbox(_TARMOQ_SINOV)
    if _NETNS and not (r.success and r.output_files):
        _NETNS = False
        r = await run_in_sandbox(_TARMOQ_SINOV)
        if r.success:
            return "1-qatlam fayl yozishni buzdi va o'chirildi; faqat Python qo'riqchisi"
    if not r.success:
        return f"sinovning o'zi yiqildi: {r.traceback[:200]}"
    if "YOPIQ" in r.stdout:
        return "yopiq (nomlar maydoni + Python qo'riqchisi)"
    return "faqat Python qo'riqchisi (konteyner nomlar maydoniga ruxsat bermadi)"


def _kill_process_tree(proc) -> None:
    """Timeoutda butun jarayon guruhini o'ldiradi (bola jarayonlar bilan)."""
    try:
        if _HAS_RESOURCE:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    async def _demo():
        """Qo'lda ishga tushiriladigan tekshiruv: `python services/sandbox.py`"""
        # 1) Oddiy fayl yaratish
        r = await run_in_sandbox(
            "with open('output/result.txt', 'w', encoding='utf-8') as f:\n"
            "    f.write('salom sandbox')\n"
            "print('tayyor')\n"
        )
        assert r.success, f"kutilmagan xato: {r.traceback}"
        assert r.output_files, "output_files bo'sh bo'lmasligi kerak"
        assert r.output_files[0][0] == "result.txt", r.output_files[0][0]
        assert r.output_files[0][1] == "salom sandbox".encode(), r.output_files[0][1]
        assert "tayyor" in r.stdout, r.stdout

        # 2) Xato kod -> success=False, traceback ichida sabab
        r = await run_in_sandbox("raise ValueError('ataylab xato')")
        assert not r.success, "xato kod success=True qaytarmasligi kerak"
        assert "ataylab xato" in r.traceback, r.traceback

        # 3) Kirish fayli ko'rinishi kerak
        r = await run_in_sandbox(
            "data = open('input.txt', encoding='utf-8').read()\n"
            "open('output/echo.txt', 'w', encoding='utf-8').write(data.upper())\n",
            input_file_bytes=b"salom",
            input_filename="test.txt",
        )
        assert r.success, r.traceback
        assert r.output_files[0][1] == b"SALOM", r.output_files[0]

        # 4) Sirlar bola-jarayonga o'tmasligi kerak
        os.environ["SANDBOX_SECRET_PROBE"] = "maxfiy_qiymat"
        r = await run_in_sandbox(
            "import os\n"
            "open('output/env.txt', 'w').write(os.environ.get('SANDBOX_SECRET_PROBE', 'YOQ'))\n"
        )
        assert r.success, r.traceback
        assert r.output_files[0][1] == b"YOQ", "muhit o'zgaruvchisi sizib chiqdi!"

        # 5) Bo'sh kod
        r = await run_in_sandbox("")
        assert not r.success

        print("sandbox.py: barcha tekshiruvlar o'tdi.")

    asyncio.run(_demo())
