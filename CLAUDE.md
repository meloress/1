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
```

```bash
node --check web/static/panel.js        # panel JS sintaksisi
node --check web/static/soz.js          # panel lug'ati (u ham JS)
python -m compileall -q .               # butun daraxt kompilyatsiyasi
```

No test framework, no linter, no build step — but the panel's JavaScript has no test that
parses it, so `node --check` is the only thing standing between a typo and a blank screen
for every admin. Run it after every `panel.js` / `soz.js` edit. Each `tests/test_*.py` is a standalone `assert`-based script with numbered `print("[N] ... OK")` lines and a final summary. New tests follow that shape. On Windows, prefix with `PYTHONIOENCODING=utf-8` — some tests print emoji and the console codepage will otherwise raise `UnicodeEncodeError` (a false failure, not a real one).

Run the whole suite by looping over `tests/test_*.py`; `test_pro_security.py` is the slow one.

Some are structural guards rather than feature tests, and they earn their keep on refactors:

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
  `test_biznes_ekran.py` / `test_biznes_tejash.py` / `test_biznes_fakt.py` — Telegram Business,
  all offline. The loop guard (`biznes_kimdan` order), the atomic draft claim, "nothing
  technical reaches the customer", "the customer path never gets the assistant prompt", and
  "a `[tanlov:]` marker never reaches the other side". `test_biznes_owner.py` walks every
  `biznes_*` SQL with `ast` and fails without an `owner_id` filter. `test_olchov.py` guards the
  business JSON measurement log (no message text in it). ⛔️ **`tests/eval_biznes.py` is not a
  unit test** — it calls the live model; run it before and after any Business prompt edit.
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

Two things about `kod()` are load-bearing and both were paid for. It **preserves the
layout** — the first version rejoined tokens with `"\n"`, which turned `def admin_only(`
into three lines and broke *fifteen* test files at once, because nearly every guard
here works by finding a declaration and slicing to the next one. And it treats only a
**logical** line end (`NEWLINE`) as a statement boundary, never `NL`: counting `NL` made
it read the keys of a multi-line dict literal, and f-strings inside multi-line calls, as
docstrings and delete them. A docstring is replaced by `0`, not by nothing, so a class
whose whole body is a docstring still parses.

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
worker anyway — one process, HTTP and polling together (see the web panel section). Do not
add a second process type for it.

Verify a deploy landed without opening a browser: `railway status --json` →
`services[].serviceInstances[].latestDeployment.status` walks BUILDING → DEPLOYING →
SUCCESS, then `/` answers 200 and any `/api/*` answers **401** without a cookie — that
401 is the gate working, not a failure.

⚠️ Since phase 7 this is no longer cosmetic. "Empty means no menu button; the bot is
unaffected" was true while every admin screen still existed in Telegram — it does not any
more. With no domain, an admin has **only** `/xabar` and `/kod`: no statistics, no user
management, no limits, no journal. Deploying without the domain is not a degraded panel,
it is no panel.

⚠️ **`ssh-agent` is not running in this environment**, so a plain `git push` can fail
with `Permission denied (publickey)` even though the key is right there in `~/.ssh/`. The
key is loaded explicitly instead:
`GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes" git push meloress main`.
It failed exactly once mid-session after several successful pushes, so do not read a
failure as "the key is wrong" — try the explicit form first.

**`git push meloress main` deploys.** The Railway service is connected to GitHub, so a push to `git@github.com:meloress/1.git` (remote `meloress`) triggers the build by itself — no API call, no token. `origin` still points at `afiffamily/1`, where this account has **no write access** (403), so never push there.

Both the account and the remote moved on 2026-09-08; the GraphQL path below is history, kept only in case the GitHub connection is removed again.

- Without a GitHub connection, `git push` does *not* deploy and a plain deploy call rebuilds the snapshot taken when the service was created, i.e. old code. Deploys then have to name the commit explicitly:
  `serviceInstanceDeployV2(serviceId, environmentId, commitSha)` against `https://backboard.railway.com/graphql/v2` with a team token (`Authorization: Bearer`, and a real `User-Agent` — Cloudflare answers `403 error code: 1010` to the default urllib one). Railway fetches the commit from the repo, so **the service must point at the repo that actually has that commit, and it must be public**. The `up` endpoint (local tarball upload) fails on this account.
- Never ask for a token in chat. Have the user put it in `RAILWAY_TOKEN` and read it from the environment without echoing it.

### Reading production logs

The user is logged into the Railway CLI on this machine (`~/.railway/config.json`), so
logs are readable directly — no token, no copy-paste:

```bash
railway status
timeout 45 railway logs      # streams, never exits on its own — the timeout is required
timeout 60 railway logs -b   # build logs
```

⚠️ **`railway link` and `railway list` are broken on this account (CLI 4.6.3).** `list`
prints an empty list and `link -p <id>` answers *"not found in Melores's Projects team"*
for a project that is demonstrably there. The CLI asks for the deprecated `me { projects }`
field, which always returns empty — the same wrong query cost an hour here. The working
query is `me { workspaces { projects { edges { node { … } } } } }`, and the link has to be
written into `~/.railway/config.json` by hand, keyed by directory path. That file holds
`user.token`; never print it.

- workspace `Melores's Projects` `e4ee0499-8975-4fdb-a58d-3070e58dd692`
- project `truthful-prosperity` `ca061dfe-9a94-41a1-a135-9312e8fbfbc5`
- environment `production` `598aeb0b-1ff2-4a49-b055-44b39b9d764a`
- service **`1`** (this bot, `@uzchatgptaibot`) `d644a705-d075-440b-a68d-9fd21dcbd44b`
- the same project also runs `Melores-Bot`, `Hisobotchi-bot`, `Trello-bot`, `Web-panel`
  and several Postgres instances — ours is the one named `1`

**Which commit is live** comes from `deployments(input: {projectId, environmentId,
serviceId})` → `node.meta.commitHash` / `commitMessage` / `createdAt` (UTC; Tashkent is
UTC+5). Use it before concluding anything from a screenshot — a table complaint was
nearly misdiagnosed because it was unclear whether the fix had deployed yet.

The logs are the best source of work. Both of the largest problems found on 2026-09-10
came from reading them, not from guessing: the image picker burning 47 843 tokens on one
request, and a silent `asyncio.TimeoutError` (whose `str()` is empty) making the picker
fall back to unseen candidates.

### Token budget

The bot runs on a free daily grant (2.5M tokens/day for `gpt-5.6-luna`). Before the September 2026 work the OpenAI usage dashboard showed **20.307M input tokens over 8 days — 2.54M/day, i.e. 101% of the grant on an average day and 248% on the busiest one**, so the model was silently falling through `MODEL_FALLBACKS` and the excess was billable.

⚠️ **Caching does not reduce that count.** OpenAI support confirmed (2026-09-09) the complimentary allowance is a *token quota*, not a discounted rate: cached and uncached input count the same. Caching only changes money, which matters once you exceed the grant. So the only lever is fewer tokens per round.

Nearly all of it is fixed overhead, not user text. Measured with `tiktoken` (`o200k_base`) — never estimate from character counts, that was 11% off:

| | tokens |
|---|---|
| `instructions` (prompt + concise + image note) | 5 521 |
| tool schemas (Pro, all four doors closed) | 2 603 |
| capability manifest | 461 |
| **fixed total per round** | **8 585** |
| history | 0 → ~8 200, then capped by the summary (~300) |
| median user message | ~10 |
| median reply | ~70 |

That fixed total grew by 226 tokens on 2026-09-14/15 and both increases were deliberate,
paid for by a live bug: `internet_search` gained the `url` field (+136, reading a pasted
link instead of searching for it) and the capability manifest gained rules (4) and (5)
(+69/+86, after the whole manifest reached a user translated into Uzbek). Re-measure with
`tiktoken` after any schema or manifest edit — the table above is checked by nothing.

Those first three are what a round costs before the user has said anything. The Railway
log confirms it: sampled `[TOKEN]` lines run 7 697 (a free user, no `generate_image` or
`open_reminder`) to 16 304, and the whole spread is history — 3 of 10 sampled requests
carried ~8 000 tokens of it. **There is no hidden waste left.** History is the full reply
text, i.e. real context; trimming it is a quality decision, not a cleanup. Round 1
usually shows `keshdan 0 = 0%` and round 2 shows 90%+, which changes latency and money
but not the quota.

The input:output ratio is about 100:1, so `max_tokens` and stop sequences save nothing — output is already tiny. And a searched request runs **~1.7 rounds**, each re-sending the whole prefix, so every token removed from the prefix is saved that many times over.

`_log_token_usage()` in `services/ai.py` prints `[TOKEN] … kirish=… (keshdan … = NN%)` for every round and **also writes the round to `user_history`**, which is what the panel's token card reads — see the web-panel section. The cached share is visible in both even though it does not reduce the quota.

Measure before optimising. The bot's own Postgres answers most questions — how many requests a day, how long replies are, how often a tool actually fires. Two guesses were wrong that way: model routing looked like a big win until `pick_reasoning_effort` turned out to classify only 3-4% of real messages as trivial (and length is a terrible proxy: "Manga Toshkent … kontrakt narxlarini ber" is 66 characters and needs a full web search), and trimming fetched page text looked worth 10% until a live search measured 1 877 tokens, not 4 000.

The cached prefix is **instructions + the tool schemas**, and OpenAI documents *changing the tools available mid-conversation* as a cache-miss cause. Two consequences. `prompt_cache_key` is set in `build_request_params()` per **plan**, never per user — the prefix is identical for everyone on a plan, and a per-user key would have ten active users each warming a private cache. And the tool loop rebuilds `active_tools` every round, dropping tools whose budget is spent, so rounds 2 and 3 of a searched request send a different prefix and start cold. Making the array stable would fix that, but the drop is also what forces the model to stop calling a spent tool, and one wasted round re-sends the whole context (~12k tokens) while the cache would only save part of it — so measure the `keshdan` percentage on multi-round requests before touching it.

`PROMPT_CACHE_RETENTION = "24h"` exists in `core/config.py` and is deliberately off: it fits a day-precision prefix perfectly, but cache **writes** cost more and OpenAI does not document how the complimentary daily grant counts them.

## Architecture

`BOT_API_103.md` is the long-form companion to this file: everything added with Bot API 10.3 and after, explained in full — including the decisions that were **tried and reverted** (the interim "preparing your file" message, the sources slide). Read it before re-attempting anything in that area; this file only carries the rules.

`REJA.md` is now the **Telegram Business** plan (phases 0-4); the rules as built and the next work are in **`BIZNES.md`**. The **web admin panel** plan it used to hold — the reasoning behind each architectural decision, what each phase changed, every departure from the mockup — lives in git: `git show 3ba4744:REJA.md`. Every `REJA.md 3.1` / `3.2.1` / `4-bo'lim` reference in code comments points at that version. Read it before touching `web/`.

### Handler registration order is a safety constraint

`main.py` registers handlers in a deliberate order and each position is justified in a comment. The critical ones:

1. `successful_payment` / `pre_checkout_query` go on `dp.message` **directly**, before any router. `handlers/messages.py` has a `GeneratingState.generating` spam-guard with no content filter; if a payment lands while a reply is streaming, that guard would swallow it — money taken, Pro not granted.
2. FSM states (gift, promo, digest, broadcast) come before the AI handlers so a user's answer to "kimga sovg'a qilay?" is not sent to GPT as a question.
3. `maintenance_gate` sits before the AI handlers but after `/start` and `/profile`; `/pro`, `/promo`, `/gift` sit *after* it — selling a subscription for a disabled bot is a refund source.
4. `generating_state_router` is included before `general_router` so a message arriving mid-reply does not start a second parallel request.

Do not reorder these without reading the comments.

### The stop button needs two things aiogram won't do for you

`sendRichMessageDraft(can_stop=True)` makes Telegram send a `stopped_message_generation` update. aiogram 3.31.0 knows that type, so `main.py` registers a plain `@dp.stopped_message_generation()` observer that maps `event.draft_id` → `handlers.messages.request_stop()`. Registration order does not matter — the observer does not touch the `dp.message` chain.

`allowed_updates` therefore needs no manual patching: `dp.resolve_used_update_types()` finds the type from that handler. Both workarounds this used to need (an `outer_middleware` catching the update before `event_type` resolved it, and appending the type by hand) were removed with the 3.29 → 3.31 upgrade; `tests/test_bot_api_103.py` check 39 guards that the resolver really lists it.

⚠️ 3.31 turned the 10.3 fields `InlineKeyboardButton.disabled` and `InlineKeyboardMarkup.force_reply` into **real model fields** — they used to live in `model_extra`. Anything reading them must check both, `pro._downgrade_kb()` included: reading only `model_extra` there dropped `disabled` from the fallback keyboard, producing a typeless button that gets the whole message rejected.

Drafts are private-chat-only (API limit); `sendRichMessage` is not. `process_stream_draft` keeps those two as separate flags (`using_rich_draft` vs `can_send_rich`) — merging them again would strip tables, collapsed sources and images from every group answer.

### The tool loop (`services/ai.py`)

`get_openai_reply()` streams from the Responses API and runs a tool loop with **per-tool round budgets** (`MAX_SEARCH_ROUNDS`, `MAX_FILE_ROUNDS`, `MAX_IMAGE_ROUNDS`, `MAX_MEMORY_ROUNDS`, `MAX_REMINDER_ROUNDS`, `MAX_NEARBY_ROUNDS`, plus `MAX_TOTAL_ROUNDS`). When a budget is spent the tool is dropped from `active_tools`, forcing the model to answer.

Tools: `internet_search`, `run_python_sandbox`, `generate_image`, `edit_image`, `update_memory`, `manage_reminder`, `find_nearby`. Three of them are reached through a cheap door (`start_file_task`, `open_memory`, `open_reminder`) — see below.

⚠️ **`open_capabilities` is a fourth door of a different kind**: it attaches nothing, it
*returns* the answer (the bot's feature list plus the reader's plan) and the model writes
from that. Same economics — 211 tokens every round, 2 214 only when called — but it does
not turn a mode on, so it has no `_mode` flag and it caps itself at one call. See "What
the model may claim it can do".

**Three tools are attached in two steps, and that is a token decision.** A cheap
"door" is always attached; the expensive real schema arrives only on the round after the
model opens it. `start_file_task` 212 → `run_python_sandbox` 5 578; `open_memory` 248 →
`update_memory` 764; `open_reminder` 212 → `manage_reminder` 772. Measured with
`tiktoken`. The door costs one extra round on the small fraction of requests that use the
tool, and saves the difference on every round of every other request — memory was used in
13 of 1 210 measured requests and the reminder tool in **none**, while `update_memory`
was attached to every DM request and `manage_reminder` to every Pro one. Opening a door
does **not** consume that tool's round budget (`memory_rounds` increments only on the
real call), or opening it would eat the budget the actual write needs. Each door needs
its own `elif` above the bare `else`, and `_capability_manifest()` must name the *door*,
never the tool behind it.

**The file tool's own numbers.** `run_python_sandbox`'s description is the whole layout manual — **5 578 tokens** measured with `tiktoken` — and the model writes the code *inside* the call, so the manual cannot move out of the schema. But `file_task_enabled` is `output_files is not None`, i.e. every DM request, while the tool is actually called in 1.4% of them (17 of 1 210 measured). So a **212-token** `start_file_task` door is attached instead; when the model calls it, `file_mode` turns on and the full tool arrives on the next round. That saves **5 366 tokens per round** — and a round is re-sent in full each loop iteration, so the real saving is that times the round count. The cost is one extra round on the 1.4%. `file_mode` stays on for the rest of the request because the file loop retries up to four times. Two things must hold: `start_file_task` needs its own `elif` above the bare `else` (otherwise "make me a presentation" becomes a DuckDuckGo query), and `_capability_manifest()` must name the tool that is *actually attached* — naming `run_python_sandbox` there would have the model call a tool it does not have.

**Dispatch order matters**: the `else` branch routes any unknown tool name to web search, so every named tool must be an `elif` *above* it — otherwise "menga rasm chiz" silently becomes a DuckDuckGo query.

**A tool that quietly returns nothing is how the context explodes.** Images are searched once per request — re-running would shift catalogue numbers under a `[rasm:2]` the model has already written — but the repeat call still re-emits the same catalogue. Returning silence taught the model "no images found", so it searched again, and again; each round appends full page text, and by round three the request hit OpenAI's 200k TPM ceiling and the whole answer was lost after 50 seconds of work. Any budget that drops a tool must say so in the tool output.

`RateLimitError` arrives **mid-stream**, not when the stream opens: the SDK sends the request on the first iteration, so `_open_response_stream()`'s fallback ladder never sees a 429 and the answer died outright. The round is retried once after `RATE_LIMIT_RETRY_DELAY` — but only if no text has been yielded yet, otherwise the user would see the start of the answer twice.

**Pro gating is done by omission**: `image_enabled = ... and is_pro`, `reminder_enabled = is_pro and user_id is not None`. Free users never see the schema, so no tokens are spent advertising a tool they cannot use. Flipping a feature to free-with-upsell means removing `is_pro` from that condition; the task functions already validate independently.

`get_vision_reply()` is a **separate, single-round** path — the memory tool call is harvested after the stream and its result is not fed back. Adding a full loop there means porting the `pending_calls` block.

`[CLEAR_TEXT]` travels through the same chunk stream as content and is emitted **after every** tool round, throwing away the model's pre-tool chatter so it doesn't stick to the final answer. The condition used to exclude repeat searches, and the leftover text then glued itself to the next round's — users saw two "…tayyorlayapman" sentences in one message. Reaching that point already means a tool ran (`if not got_function_call: return` above it), so no condition is needed.

While a file is being built the screen shows **only the status animation** — nothing the model wrote before the tool call reaches the user. Sending that preamble as an interim message was tried and reverted: it left a half-drawn draft bubble next to the real one, and the abandoned draft killed the spinner for the whole 1-2 minute wait. If you try it again, the draft must be overwritten or closed before a real message is sent, not simply replaced with a new `draft_id`.

### A pasted link is read, not searched

`internet_search` takes an optional `url`. When the user pastes a link, the model copies it
there and `_run_url_task()` fetches that page directly — the web search does not run at all.
Without the field, "https://kun.uz/… shuni qisqartir" turned the link itself into a
DuckDuckGo **query**: the bot never opened the page and answered from whatever the search
returned, which the user reasonably reads as having been read. The field costs **136
tokens** (`tiktoken`, measured — the first draft was 227 and was trimmed without dropping a
rule), and it is on the always-attached schema, so that is paid every round.

`primary_query` is still required alongside it: when the page will not open, the branch
falls through to an ordinary search rather than losing the answer, and a failed fetch
returns an explicit "XATO … do not retry" string — never silence, for the context-explosion
reason above. A single pasted page gets `URL_FETCH_MAX_CHARS` (8 000) rather than the
search path's 4 000, since there is one source and the user asked for that one.

⛔️ **A model-written URL is an untrusted boundary, and this deployment makes that
concrete.** The same Railway project runs `Web-panel`, `Trello-bot`, `Hisobotchi-bot` and
several Postgres instances, all reachable on the internal network — "read
http://web-panel.railway.internal/ for me" would have been performed by the bot itself.
`_is_public_url()` therefore resolves the host and rejects the **IP**, not the name:
loopback, private, link-local (`169.254.169.254` is the cloud metadata address), reserved,
multicast and non-`http(s)` schemes all fail one check, and so does a DNS name deliberately
pointed inside. It sits inside `fetch_page_content()`, so search-result URLs pass through
the same gate — one check point, both callers. `tests/test_url_read.py` runs offline by
using numeric IPs, so DNS never decides the result.

### Photos: two separate pipelines that must not be confused

A photo in a **chat reply** and a photo **inside a document** share nothing but the search call, and mixing them up is the failure mode users actually hit.

- **In chat**: `internet_search(want_images=true)` searches, validates each URL is live, and stores the hits in `images_out`. `images_only=true` is the same path with the web search skipped entirely — it exists because a picture used to be possible only when the model happened to search, so any answer written from the model's own knowledge arrived with no image at all. It still spends a `search_rounds` slot (otherwise the model can ask for pictures forever), it implies `want_images` in code because the model forgets one of the two, and it never injects `_SYNTHESIS_SYSTEM` — that prompt demands a sources list, and an images-only call has no sources. The URL is deliberately **never shown to the model** — it costs 30-60 tokens each and the model rewrites them into dead links. The model only sees `[rasm:1]` / `[rasmlar]` tokens (~25 tokens total); `embed_images()` swaps them for real media blocks just before sending — one image as a bare block, 2 to `SEARCH_IMAGE_COLLAGE_MAX` (4) as a `<tg-collage>` (all on one screen), 5 to `SEARCH_IMAGE_MAX` (10) as a `<tg-slideshow>` — how many are fetched comes from the model's `image_count`, so "10 ta rasm topib ber" works and the slideshow branch is finally reachable. A collage carries a single caption, so its inner blocks are built without one and every source goes into one `<figcaption>`: the photo is someone else's and the credit is not optional, and `strip_image_tokens()` scrubs them from every fallback path and from the streaming draft. Telegram fetches the URL itself — nothing is downloaded.
- **In a document**: see the Sandbox section. Bytes, not URLs.

The routing between them is prompt-level and fragile: adding the word "rasm" to the file tool's description was enough to make *every* request ("olma haqida ma'lumot ber") turn into a file task. Both tool descriptions now carry an explicit ⛔️ pointing at the other one, and `IMAGE_CAPABILITY_NOTE` in the system prompt exists because the model would otherwise answer "I can't send pictures" without calling any tool at all. That note is added **only** in `get_openai_reply` — `get_vision_reply` has no search tool, so promising it there would be a lie.

**The model picks the photos by looking at them.** `search_images()` gathers ~20 candidates, checks they are live, and then hands the thumbnails to `SEARCH_IMAGE_PICK_MODEL` (`gpt-4.1`, `detail: "low"` = 82 tokens each) in **one** call together with the user's actual request; the picker returns the indices it wants plus a short Uzbek description of each. That description is what makes "what colour is the car in the first photo" answerable, and it is deliberately written from the image, not from the request. The picker runs on a **different model from the main answer**; if it fails for any reason the first N candidates are used, i.e. the old behaviour, so a picture is never lost. An empty pick is a valid answer — an unrelated photo is worse than none.

⛔️ **The picker model must be tile-based, and that is a 23x decision.** `detail: "low"`
is honoured only by tile-based models (gpt-4o, gpt-4.1, gpt-5, gpt-5.1), where it means
~85 tokens regardless of image size. Patch-based models (gpt-4.1-mini, -nano, o4-mini)
**ignore `detail` entirely** and bill 32×32 patches times a multiplier. This was live:
with `gpt-4.1-mini` a single image request logged **47 843 input tokens** (22 candidates,
~2 175 each) and a 34-candidate request blew through `SEARCH_IMAGE_PICK_TIMEOUT` and fell
back to the unseen first-N. Measured on one live URL at `detail: "low"` (2026-09-10):

| model | tokens/image |
|---|---|
| gpt-4.1 | **82** |
| gpt-5-mini / gpt-5.4-mini | 1 390 |
| gpt-4.1-mini | 1 878 |
| gpt-4o-mini | 2 830 |

`tests/test_image_pick.py` checks 31-33 guard the model choice, its presence in the free
list, and the candidate count times the per-image cost. Note also that
`asyncio.TimeoutError` has an **empty** `str()`, so the failure log used to end in a
colon and say nothing; it now falls back to the exception class name and prints the
candidate count.

**Commons and `ddgs` are both queried and merged**, Commons first. It used to be Commons with `ddgs` as a fallback, and that is what produced the worst live bug: Commons is a free-licence encyclopedia archive with no tuning photos, so "BMW 540i tuning body kit" returned nothing, `_images_sync()` shortened the query until Commons *did* answer, and the user got the plain "BMW 540i" shots back — the same four, every time, however they refined the request. The fallback never ran because Commons always answered something. On the server DuckDuckGo's image endpoint answers `403` (datacenter IP) and `ddgs` silently switches to Bing, whose results can be unrelated ("Hongqi H5 Classic" once returned Roblox avatars) — that is now the picker's job to reject, not a filter's.

Query shortening is the **last resort**, not the first: only when *both* sources come back empty does `_images_sync()` walk the query down to 3 words, then to 2. Both steps are needed — "Hongqi H5 new model" trimmed to 3 is still "Hongqi H5 new", which also returns nothing. `_title_stem()` collapses "BMW 540i (G30) China", "… (2)", "… (3)" into one candidate: they are frames of a single shoot with different URLs, so URL dedupe alone handed the user one picture four times. URLs already sent in this chat (`core/memory.py::recent_sent_images`, cleared by `/new`) are dropped too — a repeat request must return something new or say so honestly. And `upload.wikimedia.org` is in `_TRUSTED_IMAGE_HOSTS`, so its URLs skip the liveness probe entirely: the API already guarantees they exist, while ten parallel probes earn a `429` that made live images look dead (10 candidates collapsed to 1).

The query itself is separated too. A web query is written for articles (`site:`, long phrases, figures) and is useless against an image index, so `internet_search` takes an optional short English `image_query`, and `image_query()` strips operators and bare numbers from the fallback — but **not four-digit years**: "Hongqi H5 2025" and "Hongqi H5" are different cars, and dropping the year is how a request for the new model kept returning the same old photo. `_image_relevant()` then requires one meaningful query word in the title/URL/source — when nothing matches, **no image is sent at all**, because an unrelated photo on a slide is worse than an empty one.

`[rasm:N]` is valid **only inside the reply that produced the catalogue**, so `safe_update_history()` rewrites it through `image_tokens_to_history()` before anything reaches `chat_messages` — the token becomes `[yuborilgan rasm: <description>]`. A raw token left in history reads to the model as still-live: on "rasm yubor" it would re-emit `[rasm:1]` instead of calling the tool, `embed_images()` would silently drop it, and the user got an empty answer. Deleting it outright was the other extreme — the model then had no idea what it had sent. Keeping the description costs ~15 tokens per image and is what lets it answer questions about a photo it already sent. Both the catalogue text and `IMAGE_CAPABILITY_NOTE` say outright that a link never substitutes for a picture and that every repeat request needs its own search.

Image search runs with `safesearch="on"` (`SEARCH_IMAGE_SAFESEARCH`); the library default `moderate` was not enough for a bot with no age gate.

### A failed send is not the same as a rejected send

`_telegram_api_request` reports *why* a call failed through an `outcome` out-param: `OUTCOME_REJECTED` (Telegram answered `ok:false`) versus `OUTCOME_UNKNOWN` (timeout, connection reset). The rich-message fallback ladder retries in a plainer form **only** on REJECTED. On UNKNOWN it gives up silently, because the message may well have arrived.

This exists because the shared aiohttp session caps every call at 10s — right for the 0.6s draft pings it was tuned for, wrong for a rich message carrying image URLs, since Telegram fetches each image from the source site before it creates the message. The client timed out, the ladder concluded "rejected", re-sent without images, and Telegram delivered both: users saw the same answer twice, once with photos and once without. Media sends now get `RICH_MEDIA_TIMEOUT` instead.

### Splitting a long answer must not cut a construct in half

`_split_for_telegram()` breaks answers at a limit that depends on the send path — `MAX_RICH_CHARS` (30000, rich messages cap at 32768) or `MAX_PLAIN_CHARS` (4000, `sendMessage` caps at 4096) — and the cut point lands wherever the last newline or space happens to be. Three constructs cannot survive that cut and are handled explicitly: an open code fence is closed and reopened with its language on the next part, and `_safe_cut()` moves the boundary *before* a markdown link and *before* a footnote pair. Splitting `[OLX Uzbekistan](https://…)` in the middle leaves both halves as literal text — that is how a sources list once reached a user as `• [OLX` followed by `Uzbekistan](https://…)`. A footnote is the same shape with its halves far apart — `[^1]` sits in the text, `[^1]: …` at the very end — so `_safe_cut()` takes the whole remaining text, not `rest[:limit]`, or the definition beyond the limit would be invisible to it. Anything else added to answers with paired syntax needs the same treatment. `==marked==`, `<sub>`/`<sup>` and `- [ ]` need no code at all: Telegram renders them and `build_rich_markdown()` passes them through untouched — they are prompt rules only.

A collapsible section is the one construct the model does not write itself: it writes `[batafsil: Title] … [/batafsil]` and `build_rich_markdown()` turns the pair into `<details>`, inside `_protect_spans()` so a marker in a code block stays text. Same reason as `[rasm:N]` — a malformed marker is dropped, malformed HTML gets the whole message rejected. An unpaired marker is therefore discarded, and a nested one is flattened. A pull quote works the same way: `[iqtibos: the words | who said them]` becomes `<aside>…<cite>…</cite></aside>`, the author half optional. Markdown is not parsed inside `<aside>` (only `<details>`, `<tg-collage>` and `<tg-slideshow>` parse it), so both halves are html-escaped there — unlike a `<details>` body, which stays markdown. The draft and the plain fallback are not rich, so `strip_rich_tokens()` renders both markers as plain text there (bold heading, «quoted» line); it sits beside `strip_image_tokens()` at the same two call sites.

A part cut to the rich size cannot be handed to the plain fallback as-is: when a rich message is rejected, the part is re-split with `MAX_PLAIN_CHARS` before `_answer_plain()`. Skipping that loses the whole answer — worse than the small limit it replaced. `push_update()` likewise trims the draft (rich) and the plain waiting message to different limits, since the draft can degrade to the latter mid-stream.

### A code fence in the `markdown` field breaks Telegram Web

Telegram turns ` ``` ` in a rich message's `markdown` field into the new **copyable code block** content type, which Web-K reports as `messageMediaUnsupported` — the reader sees "This message is not supported on Telegram Web" *instead of the whole answer*. Mobile and desktop render it fine, so this only shows up on the web client. `code_fences_to_html()` (`services/ai.py`) rewrites every fence to `<pre><code class="language-…">`, which is plain text plus `MessageEntityPre` and renders everywhere. It is called from `_protect_spans()` (so the later table/date/emoji passes never see the code), from the streaming draft, and from the two guest rich payloads — but **not** on the plain `text` fallback, which goes out with `parse_mode="Markdown"` and needs the fence intact.

Code longer than `LONG_CODE_LINES` (30) leaves the message entirely: `_extract_long_code()` pulls it out, `_send_output_files()` sends it as `kod_1.py`, and the text keeps a one-line note. The **original** text with the code still goes to history (`history_text`), otherwise "now change that code" would have nothing to work with.

### One request per user, and messages queue instead of vanishing

Telegram splits a message over 4096 chars into several updates, so every incoming text goes through the debounce buffer in `core/memory.py` (`text_merge_buffers`, per-chat `asyncio.Lock`) and is merged after `TEXT_MERGE_WAIT` (1.5s) — joined with `"\n"`, since the parts may equally be separate messages. The old "short first message goes through instantly" shortcut was removed: it turned three quick messages into three independent requests, the first of which then locked out the other two.

While a reply is generating, `busy_handler` (`GeneratingState.generating`) **appends to that same buffer** and `_process_merged_text`'s `finally` block starts it once the state is cleared — order matters, or the queued message re-enters the busy state and loops. Commands and media keep the old "please wait" behaviour: a queued `/pro` would be sent to GPT as a question. `TEXT_MERGE_BUFFER_TTL` is 600s because the buffer now has to survive a whole generation, not just a 1.5s timer.

`_next_or_stop()` enforces `STREAM_IDLE_TIMEOUT` (180s) — an **idle** limit, not a total one. A file task or a deep research legitimately goes minutes without emitting a chunk, and a total budget would kill exactly the work that needs it. On timeout a partial answer is still delivered (with a note); with nothing at all it raises, and the caller's existing `except` gives the user a clean error plus the retry button and refunds the points.

### Live streaming: what a rejected draft means

`push_update()` writes the accumulating answer to a `sendRichMessageDraft`, throttled to `PUSH_INTERVAL` (1.0s) **and** `PUSH_MIN_CHARS` (100) — with the first chunk forced through, because the wait is felt at the start. Editing per chunk earns a 429 and freezes the stream.

A failed draft ping is **not** proof the draft is unusable. `rich_draft_ok` records whether any draft (animation frame or content push) ever succeeded: if one has, a rejection is treated as a temporary flood-wait and retried (`RICH_DRAFT_FAILURE_LIMIT`); if none ever has, the path is abandoned immediately so the user gets the plain waiting message without delay. `_edit_message_fallback()` handles `TelegramRetryAfter` itself instead of swallowing it with every other exception.

The status animation is **restarted** when a `[STATUS]` chunk arrives after text has already streamed — the model often writes "let me search…" first, which stops the animator, and the screen then sat frozen on stale text for the 20-60s the tool ran. `/research` has its own eight-stage status list; `[STATUS]search` from inside it must not overwrite it.

### The model must not name its own tools

The system prompt has a `CONFIDENTIAL` section, but a prompt rule is not a guarantee — in a live test the bot correctly refused to print the system prompt and then listed `internet_search`, `run_python_sandbox`, … anyway. `strip_internal_names()` (`services/ai.py`) is the second layer: it replaces the real names from `INTERNAL_TOOL_NAMES` (`core/config.py`, the single list) with neutral Uzbek descriptions, on the final text, on the streaming draft, and in the guest path. It deliberately scrubs code blocks too — "list your tools as a python list" is exactly the way around it. `tests/test_no_tool_leak.py` asserts the list matches the actual tool schemas, so a new tool fails the test until it is added.

The prompt also carries a phishing/social-engineering section that fixes the *shape* of the answer (fake placeholders, a visible simulation label, red flags instead of a ready-to-send message) while explicitly forbidding over-refusal of ordinary security questions. `tests/test_safety_prompt.py` only guards that the section still exists — the wording is not asserted.

### The prompt is sent whole on every round, so duplication is expensive

The free daily grant counts tokens, not requests, and caching does not reduce that count (OpenAI support, 2026-09-09) — so anything in `instructions` is paid for on **every round of every request**, and a searched request runs ~1.7 rounds. Measured with `tiktoken` (`o200k_base`), not estimated: instructions 5 521 tokens, tool schemas 2 603, capability manifest 461.

`STRICT_MATH_RULES` used to be appended after the whole prompt and was a near-verbatim copy of the template's own `MATH, PHYSICS & CHEMISTRY` section — nine rules stated twice, side by side in one string, 274 tokens per round. It is gone; the two phrases that were unique to it ("This is a hard requirement", "There are no other acceptable delimiters") were folded into the section that remains. `CONCISE_INSTRUCTION` likewise lost the three sentences that repeated `OUTPUT CONTRACT` rule 4.

`tests/test_prompt_rules.py` is the guard: it asserts 60 individual rules are still present in the assembled `instructions`, whichever section they live in. Run it before and after any prompt edit — it was written *before* the deduplication and passed identically after, which is what made the change safe to ship. A mechanical cross-block similarity scan found no other duplication above 60%, so there is no more fat of this kind; further shrinking means rewriting prose, which is a quality decision, not a cleanup.

⚠️ The scan cannot see across languages: the tool descriptions are Uzbek and the prompt is English, so `IMAGE_CAPABILITY_NOTE` overlaps `internet_search`'s `want_images` / `images_only` descriptions without any lexical match. That overlap is deliberate and bug-paid (the model used to answer "I can't send pictures" without calling anything) — do not "deduplicate" it.

### Prompt caching constrains where text goes

`build_system_prompt()` is written to day precision so the prefix is identical all day and prompt caching works. Anything per-user (long-term memory, the user's name) goes into `messages` as a `developer` message, **never** into `instructions`. Putting user-specific text in the system prompt silently destroys the cache for everyone.

### Model list is a billing guard

`INTERNAL_TOOL_NAMES` (`core/config.py`) must list **every** tool name, doors included —
`strip_internal_names()` scrubs exactly those strings, so a name missing from it leaks.
`tests/test_no_tool_leak.py` used to compare against a hand-written tuple of schemas and
silently rotted: `start_file_task`, `find_nearby`, `open_memory` and `open_reminder` were
all missing from the list and the test still passed. It now walks the `services.ai`
module for every `{"type": "function"}` dict, so a new tool fails it until it is added.

`GPT_MODEL` and `MODEL_FALLBACKS` must stay inside OpenAI's free data-sharing list. A model outside it bills at full price and nothing warns you — the bill arrives at month end. `tests/test_free_models.py` guards this.

### Quotas: two independent systems

- **Points** (`check_and_consume_quota`) — the daily budget; cost varies by message kind and reasoning effort (`message_cost()`).
- **Daily counters** (`DAILY_COUNTERS` → `check_and_consume_daily`) — separate counts for `files`, `images`, `research`. These are the expensive operations; billing them to the points budget meant three files exhausted a user's whole day and read as "the bot broke".

`services/file_task_quota.py::DailyQuota` charges **once** per user request no matter how many times the model calls the tool, and refunds if nothing was produced.

`unlimited=True` means "nothing was deducted, do not refund" (admin/premium). Returning it for Pro would break every refund guard — `tests/test_plan_limits.py` asserts this.

Adding a new counter = one row in `DAILY_COUNTERS` + two DB columns. Nothing else.

`daily_limit()` in `core/config.py` is the **single read point** for every limit — quota code, the file/image/research counters and the admin screen all go through it. That is why the admin-editable limits sit there as an in-memory `_LIMIT_OVERRIDES` dict rather than a DB read: `daily_limit()` runs on every message. `bot_settings.limit_overrides` (JSONB) is loaded once at startup via `apply_limit_overrides()` and refreshed when an admin changes a value; `NULL`/missing means "use `PLAN_LIMITS`", so an unconfigured bot behaves exactly as before and needs no migration. Anything that reads `PLAN_LIMITS` directly bypasses the override and will silently disagree with the panel.

### Model output is an untrusted boundary

Whatever the model writes into a tool call reaches the database. Validation lives in `db/database.py`, never in the tool `description` — an instruction is not a guarantee:

- `clean_memory()` strips newlines (a multi-line memory renders as fake instructions in the developer message) and rejects card/passport/account number patterns.
- `parse_run_at()` rejects past times, unparseable strings and dates beyond `REMINDER_MAX_AHEAD_DAYS`.
- Every `UPDATE`/`DELETE` driven by a model-supplied index carries `AND user_id = $N`; the index is bounds-checked against the list actually shown to the model *before* touching the DB (note `isinstance(idx, bool)` — `True` is an `int` in Python).

### Two kinds of memory

- **Conversation history** (`db/history.py`, `chat_messages` table + RAM cache) — context. Keyed on `(chat_id, thread_id)`, see the Topics section. Stored to `CONTEXT_WINDOW_PRO` for everyone; the tariff only changes how many are *read* (free 30, Pro 80 — they were 50/150 and were cut for token cost), so switching plans needs no migration. `/new` clears this.
- **Compressed tail** (`chat_summaries`, one row per chat) — what fell out of the 80-message window. It used to be plain `DELETE`: a long conversation lost its beginning permanently and the bot never said so, which reads as "the bot forgot me". Now the rows are summarised before they go.

  ⛔️ **Order is the safety property.** `_compress_old()` fetches the summary, saves it, and deletes the raw rows **only after** that succeeded. `summarize_history_chunk()` returns an empty string on any failure — never raises — and an empty string means *keep the rows and retry on the next message*. Written the other way round, the fix would reproduce the very bug it repairs. `HISTORY_HARD_LIMIT` (200) is the backstop: if summarising stays broken the table would grow forever, so past that point the old unsummarised trim returns.

  Compression runs in a background task (the user's reply must not wait on it), batched at `HISTORY_SUMMARY_BATCH` (20) so the model is called once per 20 messages rather than on every message past 80, and guarded by a per-chat `asyncio.Lock` — two quick messages would otherwise both summarise the same rows.

  ⚠️ `HISTORY_SUMMARY_MODEL` is deliberately a **mini** model. OpenAI's free allowance is two separate buckets: big models ~250k tokens/day, mini ~2.5M — ten times larger (`tests/test_free_models.py` holds both lists). Summarising is mechanical work; taking it from the big bucket would eat the room the actual answers need. `tests/test_history_summary.py` check 14 pins this.

  The summary reaches the model as a `developer` message placed **before** the raw history — it is the older part, and appended after it the model read it as the latest thing said. It must stay out of `instructions` for the usual reason: per-user content there poisons the prompt cache for everyone. The wrapper text tells the model the block is compressed and not to quote it; without that it said "you told me…" and quoted a summary line as if verbatim.

  `clear_history()` deletes the summary too. Without that `/new` would be a lie — the user is told the history is cleared while the bot keeps using the compressed version.

  `chat_summaries.covered` counts how many messages have ever been compressed away. It
  only grows, while the raw row count falls back after every compression — which is why
  the "this conversation is long" hint (`HISTORY_LONG_WARN_AT`) is measured against
  `covered` and not against `COUNT(*)`, a number that never reaches the threshold.
  `_compress_old()` sets a RAM flag when it crosses, and `take_long_warning()` takes it
  once; the reply path must not pay a DB query for a hint.

  On token cost, be honest about the shape: measured on a live call, 7 short messages summarised to 91 tokens against 88 raw — i.e. **no saving at all on short exchanges**. The win is that raw history grows without bound (the Railway log shows 0 → ~8 200) while the summary is capped at `HISTORY_SUMMARY_MAX_CHARS` (1 200 chars ≈ 300 tokens). It is a ceiling, not a discount, and the primary reason to have it is that the conversation stops being lost.
- **Long-term memory** (`user_memories`) — facts the model chose to keep, category-prefixed (`ism:`, `kasb:`, …). Survives `/new`. Available on every tariff.

History used to live in SQLite; Railway wipes the container filesystem on every deploy, so each deploy reset every user's context. It is Postgres now — do not move it back to a file.

### Topics: one chat, several conversations

Telegram allows forum topics **inside a private chat** (Bot API 9.4), and each topic is
a separate conversation. So the history layer is keyed on `(chat_id, thread_id)`, not on
`chat_id` — `thread_id = 0` means "no topic", which is exactly what a bot with topic
mode off produces, so nothing changed for existing chats and existing rows migrated to
`0`.

`thread_id` is a **default argument** on every history function and on
`get_openai_reply` / `get_vision_reply` / `get_gpt_reply`. That is what kept the change
small: only the five reply paths in `handlers/messages.py` pass it, everything else
(guest, digest, helpers) keeps working untouched.

⚠️ **`_thread_key()` must match aiogram's own condition, exactly.** aiogram fills
`message.answer*()` with `message_thread_id if is_topic_message else None`, so the helper
uses the same test. Two different conditions and the reply lands in one topic while its
history is written to another — the bot then cannot see its own last answer, nothing
raises, nothing logs, and the user reads it as "the bot isn't listening". A forum
group's General thread is the case that separates them: it carries a
`message_thread_id` but `is_topic_message` is `False`.

`message.answer()`, `answer_voice()` and `answer_document()` therefore need **no code at
all** — aiogram routes them. The raw `bot.send_*` calls do not, and
`_send_output_files()` is the one that matters: without the explicit
`message_thread_id`, a generated PPTX arrives in the chat's main flow while the
conversation that asked for it sits in a topic.

`/new` clears **only the topic it was typed in**. `clear_history(thread_id=None)` is the
"all topics" form and is deliberately reserved for wiping a user completely —
`check_and_clear_session()` does not use it, because expiring one quiet topic must not
take the others with it. `chat_last_interaction` is keyed by the pair for the same
reason.

**Every per-conversation RAM record is keyed by the pair too**, and that was not free.
`core/memory.py` held all of it under `chat_id` alone, which produced three separate
silent failures: two messages typed in two topics inside the 1.5s debounce window merged
into **one** request whose answer went to whichever topic sent last (the other got
nothing, and the histories crossed); `/new` said "this topic's memory is cleared" while
deleting the neighbouring topic's sent-image list and location; and the "Qayta so'rash"
retry button read `thread_id` from nowhere, so the re-run answer appeared in the topic on
screen but was written to history at `thread_id = 0`. So `text_merge_buffers`,
`text_merge_locks`, `sent_image_urls` and `last_locations` are keyed `(chat_id,
thread_id)`, and `store_failed_request()` carries `thread_id` **inside the record** —
`failed_requests` stays keyed by chat because one pending failure per chat was always the
semantic.

The queue is the one place where the pair is deliberately *not* the whole story.
`GeneratingState` is aiogram's FSM key (chat + user, no thread), so one answer at a time
per user still holds; `_process_merged_text`'s `finally` therefore wakes **one** waiting
buffer from any topic of that chat and lets its own `finally` wake the next. Waking them
all would start parallel generations under a single-flight guard.

⚠️ A raw `bot.send_*` in the reply path needs `mavzu_kwargs(thread_id)`
(`handlers/helpers.py`) — aiogram fills the topic in for `message.answer()` and not for
anything else, so the error message with the retry button and the "matn juda uzun"
warning both used to land in the chat's main flow. `tests/test_topics.py` checks 21-27
pin all of the above.

⛔️ **Turning it on is a @BotFather Mini App toggle, not code.** `getMe` exposes
`has_topics_enabled` and `allows_users_to_create_topics`; `main.py` reads the first into
`messages.TOPICS_ENABLED`, which only picks the wording of the "this conversation is
long" hint — telling someone to open a topic they cannot open is worse than saying
nothing. Test on a **second bot** before flipping it on the live one: the section below
is what happens when a BotFather toggle is trusted without a live test. The specific
thing to verify is that `sendRichMessageDraft` works inside a topic, since the whole
streaming animation and the stop button are built on it.

Topic creation and deletion are left to Telegram's own UI on purpose. There is
no `forum_topic_deleted` update, but nothing needs one: nobody can send into a deleted
topic, so its rows just become unreachable. A `/suhbatlar` list was considered and
dropped — the native topic tabs already are that list.

**The bot does name a topic, once.** `editForumTopic` is allowed in a private chat (the
Bot API says so explicitly), so after the first exchange `safe_update_history()` fires a
background task that asks `HISTORY_SUMMARY_MODEL` for a 2-4 word title and renames the
topic. It costs one mini-model call per topic lifetime — the mini bucket, not the big one.

⛔️ **It must stay "once", and the reason is that the bot cannot read the name it is
overwriting.** There is no `getForumTopic` in the Bot API: `editForumTopic` is write-only.
Rename on every message and the title the *user* typed is destroyed on their next
question. `nomlash_kerakmi()` is the whole guard — private chat, real topic, the
assistant's own write, and at most 3 rows in the conversation. A bot reply always lands on
an even row (question 1, answer 2), so `<= 3` fires exactly once; the 3 is there for the
case where two messages arrive before the debounce window closes. `update_chat_history()`
returns that row count, which it was computing anyway for the trim limits, so the check
costs no extra query. `tests/test_topic_nom.py` check 3 is the one holding the line: it
runs two full exchanges and asserts Telegram was called once.

One consequence is deliberate: `/new` empties the topic's history, so the next exchange
starts from row 1 and the topic is renamed again. That is the right behaviour — the
conversation genuinely changed — but it does mean a hand-typed name does not survive
`/new`.

### Telegram Business

⛔️ **Read `BIZNES.md` before touching anything Business.** It holds every rule for
`handlers/biznes.py` and `handlers/biznes_uslub.py` (phases 1-5: the loop guard, the atomic
draft claim, "nothing technical reaches the customer", the customer path's own prompt, the
owner-style learning) and the planned next work. The four rules that break silently:

- `biznes_kimdan()` is the single loop guard and checks `sender_business_bot` **first**.
- History is keyed `(customer_chat_id, -owner_id)`; the DM queue wake-up skips negative keys.
- `biznes_yoriqnoma=` forces tools off, skips the owner's memory, and swaps `instructions`
  for `BIZNES_INSTRUCTIONS` — per-owner text only ever goes into a `developer` message.
- `/biznes` and `/mijozlar` are deliberately absent from the menu during testing.

### Inline mode must stay OFF — it breaks guest mode

⛔️ Do not enable `/setinline` in @BotFather, and do not "helpfully" suggest it.
A live test (2026-09-10) settled this: with inline on, Telegram treats
`@bot savol` in a chat as an **inline query**, the send button disappears, the
client spins and ends with an "x", and the message never arrives as
`guest_message` at all. Guest mode simply stops working.

`handle_inline_share` used to carry the opposite claim — that the two update
types "live side by side and neither replaces the other" — and its trick of
answering a non-empty query with an empty result list does **not** rescue it:
no results means the text cannot be sent as an ordinary message either. The
handler stays registered, but only for a future in which this changes.

So the choice is a prettier share button *or* guest mode, and guest mode wins by
a wide margin. With inline off, `_share_button()` falls back to a
`t.me/share/url` link — the message goes as flat text without a button, which is
a cosmetic loss, not a broken feature. The startup check is now inverted: it
warns when inline is **enabled**, since that is the broken state.

### Guest mode

⚠️ **The final answer goes through `build_rich_markdown()`, the status animation does
not.** `_edit_guest_inline_message(..., rich=True)` is the switch. It used to call only
`code_fences_to_html()`, so a group answer lost tables, `<details>`, pull quotes, maps,
buttons, collapsed sources and premium emoji — and, worse, the markers the model writes
anyway (`[batafsil: …]`, `[xarita:…]`) reached the reader as raw text. The plain-`text`
fallback rung takes `strip_rich_tokens()` for the same reason: the marker disappears, the
information stays. Status frames stay on the cheap path — they are re-sent every 4s and
every extra decoration only raises the chance of a rejection that would cost the
animation.

Guest also uses `speech_to_text_smart` / `text_to_speech_smart`, so a Pro user gets the
natural voice in a group instead of the free edge-tts one.

**Photos work in guest too.** `images_out` used to be `None` there, and that was not a
missing feature but a silent bug: `IMAGE_CAPABILITY_NOTE` is added unconditionally in
`get_openai_reply`, so the prompt promised pictures, the model called
`internet_search(want_images=true)`, and the tool answered with **silence** — which the
model reads as "no images found" and retries, the exact context-explosion path described
above. `handle_guest_message` now owns one `images: list` and passes it to all three
`get_gpt_reply` calls (not to `get_vision_reply` — single round, no search tool).

⚠️ **A media send needs its own timeout, and a timeout is not a rejection.** The shared
guest session is capped at 10s, tuned for 0.6s draft pings, while Telegram fetches every
image URL from the source site *before* it creates the message. `_edit_guest_inline_message`
therefore passes `RICH_MEDIA_TIMEOUT` on the image-bearing payload only, and `_attempt`
now returns a third value, `noaniq` — on a timeout or connection reset the ladder stops
instead of falling through to the plain payload, because the message may already have
arrived. Without that, the user sees the same answer twice, once with photos and once
without: the identical bug the DM path already paid for (`OUTCOME_UNKNOWN`).

`safe_update_history(..., images=images)` matters here as much as in the DM path — a raw
`[rasm:1]` left in history makes the model re-emit the token instead of searching, and
the user gets an empty answer.

Still missing in guest, deliberately: files (`output_files=None`) — the group has nowhere
to put one, and the caller's DM is only reachable if they have started the bot.

`handlers/guest.py` handles chats outside DMs via `guest_message`. It passes `caller_user_id` as **both** `chat_id` and `user_id`, so a person has one identity and one memory whether they write in a group or in the DM. Quota is charged to that user. Reminders are delivered to the DM regardless of where they were created.

### What is left in the bot, and why each thing stayed

`handlers/admin/` is now four modules: `common.py` (guards + helpers used by more than
one *screen*, where "screen" includes the web panel — that is why
`_check_can_remove_admin()` lives there rather than in `system.py`), `broadcast.py`,
`promo.py` (sending only), `system.py` (report only), `daily.py` (the two background
watchers), and `__init__.py`, which does **nothing but register handlers**. It was one
2671-line file; then twelve screens; now **21 registrations**, down from 57.

Everything else moved to `web/`. What stayed did so for one reason each, and the reason
is always *"the bot can do this and a web form cannot"*:

- **`/xabar`** — broadcast. `copy_message` forwards the admin's own message verbatim:
  album, formatting, premium emoji. A message reassembled from a web form loses all of it.
- **`/kod`** — sending a promo code or a referral invite to named people.
  `send_promo_gift()` sends a ready button, `send_referral_invite()` builds each person's
  *own* link. Creating and revoking codes is in the panel; only the sending is here, so
  there is no second copy of anything.
- **report** (`report_callback` / `process_report_message`) — started by an ordinary
  user, who has no panel at all. These two are the **only** handlers here with no admin
  check, deliberately.
- **the daily report** (`daily.py`) — push; its whole point is arriving without opening
  anything.
- **payments** — in `main.py`, before every router; that ordering is untouchable.

Three things survived every refactor and must keep surviving:

1. **Registration order in `__init__.py` is functional.** FSM states go *after* the
   command handlers (otherwise an admin stuck in a state cannot invoke anything else),
   and `waiting_for_button` / `waiting_for_recipients` / `waiting_for_schedule` go
   *before* `waiting_for_content` (otherwise the button label an admin types is swallowed
   as "new broadcast content").
2. **The admin check lives inside each handler, not in a filter** — because
   `report_callback` and `process_report_message` are deliberately open to ordinary users.
3. **`bot` comes from `core.loader`**, not from a closure; no handler touches `dp`.

⛔️ **Entry points are commands, not reply-keyboard text.** The four-button reply keyboard
is gone (`core/keyboards.py` deleted). A handler bound to `F.text == '📢 Xabar yuborish'`
would now be **dead code that still registers**: the button no longer exists and nobody
types that string by hand. `tests/test_admin_registry.py` check 3 fails if `F.text ==`
reappears there.

⚠️ **Deleting the keyboard does not remove it from anyone's phone.** Telegram keeps a
`ReplyKeyboardMarkup` on screen until it is replaced or explicitly removed, so `/start`
sends `ReplyKeyboardRemove()`. Without it, admins would keep tapping four buttons that
answer nothing — which reads as "the bot broke", not as "this moved to the panel".

⚠️ **The keyboard was also the only *discoverable* entry point**, so removing it without
a replacement would leave `/xabar` findable only by memory. `services/menu.py::ADMIN_COMMANDS`
puts both commands in the `/` list, for admins only. Two traps came with that: the
`_shown` cache compared a single `is_pro` bool with `is`, so an admin-flag change would
never have been noticed (it is keyed on the `(is_pro, is_admin)` pair now); and the
`sync_commands(..., True, ...)` call has to sit **inside** the `if admin_flag` branch —
outside it, every ordinary user got `is_pro=True` and saw `/kunlik` and `/research` in
their menu. `tests/test_menu.py` check 3b guards the leak.

Anything written to `user_activity` must also appear in **`core/config.py::ACTIVITY_TYPES`**
— one dict of `type -> (emoji, label, points)` — or it silently vanishes from statistics.
That list is the SQL filter (`database.activity_stats()` and `daily_report_stats()` pass
it as `= ANY($1)`), the daily report's labels and the web panel's bar names — three
consumers now that the Telegram statistics screen is gone. It used to be three
hand-written copies. `tests/test_activity_tracking.py` guards it by **importing** the
dict rather than reading a file by path, so moving code no longer breaks it.

The admin path spends **zero AI tokens**: nothing under `handlers/admin/` calls
`services.ai`, and `non_admin_predicate` in `main.py` keeps admins out of the AI handlers
entirely.

⚠️ **A test that fails after a deletion is telling you where its rule moved.** Four did,
and none of them wanted its assertion deleted: a label nothing writes any more
(`referral_campaign`) had to leave `AUDIT_ACTIONS`; a "both screens call one validator"
check became "the limits must not migrate into `web/api.py`"; two checks that read a
deleted file now check the *source* of the keys instead (does `broadcast.py` really write
this segment; is this limit key really in `PLAN_LIMITS`); and "two screens, same numbers"
became "no raw SQL in `web/api.py` or `daily.py`". Ask what the check was protecting
before you change it — it is almost never the screen.

### The web admin panel runs inside the bot process

`web/` is an aiohttp server started from `main()` — not a separate Railway service.
The reason is RAM caches: `config.apply_limit_overrides()` and
`database.load_watch_cache()` hold settings in memory, so a second process could write
a new limit to the database while the bot kept using the old value. One process, one
`DATABASE_URL`, one token. `aiohttp` is already a dependency (aiogram uses it), so the
panel added **no** new package.

It must never take the bot down: every route is wrapped by one `@web.middleware`
`try/except` that turns an unhandled exception into JSON plus a logged traceback, and
`main()` starts the server inside its own `try/except` so a failure to bind leaves the
bot running without a panel.

**Three independent auth layers** (`web/auth.py`), and only the last two are gates:

1. The blue menu button is set per chat (`services/menu.py::sync_menu_button()`) so it
   appears only for admins. This is **decoration** — the URL can be opened by hand.
2. `POST /api/session` verifies Telegram's `initData` HMAC with
   `aiogram.utils.web_app.safe_parse_webapp_init_data`, **plus an age check aiogram does
   not do** (5 minutes) — without it a stolen `initData` would work forever. Success sets
   a signed `HttpOnly; Secure` cookie holding only `user_id`, an expiry and an HMAC; no
   session table.
3. `@admin_only` on every `/api/*` handler re-runs `is_admin()` **on every request**,
   never cached, so a demoted admin is locked out on their next request rather than at
   the end of the 12-hour session.

⚠️ **The panel also sends `initData` on every request**, in `X-Telegram-Init-Data`, and
`admin_only` verifies that signature with the bot token **before** it looks at the cookie.
The header is the stronger proof — only Telegram can produce it — while the cookie is our
own signature and would stand for 12 hours if stolen. Its age limit is **24 hours**, not
the 5 minutes `/api/session` uses, and the difference is not laxness: `initData` is issued
once when the Mini App opens and never refreshes, so a 5-minute rule there would kill the
panel five minutes in. The cookie stays as the second path because a panel opened in a
plain browser has no `initData` at all.

The cookie key is a *derivative* of `BOT_TOKEN` (`sha256("webpanel:" + token)`), not the
token, so a leaked cookie signature cannot be turned back into the bot token.

⚠️ **`web/api.py` contains no SQL.** Every number it returns comes from a `db/database.py`
function — that is why `activity_stats()` and `top_users()` were moved there out of
`handlers/admin/stats.py` before that file was deleted. The second consumer is still
real: `daily.py` builds the daily report from the same functions, so a query written in
`api.py` means the panel and the report disagree from the day one of them is edited.
`tests/test_web_stats.py` check 8 fails on `SELECT`/`INSERT`/`UPDATE`/`DELETE`/`pool.acquire`
in either file.

⚠️ **Decoration must not depend on the database.** `_kim()` reads the admin's name and
role for the sidebar card, and both queries sit inside a `try/except`: authorisation
already happened above, so a one-second database hiccup must not turn a successful login
into a 500 and lock the admin out of the panel. `tests/test_web_auth.py` check 7 forces
those calls to raise and still expects `200`.

⚠️ **Refund order is Telegram first, then the database.** The order was copied from
`handlers/admin/users.py`, which has since been deleted — so `web/api.py::refund` is now
the only implementation and nothing else encodes the rule. Telegram can refuse a refund
(window expired, already refunded); the other order takes the plan away from a user whose
money never came back. `tests/test_web_users.py` check 9 is what holds the order in place.
If Telegram succeeds and the database write then fails, that is logged as its own loud
line — the plan is still live on the account.

⚠️ **Model-style input discipline applies to admin input too.** `/api/users?q=` goes to
Postgres as a parameter, never string-interpolated. The premium endpoint accepts only
`7 / 30 / 90 / null`; the first version turned an unparseable value into `None`, and
`None` means *unlimited* there — so `{"kun": "o'ttiz"}` granted lifetime Pro. Anything
the panel renders through `innerHTML` (error text, usernames) goes through `xavfsiz()`
in `panel.js` first.

⚠️ **A write endpoint that changes a cached setting must refresh the cache in the same
request.** Two do: `POST /api/limits` calls `config.apply_limit_overrides()` and
`POST /api/watch` calls `database.load_watch_cache()`. Both caches exist because they are
read on the hot path — `daily_limit()` runs on every message and `get_watch_target()` is
synchronous with no I/O at all — so without the refresh the database holds the new value
while the bot keeps using the old one, the panel says "saved", and **nothing raises**.
This is the concrete reason the panel runs in the bot's process; a second process could
not fix it at all. `tests/test_web_settings.py` checks 2 and 8 are the guard, and check 2
is the phase's whole acceptance criterion.

⚠️ **"Admin" is two tables, and a screen that reads one of them lies.** `admins` and
`superadmins` are separate, and `huquq_bormi()` checks both — so any list answering "who
can open this panel" has to check both too. `get_admins()` reads only the first, and on
the live database (2026-09-15) that table is **empty** while one superadmin exists: the
panel would have shown nobody while that person was logged into it. `database.get_panel_admins()`
is the union (`FULL OUTER JOIN`, one query, `is_super` flag included — which also removed
a per-row `is_superadmin()` call). Fake data never shows this; reading production does,
which is why every phase of this panel was checked against the live Postgres read-only.

⚠️ **`None` means two different things in the limits API and they must not be confused.**
On `POST /api/limits`, `qiymat: null` means *remove the override*, i.e. fall back to
`PLAN_LIMITS` — it is **not** unlimited (unlimited is what the `premium` plan is for, and
that plan is deliberately absent from the editable table). So an unparseable value cannot
be coerced to `None` here, for the same reason it could not be on the premium endpoint.
`0` is also not unlimited: it means "this plan does not have the feature".

`web/static/panel.js` splits its startup into `qism()`-wrapped blocks. One missing
element inside a single IIFE used to kill everything after it — navigation included —
with one line in the console and no visible cause. Buttons inside a list that is redrawn
after every write (`data-wdel`, `data-addel`, `data-pdel`, `data-pcopy`, `data-bdel`, `data-uid`) are
bound once on the **container** via `delegat()`, never on the row: rebinding after each
redraw stacks listeners and fires one click twice, which on a refund or a gift means
doing it twice.

The panel's logo is `/static/logo.jpg` **everywhere** it appears (`REJA.md` 3.2.1);
`tests/test_web_panel.py` check 4 fails on any other image source.

⚠️ **The panel has no tables and no second screen layout.** Every list is one
`.rows > .row` structure: on a wide screen a `--ust` grid variable turns it into aligned
columns, on a phone that variable is off and the row wraps into a card. The tables it
replaced were wrapped in `overflow-x:auto`, so on a phone the last column — "last seen",
and the action buttons — was simply off-screen, and nothing said so. If you add a list,
add it as `.rows`; a `<table>` there is the bug coming back.

⚠️ **The theme comes from Telegram, not from the panel.** `panel.js::tema()` copies
`tg.colorScheme` onto `data-tema` and subscribes to `themeChanged`; every colour is a
token defined on bare `:root` and re-defined under `[data-tema="light"]` *and* under
`prefers-color-scheme: light`, so the browser and the Mini App both get a complete
palette. This reverses the earlier decision (the panel used to be dark-only and painted
Telegram's header to match it) — that was fine until someone on a light client opened a
black page inside a white app. Do not re-introduce a hard-coded colour: the CSS rule is
that only the brand gradient and the SVG `<defs>` carry literal hex.

⚠️ **Panel strings live in `web/static/soz.js`, lists come from `/api/meta`.** The split
matters: a string only the panel shows belongs in the dictionary, a list the *bot* also
uses (tariff, limit, segment names) must come from `core/config.py` over `/api/meta`, or
it becomes the sixth hand-written copy.

⚠️ **Saving the limits is Telegram's MainButton, not a button per row.** The per-row
"Saqlash" was cut off at the right edge on a phone and gave that card a horizontal
scrollbar. The main button appears only when a field actually differs from what was
loaded, and after a successful save the toast offers **Bekor qilish** for 5 seconds,
which re-sends the previous values.

### The panel's second pass: speed, filters, export, alerts

⚠️ **Read endpoints run their queries in parallel, write endpoints must not.**
`overview` made **six** sequential round trips to Postgres on the most-opened screen;
`stats`, `user`, `journal_errors` and `watch` were the same shape. They are
`asyncio.gather` now. ⛔️ Do not copy the pattern into a write endpoint: `refund` needs
Telegram **before** the database, `watch_set` needs the cache refresh **after** the write,
and `user` still fetches the profile first because a missing profile makes the other two
queries pointless.

⚠️ **`_kun_qatori()` fills the empty days, and both charts go through it.** The database
only holds days where something happened, so a silent day is simply absent — and a chart
that skips it looks *better* than reality, because the dip never appears. The requests
chart and the revenue chart share the one helper (field names are parameters); a second
copy is how one of them would quietly start drawing a flat line. `panel.js::chizuvchi(prefix)`
is the same decision on the front end: the chart used to be bolted to fixed element ids
(`line`, `dots`, `tip`), so a second chart meant copying the whole function. Ids are
prefixed now (`chart-…`, `dchart-…`) and the code is one factory.

⚠️ **A filtered list and its count must be built from one filter.** `_jurnal_filtri()` /
`_audit_filtri()` return `(where, args)` and both the page query and the `COUNT(*)` use
it. Written twice, the panel says "found 41" over a filtered list, draws five pages, and
shows an empty screen from page two on — with nothing raising. The audit count also has
to carry the same `LEFT JOIN`s, because the search touches `u.username` and `t.username`.
`test_web_journal.py` checks 10-12 pin all of it, including that a malformed `kun` is
ignored rather than trusted — admin input is an untrusted boundary too.

⛔️ **CSV export escapes formulas, and that is a security control, not formatting.**
Excel executes a cell that starts with `=`, `+`, `-` or `@`, so a user who names
themselves `=HYPERLINK(…)` would be running code on the admin's machine the moment the
export is opened. `_csv_katak()` prefixes an apostrophe. The file also carries a BOM or
Excel reads it as ANSI and mangles every `o'` and `g'`. `test_web_journal.py` check 14 is
the guard.

⚠️ **The export arrives as a Telegram document, not a browser download.** The panel is a
Mini App, i.e. a Telegram webview, and a `blob:` download fails silently there — the admin
taps the button and nothing happens. `_hujjat()` sends the bytes to the **requesting
admin** (`request["user_id"]`, never a `_target`), which also means the file lands in a
chat where it can be forwarded. Every export writes an `export` row to the audit log:
data leaving the system is different from data looked at inside it.

⚠️ **Alerts exist because the panel is pull-only.** Nothing tells an admin anything until
they open it, and the daily report arrives in the morning — so a bot that died in the
evening was discovered the next day. `admin_daily.alert_watcher()` closes that window with
**exactly two** conditions: an error surge, and silence. Adding a third needs a good
reason; an alert that fires often is an alert nobody reads, and then the real one is
missed too.

Three details are load-bearing. The repeat flag lives in RAM (`_ogoh_holat`) and clears
when the condition does, so one outage is one message and a recovery re-arms it. Silence
between 02:00 and 08:00 Tashkent is **not** reported, or every night would produce a false
alarm. And `last_activity_at()` returning `None` (an empty table, a fresh bot) is not
"silent forever" — it is ignored. `tests/test_ogohlantirish.py` checks 2, 4 and 8 hold
those three.

⚠️ **Token spend is written to the database now, not only to the log.** The bot runs on
a free daily grant and the panel could not say how much of it was gone — `[TOKEN]` lines
existed only in the Railway log, which is a stream, not an answer to "how much today".
`_log_token_usage()` still logs, and additionally fires `_token_saqla()` as a background
task: the reply never waits on it and a database failure is swallowed, because accounting
is not more important than the answer.

The rows go into **`user_history`**, a table that already existed and that **nothing had
ever written to** — so no new table, and the per-user column comes free, which is what
makes "who is burning the grant" answerable at all. `token_stats()` cuts days by
**Tashkent**, not UTC (`created_at` is a naive UTC timestamp), or "today" would roll over
at 05:00 and the morning number would be yesterday's. `TOKEN_SAQLASH_KUN` (90) is trimmed
once a day inside `daily_report_watcher` — a table nothing trimmed would grow forever at
~2 400 rows a day.

⚠️ **The grant is a measurement, not a limit**, and the panel says so: tokens past it
still work, they are simply billable. So the card reads "grantdan oshdi", never
"blocked". And the cached share is displayed **beside** the total, never subtracted from
it — OpenAI confirmed (2026-09-09) that cached input counts against the quota exactly the
same. What that percentage actually tells you is whether the request prefix is still
stable through the day; if it falls, something per-user has leaked into the cached prefix.
`tests/test_web_stats.py` checks 9-9d pin the arithmetic, the empty-database case, and
that the write stays off the reply path.

⚠️ **Two asyncpg type rules broke this panel live, and no offline test could
see either.** Both endpoints came back 500 while every test passed, because the
fake database has no types at all.

- `NOW() - ($N || ' days')::interval` makes asyncpg infer `$N` as **text**, so an
  `int` raises `DataError`. Everything else in `db/database.py` already passed
  `str(...)` (`str(within_days)`, `str(int(days))`); the two new journal filters
  did not, and took the audit screen, the error screen **and** `alert_watcher()`
  down with them — the watcher retried every 15 minutes, forever.
- `SUM()` over a **BIGINT** column returns `NUMERIC`, which asyncpg gives back as
  `Decimal`, which `json_response` cannot serialise. `user_history`'s columns are
  BIGINT, so every token query needs `::bigint`. This one did not appear on
  deploy: the table was still empty, `SUM` returned `NULL`, and the screen only
  died once the first real request had been logged.

`test_web_stats.py` check 9e and `test_web_journal.py` check 17 read the **source
text** for both rules — the same approach as `test_panel_raqamlar.py`, and the only
one available without a database.

### The panel's third pass: the phone, the double tap, the stale card

Four complaints, and every one of them was invisible to the test suite because the
suite has no browser, no Telegram and no types.

⛔️ **`touch-action: manipulation` goes on `html, body`, not on the buttons.** The
complaint was double-tap zoom on *text and empty space*, so closing only the tappable
elements would have fixed the part nobody was tapping. ⚠️ Do not "also" add
`user-scalable=no` to the viewport: iOS has ignored it since iOS 10, and where it is
honoured it kills pinch-zoom for someone who needs it. Pinch still works; only the
accidental double tap stopped zooming.

⚠️ **Every input is `max(16px, …)` and 16px is an iOS constant, not a taste.** Below
it, WKWebView force-zooms the whole page on focus and never zooms back. Three
selectors carry it (`input,textarea,select`, `.field input`, `.kiritish`) — the bare
element rule matters because `font: inherit` was pulling 15px from `body`. The
`transform: scale()` trick was deliberately not used: it moves the focus ring and the
hit area with it.

⚠️ **`:hover` lives in one `@media (hover:hover) and (pointer:fine)` block.** On a
phone the hover state sticks after the finger leaves and the row reads as "selected".
Moving the rules earlier in the file was the risky part, not the media query — four of
them compete with `[aria-current]` or `.btn.danger` at *equal* specificity, so the
relative order had to be preserved. Check that before moving any of them again.

⚠️ **`tg.expand()` does nothing on desktop.** It sets the height on phones; the narrow
window on Telegram Desktop needs `requestFullscreen()` (Bot API 8.0), guarded by
`typeof`, `isVersionAtLeast("8.0")` and `try/catch`. ⛔️ **There is no platform value
`"web"`** — Telegram Web is `weba` and `webk`. Writing `"web"` makes the condition
never fire and the bug stays silent, which is why `test_panel_korinish.py` check 12
asserts the set of four exactly.

⚠️ **`sahifa()` no longer returns a `FileResponse`.** It reads `panel.html` once and
rewrites every `/static/*.css|js` link to `?v=<that file's own sha256 prefix>`, so an
admin cannot be left on yesterday's JavaScript after a deploy while an unchanged file
stays cached. Per-file hashes, not one global version. ⚠️ The version is never written
by hand: a hand-written number is forgotten exactly once, and then cache-busting
*looks* present while doing nothing — worse than not having it. `logo.jpg` is
deliberately untouched (`REJA.md` 3.2.1 fixes its URL). One consequence for local work:
the rendered page is cached in a module global, so editing CSS during development needs
a restart.

⚠️ **The error row goes to the top of the `<section>`, not into its first `.card`.**
On six of the eight screens the first `.card` sits *after* the KPI row — 1277 characters
into `dash` — so on a phone the "could not load" message was below the fold while five
`—` placeholders sat on screen saying nothing. A static `—` does not distinguish "not
loaded yet" from "the request failed", which is why the KPI values now show a skeleton
first. This was a live incident, not a hypothetical: a 500 from `/api/overview` looked
exactly like an idle panel.

### Two clicks, and why the disabled button is not the fix

`so_rov(yol, tana, usul, tugma)` disables the button for the duration of the request,
synchronously, before the first `await`. That stops the double tap **on screen**. It is
not a guarantee: a slow network, a page reload or a second app window still sends two
requests, and `set_user_premium(..., extend=True)` *adds* days, so the second one
silently turned 30 into 60.

`@bir_marta` (`web/auth.py`) is the server half. Three things decide whether it works:

- ⭐ **The key is derived from the content, never random.** A `crypto.randomUUID()` per
  call cannot stop a double tap — two taps produce two UUIDs and both look new. The key
  is `sha256(user_id + path_qs + body)` with a 10-second window; an explicit
  `Idempotency-Key` header overrides it when a deliberate repeat is wanted. ⚠️ `path_qs`,
  not `path`: `/api/export?tur=users` and `?tur=payments` share a path and an empty body.
- ⭐ **A per-key `asyncio.Lock`.** The second request arrives while the first is still
  running, so caching the result afterwards buys nothing on its own. The second waits and
  returns the first's response.
- **Only 2xx is cached.** A cached 4xx would show the admin a stale error after they had
  already fixed the cause, and a failed request performed nothing, so repeating it is
  free.

Which endpoints carry it is **computed, not listed**: those whose repeat has an external
effect (they send through `_xabar` / `_hujjat` / `_guruh_sinovi`, or pass `extend=True`).
The other eight rewrite the same state and are naturally idempotent. ⛔️ `refund` is
deliberately excluded: `refunded_at` is an atomic, *permanent* guard, and a 10-second
cache would only hide the 409 behind a 200 — the wrong trade on a money path. Its bug
was different and is fixed: `mark_payment_refunded()` already returned `False` for the
loser of a race, and the caller ignored it, so the loser still wrote an audit row and
sent the user a **second** "your money was refunded" message.

### The alert channel could fail silently, and nothing said so

The panel is pull-only, so `alert_watcher()` is the one thing that reaches an admin
without being asked. It writes to the watch group — and that send could fail with
nothing but a `logger.warning`, i.e. the "the bot is down" message failing was visible
only in the log you read when the bot is down.

⭐ **`_ogoh_holat` is set from the send's return value, never before it.** That flag
means "this has already been reported". Setting it for a message that never arrived
marks an unsaid thing as said, and since the flag only clears when the *condition*
clears, the alert was then lost completely. `_ogoh_yubor()` returns a bool for exactly
this. The retry interval is the existing 15-minute check with no backoff and no new
constant: a send that fails reaches nobody, so retrying cannot spam anyone — the only
cost is 96 failed Telegram calls a day, and it stops the moment one lands.

⛔️ **Only a group-level failure lights the banner.** `config.guruh_xato_sababi()` is
the single classifier (the list is `GURUH_XATOSI`, and `test_web_settings.py` check 15
fails if any of the three consumers copies it). "Message is too long", "can't parse
entities", a rejected media type — those fix themselves on the next message, and putting
them on the banner would leave it permanently lit, which is a banner nobody reads.
`_send_watch_copy()` therefore records **once, at the end**: the fallback rung succeeding
means the group is healthy, so writing on each `except` would flash "broken → fixed" for
a message that was actually delivered.

The state lives in three `watch_settings` columns and the banner condition compares two
timestamps, so a successful send clears it by itself — there is no "dismiss" button and
no clearing step that can be forgotten. `database.watch_holat_yoz()` only writes when the
state *changes*, because `_send_watch_copy()` runs on every message of a watched user.

### Migrations run before the bot starts, so they must be cheap

`create_users_table()` / `create_history_table()` are awaited in `main()` ahead of
polling and the web server. Everything in them blocks startup.

⛔️ **`CREATE INDEX CONCURRENTLY` is therefore NOT in them** — it is in
`indekslarni_qur()`, which `main.py` fires with `asyncio.create_task()`. `CONCURRENTLY`
scans the whole table and takes seconds on a large one; awaited, both the bot and the
panel would sit dark for that long, for something that only affects *speed*. An
unindexed bot works, just slower; a bot still waiting works not at all. The result goes
to the log only (`[indeks] … tayyor` / `… qurilmadi: …`).

Two traps come with `CONCURRENTLY`, and `test_panel_raqamlar.py` check 12 pins both.
asyncpg sends `conn.execute(sql)` over the simple query protocol and opens no
transaction — but **only when no parameters are passed**; add one and it switches to a
prepared statement and Postgres answers "cannot run inside a transaction block". And a
failed `CONCURRENTLY` leaves an **invalid** index that `IF NOT EXISTS` then happily skips
forever, so `_indeks_yarat()` checks `pg_index.indisvalid` and drops it (also
`CONCURRENTLY`) before rebuilding. Its error is logged as a warning rather than swallowed:
the existing index block ends in `except: pass`, which is why these calls sit outside it.

### `make_interval`, not string concatenation

Every day-interval in the codebase is `make_interval(days => $N::int)`. The old
`($N || ' days')::interval` made asyncpg infer `$N` as **text**, so passing an `int`
raised `DataError` — that single line killed the audit screen, the error screen and
`alert_watcher()`, which then retried every 15 minutes forever. Wrapping the arguments
in `str()` fixed the symptom and left the trap in place for the next writer.
`test_web_journal.py` check 17 walks the tree (comments stripped) and fails if the old
spelling returns. `_YOZ_MUDDAT_SQL` still contains `NOW() +` and still has no `GREATEST`,
so `test_pro_grant.py` check 4 — the frozen overwrite behaviour — is untouched by this.
### The panel's own security rules

⛔️ **The client IP is the *rightmost* `X-Forwarded-For` entry, never the first.** The
client writes the leftmost one, so the old code let anyone defeat the rate limit by
sending a different value each request — and leave a permanent key behind each time, a
memory-exhaustion path of its own. `ISHONCHLI_PROKSI` counts hops from the right, and
`XFF_TEKSHIR=1` exists to log the raw header once on Railway so that number can be
confirmed; turn it off afterwards, it prints IP addresses.

⚠️ **The rate limiter is bounded now** (`CHASTOTA_OYNA`, `CHASTOTA_MAX`) and it counts
writes per **admin**, not per IP — the caller already passed the signature and the
permission check, and a phone changes IP every few minutes. `YOZUV_RATE_LIMIT` is 120/min
and that number is aimed at a runaway script, not at a fast human: a limit set near real
usage fires on legitimate bursts, the admin learns to ignore it, and then the real one is
missed too. The measurement behind it is that the heaviest test file makes 31 writes in a
few seconds.

⛔️ **`X-Frame-Options` must never be added.** The Mini App is loaded in an iframe by
Telegram Web, so `DENY` and `SAMEORIGIN` both kill the panel outright. Framing is
controlled by `frame-ancestors` (`telegram.org` plus `*.telegram.org`, which covers
`web.`, `webk.`, `webz.`, `weba.`); desktop and mobile use an embedded webview, where the
directive does not apply at all.

⚠️ **CSP ships as `Content-Security-Policy-Report-Only` on purpose.** Two unknowns can
only be settled live: the inline `style=` attributes in `panel.html` (hence
`'unsafe-inline'` on `style-src`) and how Telegram Desktop's webview answers
`frame-ancestors`. `POST /csp-report` logs violations to Railway, because Report-Only
tells you nothing on a phone where the console cannot be opened. That endpoint is
deliberately **not** under `/api/` and deliberately has no `@admin_only` — the browser
sends the report without our header or cookie — so the "every `/api/*` is guarded" rule
stays intact. Flip to enforcing only after the log stays quiet through every screen on
iOS, Android, Desktop and Web; `test_web_xavfsizlik.py` check 6b pins the Report-Only
state so the flip has to be deliberate.

`del_cookie()` in aiohttp 3.9.5 takes only `domain`/`path`, so logout sets the cookie to
`""` with `max_age=0` and the **same** `Secure`/`SameSite`/`HttpOnly` attributes instead.

### Setting a plan is not adding to one, and the screen has to say so

Five grant sites exist. Four go through `_EXTEND_PLAN_SQL` and **add** (Stars payment,
promo code, referral reward, and the panel's gift via `extend=True`); that SQL
carries the three guards `test_pro_grant.py` freezes — `GREATEST(..., NOW())` so a lapsed
subscription's days are not added to a past date, unlimited stays unlimited, and the tier
never drops. There is no recurring-subscription path at all, so no renewal can lose days.

The fifth is the profile card, and it **overwrites** — deliberately, because it is the
correction tool: without it an admin who mistyped 3650 days could never shorten it. That
is frozen by `test_pro_grant.py` check 4 and must stay. The defect was never the
behaviour, it was that nothing said so:

- the button now reads **"Muddatni belgilash"**, against "qo'shish" on the gift screen —
  the verbs differ, so the two actions differ before any dialog opens;
- the confirmation states the **current** state in one of four wordings (free, dated,
  from-unlimited, to-unlimited) — "Ishonchingiz komilmi?" is not a confirmation, it is a
  button with extra steps, and `test_panel_korinish.py` check 14 rejects that phrasing;
- ⭐ the panel sends the `premium_until` **it displayed**, and
  `set_user_premium_checked()` compares it against the live row inside one transaction
  with `FOR UPDATE`, answering **409** on a mismatch. Without it, a payment landing
  between opening the card and tapping the chip would be erased by an admin who never saw
  it. A separate `SELECT` then `UPDATE` would leave exactly that window open, so the
  comparison has to be inside the transaction.
- ⛔️ the `holat` field is **required**; accepting its absence would leave the bypass as
  "just omit the field". The panel is this endpoint's only client and deploys in the same
  process, so an "old client" is a tab left open across a deploy — and that tab is showing
  stale numbers anyway, which is the hazard itself.

The audit row is JSON now (`{"kun":30,"oldin":{"tarif","muddat","qolgan"}}`) so the
previous expiry can actually be restored; `_premium_tafsiloti()` renders it as
`30 kun (oldin: 20 kun)` on the journal screen and falls through to the raw string for the
older rows, which are still plain `"30"` and `"sovga 45 kun"`.### Five label maps that all rotted the same way

`core/config.py` holds five dicts — `ACTIVITY_TYPES`, `AUDIT_ACTIONS`, `LIMIT_NOMI`,
`SEGMENT_NOMI`, `TARIF_NOMI` — for one reason: the same list kept being hand-written in each new
screen, and **every single copy drifted**. Found one per phase, always the same way:

- activity type labels were written twice in `handlers/admin/stats.py` and a third time
  in `handlers/admin/daily.py` as `ACTIVITY_LABELS`, which was already missing
  `location_message` — the daily report printed the raw type name;
- audit action labels lived in `handlers/admin/journal.py` as `ACTION_LABELS` and **9 of
  16 keys did not match what the code writes** (`ban` vs `ban_user`, `refund` vs
  `refund_stars`), so most of the audit screen showed technical strings;
- the four daily limits were named in `handlers/admin/journal.py::LIMIT_KEYS` *and* in
  `web/api.py::SANOQ_NOMI`, differently — "Fayl" vs "Fayllar", "Tadqiqot" vs "Chuqur
  tadqiqot". Two screens naming one setting two ways reads as two settings;
- the **tariff names** lived in `panel.js` as `PLAN = {pro: "Pro", free: "Bepul"}` and that
  copy had no `premium` at all — so a user on the unlimited `premium` plan showed as "Pro"
  in the table while the dashboard's distribution ring gave them their own segment. One
  person, two screens, two tariffs. `TARIF_NOMI` is now the list and the panel reads it
  from `/api/meta`; its keys are asserted equal to `PLAN_LIMITS`'s;
- broadcast segment labels sat inline in `handlers/admin/journal.py` as `segment_nom`.
  The first web copy of it invented `"pro"` and `"active"`, **neither of which exists**
  (`_filter_users_by_segment` writes `all` / `free` / `premium` / `pick`), so the panel
  would have shown `premium` raw. Caught by reading the source that writes the value —
  not by testing the screen.

All four are now one dict each, read by every consumer. If you add a screen that names
one of these things, read the dict — do not retype the list. And when you do write a new
copy anyway, the guard is always the same: walk the source for the calls that *write* the
values and compare both directions, as `tests/test_web_journal.py` checks 1-2 do.

The same discipline applies to **rules**, not just labels. Three validators are shared by
the Telegram screen and the panel, and neither may re-implement them:
`database.clean_promo_spec()` (promo code shape, 1-3650 days, 1-100000 uses, expiry in
the future — it used to live in the body of `process_promo_create`),
`database.clean_referral_config()`, and `handlers/admin/common.py::_check_can_remove_admin()`.
That last one moved out of `system.py` when the panel needed it: written twice, the panel
would have become a **weaker door than the bot** (removing yourself, removing a
superadmin, the three-day wait for a new admin, the last-admin guard) and nothing would
have caught it.

### Errors reach the admin through one funnel

Every admin action name written to `admin_audit` must appear in **`core/config.py::AUDIT_ACTIONS`** (`action -> (label, icon)`), which the panel's journal screen reads through `audit_nomi()`. The label carries **no emoji** — the icon is a key the panel resolves against its own line-SVG set (`panel.js::IKONKA`), so the journal matches the rest of the UI instead of being the one screen made of emoji; an unknown key draws a dot, so a new action is never invisible.

An action the code no longer writes must be **removed** from `AUDIT_ACTIONS` — `referral_campaign` was, when its flow moved to the panel — and moved to **`AUDIT_ESKI`**, the second dict, which exists only for action names that are in the live database and not in the code. Two dicts, two questions: "what does the code write" and "what is lying in the table". `audit_nomi()` falls through `AUDIT_ACTIONS` → `AUDIT_ESKI` → the raw string, and the raw string is still shown rather than hidden (`test_web_journal.py` check 4): a hidden row reads as no row at all. ⚠️ `AUDIT_ESKI` was written from the names this repo is known to have used; it could **not** be checked against the live table (production reads are blocked in this environment), so an action nobody remembers will still appear raw — which is the safe direction. It used to be a hand-written `ACTION_LABELS` in `handlers/admin/journal.py` and it had rotted badly: 9 of 16 action names did not match what the code writes (`ban` vs `ban_user`, `refund` vs `refund_stars`, `set_free` vs `set_plan`, `promo_create` vs `create_promo`), so most of the audit screen showed raw technical strings, while 6 labels hung on keys nothing ever writes. `tests/test_web_journal.py` walks the source for `log_admin_action(...)` and web's `_yoz(...)` calls and asserts both directions: every written action has a label, and every label is actually written.

`send_error_with_retry()` (`handlers/helpers.py`) is the only path a user-visible failure takes, so that is where `db.log_error()` writes to the `error_log` table — the "⚠️ Xatolar" screen reads it. Adding a second logging site elsewhere splits the picture; pass a `kind` instead (`"timeout"`, `"matn"`, …). The table trims itself on write (`ERROR_LOG_KEEP`).

### Premium emoji in the answer text

`build_rich_markdown()`'s last step swaps the emoji the model wrote for their animated form, `![ ](tg://emoji?id=…)`. The map is **loaded from an emoji pack at startup** (`TEXT_EMOJI_PACK`, currently `RestrictedEmoji` — 995 animated standard emoji) by `load_text_emoji_pack()`, because every sticker in a pack states which plain emoji it stands for, so Telegram builds the mapping. The previous hand-written `TEXT_CUSTOM_EMOJI` list was wrong in five of six entries — 🤖 pointed at a 🌟 from an unrelated pack, 🧠 at 🙂, 📄 at 📝, ⏰ at 📆, 🧹 at 🗑 — so the reader saw a different emoji than the model wrote. That list survives only as the fallback when the pack cannot be fetched. `apply_emoji_pack()` rebuilds three globals together (lookup, reverse lookup, regex); rebuilding only some would leave raw `![ ](tg://emoji?id=…)` on screen after a rejected send. This is post-processing on the bot side: **it costs no model tokens**, and the pack is fetched once at startup, never per message. ⚠️ It does change the failure profile: with 995 emoji mapped nearly every answer now carries custom emoji, so if the owner's Premium lapses the whole-message rejection stops being rare and hits every reply — the downgrade rung below is what keeps answers alive. The hand-placed `CUSTOM_EMOJI` ids used in buttons and system messages are untouched by any of this. The space in the alt text is required — `![](…)` can be read as a media block. It runs last because it must see the HTML the earlier steps produced: markdown is not parsed inside a table cell or an `<aside>`, so `_MD_DEAD_ZONE_RE` skips those regions and the plain emoji stays there (code blocks are already out via `_protect_spans()`). `TEXT_CUSTOM_EMOJI_MAX` caps the count. It was 12 and that was visible: an emoji-heavy reply (a "fun facts about octopuses" answer carries 30+) had its first twelve animated and the rest flat, so the *same* emoji appeared animated near the top and static further down — which reads as a bug. It is 50 now, one above the largest count in the whole stored history, so in practice the cap never fires; each swap costs ~36 characters against the 30000 rich limit, so 50 is ~1 800 characters. Note that emoji inside a table cell, an `<aside>` or a code block are deliberately left plain (`_outside_dead_zones`) — markdown is not parsed there, and `<tg-emoji>` is only valid in the `html` field, which this send path does not use. That mixed appearance is a platform limit, not the cap.

Custom emoji in text requires the bot owner to hold Telegram Premium, and a lapsed subscription makes Telegram reject the **whole message**. So the downgrade rung strips them: `plain_md` now goes through `strip_custom_emoji()` as well as `strip_image_tokens()`, and the flag deciding whether to retry is `bezakli` ("has media *or* premium emoji"), not `has_media`.

### A map is drawn from a marker the model writes

`[xarita:41.3111,69.2797,13]` becomes `<tg-map lat=… long=… zoom=…/>`. Coordinates come from the model — no geocoding, which would add a network call, a rate limit and a failure point. The code validates only the *ranges* (lat −90…90, long −180…180, zoom 1…20) and drops the marker when they fail; it cannot validate the *place*, since 41.9/12.5 is Rome and 41.3/69.3 is Tashkent and both look fine, so accuracy is the prompt's job. `<tg-map/>` is self-closing — written as `<tg-map></tg-map>` it gets the whole message rejected, which is exactly why the tag is emitted by code and not by the model. Like premium emoji, it is skipped inside table cells and `<aside>` via `_outside_dead_zones()`.

### Editing a photo the user already sent

`edit_image` is the same `_run_image_task()` as `generate_image` with a `source`
argument — one function, because the quota, the error text, the output-list contract and
the instruction handed back to the model are identical; only the endpoint differs. It
shares the `images` daily counter and the `MAX_IMAGE_ROUNDS` budget: to the user a drawing
and an edit are both "one picture", and a separate budget would just hand the model a
second attempt.

**The source bytes are never a tool parameter**, the same discipline as the map marker and
the location coordinate. The schema carries `prompt` and nothing else; the bytes come from
the chat through the existing `input_file_bytes` plumbing, which already carried the last
file. `handle_photo` now calls `_remember_file()` — before that the bot forgot a photo the
moment it had described it, so "now change the background" had no source at all.
`_is_image_bytes()` checks the **magic bytes, not the extension**: a PDF named `rasm.png`
would otherwise reach OpenAI and come back as an unreadable error. The schema is **386
tokens** (`tiktoken`, `o200k_base`) and is attached only while a picture is actually in the
chat, so ordinary traffic pays nothing for it — the same rule as `find_nearby`.

Two API arguments are load-bearing and neither one fails loudly if removed — the picture
just comes back wrong. `size="auto"` takes the output shape from the input, or a vertical
selfie is cropped square. `input_fidelity="high"` is what keeps the person's face, a logo
or text recognisably *the same*; below it the model redraws something similar, which
defeats the whole feature. `tests/test_image_edit.py` checks 18-19 pin both.

There are **two entry paths and both are needed.** A photo with a caption
("fonini o'zgartir") lands in `get_vision_reply`, which is single-round; the tool call is
harvested after the stream exactly as `update_memory` already was, and the result is not
fed back — so when the edit fails, *the code* appends the apology, because the model has
already written "here you go" above a message with no picture. A photo followed by a
separate message goes the ordinary `get_openai_reply` route with the full loop. Skipping
the vision path would have broken the most natural gesture there is: sending a picture and
saying what to do with it in one message.

⚠️ `pending_file_note()` needed a picture branch. The generic note says "use
run_python_sandbox to edit this file", and for a photo that sends "change the background"
into Python. Both routes are real — the sandbox still converts and resizes — so the note
names both, with `edit_image` first for anything that changes how the picture *looks*, and
says outright that a question about the photo's content needs no tool at all.

Still missing: groups. `edit_image` inherits `image_enabled`, which requires
`output_files is not None`, and `handlers/guest.py` passes `None` — so neither drawing nor
editing works outside a DM even for a Pro user.

### Finding real places near the user

A location message is stored (`core/memory.py::remember_location`, 30 min TTL) and the
`find_nearby` tool is attached **only while that record exists**. Same discipline as the
file tool: the schema is 548 tokens, and outside this flow it is never sent, so the
feature costs nothing on ordinary traffic. The short TTL is deliberate — someone driving
is somewhere else half an hour later, and answering "nearest fuel" from a stale
coordinate is a confident wrong answer.

**The model supplies the OSM tag, the code builds the query.** `categories` arrives as
`amenity=fuel`, `shop=supermarket` and is validated by `_TURKUM_RE` before it goes
anywhere near Overpass — model output is an untrusted boundary, and a category pasted
straight into the query string could restructure it. That split is also why there is no
hardcoded category list: the model knows OSM tagging, so "shinamontaj" and "bolalar
maydonchasi" work with no extra code. The coordinate is *never* a tool parameter — it
comes from the chat. A model-written coordinate would be invented, exactly like the map
marker problem.

**Mirror order is measured, not guessed** (`services/places.py`, 2026-09-10). The three
well-known Overpass instances answered in 22-40s or failed outright — 4 of 11 test
queries succeeded. `maps.mail.ru` answered the same queries in 1.6-4.9s, and holds full
planet data: verified in Tashkent, Samarkand (14 fuel stations), Namangan (nearest
pharmacy 247 m) and Nukus. It is first, the others are backup, and all are raced in
parallel.

⚠️ **An empty answer does not win that race.** `overpass.osm.ch` replies in 0.8s with
zero results because it only holds a Switzerland extract — first-success-wins would have
let it beat the slow-but-correct mirrors and the bot would say "nothing nearby" in a city
full of pharmacies. It is deliberately not in the list, and an empty result is now only
accepted once every mirror has answered. Test any new mirror on an *Uzbek* coordinate.

**The route link is built in code, never by the model.** `format_places()` appends a
ready `https://yandex.uz/maps/?rtext=~lat,lon&rtt=auto` to the nearest `ROUTE_LINKS_FOR`
(3) places and the tool description tells the model to copy it verbatim into
`[tugma: Yo'nalish | …]`. Same lesson as image URLs: a URL handed to the model comes back
rewritten and dead. Only the top three get one — a link is ~25 tokens and the model only
ever buttons the nearest.

**"Nothing found" and "the source did not answer" are different answers.** `find_nearby`
raises `PlacesUnavailable` rather than returning `[]`, and `_run_nearby_task` turns that
into an explicit instruction to tell the user it is a technical fault — because
"there is nothing near you" would be an unverified claim presented as fact.

**A location enters the conversation as a message, not as a canned card.** The first
version answered a location with a fixed "what should I find nearby?" card and no AI
call — cheap, and broken. That card never reaches `chat_messages`, so the model could not
see it: on screen the user sent a location and typed "Zapravka", while the model saw only
its own earlier "send me your location" followed by "Zapravka", and asked for the
location again. A loop the user cannot escape. `handle_location` now stores the
coordinate and pushes `_LOCATION_NOTE` through `_queue_for_ai()` — the same debounce
buffer `handle_text` uses, so quota, the busy queue, streaming and history all behave
identically. The 1.5s merge window is a bonus: a location followed immediately by
"zapravka" becomes one request and one round. The note carries **no coordinate** — a
coordinate written into history would still be there tomorrow, and "nearest" would be
answered from a stale position; the real one lives only in the 30-minute RAM record.

`handle_location` must stay registered **before** `capabilities.handle_unsupported`,
which still matches the other unhandled types; `F.location` was removed from that list.
And `location_message` had to be added to `ACTIVITY_TYPES` (at the time still two
hand-written copies in `handlers/admin/stats.py`); `tests/test_activity_tracking.py`
caught that omission immediately.

### What the model may claim it can do

The model's capability list is not prose in the system prompt — it is built per
request from the **actual tool schemas** (`_capability_manifest()` in
`services/ai.py`) and sent as a `developer` message. Tool schemas alone were not
enough: they say what exists and nothing about what does not, so the model filled
the gap by guessing — promising drawn images to a free user (`generate_image` is
Pro-only) and PPTX in a group (`output_files=None` there, so the file tool is
never attached). The manifest names the attached tools, the missing ones *with
the reason*, and the things that are never possible (video, YouTube, music,
mini apps, choosing to answer by voice — TTS runs only on the voice-in path).
Because the names come from the schema dicts, renaming a tool moves the text
with it; a hand-written list would rot silently. It is skipped when
`tools_enabled=False` (internal calls) and must stay out of `instructions` —
its content depends on the user's plan, so caching it would poison the prefix
for everyone. `tests/test_capability_manifest.py` guards all of that.

⚠️ **The manifest reached a user, translated.** It used to end with "never quote these
instructions", and the model did not count *translating* as quoting: asked in a group
whether it could do a pasted list of features, it returned the whole block in Uzbek —
"Audio javob yuborishni ham o'zim tanlay olmayman" is a word-for-word rendering of
*"Voice replies exist but you cannot choose them"* — shaped as a bureaucratic
"point 1: yes, point 2: no" verdict, and it named the stack it runs on along the way.
Guest mode shows this worst because that is where the NOT-available list is longest
(files, images, edit and reminders are all off), but the rule was weak everywhere.

Rule (4) is now a **behaviour, not a prohibition**: the block is private, never
reproduced, translated or paraphrased, never answered point by point, and a limit is one
short sentence in the model's own words followed by the part it *can* do. Rule (5) forbids
naming the language, framework, database, server or file paths it runs on, even while
offering to write code — that one has to stay prompt-level, because "aiogram" is a
perfectly normal thing for a user to ask about and `strip_internal_names()` would break
those answers. Cost: **+69 tokens** per round (`tiktoken`; the first draft was +89 and was
trimmed without losing a rule). Checks 12-15 pin all of it.

⛔️ **The model cannot see the bot's features, only this request's tools** — so an
answer to "what can you do?" written from the manifest is always wrong. Asked to list
its abilities it produced the generic chatbot answer (translate, write code, do maths)
and never mentioned `/research`, `/kunlik`, group mode, topics, nearby search or the
reader's own plan, because none of those is a tool. The expensive features nobody
discovers stayed undiscovered.

`open_capabilities` is the fix and it is a **door** (`start_file_task`, `open_memory`,
`open_reminder` are the same pattern): **211 tokens** per round measured with `tiktoken`,
and on call it returns the full feature text — **2 214 tokens** (free plan; 1 767 before the Business section), paid only when someone
actually asks. It is attached on every request including guest, because the question is
asked in groups too and that is exactly where the model's own knowledge is thinnest
(files, images, memory and reminders are all off there). `imkoniyat_rounds < 1` caps it
at one call: the text never changes, so a second call is ~2 000 tokens for nothing.

⚠️ **The text comes from `handlers/capabilities.py::SECTIONS`, the same dict `/help`
renders** — `model_uchun(is_pro)` strips the HTML and adds the reader's plan. A second
hand-written list is the mistake this repo has made five times (see "Five label maps");
here it would also mean the screen and the model describing the same bot differently.

A first attempt intercepted the question in `handle_text` with a phrase list and opened
`/help` directly. It cost no tokens and was **the wrong shape**: it answered "list
everything" and nothing else, so "lokatsiya yuborsam nima bo'ladi?" still reached a model
that did not know the answer, and no follow-up question worked. The door makes the model
*knowledgeable* instead of routing around it. `/help` stays as the command and the
`/start` button — it has buttons and copyable examples, which a chat reply does not.

⚠️ **The screen states the reader's own plan.** It used to say "3 on free, 20 on Pro"
everywhere, which a free user reads as *their* number, and the Pro section listed image
generation and reminders with no indication they were locked — so people asked for them
and were refused. `body` and `note` may now be a callable taking `is_pro`, and
`database.pro_tarifmi()` supplies it: display only, never a gate, and its condition is
copied from `check_and_consume_quota()` (plan ≠ free **and** not expired) because a
screen that says "open" while the bot says "no" is the worst kind of complaint.
`tests/test_capabilities.py` checks 12-14 hold all of it, including that the door sits
above the bare `else` (below it, "nima qila olasan" becomes a DuckDuckGo query) and that
every section renders under **both** plans — a forgotten callable would otherwise raise
only in a live chat.

### The model can draw a real button, not describe one

`[tugma: Label | https://…]` becomes `<tg-button type="url">` inside a
`<tg-button-row>`. Before this the only path to a Telegram button was code, so
"show me what it looks like" could only ever be answered with words. Same
discipline as the other markers: only `http(s)`, a malformed marker is dropped,
code blocks are untouched, and `strip_rich_tokens()` degrades it to `Label: url`
for the draft and the plain fallback. `callback_data` is deliberately not
offered — a model-invented callback has no handler and would be a dead button.

⚠️ `_RICH_PROTECT_RE` matches `https?://[^\s\]]+`, not `\S+`: the old pattern
swallowed the `]` that closes the marker, so the button never formed. A literal
`]` does not occur in a real URL (it is `%5D`).

Tables are **allowed** and the prompt says so. `_compact_tables()` turns GFM
into a real `<table compact>` (2-20 columns, separator row required). The prompt
used to forbid tables outright, which is what produced space-aligned
pseudo-tables that look fine on screen and lose all structure when copied.

⚠️ **`compact` is not a layout control** — aiogram's own field doc for
`is_compact` reads *"True, if table cells have smaller indents"*, nothing more.
It does not wrap, scroll or size columns, so reach for the prompt, not this
attribute, when a table reads badly. A live complaint ("compare two cars")
produced a tall unreadable strip because the model wrote whole sentences into
cells and the old rule said only "2 to 20 columns" — which reads as permission
for 20. The prompt now caps it at 2-4 for a phone and states that a cell is a
value, not a sentence.

A second live test ("tabulate 5 BMW models") exposed three more things the first
pass got wrong or missed. **Orientation is not fixed**: "one row per property,
one column per item" was shipped and is wrong whenever there are many items —
5 cars x 3 specs is 5 rows and 4 columns, and the rule as written asked for 6.
The rule is now "whichever side has FEWER members goes on the columns".
**Units belong in the header**, not repeated in every cell: "290 km/soat" wrapped
onto three lines where "290" under a "Tezlik (km/h)" header would not.
**Headers must be 1-2 short words** — "Maksimal tezlik" was broken *mid-word* into
"Maksi/mal/tezlik" on a phone. Total cost of the table rules: +186 tokens per
round, measured, against the ~1M/day the door tools saved the same day. `is_bordered`,
`is_striped` and `caption` also exist on the API type and are **unused**; the
HTML attribute spellings are not documented (`_EXPANDABLE_ATTR` is the standing
warning that field name ≠ attribute name), so adding them needs a live send
test before shipping — a wrong attribute gets the whole message rejected.

### `$` means two things, and the bot talks about prices

The prompt makes LaTeX mandatory and allows **only** `$…$` and `$$…$$` as delimiters, so
the math pass cannot simply stop honouring `$`. But this bot quotes prices constantly, and
a live answer (a CS2 agent price table, 2026-09-13) arrived with raw `</td></tr><tr><td>`
rendered in serif italic *inside a table cell*: `$85` opened a math span, the next cell's
`$72` closed it, and everything between — the table HTML `_compact_tables()` had just
produced — became `<tg-math>`.

Two independent defects, both now guarded by `tests/test_rich_markdown.py` checks 23-26:

- `_RICH_MATH_INLINE_RE` carried `re.S`, so an unclosed `$` ran across the whole answer;
  three bullet points of a price list were swallowed into one span. Inline math never
  spans a line — the flag is gone, and it must stay gone.
- `_looks_like_math()` accepted anything with a digit and a letter, which is every price
  sentence *and* every HTML fragment (`<`, `>`, `/` were in its `math_chars`). It now
  rejects an expression containing an HTML tag, and rejects prose — a 3+ letter word
  after LaTeX commands (`\frac`) and `{…}` groups are stripped out, so `v_{max}` and
  `\sin(x)` still count as maths while "85 dan 72 gacha" does not.

⚠️ Do not "fix" this by reordering the pipeline. `_compact_tables()` runs **before** the
math pass deliberately, and the comment above it says why: `_cell_html()` html-escapes cell
text, so a `<tg-math>` built earlier would reach the reader as literal text.

### The wait after the answer needed its own indicator

A voice question produces the text answer first, then 5-10 seconds of TTS synthesis. That
window was **completely silent**: the user read the reply, the bot went quiet, and the
voice note landed unannounced. `handle_voice` did call
`send_chat_action(chat_id, "record_voice")` — and it worked; it simply isn't enough,
because Telegram shows a chat action for **5 seconds** and the synthesis outlasts it.
Reach for `_status_indicator()` rather than a second `send_chat_action` for anything
slower than that.

`_status_indicator(message, kind)` is an async context manager that runs the same
animation `process_stream_draft()` shows, but *after* the answer has been sent: a rich
draft with `<tg-thinking>` in private chats, a plain edited message in groups (drafts are
private-chat-only), keyed by `STATUS_TEXTS_BY_TYPE["tts"]`.

⛔️ **Both rungs are cleaned up on exit and that is the whole risk of this feature.** The
draft is overwritten with empty markdown, the plain message is deleted (and, if the delete
is refused, edited to "✅" so no false "preparing…" line survives). An abandoned draft has
already cost this project once — it hung on screen and killed the next animation
(`BOT_API_103.md`). Cleanup runs from `finally`, so a synthesis failure cleans up too, and
the `await task` there catches `CancelledError` explicitly — it is a `BaseException` and
`except Exception` would let it escape and swallow the finished audio.

Clearing the draft by overwriting it with empty markdown **is verified live**
(2026-09-14): the indicator disappears when the voice note arrives, leaving no ghost
bubble. If one is ever reported after a voice answer, that call is still the place to
look.

`_thinking_html_for()` / `_thinking_plain_for()` / `_status_texts_for()` and the four
timing constants were lifted out of `process_stream_draft()` to module level for this;
they must stay shared. A second copy would drift and the bot would animate two different
ways in two places.

And `handle_voice` now says something when synthesis fails. There was no `else` on
`if generated_audio …`: the bot promised a voice reply and went silent forever, with the
user still waiting. Silence is the worst failure mode — the text answer is already
delivered, so one line saying so is enough.

### A URL must never be spoken

`clean_text_for_speech()` is the single gate every voice reply passes — free (edge-tts /
Gemini) and Pro (OpenAI TTS) both call it, so the fix for anything audible belongs there
and never in a caller. It used to strip only `*_#>` via `_MD_MARKERS_RE`, which leaves
square and round brackets alone: a live complaint (2026-09-14) had the bot reading
`[kun.uz](https://kun.uz/news/2026/09/14/…)` aloud, URL and all, at the end of every
searched answer.

Three steps now enforce one rule — a link is something you tap on screen and pure noise in
speech: the trailing sources block is dropped entirely, `[name](url)` collapses to `name`
so the meaning survives, and any bare URL left in the body is removed. Footnote markers
(`[^1]`) go too, for the same reason.

`_sources_tail()` is the shared detector behind both consumers — `_collapse_sources()`
wraps the block in a collapsible quote for the screen, the speech cleaner deletes it. Its
`min_items` differs by design: the screen keeps a single source visible (hiding one link
only makes it harder to find) while speech drops even one, since one URL read character by
character is already the whole complaint. Keeping one detector matters because the model
decides how it formats sources; two regexes would drift and one would rot silently.
`tests/test_voice_fallback.py` checks 10-15 cover both sides, including that the screen
output is unchanged.

### Inline button styles

Telegram accepts only `primary` / `success` / `danger` on a real `InlineKeyboardButton`. Any other value is rejected and **the whole message fails to send**. Use `pro_module.btn()` and the `BTN_*` constants. Where delivery matters, build a plain fallback keyboard too — `pro.send_rich()` degrades progressively, and the broadcast sender switches the entire run to plain on the first rejection.

`BTN_LINK` ("link") is the exception: it exists only for `<tg-button>` **inside a rich message** and only on callback buttons. `btn()` deliberately does not accept it.

`btn(disabled=True)` (Bot API 10.3) renders a visible but dead button. `disabled` **is** the button's type field, so `callback_data`/`url` must not be sent with it — and `_downgrade_kb()` has to carry it through, otherwise the fallback keyboard produces a typeless button and the whole message is rejected.

Buttons can also live inside the message body via `pro_module.rich_button()` / `rich_button_row()` (`<tg-button-row>`, 1-8 per row). These are HTML in the `markdown` field, so their text must be escaped — the builders do it. Escaping quotes is not enough: `html.escape()` leaves newlines alone, and a raw newline inside an attribute makes Telegram's parser cut the tag off there and print the rest as literal text. `_attr_value()` turns them into `&#10;`, which the client resolves back to a real newline when the value is used — that is what makes "copy" work on a multi-line snippet.

### The command menu is decoration, not a gate

`services/menu.py` sets the `/` list per chat (`BotCommandScopeChat`), so Pro
commands appear on purchase and vanish when the plan lapses. The free list is
set once at startup for all private chats; the per-chat scope overrides it,
which is why `/start` needs no extra DB read.

The menu can always be stale — a user can type `/kunlik` without opening it, and
expiry is only detected on the user's next message. The real check stays in the
handler. Adding a Pro command = one row in `PRO_COMMANDS`; `tests/test_menu.py`
asserts every listed command is actually registered.

`sync_menu_button()` in the same file is the blue Mini App button, set per chat the
same way and for the same reason — and it is decoration too (see the web panel section).
It is called on `/start` for **everyone**, not just admins, so a demotion that happened
while the bot was down still removes the button on the next `/start`. With `WEB_APP_URL`
empty it does nothing at all, so a deployment without a domain behaves exactly as before.

### Telegram limits worth knowing here

- Bot API cannot download files larger than 20 MB — that is why `DOCUMENT_MAX_SIZE_PRO` is 20 MB and not higher.
- `XTR` invoice amounts are the star count directly, **not** multiplied by 100. `tests/test_pro_payload.py` locks this.

### Sandbox

`services/sandbox.py` runs model-written Python with a scrubbed environment (no `BOT_TOKEN`, `OPENAI_API_KEY`, `DATABASE_URL`), a fresh temp cwd, a 60s timeout and RLIMITs on Linux. **Network is not blocked** — Railway offers no container isolation; the mitigation is that there are no secrets to steal and the timeout caps abuse.

`services/sandbox_helpers/` must stay next to `sandbox.py`; it is located via `Path(__file__).parent` and copied into each run.

**Two limits in `_apply_limits()`/`_build_child_env()` are load-bearing and only bite on Linux** (`_HAS_RESOURCE` is `False` on Windows, so local runs never see either). Memory is capped with `RLIMIT_DATA`, never `RLIMIT_AS`: `AS` counts *reserved address space*, and numpy/pandas/matplotlib/pptx reserve gigabytes they never touch — a 2 GB `AS` cap made `import pandas` itself raise `MemoryError`, and a different library failed each run. Separately, `OPENBLAS_NUM_THREADS=1` (with the `OMP_`/`MKL_`/`NUMEXPR_` twins) is required because `nproc` inside a container reports *host* cores; OpenBLAS then sizes a buffer per thread and dies with "Memory allocation still failed". These are not `PYTHON*` vars, so `-E` leaves them alone. `sandbox.check_libraries()` runs at startup and logs any library that will not import — without it, a broken import is invisible: the model just falls back to PDF and the user silently gets the wrong format.

Both helpers there exist for the same reason: the model composes documents by hardcoding coordinates and never measures what it placed. `docgen` owns text metrics for PDF; `deck` owns slide geometry for PPTX (safe margins, aspect-preserving image fit, a reserved footer band, a reserved caption line for image credit). Before `deck`, the three failures were always the same — picture over text, credit over picture, page number over picture. The tool description makes `deck` mandatory for PPTX and explicitly scopes the older manual-layout rules to PDF/DOCX/XLSX, because two sets of layout instructions produce worse output than one. `tests/test_deck_layout.py` asserts no two content shapes intersect — it already caught a 0.1" clash between the section number and its heading.

`deck` also owns image *placement*, not just geometry: `Deck(images=[...])` is a pool and every layout's `image` defaults to the `AUTO` sentinel, so photos spread across the whole deck. This exists because the model reads "put a picture on the first slide" literally and leaves every other slide bare. `image=None` is the explicit opt-out — that is why `AUTO` cannot simply be `None`. Side-by-side layouts put text and picture in frames of identical size and top, the picture cover-cropped to fill its frame exactly, so image scale never wanders between slides. `image_slide` is the opposite case — cropping a map or a chart destroys it — so there the picture is fitted whole and the card is then shrunk to hug it with fixed padding; the box it is given is only a bound, never the drawn frame. Caption and credit are positioned off the returned rect, not off that bound.

The tool description promises the model there is **no internet** inside the sandbox, and that promise is what makes generated code deterministic — a model asked to fetch a photo invents a URL, and invented URLs are dead. So photos for documents arrive the other way round: the model lists what it needs in `image_queries`, `_run_file_task` downloads and converts them **before** the run, and `run_in_sandbox(extra_files=...)` drops them in the work dir as `rasm1.jpg`, `rasm2.jpg` — positional, one per query, a missing one still burns its number so the rest don't shift. They are cached per user request, because the file loop reruns up to 4 times and a second download would hand the model *different* photos than the caption it already wrote. Everything is re-encoded to JPEG via Pillow: most DuckDuckGo image results are WEBP and python-pptx rejects WEBP.

## Other agent configs

A Codex config exists at `~/.codex/config.toml`. Reply `/import` to scan and list what is importable (MCP servers, slash commands, subagents, skills, instructions), then `/import --yes=<digest>` — the scan output names the digest — to apply the user-level items.
