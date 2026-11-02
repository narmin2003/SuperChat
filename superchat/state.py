from dataclasses import dataclass, field


def _flights(): return {"last_query": None, "last_results": [], "selected": None, "reservations": []}
def _shopping(): return {"last_query": None, "last_results": [], "searches": [], "selected": None, "cart": {}}
def _cinema(): return {"last_query": None, "last_results": [], "last_movies": [], "selected_movie": None,
                       "selected_showtime": None, "reservations": []}


@dataclass
class Session:
    id: str
    shared: dict = field(default_factory=lambda: {"language": "en", "preferences": {}, "last_domain": None})
    flights: dict = field(default_factory=_flights)
    shopping: dict = field(default_factory=_shopping)
    cinema: dict = field(default_factory=_cinema)
    history: list = field(default_factory=list)  # [{"role","text"}] shown to the whole chat
    debug: dict = field(default_factory=dict)

    def domain_state(self, domain):
        return getattr(self, domain)
