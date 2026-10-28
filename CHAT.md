# CHAT.md

The chat pipeline — `services/ai.py`, `handlers/messages.py`, `handlers/guest.py`,
`db/history.py`, `services/sandbox.py`, `services/places.py`, prompts, tools, voice. Moved
out of `CLAUDE.md` on 2026-10-28, when that file reached ~35 000 tokens loaded on every
session. `CLAUDE.md` keeps one line per section ("Where the long-form rules live"); the
reasons, the measurements and the bugs that paid for each rule are here, word for word.

### Token budget

The bot runs on OpenAI's free data-sharing grant. The dashboard lists two buckets — ~250k tokens/day for the big models (gpt-5.4, 5.2, 5.1, 5, 4.1, 4o, o1, o3) and ~2.5M/day for the mini/nano ones — but **the 5.6 family is not on that list, and the owner confirmed (2026-09-29) that `gpt-5.6-luna` is free up to 2.5M/day**. Do not "correct" this to 250k from the dashboard text; `TOKEN_KUNLIK_GRANT` is 2.5M for that reason. Before the September 2026 work the dashboard showed **20.307M input tokens over 8 days — 2.54M/day, i.e. 101% of the grant on an average day and 248% on the busiest one**; the excess is billed at standard rates, and nothing errors or falls back when the grant runs out.

⚠️ **Caching does not reduce that count.** OpenAI support confirmed (2026-09-09) the complimentary allowance is a *token quota*, not a discounted rate: cached and uncached input count the same. Caching only changes money, which matters once you exceed the grant. So the only lever is fewer tokens per round.

Nearly all of it is fixed overhead, not user text. Measured with `tiktoken` (`o200k_base`) — never estimate from character counts, that was 11% off:

| | free | Pro |
|---|---|---|
| `instructions` (prompt + concise + image note) | 5 521 | 5 521 |
| tool schemas (all doors closed) | 2 264 | 2 637 |
| capability manifest | 495 | 445 |
| **fixed total per round** | **8 280** | **8 603** |
| history | 0 → ~8 200, then capped by the summary (~300) | |
| median user message | ~10 | |
| median reply | ~70 | |

Re-measured 2026-09-30 by capturing the real request (`_open_response_stream` faked, a
DM with `output_files` and `images_out`). Free has no `generate_image` but, since the
one-time reminder went free, it does carry `open_reminder`; its manifest is longer
because of the `PRO FEATURES` line.

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

`_log_token_usage()` in `services/ai.py` prints `[TOKEN] … kirish=… (keshdan … = NN%)` for every round and **also writes the round to `user_history`**, which is what the panel's token card reads — see `WEB_PANEL.md`. The cached share is visible in both even though it does not reduce the quota.

Measure before optimising. The bot's own Postgres answers most questions — how many requests a day, how long replies are, how often a tool actually fires. Two guesses were wrong that way: model routing looked like a big win until `pick_reasoning_effort` turned out to classify only 3-4% of real messages as trivial (and length is a terrible proxy: "Manga Toshkent … kontrakt narxlarini ber" is 66 characters and needs a full web search), and trimming fetched page text looked worth 10% until a live search measured 1 877 tokens, not 4 000.

The cached prefix is **instructions + the tool schemas**, and OpenAI documents *changing the tools available mid-conversation* as a cache-miss cause. Two consequences. `prompt_cache_key` is set in `build_request_params()` per **plan**, never per user — the prefix is identical for everyone on a plan, and a per-user key would have ten active users each warming a private cache. And the tool loop rebuilds `active_tools` every round, dropping tools whose budget is spent, so rounds 2 and 3 of a searched request send a different prefix and start cold. Making the array stable would fix that, but the drop is also what forces the model to stop calling a spent tool, and one wasted round re-sends the whole context (~12k tokens) while the cache would only save part of it — so measure the `keshdan` percentage on multi-round requests before touching it.

`PROMPT_CACHE_RETENTION = "24h"` exists in `core/config.py` and is deliberately off: it fits a day-precision prefix perfectly, but cache **writes** cost more and OpenAI does not document how the complimentary daily grant counts them.

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
from that. Same economics — 244 tokens every round, ~400-2 400 only when called — but it does
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

**Pro gating is done by omission**: `image_enabled = ... and is_pro`. Free users never see the schema, so no tokens are spent advertising a tool they cannot use. Flipping a feature to free-with-upsell means removing `is_pro` from that condition; the task functions already validate independently.

