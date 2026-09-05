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

No test framework, no linter, no build step. Each `tests/test_*.py` is a standalone `assert`-based script with numbered `print("[N] ... OK")` lines and a final summary. New tests follow that shape. On Windows, prefix with `PYTHONIOENCODING=utf-8` — some tests print emoji and the console codepage will otherwise raise `UnicodeEncodeError` (a false failure, not a real one).

Run the whole suite by looping over `tests/test_*.py`; `test_pro_security.py` is the slow one.

## Deploy

Railway, project `amused-endurance`, service `bot`. **This Railway account has no GitHub connection**, which has two consequences:

- `git push` does *not* trigger a deploy.
- A plain deploy call rebuilds the snapshot taken when the service was created, i.e. old code.

Deploys must name the commit explicitly via the Railway GraphQL API:
`serviceInstanceDeployV2(serviceId, environmentId, commitSha)` against `https://backboard.railway.com/graphql/v2` with a team token. The repo `afiffamily/1` is public, so Railway fetches it without GitHub auth. The `up` endpoint (local tarball upload) fails on this account. Connecting GitHub in Railway settings would remove all of this.

## Architecture

`BOT_API_103.md` is the long-form companion to this file: everything added with Bot API 10.3 and after, explained in full — including the decisions that were **tried and reverted** (the interim "preparing your file" message, the sources slide). Read it before re-attempting anything in that area; this file only carries the rules.

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

`get_openai_reply()` streams from the Responses API and runs a tool loop with **per-tool round budgets** (`MAX_SEARCH_ROUNDS`, `MAX_FILE_ROUNDS`, `MAX_IMAGE_ROUNDS`, `MAX_MEMORY_ROUNDS`, `MAX_REMINDER_ROUNDS`, plus `MAX_TOTAL_ROUNDS`). When a budget is spent the tool is dropped from `active_tools`, forcing the model to answer.

Tools: `internet_search`, `run_python_sandbox`, `generate_image`, `update_memory`, `manage_reminder`.

**Dispatch order matters**: the `else` branch routes any unknown tool name to web search, so every named tool must be an `elif` *above* it — otherwise "menga rasm chiz" silently becomes a DuckDuckGo query.

**A tool that quietly returns nothing is how the context explodes.** Images are searched once per request — re-running would shift catalogue numbers under a `[rasm:2]` the model has already written — but the repeat call still re-emits the same catalogue. Returning silence taught the model "no images found", so it searched again, and again; each round appends full page text, and by round three the request hit OpenAI's 200k TPM ceiling and the whole answer was lost after 50 seconds of work. Any budget that drops a tool must say so in the tool output.

`RateLimitError` arrives **mid-stream**, not when the stream opens: the SDK sends the request on the first iteration, so `_open_response_stream()`'s fallback ladder never sees a 429 and the answer died outright. The round is retried once after `RATE_LIMIT_RETRY_DELAY` — but only if no text has been yielded yet, otherwise the user would see the start of the answer twice.

**Pro gating is done by omission**: `image_enabled = ... and is_pro`, `reminder_enabled = is_pro and user_id is not None`. Free users never see the schema, so no tokens are spent advertising a tool they cannot use. Flipping a feature to free-with-upsell means removing `is_pro` from that condition; the task functions already validate independently.

`get_vision_reply()` is a **separate, single-round** path — the memory tool call is harvested after the stream and its result is not fed back. Adding a full loop there means porting the `pending_calls` block.

`[CLEAR_TEXT]` travels through the same chunk stream as content and is emitted **after every** tool round, throwing away the model's pre-tool chatter so it doesn't stick to the final answer. The condition used to exclude repeat searches, and the leftover text then glued itself to the next round's — users saw two "…tayyorlayapman" sentences in one message. Reaching that point already means a tool ran (`if not got_function_call: return` above it), so no condition is needed.

While a file is being built the screen shows **only the status animation** — nothing the model wrote before the tool call reaches the user. Sending that preamble as an interim message was tried and reverted: it left a half-drawn draft bubble next to the real one, and the abandoned draft killed the spinner for the whole 1-2 minute wait. If you try it again, the draft must be overwritten or closed before a real message is sent, not simply replaced with a new `draft_id`.

