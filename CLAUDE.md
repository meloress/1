# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

**All code comments, docstrings, commit messages and user-facing strings are in Uzbek (Latin script).** Match that — a comment or bot reply in English reads as foreign here. Comments explain *why*, especially the non-obvious constraints listed below; several of them are load-bearing and were paid for with real bugs.

## Commands

```bash
python main.py                      # botni ishga tushirish (polling)
python tests/test_memory.py         # bitta testni ishga tushirish
python services/sandbox.py          # sandbox izolyatsiyasini tekshirish
python services/sandbox_helpers/deck.py   # PPTX maketlarini tekshirish
python tests/test_tts_lang.py --live  # jonli TTS sintezi bilan
python tests/eval_chat.py [--takror N] [id...]              # asosiy chat sifati — JONLI model
python tests/eval_biznes.py [--takror N] [--qoralama] [id...]  # Business — JONLI model
python tests/eval_tabiiy.py [--takror N] [id...]            # Business: «bot sezilyaptimi» — JONLI + hakam
```

```bash
node --check web/static/panel.js        # panel JS sintaksisi
node --check web/static/soz.js          # panel lug'ati (u ham JS)
python -m compileall -q .               # butun daraxt kompilyatsiyasi
```

No test framework, no linter, no build step — but the panel's JavaScript has no test that
parses it, so `node --check` is the only thing standing between a typo and a blank screen
for every admin. Run it after every `panel.js` / `soz.js` edit. Each `tests/test_*.py` is a standalone `assert`-based script with numbered `print("[N] ... OK")` lines and a final summary. New tests follow that shape. On Windows, prefix with `PYTHONIOENCODING=utf-8` — some tests print emoji and the console codepage will otherwise raise `UnicodeEncodeError` (a false failure, not a real one).

Run the whole suite by looping over `tests/test_*.py`; `test_pro_security.py` is the slow one:

```bash
fail=0; for f in tests/test_*.py; do PYTHONIOENCODING=utf-8 timeout 300 python "$f" >/dev/null 2>&1 || { echo "FAIL $f"; fail=1; }; done; echo done $fail
```

It takes ~10 minutes, so it usually runs in the background. ⛔️ **Read its output
(`done 0`) before committing.** Chaining `commit && push` onto a background run, or
pushing while it is still going, shipped two failing tests on 2026-09-29 — `git push
meloress main` deploys, so there is no review step after it.

⚠️ **Never write text containing `\n`, `\\` or other backslash escapes through a bash
heredoc.** The shell mangles them: a Python replace script written as `<<'EOF'` still put
a real newline inside a string literal (`SyntaxError: unterminated string literal`) or
failed its own `assert s.count(old) == 1`. This happened half a dozen times in one
session, and three more times on 2026-10-15 — including `python - <<'EOF'`, which looks
safe and is not. Any script containing `\n`, `\\` or `\b` goes to the scratchpad with
Write and is run as a file; the Edit tool for in-place edits.

⚠️ **The local `.env` points `DATABASE_URL` at the production database.** A test that
does not fake a `database.*` call it reaches is reading (or writing) live data — which is
why the Business tests fake `b._birinchi_marta` and friends explicitly. Reading that
database directly from here is **blocked** by the environment; do not work around it. For
a real end-to-end check use a local Postgres: `pip install pgserver`, then copy `tzdata`'s
`zoneinfo` into `pgserver/pginstall/share/postgresql/timezone`, or `Asia/Tashkent` is
unknown.

⚠️ **A fake must return the keys the real function returns.** `test_digest.py` stayed
green while `/kunlik` was dead because its fake profile carried `digest_hours` and the real
`get_full_user_profile()` did not. When a fake stands in for a `database.*` function, copy
its shape from the real `SELECT`/return, not from what the code under test hopes to read.

⚠️ **The local `.env` `BOT_TOKEN` is a different bot** — «Tramplin»
(`@tramplin_offical_bot`), not production `@vexonai` (`@uzchatgptaibot` before 2026-10-25). `getMe` from here says nothing
about the live bot. The local `OPENAI_API_KEY` **does** have credit (2026-10-15), so the
`eval_*.py` scripts run locally.

