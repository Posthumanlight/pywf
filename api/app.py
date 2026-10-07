"""FastAPI frontend for pywf. Serves a one-page chat UI and a small JSON API."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

from db.core import DB_PATH
from engine.core import (
    MissingCharactersError,
    PartyContext,
    UnknownTargetError,
    build_party,
    parse_dm_line,
    run_round,
)


_INDEX_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>pywf</title>
<style>
 body { font: 14px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; max-width: 760px; margin: 2em auto; padding: 0 1em; color: #111; }
 h1 { font-size: 1.15em; margin-bottom: .5em; }
 #roster { color: #666; font-weight: normal; }
 #log { white-space: pre-wrap; min-height: 50vh; border: 1px solid #ddd; padding: 1em; margin: 0; }
 #log .speaker { font-weight: bold; }
 #log .err { color: #a00; }
 form { display: flex; gap: .5em; margin-top: 1em; }
 #dm { flex: 1; padding: .5em; font: inherit; }
 button { padding: .5em 1em; font: inherit; cursor: pointer; }
</style>
</head>
<body>
<h1>pywf <span id="roster"></span></h1>
<div id="log"></div>
<form id="f">
 <input id="dm" placeholder="DM> type here (prefix @id to target one)" autofocus autocomplete="off">
 <button type="submit">send</button>
</form>
<script>
const log = document.getElementById('log');
const esc = s => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function append(speaker, text, cls) {
  const div = document.createElement('div');
  div.innerHTML = `<span class="speaker ${cls||''}">${esc(speaker)}&gt;</span> <span class="${cls||''}">${esc(text)}</span>`;
  log.appendChild(div);
  window.scrollTo(0, document.body.scrollHeight);
}
async function loadParty() {
  try {
    const r = await fetch('/party');
    const data = await r.json();
    document.getElementById('roster').textContent =
      '— party: ' + data.party.map(p => `${p.name} (@${p.id})`).join(', ');
  } catch (e) { append('error', 'failed to load /party: ' + e, 'err'); }
}
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = document.getElementById('dm');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  append('DM', text);
  try {
    const r = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({dm: text}),
    });
    if (!r.ok) {
      const body = await r.text();
      append('error', `HTTP ${r.status}: ${body}`, 'err');
      return;
    }
    const data = await r.json();
    for (const t of data.turns) append(t.name, t.text);
  } catch (err) { append('error', String(err), 'err'); }
});
loadParty();
</script>
</body>
</html>
"""


class ChatRequest(BaseModel):
    dm: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SqliteSaver.from_conn_string(str(DB_PATH)) as saver:
        try:
            ctx = build_party(saver)
        except MissingCharactersError as exc:
            raise RuntimeError(
                f"{exc} Available ids: {exc.available}. "
                "Seed one with: poetry run python scripts/seed_character.py <path-to-json>"
            ) from exc
        app.state.ctx = ctx
        yield


app = FastAPI(title="pywf", lifespan=lifespan)


def _ctx(app: FastAPI) -> PartyContext:
    return app.state.ctx


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML


@app.get("/party")
def party() -> dict:
    ctx = _ctx(app)
    return {"party": [{"id": cid, "name": ctx.names[cid]} for cid in ctx.party_ids]}


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    ctx = _ctx(app)
    if not req.dm or not req.dm.strip():
        raise HTTPException(status_code=400, detail="empty dm")
    try:
        parsed = parse_dm_line(req.dm, ctx.party_ids)
    except UnknownTargetError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown party member", "target": exc.target, "party": exc.party_ids},
        )
    turns = run_round(ctx, parsed.dm_text, parsed.order)
    return {"order": parsed.order, "turns": turns}
