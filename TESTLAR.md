# TESTLAR.md

What each `tests/test_*.py` guards and which check is its sharpest. Moved out of
`CLAUDE.md` «Commands» on 2026-10-28; how to run the suite, and the `tests/_manba.py` rule,
stayed there.

## Structural guards and their sharpest checks

Some are structural guards rather than feature tests, and they earn their keep on refactors:

- `test_takroriy_def.py` — no two `def`s with one name in a module or class. Python lets
  the second silently replace the first; `_mijoz_nomi` written twice in the 3 000-line
  `handlers/biznes.py` broke `/mijozlar` with every test green.
- Structural tests find tables by name with regex, so **never give a new column the name
  of an existing table** — the `biznes_chat` column made `test_biznes_owner.py` fire on a
  query that was fine.

- `test_alifbo.py` — a Latin question never gets a mixed-script answer (`messages._alifbo`):
  the live `rahmat` reply is converted. The sharpest checks are 3 and 4: «kirillda yoz» and a
  Russian quote without ўғқҳ stay Cyrillic.
- `test_retry.py` — the «↻ Qayta so'rash» button: one `query.answer` per callback (a
  second one is rejected and the cooldown alert disappears), the retry charges points
  (the original request was refunded on failure, so a free retry would be a free channel),
  Pro gets `user_id`/`is_pro`/`images_out`, and history gets the question *and* the answer.
- `test_bot_api_104.py` — a reply to a button press in a group goes to the person who
  pressed it. Check 4 is the sharpest: `query.message.from_user` is the **bot**, so the old
  `ephemeral_params(query.message)` made the limit message ephemeral *to the bot*, Telegram
  rejected it, and `send_rich`'s plain round posted it to the whole group. Checks 6-9: the
  `/biznes` link to the «💼 Biznes» topic (`t.me/<bot>/<thread_id>`). It is not shown inside
  that topic, and the topic is never opened for an owner who is not connected. Checks
  10-12: in a group, «💎 Pro tarifga o'tish» does **not** draw the Pro screen (prices, an
  invoice and the gift/promo FSM would land in the group). It sends the person who pressed
  it an ephemeral `?start=pro` link instead, and `/start pro` opens the screen in the DM
  after the ban/admin checks.
