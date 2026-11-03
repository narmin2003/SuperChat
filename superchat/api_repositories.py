"""Phase 2: real public APIs behind the Phase 1 repository interfaces (modules/router/engine unchanged).

Flights   -> Aviasales Data API (Travelpayouts), GET /aviasales/v3/prices_for_dates, token in X-Access-Token.
             Cached user-search prices: no seats, baggage or arrival time, so those fields are None (never invented).
             The API has no booking endpoint: a reservation is a local mock, as allowed by the brief.
Shopping  -> DummyJSON /products (limit/skip pagination), a public demo e-commerce catalogue (no key).
             Birmarket has no public API. Source names are English only; prices are USD converted to AZN.
Cinema    -> no public showtimes API exists, so the mock data stays (see build_repositories)."""
import os
import threading
from . import config
from .api_client import ApiClient, ApiError
from .repositories import FlightRepository, ProductRepository

USD_AZN = float(os.getenv("USD_AZN_RATE", "1.70"))  # AZN is pegged to the dollar

# city name (lower case) -> IATA city code, for the Aviasales API. Extend freely.
CITY_CODES = {"baku": "BAK", "ganja": "KVD", "nakhchivan": "NAJ", "istanbul": "IST", "antalya": "AYT", "moscow": "MOW",
              "saint petersburg": "LED", "dubai": "DXB", "doha": "DOH", "tbilisi": "TBS", "yerevan": "EVN",
              "london": "LON", "paris": "PAR", "berlin": "BER", "rome": "ROM", "madrid": "MAD", "barcelona": "BCN",
              "amsterdam": "AMS", "frankfurt": "FRA", "vienna": "VIE", "prague": "PRG", "warsaw": "WAW",
              "budapest": "BUD", "athens": "ATH", "cairo": "CAI", "tel aviv": "TLV", "new york": "NYC",
              "delhi": "DEL", "bangkok": "BKK", "singapore": "SIN"}
CITY_NAMES = {v: k.title() for k, v in CITY_CODES.items()}
AIRLINES = {"J2": "AZAL Azerbaijan Airlines", "TK": "Turkish Airlines", "PC": "Pegasus", "XQ": "SunExpress",
            "W6": "Wizz Air", "FZ": "flydubai", "SU": "Aeroflot", "QR": "Qatar Airways", "EK": "Emirates",
            "LH": "Lufthansa", "AF": "Air France", "BA": "British Airways", "KL": "KLM", "LO": "LOT Polish Airlines"}


def _client(name, base_url, key="", header="Authorization", transport=None):
    env = lambda k, d: os.getenv(f"API_{k}", d)
    return ApiClient(name, base_url, api_key=key, auth_header=header, timeout=float(env("TIMEOUT", "5")),
                     retries=int(env("RETRIES", "3")), cache_ttl=float(env("CACHE_TTL", "300")),
                     max_rps=float(env("MAX_RPS", "0")), transport=transport)


class ApiFlightRepository(FlightRepository):
    def __init__(self, client: ApiClient):
        self.client, self._flights, self._lock = client, {}, threading.Lock()

    def prepare(self, origin, destination, date_):
        o = CITY_CODES.get((origin or "").lower())
        d = CITY_CODES.get((destination or "").lower())
        if (origin and not o) or (destination and not d):
            return  # city unknown to the directory: nothing to ask the API for -> empty result
        when = date_ or config.REF_DATE.strftime("%Y-%m")
        params = {"origin": o, "destination": d, "departure_at": when, "one_way": "true", "currency": "usd",
                  "sorting": "price", "limit": 30, "page": 1}
        params = {k: v for k, v in params.items() if v}
        rows = self.client.cached(("flights", tuple(sorted(params.items()))),
                                  lambda: self.client.get_json("/aviasales/v3/prices_for_dates", params)["data"])
        with self._lock:
            for r in rows:
                f = self._map(r)
                self._flights[f["id"]] = f

    @staticmethod
    def _map(r):
        dep = r["departure_at"][:16]
        oc, dc = r["origin"], r["destination"]
        airline = r.get("airline") or ""
        return {"id": f"{oc}{dc}-{airline}{r.get('flight_number', '')}-{dep}".replace(":", ""),
                "airline": AIRLINES.get(airline, airline or "Unknown airline"), "flight_number": f"{airline}{r.get('flight_number', '')}",
                "origin": {"code": r.get("origin_airport") or oc, "city": CITY_NAMES.get(oc, oc)},
                "destination": {"code": r.get("destination_airport") or dc, "city": CITY_NAMES.get(dc, dc)},
                "departure_local": dep, "arrival_local": None,  # the API gives no arrival time
                "duration_min": r.get("duration_to") or r.get("duration"), "stops": r.get("transfers", 0), "via": None,
                "price_azn": round(float(r["price"]) * USD_AZN, 2), "cabin": "economy",
                "baggage_kg": None, "seats_available": None}

    def all(self):
        with self._lock:
            return [dict(f) for f in self._flights.values()]

    def get(self, id):
        with self._lock:
            f = self._flights.get(id)
            return dict(f) if f else None

    def reserve_seats(self, id, n) -> bool:
        return id in self._flights  # no booking endpoint exists: local mock reservation, no payment


class ApiProductRepository(ProductRepository):
    def __init__(self, client: ApiClient):
        self.client = client

    @staticmethod
    def _map(p):
        title = p["title"]
        return {"id": f"P{p['id']:03d}", "name": {"en": title, "az": title, "ru": title}, "category": p.get("category", ""),
                "brand": p.get("brand") or "", "price_azn": round(float(p["price"]) * USD_AZN, 2),
                "rating": p.get("rating"), "stock": int(p.get("stock") or 0), "color": "",
                "description": p.get("description")}

    def all(self):
        rows = self.client.cached("products", lambda: [self._map(p) for p in self.client.paged("/products")])
        return [dict(r) for r in rows]

    def get(self, id):
        return next((p for p in self.all() if p["id"] == id), None)


def make_flight_repository(transport=None):
    token = os.getenv("TRAVELPAYOUTS_TOKEN", "")
    if not token:
        raise ApiError("TRAVELPAYOUTS_TOKEN is not set")
    return ApiFlightRepository(_client("aviasales", os.getenv("FLIGHTS_BASE_URL", "https://api.travelpayouts.com"),
                                       token, "X-Access-Token", transport))


def make_product_repository(transport=None):
    return ApiProductRepository(_client("shopping", os.getenv("SHOPPING_BASE_URL", "https://dummyjson.com"),
                                        transport=transport))
