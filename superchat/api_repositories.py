"""Api* repositories (Phase 2). Same interfaces as the JSON ones, so modules/router/engine are unchanged.

ASSUMED contract (the real Aviasales / Shopping Assistant / CinemaPlus docs were not available; adjust
PATHS / _map() here only when they are):
  GET  {base}{path}?page=N&page_size=M  -> list, or {"items"|"results"|"data": [...]}
  GET  {base}{path}/{id}                -> record, 404 if unknown
  POST {base}{path}/{id}/reserve {"seats": n} -> 2xx ok, 409/422 = not enough seats
Records use the field names of the mock dataset (Appendix A)."""
import os
from . import config
from .api_client import ApiClient, ApiError
from .repositories import (FlightRepository, ProductRepository, MovieRepository, CinemaRepository,
                           ShowtimeRepository)


class _ApiRepo:
    PATH = ""

    def __init__(self, client: ApiClient):
        self.client = client

    def _map(self, rec):  # hook for field mapping once real schemas are known
        return rec

    def all(self):
        recs = self.client.cached(self.PATH, lambda: [self._map(r) for r in self.client.get_all(self.PATH)])
        return [dict(r) for r in recs]

    def get(self, id):
        cached = self.client.peek(self.PATH)  # prefer the cached list: avoids one HTTP call per id
        if cached is not None:
            return next((dict(r) for r in cached if r["id"] == id), None)
        key = f"{self.PATH}/{id}"
        rec = self.client.cached(key, lambda: self.client.get_one(key))
        return self._map(dict(rec)) if rec else None

    def reserve_seats(self, id, n) -> bool:
        r = self.client.request("POST", f"{self.PATH}/{id}/reserve", json={"seats": n})
        if r.status_code in (404, 409, 422):
            return False
        if r.status_code >= 400:
            raise ApiError(f"{self.client.name}: reserve HTTP {r.status_code}")
        self.client.invalidate()
        return True


class ApiFlightRepository(_ApiRepo, FlightRepository): PATH = "/flights"
class ApiProductRepository(_ApiRepo, ProductRepository): PATH = "/products"
class ApiMovieRepository(_ApiRepo, MovieRepository): PATH = "/movies"
class ApiCinemaRepository(_ApiRepo, CinemaRepository): PATH = "/cinemas"
class ApiShowtimeRepository(_ApiRepo, ShowtimeRepository): PATH = "/showtimes"


def _client(prefix, name, **over):
    env = lambda k, d="": os.getenv(f"{prefix}_{k}", os.getenv(f"API_{k}", d))
    return ApiClient(name, env("BASE_URL"), api_key=env("API_KEY"), auth_header=env("AUTH_HEADER", "Authorization"),
                     timeout=float(env("TIMEOUT", "5")), retries=int(env("RETRIES", "3")),
                     cache_ttl=float(env("CACHE_TTL", "60")), max_rps=float(env("MAX_RPS", "0")),
                     page_size=int(env("PAGE_SIZE", "100")), **over)


def build_api_repositories(Repositories, transports=None):
    """transports: optional {prefix: httpx transport} for tests."""
    t = transports or {}
    av = _client("AVIASALES", "aviasales", transport=t.get("AVIASALES"))
    sh = _client("SHOPPING", "shopping", transport=t.get("SHOPPING"))
    cp = _client("CINEMAPLUS", "cinemaplus", transport=t.get("CINEMAPLUS"))
    return Repositories(ApiFlightRepository(av), ApiProductRepository(sh), ApiMovieRepository(cp),
                        ApiCinemaRepository(cp), ApiShowtimeRepository(cp))
