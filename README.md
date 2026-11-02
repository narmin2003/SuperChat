# SuperChat

One chat for flights, shopping and cinema. Each message is routed automatically; state is kept per domain and per session.

## Run (one command)
```bash
pip install -r requirements.txt
cp .env.example .env        # put your NVIDIA_API_KEY (nvapi-...) into .env
python run.py               # open http://127.0.0.1:8000
```
Without a key it still works in rules-only mode (degraded: English replies, simpler routing).

## Tests
```bash
pytest -q                                   # module tests on the official mock data
python tests/run_routing_eval.py            # routing accuracy -> TEST_LOG.md (uses LLM if key is set, ~2s between calls)
USE_LLM=0 python tests/run_routing_eval.py  # rules-only baseline
```

## Architecture
- `repositories.py` – interfaces (`FlightRepository`, `ProductRepository`, `MovieRepository`, `CinemaRepository`, `ShowtimeRepository`) + JSON implementations. Phase 2: add `Api*` classes and handle `DATA_SOURCE` in `build_repositories()`; nothing else changes.
- `flights.py / shopping.py / cinema.py` – domain modules (deterministic filtering, sorting, comparison, cart, mock reservations with seat/stock checks).
- `router.py` – ONE LLM call returns JSON: route (answer / ambiguous / out_of_scope), follow-up flag, and a list of intents with args (mixed = several intents). `rules.py` is the fallback when the LLM fails.
- `composer.py` – second LLM call writes the reply from tool results only (no invented data); template fallback.
- `state.py` – per-domain state + shared state (language, last domain). "Back to the headphones" restores the earlier shopping search.
- Reference date 2026-11-02 (`config.REF_DATE`), data in `data/`.

LLM: NVIDIA NIM free tier (OpenAI-compatible API, ~40 requests/min). At most 2 LLM calls per message, retries with backoff on 429/5xx.
