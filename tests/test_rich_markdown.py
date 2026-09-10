# -*- coding: utf-8 -*-
"""build_rich_markdown() havolalarni buzmasligini tekshiradi.

Nimani qo'riqlaydi:
  URL ichida sana bo'lishi odatiy hol — `.../uz/2026-08-20/dollar-oshdi/...`.
  Himoyasiz qolsa, sana naqshi uni topib `<tg-time>` tegiga o'raydi. Natijada
  havola ochilmaydigan bo'ladi VA `markdown` maydoniga HTML-only teg tushib,
  Telegram parseri to'xtaydi — butun xabar xom ko'rinadi, hatto oddiy
  `*yulduzcha*`lar ham. Ya'ni bitta havola butun javobning bezagini o'chiradi.

  Shu bilan birga MATNDAGI haqiqiy sana hamon `<tg-time>` ga o'ralishi kerak —
  aks holda tuzatish foydali xususiyatni o'ldirgan bo'lardi.

Ishga tushirish:
    PYTHONIOENCODING=utf-8 python tests/test_rich_markdown.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ai import (build_rich_markdown, strip_rich_tokens,
                        strip_custom_emoji, strip_image_tokens)


def test_url_sanasi_tegilmaydi():
    url = ("https://uz.kursiv.media/uz/2026-08-20/"
           "dollar-oshdi-21-avgust-uchun-valyutalar-kursi-elon-qilindi/")
    out = build_rich_markdown(f"- [Kursiv Uzbekistan]({url})")
    assert url in out, f"URL o'zgartirildi:\n{out}"
    assert "<tg-time" not in out, f"havolaga vaqt tegi qo'yildi:\n{out}"
    print("[1] markdown havola ichidagi sana tegilmadi OK")


def test_yalangoch_url_ham_himoyalangan():
    url = "https://cbu.uz/uz/kurs/2026-08-21/"
    out = build_rich_markdown(f"Manba: {url}")
    assert url in out and "<tg-time" not in out, out
    print("[2] yalang'och URL ichidagi sana tegilmadi OK")


def test_matndagi_sana_hamon_ishlaydi():
    out = build_rich_markdown("Bugun, 2026-08-21 kuni kurs e'lon qilindi.")
    assert "<tg-time" in out, f"matndagi sana tegga o'ralmadi:\n{out}"
    print("[3] matndagi haqiqiy sana hamon <tg-time> ga o'raladi OK")


def test_ikkalasi_bir_xabarda():
    """Eng muhim holat — xuddi shu xato jonli javobda shunday ko'rindi."""
    url = "https://uz.kursiv.media/uz/2026-08-20/dollar-oshdi/"
    out = build_rich_markdown(
        f"Bugun, 2026-08-21 kuni kurs o'zgardi.\n\nManba: [Kursiv]({url})")
    assert url in out, f"URL buzildi:\n{out}"
    matn, havola = out.split("Manba:")
    assert "<tg-time" in matn, "matndagi sana tegilmay qoldi"
    assert "<tg-time" not in havola, f"havolaga teg qo'yildi:\n{havola}"
    print("[4] bir xabarda: matn sanasi o'raldi, URL sanasi tegilmadi OK")


def test_url_dagi_dollar_belgisi():
    """URL ichidagi `$` matematika deb qabul qilinmasligi kerak."""
    url = "https://example.com/narx?a=$100$&b=2"
    out = build_rich_markdown(f"Havola: {url}")
    assert url in out, f"URL buzildi:\n{out}"
    assert "<tg-math" not in out, out
    print("[5] URL ichidagi $ matematika deb olinmadi OK")


def test_kod_bloki_himoyada_qoldi():
    kod = "```python\nsana = '2026-08-21'\n```"
    out = build_rich_markdown(kod)
    # Blokning O'ZI endi <pre><code> ga o'giriladi: ``` fence Telegram
    # Web-K da "not supported" xabariga aylanardi (services/ai.py:
    # code_fences_to_html). Ichidagi matn esa himoyada — hech bir
    # bosqich (sana, jadval, emoji) unga tegmaydi.
    assert out == ('<pre><code class="language-python">'
                   "sana = '2026-08-21'</code></pre>"), out
    assert "<tg-time" not in out, out
    print("[6] kod bloki himoyada, <pre> ga o'girildi OK")


