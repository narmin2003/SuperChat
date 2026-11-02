# SuperChat

**One chat window for flights, shopping and cinema.** SuperChat combines three assistants (Aviasales-style flight search, an e-commerce Shopping Assistant and CinemaPlus-style cinema booking) behind a single conversational interface. The user never picks a mode: every message is routed automatically, and the conversation stays coherent when the topic changes.

- Live demo: https://superchat-csfk.onrender.com/ (free hosting, the first load can take about a minute)
- Phase 1 (mock data) is tagged `phase1`; Phase 2 (real-API layer) is on `main`.

---

## Contents
1. [Features](#features)
2. [Quick start](#quick-start)
3. [Configuration](#configuration)
4. [Example conversations](#example-conversations)
5. [How it works](#how-it-works)
6. [Data layer: Phase 1 and Phase 2](#data-layer-phase-1-and-phase-2)
7. [HTTP API](#http-api)
8. [Tests](#tests)
9. [Project structure](#project-structure)
10. [Limitations](#known-limitations)
11. [Security](#security)

---

## Features

**Single chat, automatic routing.** Each message is classified as *flights*, *shopping*, *cinema*, *mixed* (several intents in one message), *follow-up* ("the cheaper one", "and for Saturday?"), *ambiguous* (one short clarifying question) or *out of scope* (polite refusal). The whole session history is shown in one window and each reply is colour-tagged with the domain that answered.

**Flights**
- Search by origin, destination and date (one-way), including connecting flights.
- Filter and sort by price, stops, departure time, airline and cabin.
- Details: times, duration, stops and via-city, baggage allowance, seats left.
- Compare two or more flights (cheapest and fastest are highlighted).
- Mock reservation with seat check (no payment).

**Shopping**
- Search by text, category, brand, price range, colour, in-stock only; sort by price or rating.
- Product details and comparison; availability from stock data.
- Cart: add, remove, show cart with total (stock is checked).

**Cinema**
- List films by genre, rating, language or date ("what is playing tonight?").
- Cinemas and showtimes for a film, seat availability and ticket price.
- Mock ticket reservation with seat check (no payment).

**Cross-cutting**
- Separate state per domain and shared session state (language, last active domain). "Back to the headphones" restores the earlier shopping results.
- Never invents data: replies are written only from tool results; empty results are reported as such.
- Replies in the user's language (English, Azerbaijani, Russian) when the LLM is enabled.
- Data-source or LLM failures never show a stack trace; the chat keeps working.

---

## Quick start

Requirements: Python 3.10+.

```bash
git clone https://github.com/narmin2003/SuperChat.git
cd SuperChat
python3 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # put your NVIDIA_API_KEY (nvapi-...) into .env
python run.py                 # open http://127.0.0.1:8000
```

Without an API key SuperChat still runs in **rules-only mode** (simpler routing, English replies). With a key, a hosted LLM (NVIDIA NIM, free tier) does routing and writes replies. By default the app uses the bundled mock dataset and needs no internet except for the LLM.

---

## Configuration

All settings are environment variables, read from `.env` (never committed; use `.env.example` as a template).

| Variable | Default | Purpose |
|---|---|---|
| `NVIDIA_API_KEY` | – | Enables the LLM (routing + reply writing). Empty = rules-only mode. |
| `SUPERCHAT_MODEL` | `meta/llama-3.3-70b-instruct` | LLM model name. `python tools/find_model.py` finds one that works with your key. |
| `USE_LLM` | `1` | `0` forces the rule-based router (used for the baseline test run). |
| `PORT` | `8000` | Server port. |
| `DATA_SOURCE` | `json` | `json` = mock dataset in `data/`; `api` = real APIs (Phase 2). |
| `REF_DATE` | `2026-11-02` | Reference date of the mock dataset ("tonight", "Friday"). |
| `AVIASALES_BASE_URL`, `AVIASALES_API_KEY` | – | Flights API (only with `DATA_SOURCE=api`). |
| `SHOPPING_BASE_URL`, `SHOPPING_API_KEY` | – | Shopping Assistant API. |
| `CINEMAPLUS_BASE_URL`, `CINEMAPLUS_API_KEY` | – | CinemaPlus API (movies, cinemas, showtimes). |
| `API_AUTH_HEADER` | `Authorization` | `Authorization` sends `Bearer <key>`; any other name sends the raw key in that header. |
| `API_TIMEOUT` | `5` | Request timeout in seconds. |
| `API_RETRIES` | `3` | Attempts per request (429, 5xx, network errors). |
| `API_CACHE_TTL` | `60` | Cache lifetime in seconds. |
| `API_PAGE_SIZE` | `100` | Page size for paginated lists. |
| `API_MAX_RPS` | `0` | Client-side requests per second limit (`0` = off). |

Each `API_*` setting can also be set per service, e.g. `AVIASALES_TIMEOUT=10`.

---

## Example conversations

| Conversation | What it shows |
|---|---|
| "Find me a flight from Baku to Istanbul on Friday." → "What is playing tonight?" → "Do you have wireless headphones under 100 AZN?" | Switching across all three domains |
| "What is playing tonight?" → "Show me laptops." → "Okay, and the sci-fi one, any seats on Saturday?" | Domain switch and return to cinema |
| "Show me laptops." → "The second one, is it in stock?" | Follow-up inside shopping |
| "Flights to Istanbul on 6 November." → "The cheaper one, is it direct?" | Follow-up inside flights |
| "I need a flight to Istanbul on 6 November and a backpack for the trip." | Mixed intent, one coherent reply |
| "Show me something good." | Ambiguity → one clarifying question |
| "What is the weather in Ganja?" | Out of scope → polite refusal |
| "Book two seats." (no context) | Missing context → asks which film/flight |

---

## How it works

```
 Browser (static/index.html)
        │  POST /api/chat
        ▼
   app.py (FastAPI) ──► engine.SuperChat.handle()
                              │
        ┌─────────────────────┼──────────────────────────┐
        ▼                     ▼                          ▼
   router.py             domain modules             composer.py
 (LLM → JSON, falls     flights / shopping /      (LLM writes reply from
  back to rules.py)     cinema  (deterministic)    tool results; template
        │                     │                     fallback)
        │                     ▼
        │              state.py  (per-domain + shared session state)
        │                     │
        └──────────────► repositories.py  ◄── Json* (Phase 1)  |  Api* (Phase 2)
```

**Request lifecycle**
1. `router.py` makes **one LLM call** that returns JSON: language, route (`answer` / `ambiguous` / `out_of_scope`), a follow-up flag and a list of *intents* (domain, action, arguments). Several intents = a mixed request. The prompt contains the reference-date calendar and a compact summary of the session state, so "the second one" or "the cheaper one" are resolved to concrete item ids.
2. The output is validated (`_sanitize`); unknown domains, actions or malformed JSON are dropped. If the LLM is unavailable or invalid twice, `rules.py` (keyword/regex/slot rules in EN/AZ/RU) routes instead.
3. The engine executes each intent on the matching **domain module**. Modules are deterministic Python: filtering, sorting, comparison, cart, reservations with seat/stock checks. A failure in one module becomes an error result, not a crashed chat.
4. `composer.py` makes a second LLM call that writes the reply **only from the tool results** (so nothing can be invented). If the LLM is down, a template renderer produces a plain English reply.
5. At most **2 LLM calls per message**; temporary errors (429/5xx) are retried with backoff, permanent errors (bad key, retired model) switch the LLM off so the app falls back to rules.

**Routing method and trade-offs.** A hybrid: LLM function-calling-style JSON for flexibility (multilingual input, mixed intents, follow-ups) plus a rule-based fallback for robustness and offline use. The LLM costs latency and depends on a hosted service; the rules are fast and free but weaker on paraphrases and non-English text. Keeping the *actions* in plain Python means the model never touches data directly.

**State.** `state.py` keeps `flights` (last search, results, selected flight, reservations), `shopping` (last search, shortlist, earlier searches, selected product, cart), `cinema` (last movies/showtimes, selected film and showtime, reservations) and shared state (language, preferences, last domain). Switching topics never clears another domain's state, so returning to an earlier topic finds it intact. Sessions are held in memory, keyed by `session_id`.

---

## Data layer: Phase 1 and Phase 2

All data access goes through repository interfaces in `superchat/repositories.py`: `FlightRepository`, `ProductRepository`, `MovieRepository`, `CinemaRepository`, `ShowtimeRepository`. Modules, router and engine never read files or call HTTP directly.

**Phase 1 (default, `DATA_SOURCE=json`).** `Json*` repositories read the official mock dataset in `data/` (17 flights, 12 products, 8 movies, 3 cinemas, 16 showtimes). Reservations change in-memory seat counts under a lock.

**Phase 2 (`DATA_SOURCE=api`).** `Api*` repositories in `superchat/api_repositories.py` implement the same interfaces on top of `superchat/api_client.py`:

| Requirement | Implementation |
|---|---|
| Authentication | API key from `.env`, sent as Bearer or custom header; never logged |
| Rate limits | Retry on 429/5xx with exponential backoff, honours `Retry-After`; optional client-side `API_MAX_RPS` |
| Pagination | `page` / `page_size` loop until a short page |
| Latency | Per-request timeout, limited retries |
| Caching | TTL cache; stale data is served if the API goes down; cache cleared after a reservation |
| Logging | Method, path, status and duration for every call |
| Error handling | `ApiError` is caught per module; the user gets a friendly message |

> **Note:** the exact endpoint paths and response shapes of the real Aviasales / Shopping Assistant / CinemaPlus APIs depend on their documentation. The current paths (`/flights`, `/products`, `/movies`, `/cinemas`, `/showtimes`, `POST /{id}/reserve`) are an assumption documented at the top of `api_repositories.py`; when the official docs arrive, only that file (paths and the `_map()` hook) needs to change. The Phase 2 code is verified against an in-process mock API, not against the real services.

See `PHASE2_REPORT.md` for the report section.

---

## HTTP API

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/api/chat` | `{"session_id": "abc" \| null, "message": "..."}` | `{session_id, reply, category, domains, router, is_followup}` |
| `POST` | `/api/reset` | `{"session_id": "abc", "message": ""}` | `{ok: true}` – clears the session |
| `GET` | `/` | – | The chat web page |

`category` is one of `flights`, `shopping`, `cinema`, `mixed`, `ambiguous`, `out_of_scope`, `error`. Messages are limited to 1000 characters.

---

## Tests

```bash
pytest -q                                   # 21 tests, no internet or LLM needed
python tests/run_routing_eval.py            # routing accuracy -> writes TEST_LOG.md (uses the LLM if a key is set)
USE_LLM=0 python tests/run_routing_eval.py  # rules-only baseline
```

- `tests/test_modules.py` (11 tests): flights, shopping and cinema logic on the official dataset: filters, "no invented results", reservations and seat limits, cart, state restore.
- `tests/test_api.py` (10 tests): the Phase 2 layer against an in-process mock API: pagination, caching, retry on 429, giving up after retries without leaking the key, stale cache during an outage, reservations through the API, a chat that survives a full API outage, a three-domain conversation.
- `tests/run_routing_eval.py` runs 40 conversations from `tests/cases.py` (all categories). Results with the LLM: **40/40 (100%)**, see `TEST_LOG.md`; rules-only baseline: 38/40 (95%). The two baseline misses (a "this week" phrasing and a Russian mixed request) are exactly the cases the LLM router handles.

---

## Project structure

```
app.py                  FastAPI app (/api/chat, /api/reset, static page)
run.py                  Single command to start the server
superchat/
  engine.py             Orchestrates route → modules → compose; error handling
  router.py             LLM routing (JSON intents) with rule fallback
  rules.py              Rule-based router (EN/AZ/RU)
  composer.py           Reply writer (LLM) + template fallback
  llm.py                LLM client: retries, permanent-error handling, JSON extraction
  state.py              Per-domain and shared session state
  flights.py shopping.py cinema.py   Domain modules
  repositories.py       Repository interfaces + Json* implementations + build_repositories()
  api_repositories.py   Api* implementations (Phase 2)
  api_client.py         HTTP client: auth, retry, rate limit, pagination, cache, logging
  text.py common.py config.py        Text normalisation, result helpers, settings
data/                   Official mock dataset (JSON)
static/index.html       Chat web UI
tests/                  Module tests, API tests, routing evaluation and cases
tools/                  find_model.py, bench.py (LLM model helpers)
TEST_LOG.md             Routing test results and error analysis
PHASE2_REPORT.md        Phase 2 report section
SuperChat_Technical_Report.pdf   Phase 1 technical report
```

---

## Known limitations
- Sessions and mock reservations live in memory: they reset when the server restarts and are not shared between server instances.
- Without an LLM key, routing is rule-based and replies are in English.
- Filtering happens inside the modules, so with real APIs the full list is fetched (and cached) per source; a very large catalogue would need server-side search in the repositories.
- Phase 2 has not been verified against the real Aviasales, Shopping Assistant and CinemaPlus services (see the note above).
- The optional bonus tasks (voice input, visual search, full multilingual evaluation) are not implemented; the LLM mode does understand and answer in English, Azerbaijani and Russian.

## Security
No secrets are stored in the repository: `.env` and `.venv` are in `.gitignore`, and `.env.example` contains placeholders only. API keys are read from the environment and are never written to logs or error messages. No real personal or payment data is used anywhere; reservations are mock.

## Credits
Python, FastAPI, Uvicorn, httpx, pytest and the OpenAI-compatible Python client. LLM inference through NVIDIA NIM (free tier).
