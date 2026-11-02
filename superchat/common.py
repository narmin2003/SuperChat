import uuid

MAX_LIST = 8


def ok(domain, action, **data):
    return {"domain": domain, "action": action, "status": "ok", "data": data}


def empty(domain, action, **data):
    return {"domain": domain, "action": action, "status": "empty", "data": data}


def needs(domain, action, question):
    return {"domain": domain, "action": action, "status": "needs", "data": {"question": question}}


def error(domain, action, message, **data):
    return {"domain": domain, "action": action, "status": "error", "data": {"message": message, **data}}


def code(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def as_list(x):
    if x is None:
        return []
    return [str(i) for i in x] if isinstance(x, (list, tuple)) else [str(x)]
