# Phase 2 – real API integration (report section)

**Goal (brief, section 4):** replace the mock data layer with the real Aviasales, Shopping Assistant and CinemaPlus APIs; handle authentication, rate limits, pagination, latency, caching and logging.

**Design.** Phase 1 already hid data behind repository interfaces, so Phase 2 adds `Api*` implementations only. Modules, router and engine are unchanged. `DATA_SOURCE=json|api` selects the source; `json` stays the default.

| Requirement | Implementation (`superchat/api_client.py`) |
|---|---|
| Authentication | API key from `.env` (Bearer or custom header); never logged |
| Rate limits | retry on 429/5xx with backoff, honours `Retry-After`; optional client-side `API_MAX_RPS` |
| Pagination | `page` / `page_size` loop until a short page |
| Latency | request timeout (5 s), 3 attempts |
| Caching | TTL cache (60 s); stale data served if the API is down; invalidated after a reservation |
| Logging | method, path, status, duration per call |
| Errors | module failures become a friendly reply, no stack trace |

**Testing.** `tests/test_api.py` (10 tests) runs the full app against an in-process mock API (pagination, 429, outage, reservation). Total: 21/21 pass.

**Known limitations.** Endpoint paths and response shapes are assumptions until the official API documentation is received; only `api_repositories.py` (paths, `_map()`) needs to change. Filtering still happens in the modules, so very large catalogues would need server-side search.