**Live-eval baselines** — compare against these after any prompt edit:
`eval_chat.py` 48/50 with `--takror 2` (2026-09-29), `eval_biznes.py` **120/120** (112 + 8 obuna holati, 2026-10-16),
`eval_tabiiy.py` judge **9.5 / 9.5** (without / with owner style) and 0/64 "bot tells"
(2026-10-15). The handoff sentence a customer sees is **code-owned**
(`biznes.uzatish_matni()` + `UZATISH_GAPLARI`), not model text — see `BIZNES.md`
«Tabiiylik».

**What each `tests/test_*.py` guards, and its sharpest check, is in `TESTLAR.md`.** Read a
test's entry there before changing or deleting one of its assertions — several are
structural guards (duplicate `def`s, `owner_id` on every `biznes_*` SQL, no SQL in
`web/api.py`) and a failure after a refactor usually means the rule moved, not that it died.
`tests/eval_*.py` are **not** unit tests: they call the live model.

⛔️ **A test that reads source text goes through `tests/_manba.py`, never through
`read_text()` directly.** `kod(path)` blanks out comments and docstrings *in place*;
`js_kod(text)` / `css_kod(text)` do the same for the panel's files. This is the single
most repeated mistake in this repo — **four times**, always identically: a guard matched
the comment that *explains* the rule it guards, and stayed green while the code was
wrong. `@bir_marta` was found in the comment saying why `refund` is excluded from it;
`del_cookie()` in the comment saying it must not be used; "Ishonchingiz komilmi" in a
comment giving it as an example of a forbidden phrase; "chat not found" in the comment
saying the list must not be copied. `test_web_journal.py` check 18 walks every
`tests/test_*.py` with `ast` and fails on a raw `.py` read, so the rule cannot rot back.

⚠️ **Strings are deliberately kept.** Most guards here read SQL, and SQL lives in
ordinary string literals — stripping strings would kill them all. The hazard is prose,
and prose lives in comments and docstrings.

Exact token counts need `tiktoken` (`pip install tiktoken`, encoding `o200k_base`). It is **not** in `requirements.txt` — the bot never counts tokens itself, it is a local measuring tool. Do not estimate from character counts; that was 11% off on this prompt.

## Deploy

The panel is live at **`https://1-production-666e.up.railway.app`** (first deployed
2026-09-16, commit `2c292c5`).

⚠️ **Railway does not set `PORT` on this service** — checked with `railway variables`, it
is simply absent, so `web/__init__.py` falls back to **8080** and the generated domain
routes to it. An earlier version of this file claimed Railway supplies it; do not "fix"
the fallback on that assumption. `WEB_APP_URL` is read from the env or derived from
`RAILWAY_PUBLIC_DOMAIN`, which Railway *does* set once a domain exists (Settings →
Networking → Generate Domain).

⚠️ `Procfile` declares `worker: python main.py`, and the panel is served from that same
worker anyway — one process, HTTP and polling together (see `WEB_PANEL.md`). Do not
add a second process type for it.

Verify a deploy landed without opening a browser: `railway status --json` →
`services[].serviceInstances[].latestDeployment.status` walks BUILDING → DEPLOYING →
SUCCESS, then `/` answers 200 and any `/api/*` answers **401** without a cookie — that
401 is the gate working, not a failure.

⚠️ **`ssh-agent` is not running in this environment**, so a plain `git push` can fail
with `Permission denied (publickey)` even though the key is right there in `~/.ssh/`. The
key is loaded explicitly instead:
`GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes" git push meloress main`.
It failed exactly once mid-session after several successful pushes, so do not read a
failure as "the key is wrong" — try the explicit form first.

⚠️ **`git fetch meloress` before every push.** Another session once pushed the same files
to `meloress/main` in parallel; a push without looking first either fails or, after a
careless rebase, deploys code nobody tested together.

**`git push meloress main` deploys.** The Railway service is connected to GitHub, so a push to `git@github.com:meloress/1.git` (remote `meloress`) triggers the build by itself — no API call, no token. `origin` still points at `afiffamily/1`, where this account has **no write access** (403), so never push there.

- Never ask for a token in chat. Have the user put it in `RAILWAY_TOKEN` and read it from the environment without echoing it.