⚠️ **Reminders are the one feature that did flip (2026-09-29):** `reminder_enabled = user_id is not None`, so a free user can set a **one-time** reminder. Recurring (`repeat != "once"`) and `task=true` stay Pro, and that gate is in `_run_reminder_task(is_pro=…)`, not in the schema — the model is told "Pro only" and the DB is never touched (`test_reminders.py` check 23). The cost is the `open_reminder` door (212 tokens) on every free round.

⚠️ **A reminder comes back to the topic it was set in.** `scheduled_tasks.thread_id` (0 = no topic, and always 0 from guest mode), passed only when `chat_id == user_id`. Delivery tries the topic first and falls back to the plain DM (`_mavzular()`), because a deleted topic must not swallow a reminder someone relies on; a task's result is written to the history of the topic it actually landed in (check 24).

Photos (DM and guest) go through `get_openai_reply(input_image=)` — the old single-round `get_vision_reply()` is deleted.

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

The routing between them is prompt-level and fragile: adding the word "rasm" to the file tool's description was enough to make *every* request ("olma haqida ma'lumot ber") turn into a file task. Both tool descriptions now carry an explicit ⛔️ pointing at the other one, and `IMAGE_CAPABILITY_NOTE` in the system prompt exists because the model would otherwise answer "I can't send pictures" without calling any tool at all.

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

While a reply is generating, `busy_handler` (`GeneratingState.generating`) **appends to that same buffer** and `_navbatni_uygot()` starts it once the state is cleared — order matters, or the queued message re-enters the busy state and loops. ⚠️ **Every** path that sets `GeneratingState` (text, photo, document, voice, `/research`) must call it in its `finally`: `busy_handler` says "Navbatga oldim" regardless of what is running, and until 2026-09-29 only the text path woke the queue — a message typed during a photo answer silently vanished (`test_topics.py` check 22). Commands and media keep the old "please wait" behaviour: a queued `/pro` would be sent to GPT as a question. `TEXT_MERGE_BUFFER_TTL` is 600s because the buffer now has to survive a whole generation, not just a 1.5s timer.

`_next_or_stop()` enforces `STREAM_IDLE_TIMEOUT` (180s) — an **idle** limit, not a total one. A file task or a deep research legitimately goes minutes without emitting a chunk, and a total budget would kill exactly the work that needs it. On timeout a partial answer is still delivered (with a note); with nothing at all it raises, and the caller's existing `except` gives the user a clean error plus the retry button and refunds the points.

### Live streaming: what a rejected draft means

`push_update()` writes the accumulating answer to a `sendRichMessageDraft`, throttled to `PUSH_INTERVAL` (1.0s) **and** `PUSH_MIN_CHARS` (100) — with the first chunk forced through, because the wait is felt at the start. Editing per chunk earns a 429 and freezes the stream.

A failed draft ping is **not** proof the draft is unusable. `rich_draft_ok` records whether any draft (animation frame or content push) ever succeeded: if one has, a rejection is treated as a temporary flood-wait and retried (`RICH_DRAFT_FAILURE_LIMIT`); if none ever has, the path is abandoned immediately so the user gets the plain waiting message without delay. `_edit_message_fallback()` handles `TelegramRetryAfter` itself instead of swallowing it with every other exception.

The status animation is **restarted** when a `[STATUS]` chunk arrives after text has already streamed — the model often writes "let me search…" first, which stops the animator, and the screen then sat frozen on stale text for the 20-60s the tool ran. `/research` has its own eight-stage status list; `[STATUS]search` from inside it must not overwrite it.

### The model must not name its own tools

The system prompt has a `CONFIDENTIAL` section, but a prompt rule is not a guarantee — in a live test the bot correctly refused to print the system prompt and then listed `internet_search`, `run_python_sandbox`, … anyway. `strip_internal_names()` (`services/ai.py`) is the second layer: it replaces the real names from `INTERNAL_TOOL_NAMES` (`core/config.py`, the single list) with neutral Uzbek descriptions, on the final text, on the streaming draft, and in the guest path. It deliberately scrubs code blocks too — "list your tools as a python list" is exactly the way around it. `tests/test_no_tool_leak.py` asserts the list matches the actual tool schemas, so a new tool fails the test until it is added.

The prompt also carries a phishing/social-engineering section that fixes the *shape* of the answer (fake placeholders, a visible simulation label, red flags instead of a ready-to-send message) while explicitly forbidding over-refusal of ordinary security questions. `tests/test_safety_prompt.py` only guards that the section still exists — the wording is not asserted.

