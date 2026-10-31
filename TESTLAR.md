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

- `test_retry.py` — the «↻ Qayta so'rash» button: one `query.answer` per callback (a
  second one is rejected and the cooldown alert disappears), the retry charges points
  (the original request was refunded on failure, so a free retry would be a free channel),
  Pro gets `user_id`/`is_pro`/`images_out`, and history gets the question *and* the answer.
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
- `test_qidiruv.py` — web search asks ddgs for `QIDIRUV_BACKEND`, not `auto` (dead engines
  on Railway's IP, `CHAT.md`); the 2-4 queries of one search run in parallel but their
  results keep query order; an all-empty answer is retried once with `auto`.
- `test_stars_solishtir.py` — the daily Stars reconciliation reads **Telegram's own**
  transaction list (both bots), not our table: a payment missing from `star_payments` is
  sent to the superadmin. The window is stored in `bot_settings.stars_tekshirildi`, so
  deploys neither repeat alerts nor leave gaps; it does not advance while the old bot is
  still connecting (check 6), or its payments would be skipped forever.
- `test_pro_grant.py` check 6 — every `_EXTEND_PLAN_SQL` call passes days as `int(...)`.
  Five weeks of failed Stars/promo/referral grants hid behind fakes (`ADMIN.md`).
- `test_admin_registry.py` — every admin handler still registered, in order, **and none of
  the 31 screens that moved to the web panel registered again**. A returning screen fails
  with the reason ("this was not deleted, it MOVED"), because the failure to avoid is two
  places editing one setting, not a missing handler.
- `test_activity_tracking.py` — every activity type the code writes is in `ACTIVITY_TYPES`. It **imports** that dict now (it used to read a handler by file path, which broke whenever code moved).
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
  was deleted — same rule, one surviving consumer), `test_web_journal.py` checks 1-2 compare the
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
