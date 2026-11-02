import re
from .common import ok, empty, needs, error, code, as_list, MAX_LIST
from .text import norm, num, stem_in

D = "cinema"
GENRE = {"scifi": "sci-fi", "sciencefiction": "sci-fi", "fantastika": "sci-fi", "фантастика": "sci-fi", "фантастик": "sci-fi",
         "komediya": "comedy", "комедия": "comedy", "qorxu": "horror", "ужасы": "horror", "triller": "thriller",
         "macera": "adventure", "movzu": "drama", "romantik": "romance", "multfilm": "animation", "мультфильм": "animation"}
LANG = {"english": "English", "ingilis": "English", "англий": "English", "azerbaijani": "Azerbaijani", "azerbaycan": "Azerbaijani",
        "azeri": "Azerbaijani", "азербайджан": "Azerbaijani", "russian": "Russian", "rus": "Russian", "русск": "Russian"}


def _key(s):
    return re.sub(r"[\s\-_]", "", norm(s))


class CinemaModule:
    domain = D

    def __init__(self, movies, cinemas, showtimes):
        self.movies, self.cinemas, self.showtimes = movies, cinemas, showtimes

    def mview(self, m):
        return {"id": m["id"], "title": m["title"], "genre": m["genre"], "language": m["language"],
                "duration_min": m["duration_min"], "age_rating": m["age_rating"], "rating": m["rating"], "synopsis": m["synopsis"]}

    def sview(self, t):
        m, c = self.movies.get(t["movie_id"]), self.cinemas.get(t["cinema_id"])
        return {"id": t["id"], "movie": m["title"], "movie_genre": m["genre"], "cinema": c["name"], "district": c["district"],
                "date": t["date"], "time": t["time"], "hall": t["hall"], "price_azn": t["price_azn"],
                "seats_available": t["seats_available"], "seats_total": t["seats_total"], "sold_out": t["seats_available"] == 0}

    def summary(self, s):
        st = s.cinema
        rows = []
        for i, sid in enumerate(st["last_results"], 1):
            v = self.sview(self.showtimes.get(sid))
            rows.append(f"  {i}) {sid} {v['movie']} {v['movie_genre']} {v['cinema']} {v['date']} {v['time']} seats={v['seats_available']}")
        movies = [f"{i}) {m} {self.movies.get(m)['title']} {self.movies.get(m)['genre']}" for i, m in enumerate(st["last_movies"], 1)]
        return (f"cinema: selected_movie={st['selected_movie']} selected_showtime={st['selected_showtime']} "
                f"reservations={[r['code'] for r in st['reservations']]} last_movies={movies}\n" + ("\n".join(rows) if rows else "  (no showtimes yet)"))

    def _movie(self, ref):
        n = norm(ref)
        if not n:
            return None
        for m in self.movies.all():
            if m["id"].lower() == n or norm(m["title"]) == n:
                return m
        for m in self.movies.all():
            if n in norm(m["title"]) or norm(m["title"]) in n:
                return m
        return None

    def _genre_ok(self, m, g):
        gk = GENRE.get(_key(g), _key(g))
        return any(_key(x) == _key(gk) or _key(gk) in _key(x) for x in m["genre"])

    def _lang_ok(self, m, l):
        want = next((v for k, v in LANG.items() if norm(l).startswith(k)), None) or str(l).title()
        return m["language"] == want

    def _cinema_ok(self, t, c):
        cin = self.cinemas.get(t["cinema_id"])
        return norm(c) in norm(cin["name"] + " " + cin["district"])

    def handle(self, s, action, a):
        st = s.cinema
        if action == "movies":
            return self.list_movies(st, a)
        if action in ("showtimes", "availability"):
            return self.list_showtimes(st, a)
        if action == "details":
            m = self._movie(a.get("movie") or "") or (self.movies.get(st["selected_movie"]) if st["selected_movie"] else None)
            if not m:
                return needs(D, action, "Which film do you mean?")
            st["selected_movie"] = m["id"]
            ts = sorted((t for t in self.showtimes.all() if t["movie_id"] == m["id"]), key=lambda t: (t["date"], t["time"]))
            return ok(D, action, movie=self.mview(m), showtimes=[self.sview(t) for t in ts])
        if action == "recall":
            if not st["last_results"] and not st["last_movies"]:
                return empty(D, action, message="No earlier cinema search in this session.")
            return ok(D, action, movies=[self.mview(self.movies.get(i)) for i in st["last_movies"]],
                      showtimes=[self.sview(self.showtimes.get(i)) for i in st["last_results"]],
                      reservations=st["reservations"])
        if action == "reserve":
            sid = a.get("showtime_id") or st["selected_showtime"] or (st["last_results"][0] if len(st["last_results"]) == 1 else None)
            if not sid or not self.showtimes.get(str(sid)):
                return needs(D, action, "Which film and showtime should I book?")
            return self.reserve(st, str(sid), int(num(a.get("seats")) or 1))
        return error(D, action, f"Unsupported cinema action: {action}")

    def list_movies(self, st, a):
        date, cin = a.get("date"), a.get("cinema")
        sts = [t for t in self.showtimes.all() if (not date or t["date"] == str(date)[:10]) and (not cin or self._cinema_ok(t, cin))]
        res = []
        for m in self.movies.all():
            if a.get("genre") and not self._genre_ok(m, a["genre"]): continue
            if a.get("language") and not self._lang_ok(m, a["language"]): continue
            if num(a.get("min_rating")) is not None and m["rating"] < num(a["min_rating"]): continue
            if a.get("query") and norm(a["query"]) not in norm(m["title"] + " " + m["synopsis"]): continue
            mine = [t for t in sts if t["movie_id"] == m["id"]]
            if (date or cin) and not mine: continue
            res.append((m, mine))
        res.sort(key=lambda x: -x[0]["rating"])
        total, res = len(res), res[:MAX_LIST]
        st["last_query"] = {k: v for k, v in a.items() if v not in (None, "")}
        st["last_movies"] = [m["id"] for m, _ in res]
        st["last_results"] = [t["id"] for _, ts in res for t in sorted(ts, key=lambda t: (t["date"], t["time"]))] if (date or cin) else []
        st["selected_movie"] = res[0][0]["id"] if len(res) == 1 else st["selected_movie"]
        if not res:
            return empty(D, "movies", query=a)
        return ok(D, "movies", query=a, total_matches=total, movies=[
            {**self.mview(m), "showtimes": [self.sview(t) for t in sorted(ts, key=lambda t: (t["date"], t["time"]))]} for m, ts in res])

    def list_showtimes(self, st, a):
        m = None
        if a.get("movie"):
            m = self._movie(a["movie"])
            if not m:
                return empty(D, "showtimes", message=f"No film matching '{a['movie']}' in the catalogue.")
        elif not a.get("genre") and not a.get("date") and st["selected_movie"]:
            m = self.movies.get(st["selected_movie"])
        res = []
        for t in self.showtimes.all():
            mv = self.movies.get(t["movie_id"])
            if m and t["movie_id"] != m["id"]: continue
            if a.get("genre") and not self._genre_ok(mv, a["genre"]): continue
            if a.get("date") and t["date"] != str(a["date"])[:10]: continue
            if a.get("cinema") and not self._cinema_ok(t, a["cinema"]): continue
            if num(a.get("min_seats")) is not None and t["seats_available"] < num(a["min_seats"]): continue
            res.append(t)
        res.sort(key=lambda t: (t["date"], t["time"]))
        total, res = len(res), res[:MAX_LIST]
        st["last_query"] = {k: v for k, v in a.items() if v not in (None, "")}
        st["last_results"] = [t["id"] for t in res]
        st["selected_movie"] = m["id"] if m else st["selected_movie"]
        st["selected_showtime"] = res[0]["id"] if len(res) == 1 else None
        if not res:
            return empty(D, "showtimes", query=a)
        return ok(D, "showtimes", query=a, total_matches=total, showtimes=[self.sview(t) for t in res])

    def reserve(self, st, sid, n):
        t = self.showtimes.get(sid)
        if n < 1:
            return error(D, "reserve", "Number of seats must be at least 1.")
        if t["seats_available"] == 0:
            return error(D, "reserve", "This showtime is sold out.", showtime=self.sview(t))
        if t["seats_available"] < n:
            return error(D, "reserve", f"Only {t['seats_available']} seat(s) left for this showtime.", showtime=self.sview(t))
        if not self.showtimes.reserve_seats(sid, n):
            return error(D, "reserve", "Could not reserve seats, please try again.")
        r = {"code": code("CT"), "showtime_id": sid, "seats": n, "total_azn": round(t["price_azn"] * n, 2)}
        st["reservations"].append(r)
        st["selected_showtime"] = sid
        return ok(D, "reserve", reservation=r, showtime=self.sview(self.showtimes.get(sid)), note="mock reservation, no payment")
