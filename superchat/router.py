"""Hybrid router: one LLM call classifies the message AND extracts slots as JSON (function-calling style),
Python executes the tools. If the LLM fails or returns invalid output, rules.py takes over."""
import logging
from . import config, llm, rules
from .text import calendar_hint

log = logging.getLogger("superchat.router")

VALID = {
    "flights": {"search", "details", "compare", "reserve", "recall"},
    "shopping": {"search", "details", "compare", "add_to_cart", "remove_from_cart", "show_cart", "recall"},
    "cinema": {"movies", "showtimes", "details", "reserve", "recall"},
}

SYSTEM = """You are the routing brain of SuperChat, one chat for three domains: flights, shopping (e-commerce), cinema.
Read the latest user message plus the session state and output ONE JSON object, nothing else (no markdown, no prose).

Today is {today}. Calendar:
{calendar}
Resolve relative dates (tonight, tomorrow, Friday, Saturday, "6 November") to ISO dates with this calendar.

JSON schema:
{{"language":"en|az|ru","route":"answer|ambiguous|out_of_scope","is_followup":true|false,
 "intents":[{{"domain":"flights|shopping|cinema","action":"...","args":{{...}}}}],
 "clarifying_question":null|"one short question in the user's language","refusal":null|"one polite sentence in the user's language"}}

Actions and args (omit unknown args, never invent values):
flights: search{{origin,destination,date,max_price,max_stops,airline,cabin,sort_by:price|departure|duration|stops,departure_after:"HH:MM",departure_before}}
  | details{{ids}} | compare{{ids}} | reserve{{ids:[one id],passengers}} | recall{{}}
shopping: search{{query,category,brand,min_price,max_price,color,in_stock_only,sort_by:price|rating}} | details{{ids}} | compare{{ids}}
  | add_to_cart{{ids,quantity}} | remove_from_cart{{ids}} | show_cart{{}} | recall{{query}}
cinema: movies{{genre,language,date,min_rating,query,cinema}} | showtimes{{movie,genre,date,cinema,min_seats}}
  | details{{movie}} | reserve{{showtime_id,seats}} | recall{{}}

Rules:
- route "answer" with >=1 intent. If the message holds several requests (e.g. a flight AND a backpack) output one intent per request.
- route "ambiguous": cannot be assigned confidently, or a booking/purchase has no target that the state can supply
  ("show me something good", "book it", "book two seats" with nothing selected or listed). Ask exactly ONE short question.
- route "out_of_scope": unrelated to flights/shopping/cinema (weather, news, jokes...). Refuse politely in one sentence and say you can help with flights, shopping and cinema.
- Follow-ups ("the cheaper one", "the second one", "and for Saturday?", "back to the headphones") are resolved against the state:
  items are numbered in the order they were shown; use their ids (F.., P.., S.., M..) in args.ids. "Cheaper one" = lowest price among the items last listed.
  "The second one" = item #2 of the active (last_domain) list. Never invent ids that are not in the state.
- To book a showtime from state use cinema reserve with showtime_id and seats; for a flight use flights reserve with ids and passengers.
- Keep values in English: city names (Baku, Istanbul), genres (sci-fi, comedy, horror...), colours, languages (English/Azerbaijani/Russian).
  Product "query" = the product noun in English (headphones, laptop, backpack...).
- Cinema "tonight" = today's date. A genre request for seats/showtimes = cinema showtimes with genre.
- language = language of the user's message.
"""


def _state_text(session, modules):
    parts = [f"last_domain={session.shared['last_domain']} language={session.shared['language']}"]
    for d in ("flights", "shopping", "cinema"):
        parts.append(modules[d].summary(session))
    return "\n".join(parts)


def _history_text(session, n=6):
    return "\n".join(f"{h['role']}: {h['text'][:200]}" for h in session.history[-n:]) or "(none)"


def _sanitize(r):
    route = r.get("route", "answer")
    intents = []
    for it in r.get("intents") or []:
        d, a = it.get("domain"), it.get("action")
        if d in VALID and a in VALID[d]:
            args = it.get("args") if isinstance(it.get("args"), dict) else {}
            intents.append({"domain": d, "action": a, "args": args})
    if route == "answer" and not intents:
        route = "ambiguous"
        r["clarifying_question"] = r.get("clarifying_question") or "Could you clarify what you need: a flight, a product or a film?"
    return {"language": r.get("language") if r.get("language") in ("en", "az", "ru") else "en",
            "route": route if route in ("answer", "ambiguous", "out_of_scope") else "answer",
            "is_followup": bool(r.get("is_followup")), "intents": intents,
            "clarifying_question": r.get("clarifying_question"), "refusal": r.get("refusal"), "source": "llm"}


def route(text, session, modules, repos):
    if config.use_llm():
        system = SYSTEM.format(today=f"{config.REF_DATE:%A} {config.REF_DATE.isoformat()}", calendar=calendar_hint())
        user = f"SESSION STATE:\n{_state_text(session, modules)}\n\nRECENT TURNS:\n{_history_text(session)}\n\nUSER MESSAGE: {text}"
        for attempt in range(2):
            try:
                return _sanitize(llm.extract_json(llm.chat(system, user, max_tokens=500)))
            except llm.LLMError as e:
                log.warning("LLM unavailable, using rules: %s", e)
                break
            except (ValueError, KeyError, TypeError) as e:
                log.warning("Bad router JSON (attempt %d): %s", attempt + 1, e)
    r = rules.route(text, session, repos)
    r["source"] = "rules"
    return r