def test_yangi_belgilar_tegilmaydi():
    """10.3 konstruktsiyalarini Telegram O'ZI chizadi — biz tegmaymiz.

    `==marked==`, `<sub>`/`<sup>`, `- [ ]` va `[^1]` uchun kodda
    o'giruvchi YO'Q: ular `markdown` maydonida qanday yozilgan bo'lsa,
    shundayligicha ketadi. Bu test o'giruvchi keyinchalik qo'shilganda
    ularni buzib qo'ymasligini qo'riqlaydi.
    """
    matn = ("==Eng muhim jumla== va H<sub>2</sub>O, 25 m<sup>2</sup>.\n"
            "- [ ] birinchi qadam\n- [x] bajarildi\n"
            "Da'vo[^1].\n\n[^1]: Manba nomi")
    out = build_rich_markdown(matn)
    assert out == matn, f"belgilar o'zgardi:\n{out}"
    print("[7] ==, <sub>/<sup>, - [ ] va [^1] tegilmadi OK")


def test_kod_ichidagi_tenglik():
    """`x == y` kod bloki ichida marker bo'lib qolmasligi kerak."""
    kod = "```python\nif x == y == z:\n    pass\n```"
    out = build_rich_markdown(kod)
    assert out == ('<pre><code class="language-python">'
                   "if x == y == z:\n    pass</code></pre>"), out
    assert "<mark" not in out, out
    print("[8] kod bloki ichidagi `==` saqlanib qoldi OK")


def test_batafsil_belgisi():
    """`[batafsil: ...]` → `<details>`; sarlavha escape qilinadi."""
    out = build_rich_markdown(
        "Javob.\n\n[batafsil: Texnik <xususiyat>]\n- a: 1\n[/batafsil]")
    assert "<details><summary>Texnik &lt;xususiyat&gt;</summary>" in out, out
    assert "</details>" in out and "- a: 1" in out, out
    assert "[batafsil" not in out and "[/batafsil]" not in out, out
    print("[9] [batafsil: ...] <details> ga o'girildi OK")


def test_batafsil_ichma_ich_va_yarim():
    """Ichma-ich belgi ham, juftsiz belgi ham xabarni buzmaydi."""
    ichki = build_rich_markdown(
        "[batafsil: Tashqi]\nmatn [batafsil: Ichki] ichkari [/batafsil]\n[/batafsil]")
    assert ichki.count("<details>") == 1, ichki
    assert "[batafsil" not in ichki, ichki

    yarim = build_rich_markdown("Javob [batafsil: Yarim qolgan] davomi.")
    assert "<details>" not in yarim and "[batafsil" not in yarim, yarim
    assert "Javob" in yarim and "davomi." in yarim, yarim
    print("[10] ichma-ich va yopilmagan belgi xabarni buzmadi OK")


def test_batafsil_kod_ichida():
    kod = '```python\ns = "[batafsil: x]"\n```'
    out = build_rich_markdown(kod)
    assert out == ('<pre><code class="language-python">'
                   's = "[batafsil: x]"</code></pre>'), out
    assert "<details" not in out, out
    print("[11] kod bloki ichidagi belgi tegilmadi OK")


def test_batafsil_oddiy_matnda():
    """Draft va zaxira yo'lida belgi qalin sarlavhaga aylanadi."""
    out = strip_rich_tokens("Javob [batafsil: Jadval] ichi [/batafsil] oxiri")
    assert "**Jadval**" in out and "[batafsil" not in out, out
    assert "[/batafsil]" not in out and "ichi" in out, out
    print("[12] oddiy yo'lda belgi qalin matnga aylandi OK")


def test_iqtibos_belgisi():
    """`[iqtibos: matn | muallif]` → `<aside>…<cite>…</cite></aside>`."""
    out = build_rich_markdown("Matn.\n\n[iqtibos: Bilim kuch | Frensis Bekon]")
    assert "<aside>Bilim kuch<cite>Frensis Bekon</cite></aside>" in out, out
    assert "[iqtibos" not in out, out
    print("[13] iqtibos belgisi <aside><cite> ga o'girildi OK")


def test_iqtibos_muallifsiz():
    """Muallif ixtiyoriy — `<cite>` umuman qo'yilmaydi, matn escape'lanadi."""
    out = build_rich_markdown("[iqtibos: Muallifsiz <jumla>]")
    assert "<aside>Muallifsiz &lt;jumla&gt;</aside>" in out, out
    assert "<cite>" not in out, out
    print("[14] muallifsiz iqtibos ham ishladi OK")


