"""Phase 2 tests: real-API adapters against in-process mocks that copy the documented response shapes
(Travelpayouts prices_for_dates, DummyJSON /products). No network needed."""
import os
os.environ["USE_LLM"] = "0"
import httpx
import pytest
from superchat.api_client import ApiClient, ApiError
from superchat.engine import SuperChat
from superchat.repositories import build_repositories

TP_ROWS = [
    {"origin": "BAK", "destination": "IST", "origin_airport": "GYD", "destination_airport": "IST", "price": 170,
     "airline": "TK", "flight_number": "289", "departure_at": "2026-11-06T07:30:00+04:00", "transfers": 0,
     "duration": 215, "duration_to": 215, "link": "/search/x"},
    {"origin": "BAK", "destination": "IST", "origin_airport": "GYD", "destination_airport": "SAW", "price": 120,
     "airline": "PC", "flight_number": "612", "departure_at": "2026-11-06T13:10:00+04:00", "transfers": 1,
     "duration": 330, "duration_to": 330, "link": "/search/y"},
]
PRODUCTS = [{"id": i, "title": t, "category": c, "price": pr, "rating": 4.5, "stock": st, "brand": b,
             "description": "demo"} for i, (t, c, pr, st, b) in enumerate([
                 ("Apple AirPods Max Wireless Headphones", "mobile-accessories", 59.0, 10, "Apple"),
                 ("Lenovo Laptop", "laptops", 400.0, 0, "Lenovo"),
                 ("Asus Laptop", "laptops", 500.0, 7, None)], 1)]


class MockWorld:
    def __init__(self, fail_first=0, status=429, down=False):
        self.calls, self.fail_first, self.status, self.down = [], fail_first, status, down

    def __call__(self, req: httpx.Request):
        self.calls.append((req.url.host, req.url.path, dict(req.url.params), req.headers.get("x-access-token")))
        if self.down:
            raise httpx.ConnectError("down")
        if self.fail_first > 0:
            self.fail_first -= 1
            return httpx.Response(self.status, headers={"Retry-After": "1"})
        if req.url.path == "/aviasales/v3/prices_for_dates":
            if req.headers.get("x-access-token") != "tp-secret":
                return httpx.Response(200, json={"success": False, "data": {}, "error": "Wrong token"})
            return httpx.Response(200, json={"success": True, "data": TP_ROWS, "error": None, "currency": "usd"})
        if req.url.path == "/products":
            lim, skip = int(req.url.params["limit"]), int(req.url.params["skip"])
            return httpx.Response(200, json={"products": PRODUCTS[skip:skip + lim], "total": len(PRODUCTS), "skip": skip, "limit": lim})
        return httpx.Response(404)


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "api")
    monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "tp-secret")
    monkeypatch.setenv("API_RETRIES", "3")


def bot_for(world):
    t = httpx.MockTransport(world)
    return SuperChat(build_repositories({"flights": t, "products": t}))


def flights(bot, **a):
    return bot.modules["flights"].handle(bot.session("t"), "search", a)


def test_flights_mapped_from_travelpayouts(env):
    w = MockWorld(); bot = bot_for(w)
    r = flights(bot, origin="Baku", destination="Istanbul", date="2026-11-06")
    f = r["data"]["flights"]
    assert [x["price_azn"] for x in f] == [204.0, 289.0]  # USD -> AZN (1.70), sorted by price
    assert f[0]["airline"] == "Pegasus" and f[0]["stops"] == 1 and f[1]["airline"] == "Turkish Airlines"
    assert f[0]["baggage_kg"] is None and f[0]["seats_left"] is None and f[0]["arrival"] is None  # never invented
    host, path, params, token = w.calls[0]
    assert host == "api.travelpayouts.com" and token == "tp-secret"
    assert params["origin"] == "BAK" and params["destination"] == "IST" and params["departure_at"] == "2026-11-06"


def test_unknown_city_makes_no_request_and_is_empty(env):
    w = MockWorld(); bot = bot_for(w)
    r = flights(bot, origin="Baku", destination="Atlantis", date="2026-11-06")
    assert r["status"] == "empty" and not w.calls


