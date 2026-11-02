"""Finds a chat model that really works with YOUR NVIDIA key and saves it to .env as SUPERCHAT_MODEL.
Usage:  python tools/find_model.py"""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from superchat import config
from openai import OpenAI

key = os.getenv("NVIDIA_API_KEY")
if not key:
    sys.exit("NVIDIA_API_KEY not found. Put it into .env first.")
client = OpenAI(base_url=config.NVIDIA_BASE_URL, api_key=key, timeout=40, max_retries=0)
ids = sorted(m.id for m in client.models.list().data)
print(f"{len(ids)} models listed by the API.")

BAD = re.compile(r"embed|rerank|guard|safety|reward|parse|ocr|clip|vision|-vl|vila|nvclip|diffusion|sdxl|flux|riva|asr|tts|whisper|"
                 r"retriev|bge|e5|genmol|molmim|diffdock|cosmos|fuyu|kosmos|paligemma|r1|reason|thinking|coder|code|math|translate|"
                 r"nemotron-4-340b-reward|arctic-embed|usdcode|calibration", re.I)
PREFER = ["llama-3.3-70b", "llama-3.1-70b", "llama-3.3-nemotron-super", "llama-3.1-nemotron-70b", "mistral-large", "mixtral",
          "qwen", "gemma", "llama-3.1-8b", "llama-3.1-nemotron-nano", "phi", "nemotron"]
chat = [i for i in ids if not BAD.search(i)]
def rank(i):
    for k, p in enumerate(PREFER):
        if p in i.lower(): return k
    return len(PREFER)
cands = sorted(chat, key=lambda i: (rank(i), i))[:25]
print(f"Testing up to {len(cands)} candidates (about 2 seconds each)...\n")

good = []
for m in cands:
    try:
        r = client.chat.completions.create(model=m, max_tokens=40, temperature=0,
            messages=[{"role": "user", "content": 'Reply with only this JSON: {"ok": true}'}])
        out = (r.choices[0].message.content or "").strip().replace("\n", " ")
        okjson = '"ok"' in out and "true" in out.lower()
        print(f"  OK   {m:60s} {'JSON ok' if okjson else 'weird: ' + out[:30]}")
        if okjson: good.append(m)
    except Exception as e:
        print(f"  FAIL {m:60s} HTTP {getattr(e, 'status_code', '?')}")
    time.sleep(2)
    if len(good) >= 3: break

if not good:
    sys.exit("\nNo working model found. Send me this whole output.")
best = good[0]
env = config.ROOT / ".env"
lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
lines = [l for l in lines if not l.startswith("SUPERCHAT_MODEL=")] + [f"SUPERCHAT_MODEL={best}"]
env.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\nSaved SUPERCHAT_MODEL={best} to .env. Other working options: {good[1:]}")
print("Now restart:  python run.py")
