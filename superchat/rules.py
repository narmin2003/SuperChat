"""Rule-based router: used when the LLM is unavailable (no key, rate limit, bad output).
Same output schema as the LLM router so the rest of the pipeline is identical."""
import re
from .text import norm, find_cities_in_text, resolve_date, num, stem_in

KW = {
    "flights": ["flight", "fly ", "flying", "airline", "airport", "baggage", "reys", "ucus", "uchus", "aviabilet", "aktarma",
                "рейс", "авиа", "перелет", "перелёт", "самолет", "пересад", "полет", "полёт", "direct", "nonstop", "layover"],
    "shopping": ["laptop", "noutbuk", "ноутбук", "headphone", "qulaq", "науш", "phone", "telefon", "smartfon", "смартфон",
                 "watch", "saat", "speaker", "dinamik", "колонк", "shoes", "ayaqqabi", "кроссов", "обув", "backpack", "canta", "рюкзак",
                 "coffee", "qehve", "кофе", "board game", "stolustu", "настольн", "cart", "sebet", "корзин", "product", "mehsul", "товар",
                 "buy", "stock", "anbar", "наличи", "earbud", "gift", "hediyye", "подар", "brand", "ukr"],
    "cinema": ["movie", "film", "cinema", "kino", "кино", "фильм", "showtime", "seans", "сеанс", "playing", "genre", "sci-fi", "scifi",
               "comedy", "horror", "thriller", "animation", "komediya", "комеди", "ужас", "фантаст", "мультфильм", "hall", "cinemaplus"],
}
OOS = ["weather", "hava", "погод", "news", "xeber", "новост", "recipe", "retsept", "joke", "lətifə", "анекдот", "capital of", "president",
       "stock market", "bitcoin", "football score", "translate", "homework"]
ORD = {"first": 1, "1st": 1, "birinci": 1, "perv": 1, "первый": 1, "первая": 1, "second": 2, "2nd": 2, "ikinci": 2, "втор": 2,
       "third": 3, "3rd": 3, "ucuncu": 3, "трет": 3}
BOOK = ["book", "reserve", "rezerv", "buy ticket", "bron", "забронир", "резерв"]
CART_ADD = ["add to cart", "add it", "sebete", "в корзину", "put in cart", "add to my cart"]
CART_RM = ["remove", "sil", "убери", "удали", "delete"]
CART = ["cart", "sebet", "корзин", "basket"]
COMPARE = ["compare", "muqayis", "сравн", "difference", "versus", " vs "]
BACK = ["back to", "geri", "вернемся", "вернёмся", "вернуться к", "go back"]
STOPW = {"show", "me", "some", "any", "the", "a", "an", "do", "you", "have", "i", "need", "want", "find", "for", "under", "below",
         "azn", "please", "and", "with", "is", "it", "in", "on", "to", "of", "what", "are", "there", "can", "get", "looking", "cheap"}
GENRES = ["sci-fi", "scifi", "comedy", "horror", "thriller", "animation", "action", "drama", "romance", "adventure", "family", "crime", "mystery"]


def detect_lang(text):
    t = text.lower()
    if re.search(r"[а-яё]", t):
        return "ru"
    if re.search(r"[əığöüşç]", t) or re.search(r"\b(var|bir|ucun|ücün|goster|göstər|isteyirem|istəyirəm|lazim|lazım|axtar|haqqinda|nece|neçə)\b", t):
        return "az"
    return "en"


def _has(n, words):
    return any(w in n for w in words)


def _domains(n):
    return [d for d, ws in KW.items() if _has(n, ws)]


def _ordinal(n):
    for k, v in ORD.items():
        if re.search(rf"(?<!\w){k}", n):
            return v
    return None


def route(text, session, repos=None):
    n = norm(text)
    lang = detect_lang(text)
    last = session.shared.get("last_domain")
    doms = _domains(n)
    words = re.findall(r"\w+", n)
    base = {"language": lang, "is_followup": False, "clarifying_question": None, "refusal": None, "intents": [], "route": "answer"}

    if _has(n, OOS) and not doms:
        return {**base, "route": "out_of_scope", "refusal": {
            "en": "Sorry, I can only help with flights, shopping and cinema.",
            "az": "Bağışlayın, mən yalnız uçuşlar, alış-veriş və kino mövzusunda kömək edə bilərəm.",
            "ru": "Извините, я могу помочь только с авиабилетами, покупками и кино."}[lang]}

    # back-reference to an earlier topic
    if _has(n, BACK) and doms:
        return {**base, "is_followup": True, "intents": [{"domain": d, "action": "recall", "args": {"query": " ".join(w for w in words if w not in STOPW and w not in ("back", "to"))}} for d in doms[:1]]}

    wants_book = _has(n, BOOK)
    if not doms:
        if last and len(words) <= 9:  # short message depending on context
            doms, base["is_followup"] = [last], True
        elif wants_book or len(words) <= 4:
            return {**base, "route": "ambiguous", "clarifying_question": {
                "en": "Could you tell me more: are you looking for a flight, a product or a film?",
                "az": "Zəhmət olmasa dəqiqləşdirin: uçuş, məhsul, yoxsa film axtarırsınız?",
                "ru": "Уточните, пожалуйста: вы ищете рейс, товар или фильм?"}[lang]}
        else:
            return {**base, "route": "out_of_scope", "refusal": {
                "en": "Sorry, I can only help with flights, shopping and cinema.",
                "az": "Bağışlayın, mən yalnız uçuşlar, alış-veriş və kino mövzusunda kömək edə bilərəm.",
                "ru": "Извините, я могу помочь только с авиабилетами, покупками и кино."}[lang]}
    if wants_book and not doms:
        return {**base, "route": "ambiguous", "clarifying_question": "Which film/showtime or flight should I book?"}

    intents = []
    for d in doms:
        a = _intent(d, n, text, session, wants_book, repos)
        if a:
            intents.append(a)
    if not intents:
        return {**base, "route": "ambiguous", "clarifying_question": "Which flight, product or film do you mean?"}
    return {**base, "intents": intents}


