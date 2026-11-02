import logging
import uuid
from . import router, composer, rules
from .flights import FlightsModule
from .shopping import ShoppingModule
from .cinema import CinemaModule
from .repositories import build_repositories
from .state import Session

log = logging.getLogger("superchat.engine")

FRIENDLY_ERROR = {"en": "Something went wrong on my side. Please try again.",
                  "az": "Mənim tərəfimdə xəta baş verdi. Zəhmət olmasa, yenidən cəhd edin.",
                  "ru": "Произошла ошибка. Пожалуйста, попробуйте ещё раз."}


class SuperChat:
    def __init__(self, repos=None):
        self.repos = repos or build_repositories()
        self.modules = {"flights": FlightsModule(self.repos.flights), "shopping": ShoppingModule(self.repos.products),
                        "cinema": CinemaModule(self.repos.movies, self.repos.cinemas, self.repos.showtimes)}
        self.sessions = {}

    def session(self, sid=None):
        sid = sid or uuid.uuid4().hex[:10]
        if sid not in self.sessions:
            self.sessions[sid] = Session(id=sid)
        return self.sessions[sid]

    def reset(self, sid):
        self.sessions.pop(sid, None)

    @staticmethod
    def category(route):
        if route["route"] == "ambiguous": return "ambiguous"
        if route["route"] == "out_of_scope": return "out_of_scope"
        doms = {i["domain"] for i in route["intents"]}
        return "mixed" if len(doms) > 1 else next(iter(doms))

    def handle(self, sid, text):
        s = self.session(sid)
        lang = s.shared["language"]
        try:
            route = router.route(text, s, self.modules, self.repos)
            lang = s.shared["language"] = route["language"]
            cat = self.category(route)
            results = []
            if route["route"] == "ambiguous":
                reply = route["clarifying_question"]
            elif route["route"] == "out_of_scope":
                reply = route["refusal"] or rules.route("weather", s)["refusal"]
            else:
                for it in route["intents"]:
                    try:
                        results.append(self.modules[it["domain"]].handle(s, it["action"], it["args"]))
                    except Exception:  # a data-source failure must never break the chat
                        log.exception("module failure")
                        results.append({"domain": it["domain"], "action": it["action"], "status": "error",
                                        "data": {"message": "The data source is temporarily unavailable."}})
                s.shared["last_domain"] = route["intents"][-1]["domain"]
                reply = composer.compose(text, route, results, lang)
            s.history += [{"role": "user", "text": text}, {"role": "assistant", "text": reply}]
            s.debug = {"category": cat, "router": route.get("source"), "is_followup": route["is_followup"], "intents": route["intents"]}
            return {"session_id": s.id, "reply": reply, "category": cat, "domains": sorted({i["domain"] for i in route["intents"]}),
                    "router": route.get("source"), "is_followup": route["is_followup"]}
        except Exception:
            log.exception("engine failure")
            return {"session_id": s.id, "reply": FRIENDLY_ERROR.get(lang, FRIENDLY_ERROR["en"]), "category": "error",
                    "domains": [], "router": None, "is_followup": False}
