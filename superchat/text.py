import re
from datetime import timedelta
from . import config

_MAP = str.maketrans({"ı": "i", "İ": "i", "ə": "e", "Ə": "e", "ş": "s", "Ş": "s", "ç": "c", "Ç": "c",
                      "ğ": "g", "Ğ": "g", "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "ё": "е"})


def norm(s) -> str:
    """Lowercase + fold Azerbaijani letters so 'Bakı'/'baki', 'Noutbuk'/'noutbuk' match."""
    s = (str(s) if s is not None else "").translate(_MAP).lower()
    return re.sub(r"\s+", " ", s).strip()


def num(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def stem_in(token: str, hay: str) -> bool:
    """Cheap multilingual stemming: 'headphones' -> 'headphon', 'наушники' -> 'наушни'."""
    t = norm(token)
    return bool(t) and t[: max(4, len(t) - 2)] in hay


CITY_ALIASES = {
    "Baku": ["gyd", "baku", "baki", "баку"],
    "Istanbul": ["ist", "istanbul", "стамбул"],
    "Dubai": ["dxb", "dubai", "dubay", "дубай"],
    "Moscow": ["svo", "dme", "moscow", "moskva", "moskov", "москв"],
    "Tbilisi": ["tbs", "tbilisi", "tiflis", "тбилис"],
    "Tashkent": ["tas", "tashkent", "daskend", "ташкент"],
}


def canon_city(x):
    if not x:
        return None
    n = norm(x)
    for city, aliases in CITY_ALIASES.items():
        for a in aliases:
            if (len(a) == 3 and n == a) or (len(a) > 3 and n.startswith(a)):
                return city
    return str(x).strip().title()


def find_cities_in_text(text: str):
    """Ordered list of known cities mentioned in free text (used by the rule-based router)."""
    found = []
    for w in re.findall(r"[\w'-]+", norm(text)):
        for city, aliases in CITY_ALIASES.items():
            if any(len(a) > 3 and w.startswith(a) for a in aliases) and city not in found:
                found.append(city)
    return found


WEEKDAYS = [  # monday=0 ; longer names first inside each list
    ["monday", "bazar ertesi", "понедельн"], ["tuesday", "cersenbe axsami", "вторник"],
    ["wednesday", "cersenbe", "сред"], ["thursday", "cume axsami", "четверг"],
    ["friday", "cume", "пятниц"], ["saturday", "senbe", "суббот"], ["sunday", "bazar", "воскресен"],
]
MONTHS = {"january": 1, "yanvar": 1, "январ": 1, "february": 2, "fevral": 2, "феврал": 2, "march": 3, "mart": 3, "март": 3,
          "april": 4, "aprel": 4, "апрел": 4, "may": 5, "май": 5, "мая": 5, "june": 6, "iyun": 6, "июн": 6,
          "july": 7, "iyul": 7, "июл": 7, "august": 8, "avqust": 8, "август": 8, "september": 9, "sentyabr": 9, "сентябр": 9,
          "october": 10, "oktyabr": 10, "октябр": 10, "november": 11, "noyabr": 11, "ноябр": 11, "december": 12, "dekabr": 12, "декабр": 12}


def resolve_date(text: str):
    """Free text -> ISO date relative to the dataset's reference date, or None."""
    n = norm(text)
    today = config.REF_DATE
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", n)
    if m:
        return m.group(0)
    if re.search(r"tonight|today|bu axsam|bu gun|сегодня|\bbugun", n):
        return today.isoformat()
    if re.search(r"tomorrow|\bsabah\b|завтра", n):
        return (today + timedelta(days=1)).isoformat()
    for key, mo in MONTHS.items():
        m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?{key}", n) or re.search(rf"{key}\w*\s+(\d{{1,2}})\b", n)
        if m:
            try:
                return today.replace(month=mo, day=int(m.group(1))).isoformat()
            except ValueError:
                return None
    for wd, names in enumerate(WEEKDAYS):
        if any(re.search(rf"(?<![a-z]){nm}", n) for nm in names):
            return (today + timedelta(days=(wd - today.weekday()) % 7)).isoformat()
    return None


def calendar_hint(days=10) -> str:
    return "\n".join(f"{(config.REF_DATE + timedelta(days=i)):%A} {(config.REF_DATE + timedelta(days=i)).isoformat()}"
                     + (" (today)" if i == 0 else "") for i in range(days))
