"""Turns tool results into the final reply. The LLM only sees tool results, so it cannot invent data;
a plain-English template renderer is the fallback when the LLM is unavailable."""
import json
import logging
from . import config, llm

log = logging.getLogger("superchat.composer")

SYSTEM = """You are SuperChat, a concise assistant for flights, shopping and cinema.
Write the reply to the user's message using ONLY the facts in RESULTS (JSON from our systems).
Rules:
- Reply in language "{lang}" (en=English, az=Azerbaijani, ru=Russian). Be short: no filler.
- Never invent flights, products, films, prices, times or availability. If a result has status "empty", say plainly nothing matches
  (and mention other_dates_on_this_route if present). If status is "needs", ask that one question. If "error", explain the message simply.
- Present lists numbered 1., 2., 3. in the SAME order as given so the user can say "the second one". Do not show internal ids (F001, P002, S003, M001) - reservation codes ARE shown.
- Prices in AZN, times 24h and local, durations like 3h 35m. State seats left / stock when relevant; flag sold-out or out-of-stock items.
- If "assumption" is present, mention it in one short clause. If results cover several domains, give one coherent reply with a short line per domain.
- After a successful reservation say it is a mock reservation (no payment). After listing options you may end with ONE short next-step suggestion."""


def _compact(o):
    if isinstance(o, dict):
        return {k: _compact(v) for k, v in o.items() if v not in (None, [], {})}
    if isinstance(o, list):
        return [_compact(i) for i in o]
    return o


def compose(text, route, results, lang):
    if config.use_llm():
        try:
            payload = json.dumps(_compact(results), ensure_ascii=False)
            return llm.chat(SYSTEM.format(lang=lang), f"USER MESSAGE: {text}\n\nRESULTS:\n{payload}", max_tokens=600, temperature=0.2)
        except llm.LLMError as e:
            log.warning("LLM compose failed, template used: %s", e)
    return render_plain(results)


def _dur(m):
    return f"{m // 60}h {m % 60:02d}m"


def _flight(i, f):
    stops = "direct" if f["stops"] == 0 else f"{f['stops']} stop via {f['via']}"
    return (f"{i}. {f['airline']} {f['flight_number']} {f['from']}→{f['to']} {f['departure'][:10]} {f['departure'][11:]}–{f['arrival'][11:]}, "
            f"{_dur(f['duration_min'])}, {stops}, {f['baggage_kg']} kg, {f['seats_left']} seats left, {f['price_azn']:.0f} AZN")


def _product(i, p):
    st = f"{p['stock']} in stock" if p["in_stock"] else "OUT OF STOCK"
    return f"{i}. {p['name']} ({p['brand']}, {p['color']}) {p['price_azn']:.2f} AZN, rating {p['rating']}, {st}"


def _show(i, t):
    seats = "SOLD OUT" if t["sold_out"] else f"{t['seats_available']} seats left"
    return f"{i}. {t['movie']} – {t['cinema']}, {t['date']} {t['time']}, {t['hall']}, {t['price_azn']:.2f} AZN, {seats}"


def render_plain(results):
    out = []
    for r in results:
        d, a, s = r["data"], r["action"], r["status"]
        if s == "needs":
            out.append(d["question"])
        elif s == "error":
            out.append(d["message"])
        elif s == "empty":
            msg = d.get("message") or f"Nothing in our data matches ({r['domain']})."
            if d.get("other_dates_on_this_route"):
                msg += " Other dates on this route: " + ", ".join(d["other_dates_on_this_route"])
            out.append(msg)
        elif "reservation" in d:
            x = d["reservation"]
            out.append(f"Reserved (mock, no payment). Code {x['code']}, total {x['total_azn']} AZN.")
        elif "flights" in d:
            out.append(("(" + d["assumption"] + ")\n" if d.get("assumption") else "") + "\n".join(_flight(i, f) for i, f in enumerate(d["flights"], 1)))
        elif "products" in d:
            out.append("\n".join(_product(i, p) for i, p in enumerate(d["products"], 1)))
        elif "cart" in d and a in ("show_cart", "add_to_cart", "remove_from_cart"):
            c = d["cart"]
            out.append("Cart: " + (", ".join(f"{x['quantity']}× {x['name']}" for x in c["items"]) or "empty") + f". Total {c['total_azn']} AZN")
        elif "movies" in d and d["movies"] and "showtimes" in d["movies"][0]:
            lines = []
            for i, m in enumerate(d["movies"], 1):
                lines.append(f"{i}. {m['title']} ({', '.join(m['genre'])}, {m['language']}, ★{m['rating']})")
                lines += [f"   {t['cinema']} {t['date']} {t['time']} – {t['price_azn']:.2f} AZN, " + ("sold out" if t["sold_out"] else f"{t['seats_available']} seats") for t in m["showtimes"]]
            out.append("\n".join(lines))
        elif "showtimes" in d:
            out.append("\n".join(_show(i, t) for i, t in enumerate(d["showtimes"], 1)))
        elif "movie" in d:
            m = d["movie"]
            out.append(f"{m['title']} ({', '.join(m['genre'])}, {m['language']}, {m['duration_min']} min, {m['age_rating']}): {m['synopsis']}")
    return "\n\n".join(out) or "Done."
