"""Data access layer. Modules only talk to these interfaces; Phase 2 = write Api* classes and
switch DATA_SOURCE (see build_repositories). No module imports json or files directly."""
import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from . import config


class FlightRepository(ABC):
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


def build_repositories() -> Repositories:
    import os
    source = os.getenv("DATA_SOURCE", "json")
    if source == "json":
        return Repositories(JsonFlightRepository(), JsonProductRepository(), JsonMovieRepository(),
                            JsonCinemaRepository(), JsonShowtimeRepository())
    if source == "api":
        from .api_repositories import build_api_repositories
        return build_api_repositories(Repositories)
    raise ValueError(f"Unknown DATA_SOURCE={source!r} (use 'json' or 'api')")
