# Phase 2 – real API integration (report section)

**Goal (brief, section 4):** replace the mock data layer with real APIs; handle authentication, rate limits, pagination, latency, caching and logging.

**APIs found and used**
| Domain | API | Why / limits |
|---|---|---|
| Flights | Aviasales Data API (Travelpayouts), `prices_for_dates`, free token | The real Aviasales API. Cached fares only: no seats, baggage or arrival time (shown as unavailable); no booking endpoint, so reservations stay mock. |
| Shopping | DummyJSON `/products`, no key | Birmarket has no public API; DummyJSON is a public e-commerce catalogue (194 items, stock, brand, rating). English names only, no colour; USD→AZN at 1.70. |
| Cinema | none | No public showtimes API for Azerbaijani cinemas was found; the mock dataset stays. |

**Design.** Phase 1 hid data behind repository interfaces, so Phase 2 adds `Api*` implementations only; modules, router and engine are unchanged except for a `prepare()` hook (real flight APIs are queried per route) and handling of fields a real source does not provide (`None`, never invented). `FLIGHTS_SOURCE` / `SHOPPING_SOURCE` (default `DATA_SOURCE`) choose the source per domain; mock stays the default.

| Requirement | Implementation (`superchat/api_client.py`) |
|---|---|
| Authentication | `X-Access-Token` header from `.env`; never logged |
| Rate limits | retry on 429/5xx with backoff, honours `Retry-After`; optional client-side `API_MAX_RPS` |
| Pagination | DummyJSON `limit`/`skip` loop until `total`; Travelpayouts `limit`/`page` |
| Latency | request timeout (5 s), 3 attempts |
| Caching | TTL cache (5 min); stale data served if the API is down |
| Logging | method, path, status, duration per call |
| Errors | friendly reply, no stack trace; missing token falls back to mock flights |

**Testing.** `tests/test_api.py` (14 tests) uses in-process mocks that copy the documented responses; total 25/25 pass. Live calls need a Travelpayouts token and were not run in the test suite.

**Limitations.** Cached fares may not exist for a given route/date ("nothing found"); city names need an entry in `CITY_CODES`; DummyJSON is not Birmarket; cinema remains mock.