### Reading production logs

⚠️ Run `railway whoami` first: "Unauthorized" means the login expired, every command prints
nothing, and an empty `grep` then reads as "no errors" when it is "no access". Only the user
can log in again (`railway login`, browser flow) — say so instead of concluding anything.
`timeout 45 railway logs` (the stream never exits on its own). Railway project/service ids,
the GraphQL queries for older logs and for **which commit is live**, and why `railway link`
/ `railway list` are broken on this account: **`DEPLOY.md`**. ⚠️ After a push, wait for
`SUCCESS <the hash you pushed>`, not just `SUCCESS` — the previous deploy reports it too.

## Architecture

`BOT_API_103.md` is the long-form companion to this file: everything added with Bot API 10.3 and after, explained in full — including the decisions that were **tried and reverted** (the interim "preparing your file" message, the sources slide). Read it before re-attempting anything in that area; this file only carries the rules.

`REJA.md` is now the **Telegram Business** plan (phases 0-4); the rules as built and the next work are in **`BIZNES.md`**. The **web admin panel** plan it used to hold — the reasoning behind each architectural decision, what each phase changed, every departure from the mockup — lives in git: `git show 3ba4744:REJA.md`. Every `REJA.md 3.1` / `3.2.1` / `4-bo'lim` reference in code comments points at that version. Read it before touching `web/`.

### Handler registration order is a safety constraint

`main.py` registers handlers in a deliberate order and each position is justified in a comment. The critical ones:

1. `successful_payment` / `pre_checkout_query` go on `dp.message` **directly**, before any router. `handlers/messages.py` has a `GeneratingState.generating` spam-guard with no content filter; if a payment lands while a reply is streaming, that guard would swallow it — money taken, Pro not granted. They also sit **before `register_admin_handlers()`**: the admin module's report state (`ReportStates`, open to ordinary users) has no content filter either (`test_admin_registry.py` check 6).
2. FSM states (gift, promo, digest, broadcast) come before the AI handlers so a user's answer to "kimga sovg'a qilay?" is not sent to GPT as a question.
3. `maintenance_gate` sits before the AI handlers but after `/start` and `/profile`; `/pro`, `/promo`, `/gift` sit *after* it — selling a subscription for a disabled bot is a refund source.
4. `generating_state_router` is included before `general_router` so a message arriving mid-reply does not start a second parallel request.

Do not reorder these without reading the comments.

### Where the long-form rules live

Every rule below was paid for with a live bug; the bug, the measurement and the reasoning
are in the companion file, under the **same section title**. ⛔️ Read that section before
touching its code — the one-liner tells you *that* something breaks silently, not *why*.

| Touching | Read first |
|---|---|
| `services/ai.py`, `handlers/messages.py`, `handlers/guest.py`, `db/history.py`, `services/sandbox.py`, `services/places.py`, prompts, tools, TTS | **`CHAT.md`** |
| `handlers/admin/`, `db/database.py` SQL, migrations, `core/config.py` label dicts | **`ADMIN.md`** |
| `web/` | **`WEB_PANEL.md`** |
| `handlers/biznes*.py`, `handlers/instagram.py` | **`BIZNES.md`** |
| Railway, logs, which bot/token runs where | **`DEPLOY.md`** |
| What a test guards | **`TESTLAR.md`** |
| Anything from Bot API 10.3+ (drafts, rich messages, reverted attempts) | **`BOT_API_103.md`** |

**`CHAT.md`** — the chat pipeline, one line per section:

- **Token budget** — the free grant counts tokens, cached ones too; ~8 280 (free) / 8 603
  (Pro) fixed tokens per round. Re-measure with `tiktoken` after any schema/manifest/prompt
  edit. `prompt_cache_key` is per **plan**, never per user; `PROMPT_CACHE_RETENTION` is off on purpose.
- **Stop button** — `@dp.stopped_message_generation()` observer; in aiogram 3.31
  `disabled`/`force_reply` are real fields, read both them and `model_extra`; keep
  `using_rich_draft` and `can_send_rich` separate.