### The prompt is sent whole on every round, so duplication is expensive

The free daily grant counts tokens, not requests, and caching does not reduce that count (OpenAI support, 2026-09-09) — so anything in `instructions` is paid for on **every round of every request**, and a searched request runs ~1.7 rounds. Measured with `tiktoken` (`o200k_base`), not estimated — see the table in "Token budget" (8 280 free / 8 603 Pro per round; +33 from `open_capabilities(bolim)`, 2026-10-06).

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

### A reminder can do the work, not just announce it

`manage_reminder(task=true)` (2026-09-29) stores `scheduled_tasks.vazifa = TRUE`; at fire
time `helpers._vazifani_bajar()` runs the text through the **full loop** (search, internet
images) and sends the answer — "har kuni 9 da dollar kursini yubor" used to deliver the
words "dollar kursi" every morning. Three rules, `tests/test_reminders.py` checks 18-22:
the run uses `chat_id=0` (the user's history is not re-sent each morning) but the **result
is written to the user's history**, so "tell me more" works; a lapsed Pro gets the cheap
plain reminder, not a paid search; and any failure falls back to the plain reminder —
someone relying on it must never get nothing. It runs as a background task so one slow
search does not delay everyone else's 09:00. Live-tested: the model sets `task` for
"yuborib tur" and leaves it off for "qo'ng'iroq qilishni eslat".

⚠️ **`/kunlik` is capped at `digest._MAX_HOURS` (4) hours a day.** Each digest is a full
searched answer (~15k tokens); the old «Barcha soatlar» button gave one user 24 a day —
~15% of the whole grant, and the same news 24 times. Stored rows above the cap are trimmed
by the migration in `ensure_profile_columns()`.

⛔️ **`/kunlik` delivered nothing for at least a week (2026-09-25 → 10-02: zero `[Daydjest]`
lines in the Railway log) while users complained.** Every link was correct on its own; the
chain was not. The topics prompt waits in a **RAM** FSM state and every deploy (20+ on a busy
day) wipes it, so the typed topics became an ordinary AI question, `digest_topics` stayed
NULL, the screen still said «✅ Faol», and `take_due_digests()` required `digest_topics IS NOT
NULL` — silently skipping that user forever. ⛔️ Sending a default topic instead
(`_STANDART_MAVZU`, 2026-10-02) was **reverted on 10-06**: a user who never wrote a topic
got news every day and complained. Now the answer is caught as a **reply** to the
`force_reply` prompt (`digest.mavzu_javobimi`, registered right after the FSM handler,
before the AI handlers), the SQL keeps `digest_topics IS NOT NULL`, and the screen says
"mavzu yozilmagan — daydjest kelmaydi". Separately, the model once wrote its tool call
into the digest **as text** (`to=functions.internet_search code: {…}` ×3, plus an
unassigned code point); `strip_internal_names()` — the gate every reply path already
uses — now strips those before renaming tools (`test_no_tool_leak.py` 11-12).
Also: `get_full_user_profile()` never returned `digest_hours` (the test's fake profile did,
which is why it stayed green — check 15 reads the real return keys), the screen gated on
`plan_type` alone while delivery also checks expiry (`_pro_faol`), one user's exception
stopped the whole due batch after every row was already marked sent (`_bitta_daydjest`,
3 in parallel), and the digest now goes to the topic `/kunlik` was set in
(`digest_thread_id`, `_mavzular` fallback). Verified end-to-end on a local Postgres
(`pip install pgserver`; copy `tzdata`'s `zoneinfo` into
`pgserver/pginstall/share/postgresql/timezone` or `Asia/Tashkent` is unknown).
`tests/test_digest.py` checks 15-22.

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
`get_openai_reply` / `get_gpt_reply`. That is what kept the change
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

**The icon comes in the same call** (2026-09-29). Telegram only accepts icons from its own
set (`getForumTopicIconStickers`, 112 emoji, fetched once into `_IKONKALAR`), so the
naming prompt lists them (+269 tokens, once per topic, mini bucket) and the model answers
`EMOJI | Sarlavha`. `_ikonka_ajrat()` matches ignoring U+FE0F; an emoji outside the set
(live: 🐙) means no icon, never no name, and a rejected icon retries with the name alone.
Same once-only rule as the name — the bot cannot see an icon the user picked.
`tests/test_topic_nom.py` checks 20-25. ⚠️ Not yet live-tested inside a real private-chat
topic; the fallback is what makes that safe.

One consequence is deliberate: `/new` empties the topic's history, so the next exchange
starts from row 1 and the topic is renamed again. That is the right behaviour — the
conversation genuinely changed — but it does mean a hand-typed name does not survive
`/new`.

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
information stays.

⚠️ **In production `caller_chat_id` is always `None`** (every `[Guest]` log line), so the
draft path never runs and the inline message IS the whole UX. Since 2026-09-29 it mimics
the DM: the placeholder and every status frame carry the DM's animated premium emoji
(`_guest_status_md`, markdown `![ ](tg://emoji?id=…)`) — ⛔️ **not** `<tg-thinking>`: Telegram
rejects that block outside a private-chat draft with `RICH_MESSAGE_BLOCK_UNSUPPORTED`
(live, 2026-09-29). The emoji is the bot's own logo, animated per status kind — spin (text), magnifier (search/research),
page being written (document/file_task), viewfinder (photo), pencil (image), clock arc (reminder),
dots flying in (memory), sound bars (voice/tts). It lives in `handlers/messages.py`
(`status_emoji_id()`), so the **DM `<tg-thinking>` status uses the same set**; `EMOJI_ID_BY_TYPE`
is only the fallback when the set is missing
(`assets/status_*.webm`, each ≤ 64 KB — 207 KB was rejected live as "file is too big"; one
custom-emoji set `holat4_by_<bot>` (plus a `kichik` logo drawn at ~46% of the frame for the Business «ᵃᵛᵗᵒʲᵃᵛᵒᵇ» mark — custom emoji cannot be scaled) created once at startup by `logo_emojini_tayyorla()`, owned by
the superadmin, sticker order = `_LOGO_TURLAR`). ⛔️ **Never bump `_LOGO_TOPLAM`**: owners
have added `holat4` to their own emoji, and a new name is a new set they would have to find
and add again. A **changed** animation gets a new emoji in `_LOGO_BELGI` instead — at
startup any sticker whose emoji differs (ignoring U+FE0F) is `replace_sticker_in_set`-ed in
place (`text` went 🤖 → 💭 on 2026-10-16: the old one was clipped at the frame edge and the
neon tube's half-transparent middle left stray lines; the mask is now solid, logo at 70%
with a spinner arc). A **new** type is appended to the end of
`_LOGO_TURLAR` instead: at startup the missing ones are `add_sticker_to_set`-ed onto the
**same** set, in order, stopping at the first failure — the owner has that set in their
emoji, a bump would hand them a new one to re-add. Since 2026-10-16 the set also replaces
the `/start`, `/help` and Pro emoji: `pro.pe()` and `btn(icon=)` go through
`config.emoji_id()` (`LOGO_ORNIGA` maps each `CUSTOM_EMOJI` key to a logo type; Instagram
stays its own mark). `[STATUS]search` switches the wording, and
once ≥`_JONLI_MIN_BELGI` characters exist the answer streams into the message (" ✍️"),
falling back to status on the next tool round. Two budget rules hold it together: a
rejected premium frame sets `rad` and the rest of the request goes plain (never two
requests per frame), and **every** edit — status, stream, restart — waits
`_INLINE_PING_INTERVAL` after the last one (`inline["oxirgi"]`); a 429 stops both and
leaves the budget to the final answer. There is still no stop button: that is a draft
feature, and drafts need a private chat id Telegram does not give guest mode.

⚠️ **`MAX_GUEST_REPLY_LEN` (3800) is for the plain `text` rung only.** The rich payload
carries up to `MAX_RICH_CHARS`; every plain fallback goes through `_oddiyga_qisqa()`, which
cuts, closes an open fence and **says** it cut. It used to apply to every path, so a long
group answer silently lost its end.

Guest also uses `speech_to_text_smart` / `text_to_speech_smart`, so a Pro user gets the
natural voice in a group instead of the free edge-tts one.

**Photos work in guest too.** `images_out` used to be `None` there, and that was not a
missing feature but a silent bug: `IMAGE_CAPABILITY_NOTE` is added unconditionally in
`get_openai_reply`, so the prompt promised pictures, the model called
`internet_search(want_images=true)`, and the tool answered with **silence** — which the
model reads as "no images found" and retries, the exact context-explosion path described
above. `handle_guest_message` now owns one `images: list` and passes it to all three
`get_gpt_reply` calls, photos included.

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

**A DM photo takes the full loop** (2026-09-29): `handle_photo` calls `get_gpt_reply(...,
input_image=<base64>, input_file_bytes=<bytes>)`, so a photo with a caption gets search,
internet images, files, `edit_image` and memory exactly like text. The single-round
`get_vision_reply` had no search tool, so "how much is this phone?" was answered by
guessing; live-tested after the switch, the model read the label, searched uzum/texnomart and
cited them. The image goes **only into this request's user message** — history gets the text
`[Rasm yuborildi]: …`, or every later request would re-pay the image tokens.
Guest photos take the same path (`images_out`, no `output_files`); `get_vision_reply` is deleted.
`tests/test_rasm_qidiruv.py` pins it. **An album is one request** (`_albomlar`, keyed
`(chat_id, media_group_id)`): the first photo waits `ALBOM_KUTISH` (1.2 s), the rest append and
return, and all go as a list in `input_image` — one charge, capped at `ALBOM_MAX` (5) images.
Before, three photos were three requests, three charges, and "compare these" could not work.

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
`open_reminder` are the same pattern): **244 tokens** per round measured with `tiktoken`,
paid only when someone actually asks. It is attached on every request including guest, because the question is
asked in groups too and that is exactly where the model's own knowledge is thinnest
(files, images, memory and reminders are all off there). `imkoniyat_rounds < 1` caps it
at one call: the text never changes, so a second call is ~2 000 tokens for nothing.

