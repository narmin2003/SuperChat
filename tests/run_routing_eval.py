"""Routing accuracy test. Usage:  python tests/run_routing_eval.py          (LLM if NVIDIA_API_KEY is set)
                                  USE_LLM=0 python tests/run_routing_eval.py (rules only)
Writes TEST_LOG.md with accuracy per category and an error list for the error analysis."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections import defaultdict
from superchat import config
from superchat.engine import SuperChat
from tests.cases import CASES

delay = float(os.getenv("EVAL_DELAY", "2.0" if config.use_llm() else "0"))
bot, per, errors, ok_n = SuperChat(), defaultdict(lambda: [0, 0]), [], 0
for i, (turns, expect) in enumerate(CASES):
    sid, got, r = f"eval{i}", None, None
    for t in turns:
        r = bot.handle(sid, t)
        time.sleep(delay)
    got = r["category"]
    per[expect][1] += 1
    if got == expect:
        per[expect][0] += 1; ok_n += 1
    else:
        errors.append((turns, expect, got, r["reply"][:140].replace("\n", " ")))
mode = f"LLM {config.MODEL}" if config.use_llm() else "rules only"
lines = [f"# Routing test log ({mode})", "", f"Overall: **{ok_n}/{len(CASES)} = {100*ok_n/len(CASES):.1f}%**", "",
         "| Category | Correct | Total | Accuracy |", "|---|---|---|---|"]
for k in sorted(per):
    c, n = per[k]; lines.append(f"| {k} | {c} | {n} | {100*c/n:.0f}% |")
lines += ["", "## Errors", "", "| Conversation (last turn) | Expected | Got | Reply start |", "|---|---|---|---|"]
for turns, e, g, rep in errors:
    lines.append(f"| {turns[-1]} | {e} | {g} | {rep} |")
open("TEST_LOG.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
