import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
REF_DATE = date.fromisoformat(os.getenv("REF_DATE", "2026-11-02"))  # reference date of the mock dataset
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
MODEL = os.getenv("SUPERCHAT_MODEL", "meta/llama-3.3-70b-instruct")


LLM_DISABLED = None  # set by llm.py after a permanent error (410/404/401/403) so we stop retrying


def use_llm() -> bool:
    """Read dynamically so tests can switch USE_LLM=0 (rule-based fallback only)."""
    return os.getenv("USE_LLM", "1") != "0" and bool(os.getenv("NVIDIA_API_KEY")) and LLM_DISABLED is None