⚠️ **It takes a required `bolim` (2026-10-06).** `hammasi` returns every section's short
text (**2 513** tokens, free) — the old behaviour, unchanged. A single section returns that
section **plus `_BATAFSIL`**: buttons, modes, setup steps, written with the exact labels
the user sees on screen (biznes 1 937, pro 829, the rest ~400-700). So "what does the
Pauza button do?" is answered from fact, and costs less than the whole list. `_BATAFSIL`
is model-only — `/help` stays short. The enum in `services/ai.py` must equal
`capabilities.BOLIMLAR` (`test_capabilities.py` 12c); 12e asserts a section never
outgrows `hammasi`. The parameter cost **+33 tokens per round** (211 → 244) and that
number was fought for: a per-value description put it at 398, i.e. more than the whole
saving. Live (`eval_chat.py` `biznes_free` / `biznes_tugma` / `kunlik_qanday`): the right
section every time; without the "biznesni qanday ulayman" example in the description the
model once web-searched Telegram Business instead. `[Imkoniyat] bolim=…` in the log is the
only measure of how often the door opens — read it before re-weighing this.

⚠️ **The text comes from `handlers/capabilities.py::SECTIONS`, the same dict `/help`
renders** — `model_uchun(is_pro)` strips the HTML and adds the reader's plan. A second
hand-written list is the mistake this repo has made five times (see `ADMIN.md` "Five label maps");
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