def test_iqtibos_kod_va_oddiy_yol():
    kod = '```\nx = "[iqtibos: kod ichida]"\n```'
    out = build_rich_markdown(kod)
    assert out == '<pre><code>x = "[iqtibos: kod ichida]"</code></pre>', out
    assert "<aside" not in out, out

    oddiy = strip_rich_tokens("a [iqtibos: Bilim kuch | Bekon] b")
    assert "«Bilim kuch» — Bekon" in oddiy and "[iqtibos" not in oddiy, oddiy
    print("[15] kod ichida tegilmadi, oddiy yo'lda qo'shtirnoqqa aylandi OK")


def test_premium_emoji_matnda():
    """Ma'lum emoji `![ ](tg://emoji?id=...)` ga aylanadi — BO'SH JOY bilan."""
    from core.config import CUSTOM_EMOJI
    out = build_rich_markdown("Salom 🤖 fayl 📄 tayyor.")
    assert f"![ ](tg://emoji?id={CUSTOM_EMOJI['bot']})" in out, out
    assert f"![ ](tg://emoji?id={CUSTOM_EMOJI['file']})" in out, out
    # ⚠️ Alt matnda bo'sh joy SHART: `![](` media blok deb o'qilishi mumkin.
    assert "![](" not in out, out
    print("[16] matndagi emoji premium variantga o'girildi (bo'sh alt) OK")


def test_premium_emoji_tegilmaydigan_joylar():
    """Kod, jadval katagi va `<aside>` — markdown parslanmaydi."""
    kod = '```python\nx = "🤖"\n```'
    kod_out = build_rich_markdown(kod)
    assert "tg://emoji" not in kod_out and "🤖" in kod_out, kod_out

    jadval = build_rich_markdown("| a | 🤖 |\n|---|---|\n| 1 | 📄 |")
    assert "tg://emoji" not in jadval and "🤖" in jadval, jadval

    iqtibos = build_rich_markdown("[iqtibos: Men 🤖 man | Bot]")
    assert "tg://emoji" not in iqtibos and "🤖" in iqtibos, iqtibos
    print("[17] kod, jadval va iqtibos ichida emoji tegilmadi OK")


def test_premium_emoji_chegarasi_va_qaytishi():
    from core.config import TEXT_CUSTOM_EMOJI_MAX
    ko_p = build_rich_markdown("🧠 " * (TEXT_CUSTOM_EMOJI_MAX + 8))
    assert ko_p.count("tg://emoji") == TEXT_CUSTOM_EMOJI_MAX, ko_p.count("tg://emoji")
    assert "🧠" in ko_p, "chegaradan keyingilari oddiy emoji bo'lib qolishi kerak"

    # Premium obuna tugasa — emojisiz variant qayta yuboriladi.
    asl = "Salom 🤖 fayl 📄."
    assert strip_custom_emoji(build_rich_markdown(asl)) == asl
    print("[18] chegara ishladi, emojisiz zaxira variant asl matnni tikladi OK")


def test_tugma_belgisi():
    """`[tugma: Yozuv | url]` → HAQIQIY `<tg-button>`.

    Muammo tarixi: modelning javob matnidan Telegram UI elementiga yo'l
    YO'Q edi — tugmalar faqat kod yozgan joyda paydo bo'lardi. Shuning
    uchun "kodini emas, ko'rinishini ko'rsat" so'roviga model yana matn
    bilan tushuntirardi.
    """
    out = build_rich_markdown("Manba:\n\n[tugma: Saytga o'tish | https://cbu.uz/uz/]")
    assert '<tg-button type="url" url="https://cbu.uz/uz/">' in out, out
    assert "<tg-button-row" in out and "[tugma" not in out, out
    print("[19] [tugma: ...] haqiqiy <tg-button> ga aylandi OK")


def test_tugma_buzuq_va_kod():
    """Noto'g'ri belgi tashlanadi, kod bloki tegilmaydi."""
    yomon = build_rich_markdown("[tugma: Yomon | ftp://x] va [tugma: Havolasiz]")
    assert "<tg-button" not in yomon and "[tugma" not in yomon, yomon
    assert "va" in yomon, yomon

    kod = '```\nx = "[tugma: K | https://a.b]"\n```'
    kod_out = build_rich_markdown(kod)
    assert kod_out == ('<pre><code>x = "[tugma: K | https://a.b]"'
                       "</code></pre>"), kod_out

    oddiy = strip_rich_tokens("Manba [tugma: Sayt | https://cbu.uz] oxiri")
    assert "Sayt: https://cbu.uz" in oddiy and "[tugma" not in oddiy, oddiy
    print("[20] buzuq belgi tashlandi, kod va oddiy yo'l joyida OK")



