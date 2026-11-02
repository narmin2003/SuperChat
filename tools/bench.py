"""Measures real latency of candidate models with a router-sized request.
Usage: python tools/bench.py                 (tests the 2 working models)
       python tools/bench.py model1 model2   (tests the models you name)"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from superchat import config
from superchat.router import SYSTEM
from superchat.text import calendar_hint
from superchat import llm
from openai import OpenAI

models = sys.argv[1:] or ["nvidia/nemotron-3.5-bolt-e4b", "nvidia/nemotron-3-ultra-550b-a55b"]
client = OpenAI(base_url=config.NVIDIA_BASE_URL, api_key=os.environ["NVIDIA_API_KEY"], timeout=90, max_retries=0)
system = SYSTEM.format(today="Monday 2026-11-02", calendar=calendar_hint())
msgs = ["Find me a flight from Baku to Istanbul on Friday.", "I need a flight to Istanbul on 6 November and a backpack for the trip.",
        "Show me something good.", "Bakıdan İstanbula 6 noyabrda uçuş göstər"]
for m in models:
    print(f"\n== {m}")
    for t in msgs:
        user = f"SESSION STATE:\nlast_domain=None language=en\n\nRECENT TURNS:\n(none)\n\nUSER MESSAGE: {t}"
        t0 = time.time()
        try:
            r = client.chat.completions.create(model=m, temperature=0, max_tokens=500,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            out = r.choices[0].message.content or ""
            try:
                j = llm.extract_json(out); ok = f"JSON ok route={j.get('route')} intents={[i.get('domain') for i in j.get('intents', [])]}"
            except Exception:
                ok = "BAD JSON: " + out[:60].replace("\n", " ")
            print(f"  {time.time()-t0:5.1f}s  {ok}  | {t[:40]}")
        except Exception as e:
            print(f"  {time.time()-t0:5.1f}s  ERROR {getattr(e,'status_code','?')} | {t[:40]}")
        time.sleep(1.5)