### Two free TTS engines, two ways to go silent

Uzbek speech goes to Gemini (`GEMINI_TTS_MODEL`, `gemini-3.1-flash-tts-preview`) and falls
back to edge-tts; Russian/English go straight to edge-tts. Both fail without raising
anything a user would see as an error — the voice note just never arrives.

- ⛔️ **Never call the bot's Gemini TTS model for anything else** (tests, ads, experiments).
  The free tier is a **per-model** quota (on `gemini-2.5-flash-preview-tts`: 3 requests/min,
  10/day), so ten side calls on the bot's model end Uzbek voice replies for every user until
  the next day. Use a different model for side work; its quota is separate.
- ⚠️ **edge-tts breaks when Microsoft rejects an old client.** `7.2.8` started returning
  `WSServerHandshakeError 403` for every voice (found 2026-10-15) and was bumped to `7.3.1`.
  If `TTS xatosi (ovoz=…)` lines appear for all languages at once, test the newest edge-tts
  in a scratch venv before touching code — the API has not changed between these versions.

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
same way and for the same reason — and it is decoration too (see `WEB_PANEL.md`).
It is called on `/start` for **everyone**, not just admins, so a demotion that happened
while the bot was down still removes the button on the next `/start`. With `WEB_APP_URL`
empty it does nothing at all, so a deployment without a domain behaves exactly as before.

### Telegram limits worth knowing here

- Bot API cannot download files larger than 20 MB — that is why `DOCUMENT_MAX_SIZE_PRO` is 20 MB and not higher.
- `XTR` invoice amounts are the star count directly, **not** multiplied by 100. `tests/test_pro_payload.py` locks this.

