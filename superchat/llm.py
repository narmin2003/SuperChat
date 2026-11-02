import json
import logging
import re
import time
from . import config

log = logging.getLogger("superchat.llm")
_client = None
PERMANENT = {400, 401, 403, 404, 410}  # retrying these never helps


class LLMError(Exception):
    pass


def _get_client():
    global _client
    if _client is None:
        import os
        from openai import OpenAI
        _client = OpenAI(base_url=config.NVIDIA_BASE_URL, api_key=os.environ["NVIDIA_API_KEY"], timeout=40, max_retries=0)
    return _client


def chat(system: str, user: str, max_tokens=700, temperature=0.0) -> str:
    """One chat completion. Retries only temporary failures (429 / 5xx / network); permanent errors
    (wrong or retired model, bad key) switch the LLM off and the rule-based router takes over."""
    delays = [1.5, 4, 8]
    last = None
    for attempt in range(len(delays) + 1):
        t0 = time.time()
        try:
            r = _get_client().chat.completions.create(
                model=config.MODEL, temperature=temperature, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            text = r.choices[0].message.content or ""
            log.info("LLM %s answered in %.1fs", config.MODEL, time.time() - t0)
            return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        except Exception as e:  # noqa: BLE001
            last = e
            status = getattr(e, "status_code", None)
            if status in PERMANENT:
                config.LLM_DISABLED = f"HTTP {status} for model {config.MODEL}"
                log.error("LLM disabled (%s). Run `python tools/find_model.py` to pick a working model, then restart.", config.LLM_DISABLED)
                raise LLMError(config.LLM_DISABLED)
            log.warning("LLM call failed (attempt %d): %s %s", attempt + 1, type(e).__name__, status or "")
            if attempt < len(delays):
                time.sleep(delays[attempt])
    raise LLMError(str(last))


def extract_json(text: str):
    text = re.sub(r"```(?:json)?", "", text)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in LLM output")
    return json.loads(text[a:b + 1])