### Photos: two separate pipelines that must not be confused

A photo in a **chat reply** and a photo **inside a document** share nothing but the search call, and mixing them up is the failure mode users actually hit.

- **In chat**: `internet_search(want_images=true)` searches, validates each URL is live, and stores the hits in `images_out`. `images_only=true` is the same path with the web search skipped entirely — it exists because a picture used to be possible only when the model happened to search, so any answer written from the model's own knowledge arrived with no image at all. It still spends a `search_rounds` slot (otherwise the model can ask for pictures forever), it implies `want_images` in code because the model forgets one of the two, and it never injects `_SYNTHESIS_SYSTEM` — that prompt demands a sources list, and an images-only call has no sources. The URL is deliberately **never shown to the model** — it costs 30-60 tokens each and the model rewrites them into dead links. The model only sees `[rasm:1]` / `[rasmlar]` tokens (~25 tokens total); `embed_images()` swaps them for real media blocks just before sending — one image as a bare block, 2 to `SEARCH_IMAGE_COLLAGE_MAX` as a `<tg-collage>` (all on one screen), more than that as a `<tg-slideshow>`. A collage carries a single caption, so its inner blocks are built without one and every source goes into one `<figcaption>`: the photo is someone else's and the credit is not optional, and `strip_image_tokens()` scrubs them from every fallback path and from the streaming draft. Telegram fetches the URL itself — nothing is downloaded.
- **In a document**: see the Sandbox section. Bytes, not URLs.

The routing between them is prompt-level and fragile: adding the word "rasm" to the file tool's description was enough to make *every* request ("olma haqida ma'lumot ber") turn into a file task. Both tool descriptions now carry an explicit ⛔️ pointing at the other one, and `IMAGE_CAPABILITY_NOTE` in the system prompt exists because the model would otherwise answer "I can't send pictures" without calling any tool at all. That note is added **only** in `get_openai_reply` — `get_vision_reply` has no search tool, so promising it there would be a lie.

**Wikimedia Commons is the primary image source, `ddgs` only the fallback**, and `search_images()` tries each source *separately* — Commons returning hits is not enough, its links must also survive. On the server DuckDuckGo's image endpoint answers `403` (datacenter IP) and `ddgs` silently switches to Bing, whose results were not merely worse but unrelated: a "Hongqi H5 Classic" request returned Roblox avatars. Filtering Bing is unwinnable — a generic word like "classic" always matches something — which is why the source moved rather than the filter tightening. Commons also never IP-blocks and its images are freely licensed, which matters for the student presentations this bot is used for.

Two things about Commons are load-bearing. It matches *literally*, so "Hongqi H5 Classic" returns nothing while "Hongqi H5" returns dozens — `_images_sync()` walks the query down to 3 words, then to 2. Both steps are needed: "Hongqi H5 new model" trimmed to 3 is still "Hongqi H5 new", which also returns nothing, and the user simply gets no picture. And `upload.wikimedia.org` is in `_TRUSTED_IMAGE_HOSTS`, so its URLs skip the liveness probe entirely: the API already guarantees they exist, while ten parallel probes earn a `429` that made live images look dead (10 candidates collapsed to 1).

The query itself is separated too. A web query is written for articles (`site:`, long phrases, figures) and is useless against an image index, so `internet_search` takes an optional short English `image_query`, and `image_query()` strips operators and bare numbers from the fallback — but **not four-digit years**: "Hongqi H5 2025" and "Hongqi H5" are different cars, and dropping the year is how a request for the new model kept returning the same old photo. `_image_relevant()` then requires one meaningful query word in the title/URL/source — when nothing matches, **no image is sent at all**, because an unrelated photo on a slide is worse than an empty one.

`[rasm:N]` is valid **only inside the reply that produced the catalogue**, so `safe_update_history()` strips image tokens before anything reaches `chat_messages`. A token left in history reads to the model as still-live: on "rasm yubor" it would re-emit `[rasm:1]` instead of calling the tool, `embed_images()` would silently drop it, and the user got an empty answer — or, compensating, a bare link. Both the catalogue text and `IMAGE_CAPABILITY_NOTE` now say outright that a link never substitutes for a picture and that every repeat request needs its own search.