### Sandbox

`services/sandbox.py` runs model-written Python with a scrubbed environment (no `BOT_TOKEN`, `OPENAI_API_KEY`, `DATABASE_URL`), a fresh temp cwd, a 60s timeout and RLIMITs on Linux. **Network is closed (2026-09-29)** — the same Railway project runs Postgres, `Web-panel` and other bots on the internal network, so model-written code could reach them. Two layers: a **seccomp** filter in `preexec_fn` (kernel rejects `socket(AF_INET/AF_INET6)` and `io_uring_setup`, inherited by subprocesses and ctypes — a network namespace was tried first and **Railway refuses `unshare`**), and `_qoriqchi.py`, which patches `socket`/DNS for a readable error and then `runpy`s `script.py` (line numbers unchanged). The second layer alone is bypassable via `_socket`/subprocess; the startup log line `🔒 [Sandbox] tarmoq: …` says which layers are live — read it after a deploy. `tarmoq_tekshir()` turns layer 1 off if it breaks file writes. Tracebacks keep the **tail** (`[-3000:]`): the head-cut used to drop the actual error line. `tests/test_sandbox_tarmoq.py`.

`services/sandbox_helpers/` must stay next to `sandbox.py`; it is located via `Path(__file__).parent` and copied into each run.

**Two limits in `_apply_limits()`/`_build_child_env()` are load-bearing and only bite on Linux** (`_HAS_RESOURCE` is `False` on Windows, so local runs never see either). Memory is capped with `RLIMIT_DATA`, never `RLIMIT_AS`: `AS` counts *reserved address space*, and numpy/pandas/matplotlib/pptx reserve gigabytes they never touch — a 2 GB `AS` cap made `import pandas` itself raise `MemoryError`, and a different library failed each run. Separately, `OPENBLAS_NUM_THREADS=1` (with the `OMP_`/`MKL_`/`NUMEXPR_` twins) is required because `nproc` inside a container reports *host* cores; OpenBLAS then sizes a buffer per thread and dies with "Memory allocation still failed". These are not `PYTHON*` vars, so `-E` leaves them alone. `sandbox.check_libraries()` runs at startup and logs any library that will not import — without it, a broken import is invisible: the model just falls back to PDF and the user silently gets the wrong format.

Both helpers there exist for the same reason: the model composes documents by hardcoding coordinates and never measures what it placed. `docgen` owns text metrics for PDF; `deck` owns slide geometry for PPTX (safe margins, aspect-preserving image fit, a reserved footer band, a reserved caption line for image credit). Before `deck`, the three failures were always the same — picture over text, credit over picture, page number over picture. The tool description makes `deck` mandatory for PPTX and explicitly scopes the older manual-layout rules to PDF/DOCX/XLSX, because two sets of layout instructions produce worse output than one. `tests/test_deck_layout.py` asserts no two content shapes intersect — it already caught a 0.1" clash between the section number and its heading.

`deck` also owns image *placement*, not just geometry: `Deck(images=[...])` is a pool and every layout's `image` defaults to the `AUTO` sentinel, so photos spread across the whole deck. This exists because the model reads "put a picture on the first slide" literally and leaves every other slide bare. `image=None` is the explicit opt-out — that is why `AUTO` cannot simply be `None`. Side-by-side layouts put text and picture in frames of identical size and top, the picture cover-cropped to fill its frame exactly, so image scale never wanders between slides. `image_slide` is the opposite case — cropping a map or a chart destroys it — so there the picture is fitted whole and the card is then shrunk to hug it with fixed padding; the box it is given is only a bound, never the drawn frame. Caption and credit are positioned off the returned rect, not off that bound.

The tool description promises the model there is **no internet** inside the sandbox, and that promise is what makes generated code deterministic — a model asked to fetch a photo invents a URL, and invented URLs are dead. So photos for documents arrive the other way round: the model lists what it needs in `image_queries`, `_run_file_task` downloads and converts them **before** the run, and `run_in_sandbox(extra_files=...)` drops them in the work dir as `rasm1.jpg`, `rasm2.jpg` — positional, one per query, a missing one still burns its number so the rest don't shift. They are cached per user request, because the file loop reruns up to 4 times and a second download would hand the model *different* photos than the caption it already wrote. Everything is re-encoded to JPEG via Pillow: most DuckDuckGo image results are WEBP and python-pptx rejects WEBP.