- **Tool loop** — every named tool is an `elif` **above** the bare `else` (which is web
  search). Doors (`start_file_task`, `open_memory`, `open_reminder`, `open_capabilities`)
  stand in for expensive schemas; the manifest names the door, never the tool behind it. A
  budget that drops a tool must **say so** in the tool output — silence explodes the context.
  A 429 arrives mid-stream. Pro gating is by omission from the schema.
- **Pasted link** — a model-written URL is untrusted: `_is_public_url()` rejects by the
  **resolved IP** (internal Railway services are reachable).
- **Photos** — chat pictures are URLs behind `[rasm:N]` tokens the model never sees as URLs;
  document pictures are bytes. The picker model must be **tile-based** (`gpt-4.1`; a
  patch-based one costs 23x). `[rasm:N]` is rewritten before it reaches history.
- **Failed vs rejected send** — retry plainer only on `OUTCOME_REJECTED`; a timeout may have
  delivered. Media sends get `RICH_MEDIA_TIMEOUT`.
- **Splitting / code fences** — `_safe_cut()` never cuts a link, footnote or fence; a rich-size
  part is re-split before the plain fallback. Fences become `<pre><code>` (Telegram Web
  cannot show them), but not on the plain fallback; >30 lines leave as a file.
- **Queue** — every path that sets `GeneratingState` wakes the queue in its `finally`.
- **Streaming** — one failed draft ping is not proof the draft is dead (`rich_draft_ok`).
- **Tool names / model list** — `INTERNAL_TOOL_NAMES` lists every tool, doors included;
  `GPT_MODEL`/fallbacks stay on OpenAI's free list (`test_free_models.py`).
- **Prompt** — per-user text never goes into `instructions` (kills the cache for everyone);
  run `test_prompt_rules.py` before and after any prompt edit; the `IMAGE_CAPABILITY_NOTE`
  overlap is deliberate.
- **Quotas** — `daily_limit()` is the single read point; `unlimited=True` never for Pro; a new
  counter is one `DAILY_COUNTERS` row + two columns.
- **Model output is untrusted** — validation lives in `db/database.py`; every model-indexed
  write carries `AND user_id = $N`.
- **Reminders / `/kunlik`** — a task reminder falls back to the plain one on any failure;
  `/kunlik` is capped at 4 hours; digest topics are caught as a **reply**, not RAM FSM.
- **Memory** — `_compress_old()` deletes raw rows only **after** the summary is saved; the
  summary model is a mini one; `/new` deletes the summary too.
- **Topics** — `_thread_key()` uses aiogram's own `is_topic_message`; a raw `bot.send_*`
  needs `mavzu_kwargs(thread_id)`; RAM records are keyed `(chat_id, thread_id)`; a topic is
  renamed **once** (the bot cannot read the name it overwrites).
- ⛔️ **Inline mode stays OFF** in @BotFather — with it on, guest mode stops working. Do not
  suggest enabling it.
- **Guest mode** — the final answer goes through `build_rich_markdown()`; no `<tg-thinking>`
  outside a private-chat draft; a timeout is not a rejection; status emoji come from the
  `holat4_by_<bot>` set.
- **Premium emoji, maps, buttons, tables, `$`** — the model writes markers, code emits the
  tags; a lapsed Premium rejects the whole message, so the downgrade rung strips them.
  `_compact_tables()` runs before maths; inline maths never takes `re.S`.
- **Editing a photo** — the bytes are never a tool parameter; `size="auto"` and
  `input_fidelity="high"` must stay.
- **Places** — the model gives an OSM tag, `_TURKUM_RE` validates it; an empty mirror never
  wins the race; "source down" (`PlacesUnavailable`) is not "nothing nearby".
- **What the model may claim** — the manifest is built from the real schemas and stays out
  of `instructions`; `open_capabilities` reads `capabilities.SECTIONS`, the same dict as `/help`.
- **Voice** — the status indicator cleans up in `finally`; ⛔️ never call the bot's Gemini
  TTS model for anything else (per-model quota); `clean_text_for_speech()` is the single gate.
- **Inline button styles** — only `primary` / `success` / `danger`; anything else rejects
  the message. The `/` menu is decoration — the real check stays in the handler.