- `test_vidjet.py` — the quiz widget and the live `/profile` card (Bot API 10.4). The
  sharpest checks: 9-10 (the draft hides the `+` answer lines, even in an unclosed block),
  12 (a model-written `</script>` cannot close the script), 17 (a rejected widget sends the
  quiz as **text**: the block was already cut out of the answer, so silence would lose the
  questions), 24 (a database error still answers the query, or the widget shows `TIMEOUT`)
  and 29 (a real aiogram `Dispatcher` gets `widget_query` without "unknown update type"). Checks 31-42 are the weather
  tool and card: 37 keeps "place not found" apart from "service down", 38 pins the
  `ob_havo` dispatch above the bare `else`, 39 is the group case (`None`, numbers in the
  text) and 41 sends the numbers as text when the card is rejected. 43-44: LaTeX and
  markdown never reach a widget raw (live: «$7 \times 8$»), while «$5 va $10» stays a price.
  45-54 cover currency. The sharpest is 45, where `Nominal` (VND per 10 units) would
  otherwise be a 10x error. 55-59 cover flashcards, 60-62 quotes from a rich message (the
  quote's `text` is empty and the words are in `rich_texts`), and 63-64 cover `/kunlik`
  sending the card, with text when it is rejected. 65-70 are the reminder countdown card.
  65 picks the newest reminder at that time. 66 shows that a database error means no card
  and no failure. 68 shows that `"e:<id>"` reads the **asking** user's list, so another
  person's id answers `{x:1}`. 69 shows that a rejected card sends no extra text, because
  the reply already gave the time.
- `test_brend_kartalar.py` — the `/start`, `/pro`, `/kunlik`, `/research` and `/profile` cards.
  - Check 23: every non-brand card (weather, currency, prayer times, reminder, quiz,
    flashcards) still fits 4 KB and carries the logo signature.
  - Checks 25-27: the full profile state (expired Pro reads as free, join date in Tashkent
    time) and the `"y"` answer without a name.
  - Check 2: no `opacity`/`filter` (the widget's heavy elements).
  - Check 4: the comparison numbers come from PLAN_LIMITS.
  - Check 6: the Pro card's buttons are exactly the normal screen's, so the payment path is
    unchanged.
  - Check 8: a rejected card sends the full text screen.
  - Check 10: the `/start` card returns False on any error, so the greeting is never lost.
  - Check 13: the `/kunlik` caption is fixed, because the state lives on the card.
  - Checks 15 and 19: `"k"` and `"r:<id>"` answer only the asking user.
  - Check 16: progress is the queries plus the count of unique links.
- `test_namoz.py` — prayer times.
  - Check 1 compares the calculation with the official Tashkent table on 24 dates of 2026
    and allows ±1 minute. The full year was checked once on 2026-11-10: all 2 190 times
    were within ±1.
  - Check 6 is the sharpest: a city in `UZ_FARQ` never reaches the geocoder, which put
    «Farg‘ona» at 68.3° longitude, a 14-minute error.
  - Check 10: Nukus is Tashkent + 39 minutes, which is how the official table works.
  - Checks 9 and 11: when namoz-vaqti.uz is down or returns a malformed table, the bot uses
    its own calculation, and the source line says so. A failed month is not retried on
    every request.
  - Check 12: the card's `"n:"` request comes from the device, so it is range-checked and
    the time-zone name is validated.
  - Check 16: suhoor (saharlik) is Fajr and iftar is Maghrib, stated to the model.
- `test_biznes_ekran.py` — the `/biznes` screens plus the owner-facing premium-emoji
  middleware (a request carrying `business_connection_id` is never touched by it), the
  customer send path `_mijozga()` and its fallback ladder, and the cancel flow (the
  «✖️ Bekor qilish» button, and pressing any *other* button clears a waiting FSM state).

- `test_karta_tolov.py` — the karta (so'm) Pro payment: a receipt never grants Pro by
  itself, only the superadmin's button does (a forged `pro:kt` from anyone else is refused
  before the database); a second press is "allaqachon hal qilingan"; the receipt handler
  sits before the AI handlers, photo/document only; a stale waiting state passes the photo
  on to the AI (`SkipHandler`, check 15 proves aiogram really propagates it); card prices
  keep the Stars ratio so the discount badges stay true; Stars buttons stay next to the
  card button; a database error reading the card does not break `/pro`. Checks 16-19 are
  the panel setting: an ordinary admin sees the card but gets 403 on write, a bad number
  is 400, the audit row holds only the last four digits, the superadmin is told in
  Telegram, both fields empty turns it off. Its SQL (unique amount, one pending request
  per user, retry after reject, Pro added once, the `bot_settings` columns) was run
  against pgserver, not just fakes. Check 21: the FSM lives in RAM and a deploy wipes it,
  so a receipt photo with no state is matched to a pending request **in the database**
  (`karta_chek_kutilmoqda`, also pgserver-checked) — otherwise a paid receipt went to the
  AI as "photo analysis" and never reached the superadmin.
- `test_qidiruv.py` — web search.
  - Every engine in `QIDIRUV_BACKEND` and `QIDIRUV_ZAXIRA` must be in ddgs's **own**
    `ENGINES["text"]`. Bing was not, and search ran on two engines for weeks.
  - No `auto`.
  - The 2-4 queries of one search run in parallel, and results keep query order.
  - An empty answer is retried once, without `site:`.
  - The Wikipedia fallback runs only when the engines failed, never on a plain
    "No results".
  - `site_siz()` is checked on the real logged queries.
- `test_tiklanish.py` — self-healing.
  - A stuck `GeneratingState` (older than `BAND_MAX`) is cleared, and the message reaches
    the **next** router. This runs through a real aiogram `Dispatcher` with `MemoryStorage`,
    because `SkipHandler` propagation is aiogram's behaviour and no fake would prove it.
  - A stuck request that finishes late does not clear its replacement's state.
  - A reply killed by a deploy:
    - one message per chat;
    - points refunded for every row;
    - the «Qayta so'rash» button goes through the existing `failed_requests` / `retry:<chat>`
      path, topic kept;
    - nothing at all happens off Railway.
  - The deploy self-check sends a ✅ with sound to the superadmin (silent until 2026-11-10), or a loud ❌ to the superadmin
    and the watch group.
  - Source guards: `GeneratingState` is set only in `_band()`, and the queue is woken only
    behind `_bosh()`.
  - The SQL was run on pgserver.
- `test_avto_tatil.py` — maintenance that turns itself on. Its sharpest checks guard
  against the bot stopping itself:
  - a per-minute 429, 5xx, timeouts and dropped connections never count;
  - one serious error is not enough, and a success resets the count;
  - a control request that passes or is inconclusive switches nothing on;
  - only maintenance the bot switched on itself gets switched off, and a manual one is never
    touched.

  Business checks: a customer gets the panel text once per maintenance per chat, a paused
  chat stays silent, and an Instagram comment gets nothing. Source guards cover the hooks in
  `get_openai_reply` and the SQL that clears the flag on a manual switch.
- `test_karta_eslatma.py` — the karta payment after the request: `/pro` shows an open
  request's state on top (checking / rejected / open until HH:MM) so nobody opens a second
  one; one reminder after `KARTA_ESLATMA`, and when the window closes the request becomes
  `eskirdi` and the user is told "time is up — if you paid, write to the admin" **with the
  admin button**. A receipt that lands on a just-closed request is pointed to the admin too.
  `eskirdi` is not in `_KARTA_FAOL` (frees the amount, takes no receipt).
- `test_pro_obuna.py` — the monthly Stars subscription: someone else's `prosub:` link cannot
  be paid (pre_checkout) nor granted (successful_payment); a renewal is a short message, not
  🎉; a second concurrent subscription is cancelled; `grant_paid_pro(obuna=…)` lifts Pro to
  the next charge + `OBUNA_ZAXIRA_SOAT` and upserts `pro_obuna` (not for the second one); no
  «tugayapti» reminder for an active subscriber; the reminder tool asks for `DD.MM.YYYY
  HH:MM` so the answer's time becomes `<tg-time format="wDt">`.
- `test_reasoning_effort.py` — `none` (no thinking) only when the **whole** message is a
  greeting/thanks; "hisobla 17*23", "noto'g'ri javob berding", "ha" used to get `none` by
  prefix. A short message after earlier turns is one level above the previous questions
  (cap `medium`, Pro lifts it) — no word list decides "yes" vs "you're wrong".
- `test_stars_solishtir.py` — the daily Stars reconciliation reads **Telegram's own**
  transaction list (both bots), not our table: a payment missing from `star_payments` is
  sent to the superadmin. The window is stored in `bot_settings.stars_tekshirildi`, so
  deploys neither repeat alerts nor leave gaps; it does not advance while the old bot is
  still connecting (check 6), or its payments would be skipped forever.
- `test_pro_grant.py` check 6 — every `_EXTEND_PLAN_SQL` call passes days as `int(...)`.
  Five weeks of failed Stars/promo/referral grants hid behind fakes (`ADMIN.md`).
- `test_plan_limits.py` check 5 — the downgrade done inside the quota functions keeps
  `premium_until`, and `expire_premiums()` has no `plan_type <> 'free'` condition. Before
  2026-11-06 the inline downgrade cleared the date, so a buyer who kept using the bot
  never got the «Pro tugadi / Pro'ni qaytarish» message; only people who had stopped
  writing did.
- `test_admin_registry.py` — every admin handler still registered, in order, **and none of
  the 31 screens that moved to the web panel registered again**. A returning screen fails
  with the reason ("this was not deleted, it MOVED"), because the failure to avoid is two
  places editing one setting, not a missing handler.
- `test_activity_tracking.py` — every activity type the code writes is in `ACTIVITY_TYPES`. It **imports** that dict now (it used to read a handler by file path, which broke whenever code moved). Since 2026-11-05 `start` is no exception any more: it is in the dict, otherwise the panel dumped it into «Boshqa» and logged a warning every time. Check 4b keeps it out of the daily top-5 through `ACTIVITY_BUYRUQLAR`.
- `test_olchov.py` 10-14 — reply speed:
  - `ttft` records only the **first** word;
  - a flow that never called the model is not stored;
  - a failing store does not break the flow;
  - `boshlash()` keeps the user's typing time out;
  - the wrapped chat handlers keep the signature aiogram reads;
  - storing happens only on Railway.
- `test_image_pick.py` 34-38 — the picker gets Bing's thumbnail while the user gets the original. When OpenAI cannot download an image, we fetch the images ourselves, drop the one that will not load, and the indices map back correctly. Another error (429) does not trigger the download. An internal address is never fetched.
- `test_prompt_rules.py` — 60 individual prompt rules still present in the assembled `instructions`. Run it **before and after** any prompt edit; identical results are what make a prompt change safe to ship.
- `test_url_read.py` — the untrusted-boundary guard on `internet_search(url=…)`: a
  model-written URL must never reach an internal address, and a page that will not open
  must return an explicit error rather than silence. Runs offline (numeric IPs, no DNS).
- `test_history_summary.py` — the one that matters most if you touch `db/history.py`:
  it proves that when summarising fails (empty result, model error, exception) the raw
  messages are **not** deleted. Get that backwards and the repair silently destroys the
  conversations it exists to save. Runs with a fake pool, no DB and no network.
- `test_topics.py` — the two silent failures of per-topic conversations: a reply
  going to one topic while its history is written to another (the bot then cannot see
  its own answer, and nothing logs), and result files landing in the chat's main flow
  instead of the topic. Pins `_thread_key()` to aiogram's own `is_topic_message`
  condition. Runs offline.
- `test_voice_status.py` — the TTS status indicator cleans up on every exit path
  (draft emptied, group message deleted, and both still done when the body raises). An
  abandoned draft hangs on screen and kills the next animation.
- `test_biznes.py` / `test_biznes_yordamchi.py` / `test_biznes_avtomat.py` /
  `test_biznes_hisobot.py` / `test_biznes_uslub.py` / `test_biznes_mavzu.py` /
  `test_biznes_tanlov.py` / `test_biznes_qaror.py` / `test_biznes_ishonch.py` /
  `test_biznes_pauza.py` / `test_biznes_kesh.py` / `test_biznes_owner.py` /
  `test_biznes_ekran.py` / `test_biznes_tejash.py` / `test_biznes_fakt.py` /
  `test_biznes_media.py` / `test_biznes_tozalash.py` — Telegram Business,
  all offline. The loop guard (`biznes_kimdan` order), the atomic draft claim, "nothing
  technical reaches the customer", "the customer path never gets the assistant prompt", and
  "a `[tanlov:]` marker never reaches the other side". `test_biznes_owner.py` walks every
  `biznes_*` SQL with `ast` and fails without an `owner_id` filter. `test_olchov.py` guards the
  business JSON measurement log (no message text in it). ⛔️ **`tests/eval_biznes.py` is not a
  unit test** — it calls the live model; run it before and after any Business prompt edit.
- ⛔️ **`tests/eval_chat.py`** — the same for the main chat (25 cases, live model + live
  search): which tool must / must not fire, and what the text must / must not contain.
  `test_prompt_rules.py` proves a rule is *in* the prompt; this proves the model *follows*
  it. Baseline 2026-09-29: **48/50 (96%)** with `--takror 2`; the two misses are random
  (`\(` once instead of `$`, one generic capabilities answer). Its first run found the free
  user never hearing "this needs Pro" for drawing and reminders — fixed by the separate
  `PRO FEATURES` manifest line (+44 tokens/round, free plan only). Model text uses `‘` for
  the Uzbek apostrophe; the harness normalises it before matching.
- `test_nearby.py` — the untrusted-boundary guard on `find_nearby`: a model-written category must never reach the Overpass query intact, and "the source failed" must never be reported as "nothing nearby". Runs offline.
- `test_image_edit.py` — `edit_image`'s three silent failure modes: the dispatch branch sitting above the bare `else`, the source bytes staying out of the tool schema, and the two API arguments (`size="auto"`, `input_fidelity="high"`) that only degrade the picture rather than raising. Runs offline.
- `test_file_intent.py` / `test_emoji_pack.py` / `test_image_pick.py` — the three places where a config number silently changes behaviour (which tool schema is attached, which emoji map is live, how many photos come back). `test_image_pick.py` also pins the picker model to a tile-based one; a patch-based model there costs 23x per image.
- `test_admin_extras.py` checks 12-13 — every admin callback handler still starts with `require_admin_or_deny_query`, and the user counts in `activity_stats()` still filter the same set (check 13 asserts the `_ODDIY_USER` constant is the single place that says so, so "one query excludes admins, the other doesn't" is structurally impossible). Both were written after the corresponding bug, and the guard check was verified by deleting the guard and watching it fail. (They were checks 19-20 until phase 7 cut the file from 20 checks to 13 — renumber this line if it moves again, or the next reader looks for a check that is not there.)

- `test_admin_kod.py` — the `/kod` sending flow, which after phase 7 is the only admin
  path the web tests do not cover. Runs offline. Its sharpest check is that a code whose
  uses are spent or which was revoked never reaches the picker: sending one means handing
  someone a gift that will not work.
- `test_web_auth.py` / `test_web_panel.py` / `test_web_stats.py` / `test_web_users.py` /
  `test_web_journal.py` / `test_web_settings.py` / `test_web_promo.py` /
  `test_web_xavfsizlik.py` / `test_bir_marta.py` — the web panel.
  All nine run offline (no DB, no network, no browser) by replacing `web.huquq_bormi`
  and the `database` calls. The ones that earn their keep: `test_web_users.py` check 9
  proves the refund does **not** touch the database when Telegram refuses,
  `test_web_stats.py` check 8 proves there is no raw SQL in `web/api.py` or `daily.py`
  (it used to compare the panel against the Telegram statistics screen, until that screen
  was deleted — same rule, one surviving consumer), `test_web_stats.py` check 9f pins the
  token card to the **grant day (UTC, 05:00 Tashkent)**, the business token share too,
  `test_web_journal.py` checks 1-2 compare the
  audit action names the code actually writes against `AUDIT_ACTIONS` in both directions,
  **`test_web_settings.py` check 2 is the one that proves the panel is worth having at
  all** — it changes a limit through the HTTP endpoint and then asserts
  `config.daily_limit()` returns the new number, i.e. that the bot's RAM cache was
  refreshed — and its check 11 proves the panel goes through the *same* admin-removal
  gate as the bot. `test_web_promo.py` check 6 pins `extend=True` on gifted Pro (without
  it a gift wipes the days the user already had).
- `test_panel_raqamlar.py` — the one that exists because the numbers on a single screen
  disagreed with each other. It reads the **text of the SQL**, so it needs no database and
  still fails the moment a definition is written a second time: that "Pro" means one thing
  in all three queries, that every per-person count excludes admins, that the request-type
  bars sum to the request KPI, that a promo code expires at 23:59:59 **Tashkent** rather
  than at 05:00, and that `set_user_premium()` still defaults to `plan='pro'`. That last
  one is the sharpest: the default used to be `'premium'`, i.e. the panel's
  "Pro berish · 7 kun" button quietly handed out the unlimited tier.
- `test_ogohlantirish.py` — the two alerts (error surge, silent bot). Its sharpest
  checks are that one outage produces **one** message (a repeating alert is an
  ignored alert), that night-time silence is not reported, and that an empty
  `user_activity` table is not read as "silent forever". Runs offline.
- `test_bir_marta.py` — the idempotency decorator. Its sharpest check is **2**, which
  fires two requests with `asyncio.gather`: a real double-tap arrives while the first
  request is still running, so "store the result afterwards" buys nothing on its own —
  the per-key lock is the whole feature. Deleting the lock leaves check 1 passing and
  only check 2 fails, which is exactly the illusion the check exists to break. Check 7
  recomputes which endpoints need the decorator **from the source** rather than from a
  list, so a new endpoint forces a decision.
- `test_web_xavfsizlik.py` — the panel's security rules, all of which break silently:
  the client IP must not come from the **first** `X-Forwarded-For` entry (the client
  writes that one), `_urinishlar` must stay bounded, `X-Frame-Options` must stay
  **absent** (it would kill the Mini App inside Telegram Web's iframe), and `initData`
  must appear in no log line.
- `test_panel_korinish.py` — the panel's *appearance* rules. No browser is available here,
  so it checks the rule instead: no `<table>` and no horizontally scrolling list, content
  padded past the fixed bottom nav **plus** the device inset, every colour token defined in
  **both** themes (never only inside a media query), and the muted text colours run through
  an actual WCAG contrast calculation in each theme — the old `--ink-3` scored 3.7:1, which
  is every hint on every screen failing AA. It also pins that each `fetch` carries the
  Telegram signature.

- `test_eski_bot.py` — the old `@uzchatgptaibot` redirect (`DEPLOY.md` «The bot moved to
  @vexonai»). Its sharpest check is **2**: an old-bot Business customer gets nothing and
  the owner is told once — "this bot has stopped" must never land in the owner's name.
  Check 7 pins `ESKI_BOT_TOKEN != BOT_TOKEN` in `main.py`, check 8 that the module never
  imports the database.
- `test_biznes_almashuv.py` — a new Business connection inherits the owner's settings.
  Check 3 is the one that matters: if the copy fails, the connection is **still saved**,
  so the owner is never left with no connection at all; checks 4-6 read the SQL (`ig:`
  untouched, only `kutmoqda` drafts move, one transaction).

## How `tests/_manba.py` works

Two things about `kod()` are load-bearing and both were paid for. It **preserves the
layout** — the first version rejoined tokens with `"\n"`, which turned `def admin_only(`
into three lines and broke *fifteen* test files at once, because nearly every guard
here works by finding a declaration and slicing to the next one. And it treats only a
**logical** line end (`NEWLINE`) as a statement boundary, never `NL`: counting `NL` made
it read the keys of a multi-line dict literal, and f-strings inside multi-line calls, as
docstrings and delete them. A docstring is replaced by `0`, not by nothing, so a class
whose whole body is a docstring still parses.