def test_belgi_ichidagi_bosh_joy():
    """`[ xarita:... ]` — qavsdan KEYIN bo'sh joy bilan yozilgani ham ishlaydi.

    JONLI XATO: bot "Surxondaryo qayerda" savoliga to'g'ri javob berib,
    oxirida `[ xarita:37.2242,67.2783,7 ]` deb YOZDI — va foydalanuvchi
    xarita o'rniga xuddi shu xom qavsni ko'rdi. Regex `\[xarita:` deb
    boshlanardi, model esa promptdagi misolni aynan ko'chirmaydi.
    `[ batafsil: ...]` da yanada yomon edi: ochilish belgisi xom qolib,
    `[/batafsil]` o'chirilardi — javob chala ko'rinardi.

    Promptga "bo'sh joy qo'yma" deb yozish yechim emas: misol allaqachon
    promptda turgan edi. Shuning uchun tekshiruv KODda.
    """
    assert '<tg-map lat="37.2242"' in build_rich_markdown(
        "[ xarita:37.2242,67.2783,7 ]")
    batafsil = build_rich_markdown("[ batafsil: Tarixi ] ichi [ /batafsil ]")
    assert "<details><summary>Tarixi</summary>" in batafsil, batafsil
    assert "</details>" in batafsil and "batafsil]" not in batafsil, batafsil
    assert "<tg-button" in build_rich_markdown("[ tugma: Sayt | https://a.uz ]")
    assert "<aside>" in build_rich_markdown("[ iqtibos: Bilim kuch | Bekon ]")
    # Oddiy yo'l (draft/zaxira xabar) ham xuddi shu belgilarni tozalashi shart
    oddiy = strip_rich_tokens("Joy [ xarita:41.3,69.2,14 ] shu yerda")
    assert "xarita" not in oddiy and "shu yerda" in oddiy, oddiy
    assert strip_image_tokens("a [ rasm:1 ] b [ rasmlar ] c").split() == list("abc")

def test_havola_himoyasi_buzilmadi():
    """`]` istisnosi havola himoyasini BUZMASLIGI kerak (regressiya)."""
    url = "https://uz.kursiv.media/uz/2026-08-20/dollar/"
    yalangoch = build_rich_markdown(f"Havola: {url} va matn")
    assert url in yalangoch and "<tg-time" not in yalangoch, yalangoch

    ichida = build_rich_markdown(f"- [Kursiv]({url})")
    assert url in ichida and "<tg-time" not in ichida, ichida

    aralash = build_rich_markdown(
        "Sana 2026-08-21 [tugma: Ochish | https://a.uz/2026-08-21/x]")
    assert "<tg-time" in aralash.split("<tg-button")[0], aralash
    assert 'url="https://a.uz/2026-08-21/x"' in aralash, aralash
    print("[21] havola himoyasi saqlandi, faqat tugma yopilishi ochildi OK")


def test_jadval_haqiqiy():
    """GFM jadval HAQIQIY <table> ga aylanadi — pseudo-jadval emas."""
    out = build_rich_markdown("| Model | Narxi |\n|---|---|\n| H5 | 300 mln |")
    assert "<table compact>" in out and "<th>Model</th>" in out, out
    assert "<td>300 mln</td>" in out, out
    print("[22] markdown jadval haqiqiy <table> ga aylandi OK")


if __name__ == "__main__":
    test_url_sanasi_tegilmaydi()
    test_yalangoch_url_ham_himoyalangan()
    test_matndagi_sana_hamon_ishlaydi()
    test_ikkalasi_bir_xabarda()
    test_url_dagi_dollar_belgisi()
    test_kod_bloki_himoyada_qoldi()
    test_yangi_belgilar_tegilmaydi()
    test_kod_ichidagi_tenglik()
    test_batafsil_belgisi()
    test_batafsil_ichma_ich_va_yarim()
    test_batafsil_kod_ichida()
    test_batafsil_oddiy_matnda()
    test_iqtibos_belgisi()
    test_iqtibos_muallifsiz()
    test_iqtibos_kod_va_oddiy_yol()
    test_premium_emoji_matnda()
    test_premium_emoji_tegilmaydigan_joylar()
    test_premium_emoji_chegarasi_va_qaytishi()
    test_tugma_belgisi()
    test_tugma_buzuq_va_kod()
    test_belgi_ichidagi_bosh_joy()
    test_havola_himoyasi_buzilmadi()
    test_jadval_haqiqiy()
    print("\nrich_markdown: barcha tekshiruvlar o'tdi (23/23).")