Image search runs with `safesearch="on"` (`SEARCH_IMAGE_SAFESEARCH`); the library default `moderate` was not enough for a bot with no age gate.

### A failed send is not the same as a rejected send

`_telegram_api_request` reports *why* a call failed through an `outcome` out-param: `OUTCOME_REJECTED` (Telegram answered `ok:false`) versus `OUTCOME_UNKNOWN` (timeout, connection reset). The rich-message fallback ladder retries in a plainer form **only** on REJECTED. On UNKNOWN it gives up silently, because the message may well have arrived.

This exists because the shared aiohttp session caps every call at 10s — right for the 0.6s draft pings it was tuned for, wrong for a rich message carrying image URLs, since Telegram fetches each image from the source site before it creates the message. The client timed out, the ladder concluded "rejected", re-sent without images, and Telegram delivered both: users saw the same answer twice, once with photos and once without. Media sends now get `RICH_MEDIA_TIMEOUT` instead.

### Splitting a long answer must not cut a construct in half

`_split_for_telegram()` breaks answers at a limit that depends on the send path — `MAX_RICH_CHARS` (30000, rich messages cap at 32768) or `MAX_PLAIN_CHARS` (4000, `sendMessage` caps at 4096) — and the cut point lands wherever the last newline or space happens to be. Three constructs cannot survive that cut and are handled explicitly: an open code fence is closed and reopened with its language on the next part, and `_safe_cut()` moves the boundary *before* a markdown link and *before* a footnote pair. Splitting `[OLX Uzbekistan](https://…)` in the middle leaves both halves as literal text — that is how a sources list once reached a user as `• [OLX` followed by `Uzbekistan](https://…)`. A footnote is the same shape with its halves far apart — `[^1]` sits in the text, `[^1]: …` at the very end — so `_safe_cut()` takes the whole remaining text, not `rest[:limit]`, or the definition beyond the limit would be invisible to it. Anything else added to answers with paired syntax needs the same treatment. `==marked==`, `<sub>`/`<sup>` and `- [ ]` need no code at all: Telegram renders them and `build_rich_markdown()` passes them through untouched — they are prompt rules only.

A collapsible section is the one construct the model does not write itself: it writes `[batafsil: Title] … [/batafsil]` and `build_rich_markdown()` turns the pair into `<details>`, inside `_protect_spans()` so a marker in a code block stays text. Same reason as `[rasm:N]` — a malformed marker is dropped, malformed HTML gets the whole message rejected. An unpaired marker is therefore discarded, and a nested one is flattened. A pull quote works the same way: `[iqtibos: the words | who said them]` becomes `<aside>…<cite>…</cite></aside>`, the author half optional. Markdown is not parsed inside `<aside>` (only `<details>`, `<tg-collage>` and `<tg-slideshow>` parse it), so both halves are html-escaped there — unlike a `<details>` body, which stays markdown. The draft and the plain fallback are not rich, so `strip_rich_tokens()` renders both markers as plain text there (bold heading, «quoted» line); it sits beside `strip_image_tokens()` at the same two call sites.

A part cut to the rich size cannot be handed to the plain fallback as-is: when a rich message is rejected, the part is re-split with `MAX_PLAIN_CHARS` before `_answer_plain()`. Skipping that loses the whole answer — worse than the small limit it replaced. `push_update()` likewise trims the draft (rich) and the plain waiting message to different limits, since the draft can degrade to the latter mid-stream.

### Prompt caching constrains where text goes

