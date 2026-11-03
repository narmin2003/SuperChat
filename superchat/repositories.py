"""Data access layer. Modules only talk to these interfaces; Phase 2 = write Api* classes and
switch DATA_SOURCE (see build_repositories). No module imports json or files directly."""
import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from . import config


class FlightRepository(ABC):
    def prepare(self, origin, destination, date) -> None:
        """Hook for sources that must be queried per route (real flight APIs). No-op for the mock data."""

    @abstractmethod
    def all(self) -> list: ...
    @abstractmethod
    def get(self, id): ...
    @abstractmethod
    def reserve_seats(self, id, n) -> bool: ...


class ProductRepository(ABC):
    @abstractmethod
    def all(self) -> list: ...
    @abstractmethod
    def get(self, id): ...


class MovieRepository(ABC):
    @abstractmethod
    def all(self) -> list: ...
    @abstractmethod
    def get(self, id): ...


class CinemaRepository(ABC):
    @abstractmethod
    def all(self) -> list: ...
    @abstractmethod
    def get(self, id): ...


class ShowtimeRepository(ABC):
    @abstractmethod
    def all(self) -> list: ...
    @abstractmethod
    def get(self, id): ...
    @abstractmethod
    def reserve_seats(self, id, n) -> bool: ...


_lock = threading.Lock()


class _JsonBase:
    FILE = ""

    def __init__(self):
        self._items = json.loads((config.DATA_DIR / self.FILE).read_text(encoding="utf-8"))

    def all(self):
        return [dict(x) for x in self._items]

    def get(self, id):
        return next((dict(x) for x in self._items if x["id"] == id), None)

    def reserve_seats(self, id, n) -> bool:
        with _lock:
            item = next((x for x in self._items if x["id"] == id), None)
            if not item or item["seats_available"] < n:
                return False
            item["seats_available"] -= n
            return True


class JsonFlightRepository(_JsonBase, FlightRepository): FILE = "flights.json"
class JsonProductRepository(_JsonBase, ProductRepository): FILE = "products.json"
class JsonMovieRepository(_JsonBase, MovieRepository): FILE = "movies.json"
class JsonCinemaRepository(_JsonBase, CinemaRepository): FILE = "cinemas.json"
class JsonShowtimeRepository(_JsonBase, ShowtimeRepository): FILE = "showtimes.json"


@dataclass
class Repositories:
    flights: FlightRepository
    products: ProductRepository
    movies: MovieRepository
    cinemas: CinemaRepository
    showtimes: ShowtimeRepository


def _source(domain):
    import os
    src = os.getenv(f"{domain}_SOURCE", os.getenv("DATA_SOURCE", "json"))
    if src not in ("json", "api"):
        raise ValueError(f"Unknown {domain}_SOURCE/DATA_SOURCE={src!r} (use 'json' or 'api')")
    return src


def build_repositories(transports=None) -> Repositories:
    """Per-domain source: FLIGHTS_SOURCE / SHOPPING_SOURCE (default DATA_SOURCE). Cinema is always the mock data:
    no public showtimes API exists. A misconfigured real source falls back to the mock data with a loud warning."""
    import logging
    transports = transports or {}
    flights, products = JsonFlightRepository(), JsonProductRepository()
    from .api_client import ApiError
    for domain, name in (("FLIGHTS", "flights"), ("SHOPPING", "products")):
        if _source(domain) == "api":
            from . import api_repositories as api
            try:
                repo = api.make_flight_repository(transports.get("flights")) if name == "flights" \
                    else api.make_product_repository(transports.get("products"))
            except ApiError as e:
                logging.getLogger("superchat").error("%s: %s - falling back to mock data", domain, e)
            else:
                flights, products = (repo, products) if name == "flights" else (flights, repo)
    return Repositories(flights, products, JsonMovieRepository(), JsonCinemaRepository(), JsonShowtimeRepository())