def test_flight_search_is_cached(env):
    w = MockWorld(); bot = bot_for(w)
    flights(bot, origin="Baku", destination="Istanbul", date="2026-11-06")
    flights(bot, origin="Baku", destination="Istanbul", date="2026-11-06")
    assert len(w.calls) == 1


def test_reserve_api_flight_without_seat_info(env):
    bot = bot_for(MockWorld()); s = bot.session("t")
    r = bot.modules["flights"].handle(s, "search", {"origin": "Baku", "destination": "Istanbul", "date": "2026-11-06"})
    fid = r["data"]["flights"][0]["id"]
    res = bot.modules["flights"].handle(s, "reserve", {"ids": [fid], "passengers": 2})
    assert res["status"] == "ok" and res["data"]["reservation"]["total_azn"] == 408.0


def test_wrong_token_is_a_clean_error(env):
    c = ApiClient("t", "http://x", "bad", "X-Access-Token", transport=httpx.MockTransport(MockWorld()), sleep=lambda s: None)
    with pytest.raises(ApiError) as e:
        c.get_json("/aviasales/v3/prices_for_dates", {})
    assert "bad" not in str(e.value)


def test_products_mapped(env):
    w = MockWorld(); bot = bot_for(w)
    prods = bot.repos.products.all()
    assert len(prods) == 3 and prods[0]["id"] == "P001" and prods[0]["price_azn"] == 100.3
    assert prods[2]["brand"] == "" and prods[0]["name"]["en"].startswith("Apple")


def test_pagination_requests_every_page(env):
    w = MockWorld()
    c = ApiClient("shop", "http://x", transport=httpx.MockTransport(w))
    assert len(c.paged("/products", page_size=2)) == 3
    assert [call[2]["skip"] for call in w.calls] == ["0", "2"]


def test_shopping_module_works_on_api_products(env):
    bot = bot_for(MockWorld()); s = bot.session("t"); m = bot.modules["shopping"]
    r = m.handle(s, "search", {"query": "laptop"})
    assert {p["name"] for p in r["data"]["products"]} == {"Lenovo Laptop", "Asus Laptop"}
    assert m.handle(s, "add_to_cart", {"ids": ["P002"]})["status"] == "error"  # stock 0 comes from the API
    assert m.handle(s, "add_to_cart", {"ids": ["P003"]})["status"] == "ok"


def test_retry_after_429_then_success(env):
    w = MockWorld(fail_first=2)
    c = ApiClient("t", "http://x", transport=httpx.MockTransport(w), sleep=lambda s: None)
    assert len(c.paged("/products")) == 3


def test_stale_cache_when_api_goes_down(env):
    w = MockWorld(); bot = bot_for(w)
    bot.repos.products.all()
    bot.repos.products.client.cache_ttl = 0
    w.down = True
    assert len(bot.repos.products.all()) == 3


def test_chat_survives_outage_without_stack_trace(env):
    bot = bot_for(MockWorld(down=True))
    reply = bot.handle("s", "Find me a flight from Baku to Istanbul on Friday")["reply"]
    assert reply and "Traceback" not in reply
    assert bot.handle("s", "Show me laptops")["reply"]


def test_cinema_stays_on_mock_data(env):
    bot = bot_for(MockWorld())
    assert bot.handle("s", "What is playing tonight?")["category"] == "cinema"


def test_missing_token_falls_back_to_mock_flights(env, monkeypatch):
    monkeypatch.delenv("TRAVELPAYOUTS_TOKEN")
    bot = bot_for(MockWorld())
    assert len(bot.repos.flights.all()) == 17  # mock dataset


def test_sources_can_be_chosen_per_domain(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "json")
    monkeypatch.setenv("SHOPPING_SOURCE", "api")
    repos = build_repositories({"products": httpx.MockTransport(MockWorld())})
    assert type(repos.products).__name__ == "ApiProductRepository" and type(repos.flights).__name__ == "JsonFlightRepository"