`build_system_prompt()` is written to day precision so the prefix is identical all day and prompt caching works. Anything per-user (long-term memory, the user's name) goes into `messages` as a `developer` message, **never** into `instructions`. Putting user-specific text in the system prompt silently destroys the cache for everyone.

### Model list is a billing guard

`GPT_MODEL` and `MODEL_FALLBACKS` must stay inside OpenAI's free data-sharing list. A model outside it bills at full price and nothing warns you — the bill arrives at month end. `tests/test_free_models.py` guards this.

### Quotas: two independent systems

- **Points** (`check_and_consume_quota`) — the daily budget; cost varies by message kind and reasoning effort (`message_cost()`).
- **Daily counters** (`DAILY_COUNTERS` → `check_and_consume_daily`) — separate counts for `files`, `images`, `research`. These are the expensive operations; billing them to the points budget meant three files exhausted a user's whole day and read as "the bot broke".

`services/file_task_quota.py::DailyQuota` charges **once** per user request no matter how many times the model calls the tool, and refunds if nothing was produced.

`unlimited=True` means "nothing was deducted, do not refund" (admin/premium). Returning it for Pro would break every refund guard — `tests/test_plan_limits.py` asserts this.

Adding a new counter = one row in `DAILY_COUNTERS` + two DB columns. Nothing else.

### Model output is an untrusted boundary

Whatever the model writes into a tool call reaches the database. Validation lives in `db/database.py`, never in the tool `description` — an instruction is not a guarantee:

- `clean_memory()` strips newlines (a multi-line memory renders as fake instructions in the developer message) and rejects card/passport/account number patterns.
- `parse_run_at()` rejects past times, unparseable strings and dates beyond `REMINDER_MAX_AHEAD_DAYS`.
- Every `UPDATE`/`DELETE` driven by a model-supplied index carries `AND user_id = $N`; the index is bounds-checked against the list actually shown to the model *before* touching the DB (note `isinstance(idx, bool)` — `True` is an `int` in Python).

### Two kinds of memory

- **Conversation history** (`db/history.py`, `chat_messages` table + RAM cache) — context. Stored to `CONTEXT_WINDOW_PRO` for everyone; the tariff only changes how many are *read* (free 50, Pro 150), so switching plans needs no migration. `/new` clears this.
- **Long-term memory** (`user_memories`) — facts the model chose to keep, category-prefixed (`ism:`, `kasb:`, …). Survives `/new`. Available on every tariff.

History used to live in SQLite; Railway wipes the container filesystem on every deploy, so each deploy reset every user's context. It is Postgres now — do not move it back to a file.

### Guest mode

`handlers/guest.py` handles chats outside DMs via `guest_message`. It passes `caller_user_id` as **both** `chat_id` and `user_id`, so a person has one identity and one memory whether they write in a group or in the DM. Quota is charged to that user. Reminders are delivered to the DM regardless of where they were created.

### Activity types must be registered twice

Anything written to `user_activity` must also appear in the SQL filter and `type_labels` in `handlers/admin.py`, or it silently vanishes from admin statistics. `tests/test_activity_tracking.py` guards this.

### Premium emoji in the answer text

`build_rich_markdown()`'s last step swaps the emoji listed in `TEXT_CUSTOM_EMOJI` (🤖 📄 🧠 ⏰ 🧹 ✍️) for their animated form, `![ ](tg://emoji?id=…)`. The space in the alt text is required — `![](…)` can be read as a media block. It runs last because it must see the HTML the earlier steps produced: markdown is not parsed inside a table cell or an `<aside>`, so `_MD_DEAD_ZONE_RE` skips those regions and the plain emoji stays there (code blocks are already out via `_protect_spans()`). `TEXT_CUSTOM_EMOJI_MAX` caps the count — each swap costs ~40 characters against the 32768 limit.

Custom emoji in text requires the bot owner to hold Telegram Premium, and a lapsed subscription makes Telegram reject the **whole message**. So the downgrade rung strips them: `plain_md` now goes through `strip_custom_emoji()` as well as `strip_image_tokens()`, and the flag deciding whether to retry is `bezakli` ("has media *or* premium emoji"), not `has_media`.

### A map is drawn from a marker the model writes

`[xarita:41.3111,69.2797,13]` becomes `<tg-map lat=… long=… zoom=…/>`. Coordinates come from the model — no geocoding, which would add a network call, a rate limit and a failure point. The code validates only the *ranges* (lat −90…90, long −180…180, zoom 1…20) and drops the marker when they fail; it cannot validate the *place*, since 41.9/12.5 is Rome and 41.3/69.3 is Tashkent and both look fine, so accuracy is the prompt's job. `<tg-map/>` is self-closing — written as `<tg-map></tg-map>` it gets the whole message rejected, which is exactly why the tag is emitted by code and not by the model. Like premium emoji, it is skipped inside table cells and `<aside>` via `_outside_dead_zones()`.

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