def _pick(session, d, n, repos):
    """Resolve 'the second one' / 'cheaper one' against the last listed results of a domain."""
    st = session.domain_state(d)
    ids = st["last_movies"] if False else st["last_results"]
    if not ids:
        return None
    k = _ordinal(n)
    if k and k <= len(ids):
        return ids[k - 1]
    if repos and re.search(r"cheap|ucuz|дешев|lowest", n):
        if d == "flights":
            return min(ids, key=lambda i: repos.flights.get(i)["price_azn"])
        if d == "shopping":
            return min(ids, key=lambda i: repos.products.get(i)["price_azn"])
    return None


def _intent(d, n, text, session, wants_book, repos):
    date = resolve_date(text)
    mp = None
    m = re.search(r"(?:under|below|up to|max|en cox|ən çox|до|менее|dən aşağı)\s*(\d+)", n) or re.search(r"(\d+)\s*(?:azn|manat|ман)", n)
    if m:
        mp = num(m.group(1))
    if d == "flights":
        pid = _pick(session, d, n, repos)
        if wants_book:
            return {"domain": d, "action": "reserve", "args": {"ids": [pid] if pid else [], "passengers": _count(n)}}
        if _has(n, COMPARE):
            return {"domain": d, "action": "compare", "args": {}}
        short = len(n.split()) <= 8
        if (pid or _has(n, ["direct", "nonstop", "duz", "прям", "baggage", "bagaj", "багаж", "seats", "stops"])) and session.flights["last_results"] and short:
            return {"domain": d, "action": "details", "args": {"ids": [pid] if pid else []}}
        cities = find_cities_in_text(text)
        dest = cities[-1] if cities else None
        orig = cities[0] if len(cities) > 1 else None
        if _has(n, ["from", "dan ", "den ", "из "]) is False and len(cities) == 1:
            orig = None
        sort = "price" if re.search(r"cheap|ucuz|дешев", n) else ("departure" if "earliest" in n else None)
        return {"domain": d, "action": "search", "args": {"origin": orig, "destination": dest, "date": date, "max_price": mp,
                                                            "max_stops": 0 if _has(n, ["direct", "nonstop", "прям", "duz"]) else None, "sort_by": sort}}
    if d == "shopping":
        pid = _pick(session, d, n, repos)
        if _has(n, CART_RM) and _has(n, CART + ["it"]) or (_has(n, CART_RM) and session.shopping["cart"]):
            return {"domain": d, "action": "remove_from_cart", "args": {"ids": [pid] if pid else []}}
        if _has(n, CART_ADD):
            return {"domain": d, "action": "add_to_cart", "args": {"ids": [pid] if pid else [], "quantity": _count(n)}}
        if _has(n, CART) and not _has(n, ["add"]):
            return {"domain": d, "action": "show_cart", "args": {}}
        if _has(n, COMPARE):
            return {"domain": d, "action": "compare", "args": {}}
        if pid or (_has(n, ["stock", "anbar", "наличи", "available"]) and session.shopping["last_results"] and len(n.split()) <= 8):
            return {"domain": d, "action": "details", "args": {"ids": [pid] if pid else []}}
        catalog = " ".join(norm(" ".join([*p["name"].values(), p["category"], p["brand"], p["color"]])) for p in repos.products.all()) if repos else ""
        words = [w for w in re.findall(r"\w+", n) if len(w) >= 3 and w not in STOPW and not w.isdigit() and w != "azn"
                 and (not catalog or stem_in(w, catalog))]
        return {"domain": d, "action": "search", "args": {"query": " ".join(words), "max_price": mp}}
    if d == "cinema":
        if wants_book:
            return {"domain": d, "action": "reserve", "args": {"seats": _count(n)}}
        genre = next((g for g in GENRES if g in n), None) or ("sci-fi" if _has(n, ["фантаст", "fantast"]) else None)
        if _has(n, ["seat", "yer", "мест", "showtime", "seans", "сеанс", "available", "price", "bilet", "билет"]) or ("playing" in n and False):
            return {"domain": d, "action": "showtimes", "args": {"genre": genre, "date": date}}
        return {"domain": d, "action": "movies", "args": {"genre": genre, "date": date}}
    return None


def _count(n):
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "iki": 2, "uc": 3, "dve": 2, "два": 2, "три": 3}
    m = re.search(r"\b(\d+)\b", n)
    if m:
        return int(m.group(1))
    return next((v for k, v in words.items() if re.search(rf"\b{k}\b", n)), 1)
