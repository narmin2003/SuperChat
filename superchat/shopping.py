import re
from .common import ok, empty, needs, error, as_list, MAX_LIST
from .text import norm, num, stem_in

D = "shopping"
STOP = {"the", "and", "for", "any", "some", "show", "find", "have", "you", "with", "under", "below", "azn", "please", "want", "need", "looking"}


class ShoppingModule:
    domain = D

    def __init__(self, repo):
        self.repo = repo

    def view(self, p):
        return {"id": p["id"], "name": p["name"]["en"], "name_az": p["name"]["az"], "name_ru": p["name"]["ru"],
                "category": p["category"], "brand": p["brand"], "price_azn": p["price_azn"], "rating": p["rating"],
                "stock": p["stock"], "in_stock": p["stock"] > 0, "color": p["color"], "description": p.get("description")}

    def summary(self, s):
        st = s.shopping
        rows = []
        for i, pid in enumerate(st["last_results"], 1):
            p = self.repo.get(pid)
            rows.append(f"  {i}) {pid} {p['name']['en']} {p['price_azn']} AZN stock={p['stock']}")
        cart = {k: v for k, v in st["cart"].items()}
        past = [x["query"] for x in st["searches"]]
        return f"shopping: selected={st['selected']} cart={cart} past_searches={past}\n" + ("\n".join(rows) if rows else "  (no results yet)")

    def _hay(self, p, with_description=False):
        parts = [*p["name"].values(), p["category"], p["brand"], p["color"]]
        if with_description:
            parts.append(p.get("description") or "")
        return norm(" ".join(parts))

    def _ids(self, a, st):
        ids = [i for i in as_list(a.get("ids") or a.get("id")) if self.repo.get(i)]
        if not ids and st["selected"]:
            ids = [st["selected"]]
        if not ids and len(st["last_results"]) == 1:
            ids = list(st["last_results"])
        return ids

    def handle(self, s, action, a):
        st = s.shopping
        if action == "search":
            return self.search(st, a)
        if action == "recall":
            return self.recall(st, a)
        if action == "details":
            ids = self._ids(a, st)
            if not ids:
                return needs(D, action, "Which product do you mean?")
            st["selected"] = ids[0]
            return ok(D, action, products=[self.view(self.repo.get(i)) for i in ids])
        if action == "compare":
            ids = [i for i in as_list(a.get("ids")) if self.repo.get(i)] or st["last_results"][:3]
            if len(ids) < 2:
                return needs(D, action, "Which products should I compare?")
            return ok(D, action, products=[self.view(self.repo.get(i)) for i in ids])
        if action == "add_to_cart":
            ids = self._ids(a, st)
            if not ids:
                return needs(D, action, "Which product should I add to the cart?")
            return self.add(st, ids[0], int(num(a.get("quantity")) or 1))
        if action == "remove_from_cart":
            ids = [i for i in as_list(a.get("ids") or a.get("id")) if i in st["cart"]] or ([st["selected"]] if st["selected"] in st["cart"] else [])
            if not ids:
                return error(D, action, "That product is not in the cart.", cart=self.cart_view(st))
            for i in ids:
                st["cart"].pop(i)
            return ok(D, action, removed=ids, cart=self.cart_view(st))
        if action == "show_cart":
            return ok(D, action, cart=self.cart_view(st))
        return error(D, action, f"Unsupported shopping action: {action}")

    def cart_view(self, st):
        items, total = [], 0.0
        for pid, q in st["cart"].items():
            p = self.repo.get(pid)
            sub = round(p["price_azn"] * q, 2)
            total += sub
            items.append({"id": pid, "name": p["name"]["en"], "name_az": p["name"]["az"], "name_ru": p["name"]["ru"],
                          "quantity": q, "unit_price_azn": p["price_azn"], "subtotal_azn": sub})
        return {"items": items, "total_azn": round(total, 2)}

    def add(self, st, pid, q):
        p = self.repo.get(pid)
        have = st["cart"].get(pid, 0)
        if q < 1:
            return error(D, "add_to_cart", "Quantity must be at least 1.")
        if p["stock"] <= 0:
            return error(D, "add_to_cart", "This product is out of stock.", product=self.view(p))
        if have + q > p["stock"]:
            return error(D, "add_to_cart", f"Only {p['stock']} in stock ({have} already in cart).", product=self.view(p))
        st["cart"][pid] = have + q
        st["selected"] = pid
        return ok(D, "add_to_cart", added=self.view(p), quantity=q, cart=self.cart_view(st))

    def recall(self, st, a):
        q = norm(a.get("query") or "")
        if q:
            for srch in reversed(st["searches"]):
                if all(stem_in(t, norm(srch["query"])) for t in q.split() if len(t) >= 3):
                    st["last_results"] = list(srch["ids"])
                    st["selected"] = srch["ids"][0] if len(srch["ids"]) == 1 else None
                    break
        if not st["last_results"]:
            return empty(D, "recall", message="No earlier product search in this session.")
        return ok(D, "recall", products=[self.view(self.repo.get(i)) for i in st["last_results"]], cart=self.cart_view(st))

    def search(self, st, a):
        toks = [t for t in re.split(r"\W+", norm(a.get("query") or "")) if len(t) >= 3 and t not in STOP]
        cats = [t for t in re.split(r"\W+", norm(a.get("category") or "")) if len(t) >= 3]
        lo, hi = num(a.get("min_price")), num(a.get("max_price"))
        res = []
        products = self.repo.all()
        # match on name/category/brand/colour first; fall back to descriptions only if that finds nothing
        for with_desc in (False, True):
            hits = [p for p in products if all(stem_in(t, self._hay(p, with_desc)) for t in toks + cats)]
            if hits or not (toks or cats):
                break
        for p in hits:
            if a.get("brand") and norm(a["brand"]) not in norm(p["brand"]): continue
            if a.get("color") and norm(a["color"]) not in norm(p["color"]): continue
            if lo is not None and p["price_azn"] < lo: continue
            if hi is not None and p["price_azn"] > hi: continue
            if a.get("in_stock_only") and p["stock"] <= 0: continue
            res.append(p)
        sb = a.get("sort_by")
        if sb == "price": res.sort(key=lambda p: p["price_azn"])
        elif sb == "rating": res.sort(key=lambda p: -p["rating"])
        total, res = len(res), res[:MAX_LIST]
        qdesc = " ".join(toks + cats) or "all"
        st["last_query"] = {k: v for k, v in a.items() if v not in (None, "")}
        st["last_results"] = [p["id"] for p in res]
        st["selected"] = res[0]["id"] if len(res) == 1 else None
        st["searches"] = (st["searches"] + [{"query": qdesc, "ids": list(st["last_results"])}])[-6:]
        if not res:
            return empty(D, "search", query=a)
        return ok(D, "search", query=a, total_matches=total, products=[self.view(p) for p in res])
