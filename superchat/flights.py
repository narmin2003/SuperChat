import logging
from .common import ok, empty, needs, error, code, as_list, MAX_LIST
from .text import norm, num, canon_city

D = "flights"
SORTS = {"price": lambda f: (f["price_azn"], f["departure_local"]), "departure": lambda f: f["departure_local"],
         "duration": lambda f: f["duration_min"], "stops": lambda f: (f["stops"], f["price_azn"])}


class FlightsModule:
    domain = D

    def __init__(self, repo):
        self.repo = repo
        self.cities = {}
        try:  # city names are cosmetic: a data-source outage at startup must not stop the app
            for f in repo.all():
                for k in ("origin", "destination"):
                    self.cities[f[k]["code"]] = f[k]["city"]
        except Exception:
            logging.getLogger("superchat.flights").warning("could not preload flights; continuing")

    def view(self, f):
        return {"id": f["id"], "airline": f["airline"], "flight_number": f["flight_number"],
                "from": f["origin"]["city"], "to": f["destination"]["city"],
                "departure": f["departure_local"], "arrival": f["arrival_local"],
                "duration_min": f["duration_min"], "stops": f["stops"],
                "via": self.cities.get(f["via"], f["via"]) if f["via"] else None,
                "price_azn": f["price_azn"], "cabin": f["cabin"], "baggage_kg": f["baggage_kg"],
                "seats_left": f["seats_available"]}

    def summary(self, s):
        st = s.flights
        rows = []
        for i, fid in enumerate(st["last_results"], 1):
            v = self.view(self.repo.get(fid))
            rows.append(f"  {i}) {fid} {v['airline']} {v['from']}->{v['to']} {v['departure'][:16]} stops={v['stops']} {v['price_azn']} AZN")
        res = [r["code"] for r in st["reservations"]]
        return f"flights: selected={st['selected']} reservations={res}\n" + ("\n".join(rows) if rows else "  (no results yet)")

    def _ids(self, a, st):
        ids = [i for i in as_list(a.get("ids") or a.get("id")) if self.repo.get(i)]
        if not ids and st["selected"]:
            ids = [st["selected"]]
        if not ids and len(st["last_results"]) == 1:
            ids = list(st["last_results"])
        return ids

    def handle(self, s, action, a):
        st = s.flights
        if action == "search":
            return self.search(st, a)
        if action == "recall":
            return self._show(st, "recall")
        if action == "details":
            ids = self._ids(a, st)
            if not ids:
                return needs(D, action, "Which flight do you mean? (e.g. the first one from the list)")
            st["selected"] = ids[0]
            return ok(D, action, flights=[self.view(self.repo.get(i)) for i in ids])
        if action == "compare":
            ids = [i for i in as_list(a.get("ids")) if self.repo.get(i)] or st["last_results"][:3]
            if len(ids) < 2:
                return needs(D, action, "Which flights should I compare? Search first or name two flights.")
            fl = [self.view(self.repo.get(i)) for i in ids]
            return ok(D, action, flights=fl, cheapest=min(fl, key=lambda f: f["price_azn"])["id"],
                      fastest=min(fl, key=lambda f: f["duration_min"])["id"])
        if action == "reserve":
            ids = self._ids(a, st)
            if not ids:
                return needs(D, action, "Which flight should I reserve?")
            return self.reserve(st, ids[0], int(num(a.get("passengers")) or 1))
        return error(D, action, f"Unsupported flights action: {action}")

    def _show(self, st, action):
        if not st["last_results"]:
            return empty(D, action, message="No flight search yet in this session.")
        return ok(D, action, flights=[self.view(self.repo.get(i)) for i in st["last_results"]],
                  selected=st["selected"], reservations=st["reservations"])

    def search(self, st, a):
        o, d = canon_city(a.get("origin")), canon_city(a.get("destination"))
        if not o and not d:
            return needs(D, "search", "Where would you like to fly from and to?")
        assumed = None
        if d and not o and d != "Baku":
            o, assumed = "Baku", "origin assumed to be Baku"
        try:
            self.repo.prepare(o, d, str(a["date"])[:10] if a.get("date") else None)
        except Exception as e:  # noqa: BLE001 - data source down: say so, keep the chat alive
            logging.getLogger("superchat.flights").warning("flight source failed: %s", e)
            return error(D, "search", "The flight data source is temporarily unavailable. Please try again in a moment.")
        route = [f for f in self.repo.all()
                 if (not o or f["origin"]["city"] == o) and (not d or f["destination"]["city"] == d)]
        res = list(route)
        date = a.get("date")
        if date:
            res = [f for f in res if f["departure_local"][:10] == str(date)[:10]]
        mp, ms = num(a.get("max_price")), num(a.get("max_stops"))
        if mp is not None: res = [f for f in res if f["price_azn"] <= mp]
        if ms is not None: res = [f for f in res if f["stops"] <= ms]
        if a.get("airline"): res = [f for f in res if norm(a["airline"]) in norm(f["airline"])]
        if a.get("cabin"): res = [f for f in res if norm(a["cabin"]) == f["cabin"]]
        if a.get("departure_after"): res = [f for f in res if f["departure_local"][11:16] >= a["departure_after"]]
        if a.get("departure_before"): res = [f for f in res if f["departure_local"][11:16] <= a["departure_before"]]
        res.sort(key=SORTS.get(a.get("sort_by") or "price", SORTS["price"]))
        st["last_query"] = {k: v for k, v in a.items() if v not in (None, "")}
        total = len(res)
        res = res[:MAX_LIST]
        st["last_results"] = [f["id"] for f in res]
        st["selected"] = res[0]["id"] if len(res) == 1 else None
        query = {"origin": o, "destination": d, "date": date}
        if not res:
            alts = sorted({f["departure_local"][:10] for f in route})
            return empty(D, "search", query=query, assumption=assumed, other_dates_on_this_route=alts)
        return ok(D, "search", query=query, assumption=assumed, total_matches=total, flights=[self.view(f) for f in res])

    def reserve(self, st, fid, n):
        f = self.repo.get(fid)
        if n < 1:
            return error(D, "reserve", "Number of passengers must be at least 1.")
        if f["seats_available"] is not None and f["seats_available"] < n:
            return error(D, "reserve", f"Only {f['seats_available']} seat(s) left on this flight.", seats_left=f["seats_available"])
        if not self.repo.reserve_seats(fid, n):
            return error(D, "reserve", "Could not reserve seats, please try again.")
        r = {"code": code("FR"), "flight_id": fid, "passengers": n, "total_azn": round(f["price_azn"] * n, 2)}
        st["reservations"].append(r)
        st["selected"] = fid
        return ok(D, "reserve", reservation=r, flight=self.view(self.repo.get(fid)), note="mock reservation, no payment")
