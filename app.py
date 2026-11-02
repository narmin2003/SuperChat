import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
from superchat.engine import SuperChat

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = FastAPI(title="SuperChat")
bot = SuperChat()
STATIC = Path(__file__).parent / "static"


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str


@app.post("/api/chat")
def chat(body: ChatIn):
    return bot.handle(body.session_id, body.message.strip()[:1000])


@app.post("/api/reset")
def reset(body: ChatIn):
    if body.session_id:
        bot.reset(body.session_id)
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