- **Sandbox** — network closed (seccomp + `_qoriqchi.py`); `RLIMIT_DATA`, never `RLIMIT_AS`;
  `OPENBLAS_NUM_THREADS=1`; `deck` is mandatory for PPTX.

**`ADMIN.md`** — admin handlers and the database:

- **What is left in the bot** — `handlers/admin/` registers 21 handlers; registration order
  is functional; the admin check lives **inside** each handler (report is open to users);
  no `F.text ==` entry points. Anything written to `user_activity` must be in `ACTIVITY_TYPES`.
- **asyncpg types / `make_interval`** — `make_interval(days => $N::int)`, never
  `($N || ' days')`; `SUM()` over BIGINT needs `::bigint`; TIMESTAMPTZ comes back in UTC.
- **Migrations** — startup migrations must be cheap; `CREATE INDEX CONCURRENTLY` runs in
  `indekslarni_qur()` as a background task, with **no** parameters.
- **Five label maps** — `ACTIVITY_TYPES`, `AUDIT_ACTIONS`, `LIMIT_NOMI`, `SEGMENT_NOMI`,
  `TARIF_NOMI`: read the dict, never retype the list. Shared validators
  (`clean_promo_spec()`, `clean_referral_config()`, `_check_can_remove_admin()`) are never re-implemented.
- **Errors funnel** — every audit action is in `AUDIT_ACTIONS` (removed ones go to
  `AUDIT_ESKI`); `send_error_with_retry()` is the only place a user-visible failure is logged.

### Telegram Business

⛔️ **Read `BIZNES.md` before touching anything Business.** It holds every rule for
`handlers/biznes.py`, `handlers/biznes_uslub.py` and `handlers/biznes_media.py` (phases 1-5: the loop guard, the atomic
draft claim, "nothing technical reaches the customer", the customer path's own prompt, the
owner-style learning) and the planned next work. The four rules that break silently:

- `biznes_kimdan()` is the single loop guard and checks `sender_business_bot` **first**.
- History is keyed `(customer_chat_id, -owner_id)`; the DM queue wake-up skips negative keys.
- `biznes_yoriqnoma=` forces tools off, skips the owner's memory, and swaps `instructions`
  for `BIZNES_INSTRUCTIONS` — per-owner text only ever goes into a `developer` message.
- Menu (2026-09-30): `/biznes` is shown to **everyone** (a free user gets the status and
  /pro), `/mijozlar` to Pro only. Menu path and right names come from Telegram's official
  translations — see `BIZNES.md`; the guessed "Chatbots" was wrong in all three languages.
