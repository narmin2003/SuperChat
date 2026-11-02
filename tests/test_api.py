"""Phase 2 tests: Api* repositories against an in-process mock API (httpx.MockTransport, no network).
The mock serves the official dataset, so the same module behaviour must hold as with JSON."""
import json
import os
os.environ["USE_LLM"] = "0"
import httpx
import pytest
from superchat import config
from superchat.api_client import ApiClient, ApiError
from superchat.engine import SuperChat
from superchat.repositories import Repositories, build_repositories
from superchat.api_repositories import build_api_repositories

FILES = {"flights": "flights.json", "products": "products.json", "movies": "movies.json",
         "cinemas": "cinemas.json", "showtimes": "showtimes.json"}
DATA = {k: json.loads((config.DATA_DIR / v).read_text(encoding="utf-8")) for k, v in FILES.items()}


class MockApi:
    """Fake backend: pagination, auth check, optional failures (429 / 500 / down)."""
    def __init__(self, fail_first=0, status=429, down=False):
        self.data = json.loads(json.dumps(DATA))
        self.calls, self.fail_first, self.status, self.down = [], fail_first, status, down

    def __call__(self, req: httpx.Request):
        self.calls.append((req.method, req.url.path))
        if self.down:
            raise httpx.ConnectError("down")
        if self.fail_first > 0:
            self.fail_first -= 1
            return httpx.Response(self.status, headers={"Retry-After": "1"})
        if req.headers.get("authorization") != "Bearer test-key":
            return httpx.Response(401)
        parts = req.url.path.strip("/").split("/")
        rows = self.data.get(parts[0])
        if rows is None:
            return httpx.Response(404)
        if len(parts) == 1:
            page, size = int(req.url.params["page"]), int(req.url.params["page_size"])
            return httpx.Response(200, json={"items": rows[(page - 1) * size: page * size]})
        rec = next((r for r in rows if r["id"] == parts[1]), None)
        if rec is None:
            return httpx.Response(404)
        if len(parts) == 3 and req.method == "POST":
            n = json.loads(req.content)["seats"]
            if rec["seats_available"] < n:
                return httpx.Response(409)
            rec["seats_available"] -= n
            return httpx.Response(200, json=rec)
        return httpx.Response(200, json=rec)


@pytest.fixture()
def env(monkeypatch):
    for p in ("AVIASALES", "SHOPPING", "CINEMAPLUS"):
        monkeypatch.setenv(f"{p}_BASE_URL", "http://mock")
        monkeypatch.setenv(f"{p}_API_KEY", "test-key")
    monkeypatch.setenv("API_PAGE_SIZE", "5")  # force multi-page pagination


def make_bot(api):
    t = httpx.MockTransport(api)
    return SuperChat(build_api_repositories(Repositories, {"AVIASALES": t, "SHOPPING": t, "CINEMAPLUS": t}))


def test_api_flights_same_result_as_json(env):
    bot = make_bot(MockApi())
    r = bot.modules["flights"].handle(bot.session("a"), "search", {"origin": "Baku", "destination": "Istanbul", "date": "2026-11-06"})
    assert {x["id"] for x in r["data"]["flights"]} == {"F001", "F002", "F013"}


def test_pagination_fetches_all_17_flights(env):
    api = MockApi()
    bot = make_bot(api)
    assert len(bot.repos.flights.all()) == 17
    assert sum(1 for m, p in api.calls if p == "/flights") == 4  # 17 items / page_size 5


def test_cache_avoids_repeat_calls(env):
    api = MockApi()
    bot = make_bot(api)
    bot.repos.products.all(); n = len(api.calls)
    bot.repos.products.all(); bot.repos.products.get("P001")
    assert len(api.calls) == n


def test_retry_on_429_then_success(env, monkeypatch):
    api = MockApi(fail_first=2)
    c = ApiClient("t", "http://mock", "test-key", transport=httpx.MockTransport(api), sleep=lambda s: None)
    assert c.get_all("/products")


def test_gives_up_after_retries_without_leaking_key(env):
    c = ApiClient("t", "http://mock", "test-key", transport=httpx.MockTransport(MockApi(fail_first=99, status=503)),
                  sleep=lambda s: None)
    with pytest.raises(ApiError) as e:
        c.get_all("/flights")
    assert "test-key" not in str(e.value)


def test_stale_cache_when_api_goes_down(env):
    api = MockApi()
    bot = make_bot(api)
    bot.repos.products.all()
    bot.repos.products.client.cache_ttl = 0  # expire
    api.down = True
    assert len(bot.repos.products.all()) == 12


def test_chat_survives_api_outage_without_stack_trace(env):
    api = MockApi(down=True)
    bot = make_bot(api)  # startup also survives
    reply = bot.handle("s", "Find me a flight from Baku to Istanbul on Friday")["reply"]
    assert "Traceback" not in reply and reply


def test_reservation_goes_through_api_and_invalidates_cache(env):
    api = MockApi()
    bot = make_bot(api)
    before = bot.repos.flights.get("F001")["seats_available"]
    assert bot.repos.flights.reserve_seats("F001", 2) is True
    assert bot.repos.flights.get("F001")["seats_available"] == before - 2
    assert bot.repos.flights.reserve_seats("F001", 999) is False


def test_missing_base_url_is_clear_error(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "api")
    for p in ("AVIASALES", "API"):
        monkeypatch.delenv(f"{p}_BASE_URL", raising=False)
    with pytest.raises(ApiError):
        build_repositories()


def test_cross_domain_conversation_on_api(env):
    bot = make_bot(MockApi())
    for q in ("Find me a flight from Baku to Istanbul on Friday.", "What is playing tonight?",
              "Do you have wireless headphones under 100 AZN?"):
        assert bot.handle("s", q)["category"] in ("flights", "cinema", "shopping")
