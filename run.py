"""Single command to run SuperChat:  python run.py"""
import os
import uvicorn
from superchat import config

if __name__ == "__main__":
    mode = "LLM (NVIDIA NIM, model %s)" % config.MODEL if config.use_llm() else "RULES ONLY (set NVIDIA_API_KEY in .env to enable the LLM)"
    print(f"SuperChat router mode: {mode}")
    uvicorn.run("app:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