- Owner's task (2026-10-06): in the «💼 Biznes» topic the owner says "soat 8 da Xusanga salom
  deb yoz" and the `biznes_xabar` tool finds, asks and sends **on their behalf** — attached
  only there (Pro), `chat_id` checked against that owner's customer file, scheduled rows in
  `scheduled_tasks.biznes_kimga`. ⛔️ Telegram's 24-hour rule cannot be bypassed; a rejected
  send returns the text plus a `t.me/<user>?text=` link, never "sent". It can also list,
  delete and edit what **it** sent (`biznes_yuborilgan`, never the owner's own messages).
  The topic also gets a `[BIZNES HOLATI]` developer block (drafts, waiting chats, sent,
  scheduled — none of which is in the topic history), the text of a bot message the owner
  replied to, and can read a customer chat, edit Knowledge **by line number** and change
  settings. Every write (send / Knowledge / setting) is a proposal confirmed by "ha" in code.
- Instagram Direct (2026-10-15, `handlers/instagram.py`): the same pipeline, not a copy — a
  webhook message is shaped like a `Message` and fed to `biznes_xabar()`, and `_mijozga()`
  routes `ig:` connections to the Graph API. Customer chat id is `-IGSID`. ⛔️ Unsigned
  webhooks are rejected and the bot's own echo must not read as "owner wrote" (auto-pause).
  v2: photos/voice/story replies via `ig_media` → `biznes_media._ig_matn`, post comments →
  one private reply (`_izohlar`), ice breakers, `HUMAN_AGENT` only for owner-approved sends
  (`_mijozga(inson=True)`), every token call through `_api()` (code 190 → `_uzildi()`).
  Meta review texts: `META_REVIEW.md`.
  Meta app `3662254713943153`, Instagram app `1786464089226237`; published but **App Review
  not submitted**, so only accounts added under App Roles → Instagram Testers can connect
  (`uzchatgptai` is one). Opening it to everyone = Business Verification → Advanced Access
  for `instagram_business_basic` / `instagram_business_manage_messages`. The `comments` and
  `messaging_postbacks` webhook fields must be ticked in the Meta dashboard or v2's comment
  replies and ice breakers never fire. Meta sends webhooks as `v26.0` while
  `IG_GRAPH` is `v23.0` — works today, check it first if a Graph call starts failing.

### The bot moved to @vexonai; the old one only redirects

Since 2026-10-25 `BOT_TOKEN` is **`@vexonai`** and the old `@uzchatgptaibot` token sits in
`ESKI_BOT_TOKEN`; `handlers/eski_bot.py` polls it in the same process and answers everything
with one fixed "moved" message. Full rules: **`DEPLOY.md`** «The bot moved to @vexonai». The
ones that break silently:

- ⛔️ An old-bot Business **customer** gets nothing (it would land in the owner's name); only
  the owner is told, once. `pre_checkout_query` there is rejected.
- `ESKI_BOT_TOKEN == BOT_TOKEN` is refused — two pollers on one token starve the main bot.
- User-facing texts take the bot name from `pro.BOT_USERNAME` (fallback `'vexonai'`), never
  a hard-coded name.
- ⛔️ A new Business connection inherits the owner's settings
  (`database.biznes_telegram_almashdi()`); without it a reconnected owner sat in `buyruq`
  mode and customers got silence.
- The panel's «Ko'chish» card, `kochish_stats()` and `KOCHISH_VAQTI` are temporary — delete
  them together once the old bot is switched off. Keep the old token for months anyway:
  Stars from old payments refund only through it.
- Status animations come from `python assets/status_yasash.py`; a changed animation needs a
  new `_LOGO_BELGI` emoji, and ⛔️ never bump `_LOGO_TOPLAM`.

### The web admin panel lives in `WEB_PANEL.md`

⛔️ **Read `WEB_PANEL.md` before touching `web/`.** It holds every rule for the panel:
why it runs inside the bot process, the three auth layers, `web/api.py` having no SQL,
refund order, cache refresh on write, the phone/theme rules, `@bir_marta`, the alert
channel, the security headers and the plan-setting confirmation. The rules that break
silently, in one line each:

- `web/api.py` contains no SQL — every number comes from `db/database.py` (`test_web_stats.py` 8).
- A write that changes a cached setting refreshes the cache in the same request (`test_web_settings.py` 2, 8).
- Refund: Telegram first, then the database (`test_web_users.py` 9).
- Client IP is the **rightmost** `X-Forwarded-For` entry; `X-Frame-Options` must never be added.
- No `<table>` in the panel; every list is `.rows > .row`. Run `node --check` after any JS edit.

## Promo videos (not part of the bot)

Ads for the Business feature were made outside the repo, and **must not change the bot**:
Chrome renders the frames (`puppeteer-core` driving the local Chrome, a deterministic
`render(t)` in one HTML file), ffmpeg assembles them, the voice-over is Gemini TTS on a
*non-bot* model (see "Two free TTS engines"), music and effects are synthesised with numpy,
and the VO is checked by transcribing it back with `gpt-4o-transcribe`. Outputs are
`Desktop\UzBot_Biznes_reklama*.mp4`; the scripts lived in a session scratchpad and are gone.
Source clips from Gemini/Flow are large `.MP4` files — keep them out of git (`.gitignore`).
⛔️ `web/static/logo.jpg` is the **Vexon AI** mark since 2026-10-25 (`assets/vexon_logo.jpg` is the
full logo); before that it was the OpenAI mark, which must never appear in an ad. No paid video API
(Veo etc.) without the owner's explicit yes.

## Other agent configs

A Codex config exists at `~/.codex/config.toml`. Reply `/import` to scan and list what is importable (MCP servers, slash commands, subagents, skills, instructions), then `/import --yes=<digest>` — the scan output names the digest — to apply the user-level items.
