"""Module-level tests on the official mock data (no LLM needed). Run: pytest -q"""
import os
os.environ["USE_LLM"] = "0"
import pytest
from superchat.engine import SuperChat


@pytest.fixture()
def bot():
    return SuperChat()


def ids(res, key):
    return [x["id"] for x in res["data"][key]]


def test_flights_friday_includes_connecting(bot):
    r = bot.modules["flights"].handle(bot.session("a"), "search", {"origin": "Baku", "destination": "Istanbul", "date": "2026-11-06"})
    assert set(ids(r, "flights")) == {"F001", "F002", "F013"}


def test_flights_unknown_route_is_empty_not_invented(bot):
    r = bot.modules["flights"].handle(bot.session("a"), "search", {"origin": "Baku", "destination": "Ganja", "date": "2026-11-06"})
    assert r["status"] == "empty"


def test_flight_reserve_respects_seats(bot):
    s, m = bot.session("a"), bot.modules["flights"]
    assert m.handle(s, "reserve", {"ids": ["F002"], "passengers": 4})["status"] == "error"   # only 3 seats
    assert m.handle(s, "reserve", {"ids": ["F002"], "passengers": 3})["status"] == "ok"
    assert m.handle(s, "reserve", {"ids": ["F002"], "passengers": 1})["status"] == "error"   # now 0


def test_products_headphones_under_100(bot):
    r = bot.modules["shopping"].handle(bot.session("a"), "search", {"query": "headphones", "max_price": 100})
    assert ids(r, "products") == ["P001"]


def test_laptops_only_laptops_and_multilingual(bot):
    m, s = bot.modules["shopping"], bot.session("a")
    assert ids(m.handle(s, "search", {"query": "laptops"}), "products") == ["P003", "P004"]
    assert "P003" in ids(m.handle(s, "search", {"query": "noutbuk"}), "products")
    assert "P003" in ids(m.handle(s, "search", {"query": "ноутбуки"}), "products")


def test_cart_stock_and_total(bot):
    m, s = bot.modules["shopping"], bot.session("a")
    assert m.handle(s, "add_to_cart", {"ids": ["P002"]})["status"] == "error"                  # stock 0
    assert m.handle(s, "add_to_cart", {"ids": ["P010"], "quantity": 2})["data"]["cart"]["total_azn"] == 130.0
    assert m.handle(s, "add_to_cart", {"ids": ["P011"], "quantity": 9})["status"] == "error"   # stock 5
    assert m.handle(s, "remove_from_cart", {"ids": ["P010"]})["data"]["cart"]["total_azn"] == 0


def test_cinema_tonight_and_sold_out(bot):
    r = bot.modules["cinema"].handle(bot.session("a"), "movies", {"date": "2026-11-02"})
    assert {m["id"] for m in r["data"]["movies"]} == {"M001", "M003", "M008"}
    assert any(t["sold_out"] for m in r["data"]["movies"] for t in m["showtimes"])


def test_cinema_scifi_saturday_is_ambiguous_two_results(bot):
    r = bot.modules["cinema"].handle(bot.session("a"), "showtimes", {"genre": "sci-fi", "date": "2026-11-07"})
    assert ids(r, "showtimes") == ["S011", "S012"]


def test_ticket_reserve_limits(bot):
    s, m = bot.session("a"), bot.modules["cinema"]
    assert m.handle(s, "reserve", {"showtime_id": "S003", "seats": 1})["status"] == "error"    # sold out
    assert m.handle(s, "reserve", {"showtime_id": "S012", "seats": 6})["status"] == "error"    # 5 left
    assert m.handle(s, "reserve", {"showtime_id": "S012", "seats": 2})["status"] == "ok"
    assert m.handle(s, "reserve", {})["status"] in ("ok", "needs")


def test_state_survives_domain_switch(bot):
    bot.handle("s", "Show me headphones")
    bot.handle("s", "Flights from Baku to Dubai on 6 November")
    bot.handle("s", "What is playing tonight?")
    r = bot.handle("s", "back to the headphones")
    assert "Headphones" in r["reply"] and r["domains"] == ["shopping"]


def test_sample_conversations_rules_mode(bot):
    r = bot.handle("c4", "Flights to Istanbul on 6 November.")
    r = bot.handle("c4", "The cheaper one, is it direct?")
    assert "1 stop" in r["reply"]
    assert bot.handle("c8", "Book two seats.")["category"] == "ambiguous"
    assert bot.handle("c7", "What is the weather in Ganja?")["category"] == "out_of_scope"
    assert bot.handle("c5", "I need a flight to Istanbul on 6 November and a backpack for the trip.")["category"] == "mixed"
