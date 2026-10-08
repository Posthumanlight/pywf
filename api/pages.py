"""HTML page templates for the FastAPI frontend.

Rendered as Python strings; no templating engine. Alpine.js + HTMX via CDN.
"""
import html
import json
from typing import Any

from data.srd_catalog import CLASSES, FEATS, SPECIES, SPELLS, SUBCLASSES


_HEAD = """<meta charset="utf-8">
<title>pywf</title>
<script defer src="https://unpkg.com/alpinejs@3.14.1/dist/cdn.min.js"></script>
<script src="https://unpkg.com/htmx.org@2.0.3"></script>
<script src="https://cdn.jsdelivr.net/npm/marked"></script>
<style>
 body { font: 14px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; max-width: 960px; margin: 2em auto; padding: 0 1em; color: #111; }
 h1 { font-size: 1.15em; margin: 0 0 .75em 0; }
 nav { margin-bottom: 1em; }
 nav a { color: #06c; margin-right: 1em; }
 table { border-collapse: collapse; width: 100%; }
 th, td { text-align: left; padding: .4em .6em; border-bottom: 1px solid #eee; }
 th { background: #f6f6f6; }
 .actions a, .actions button { margin-right: .4em; }
 button, .btn { padding: .3em .8em; font: inherit; cursor: pointer; }
 .btn-danger { color: #a00; }
 fieldset { border: 1px solid #ddd; margin: 1em 0; padding: .75em 1em; }
 legend { font-weight: bold; padding: 0 .4em; }
 .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .5em; }
 .row { display: flex; gap: .5em; align-items: center; margin-bottom: .3em; }
 .row input, .row select { flex: 1; padding: .3em; font: inherit; }
 .chip { display: inline-block; background: #eef; padding: .15em .5em; border-radius: 10px; margin: 0 .3em .3em 0; }
 .chip button { background: none; border: none; margin-left: .3em; cursor: pointer; color: #a00; }
 input, textarea, select { font: inherit; padding: .3em; }
 textarea { width: 100%; min-height: 3em; }
 .error { background: #fee; border: 1px solid #a00; padding: .5em; margin: 1em 0; white-space: pre-wrap; }
 .success { background: #efe; border: 1px solid #0a0; padding: .5em; margin: 1em 0; }
 label { display: block; font-size: .85em; color: #555; margin-bottom: .1em; }
 label.inline { display: inline-block; margin-right: .5em; }
 [x-cloak] { display: none; }
 .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1em; margin: 1em 0; }
 .card { border: 1px solid #ddd; border-radius: 6px; padding: 1em; }
 .card h2 { font-size: 1em; margin: 0 0 .5em 0; }
 .card .snapshot { color: #555; min-height: 2.5em; }
 .card .actions { margin-top: .75em; }
 .back { margin-bottom: 1em; }
 .back a { color: #06c; }
 .spell-picker { position: relative; flex: 1; }
 .spell-picker input { width: 100%; }
 .suggest { position: absolute; z-index: 10; left: 0; right: 0; background: #fff; border: 1px solid #ddd; padding: .5em; max-height: 20em; overflow: auto; box-shadow: 0 2px 6px rgba(0,0,0,.08); }
 .suggest ul { list-style: none; padding: 0; margin: .5em 0 0 0; }
 .suggest li { padding: .25em .5em; cursor: pointer; }
 .suggest li:hover { background: #eef; }
 .suggest li.empty { color: #999; font-style: italic; cursor: default; }
 .srd-head { margin-bottom: .4em; }
 .srd-head .err { color: #a00; margin-left: .5em; }
 .srd-head .loading { color: #888; margin-left: .5em; }
 .srd-body { background: #fafafa; border: 1px solid #ddd; padding: .75em 1em; margin: 0; }
 .srd-body h1, .srd-body h2, .srd-body h3, .srd-body h4 { margin: .8em 0 .3em 0; line-height: 1.2; }
 .srd-body h1 { font-size: 1.3em; border-bottom: 1px solid #ccc; padding-bottom: .15em; }
 .srd-body h2 { font-size: 1.15em; }
 .srd-body h3 { font-size: 1.05em; }
 .srd-body h4 { font-size: 1em; color: #333; }
 .srd-body p { margin: .4em 0; }
 .srd-body ul, .srd-body ol { margin: .4em 0; padding-left: 1.5em; }
 .srd-body li { margin: .15em 0; }
 .srd-body code { background: #eee; padding: 0 .25em; border-radius: 3px; font-size: 0.95em; }
 .srd-body pre { background: #eee; padding: .5em; overflow-x: auto; }
 .srd-body table { border-collapse: collapse; width: 100%; margin: .5em 0; font-size: .95em; }
 .srd-body th, .srd-body td { border: 1px solid #ddd; padding: .3em .5em; text-align: left; }
 .srd-body th { background: #f0f0f0; }
 .srd-body hr { border: 0; border-top: 1px solid #ddd; margin: .8em 0; }
 .srd-body blockquote { border-left: 3px solid #ccc; margin: .5em 0; padding: .2em .8em; color: #555; }

 /* Character form two-column layout */
 body:has(.form-page) { max-width: none; padding: 0 1em; }
 .form-page { max-width: 1600px; margin: 0 auto; }
 .form-grid { display: grid; grid-template-columns: minmax(0, 1fr) clamp(300px, 32vw, 520px); gap: 1.5em; align-items: start; }
 .form-column { min-width: 0; }
 .srd-column { position: sticky; top: 1em; max-height: calc(100vh - 2em); overflow-y: auto; }
 .srd-column .srd-body { max-height: none; }

 /* Mobile floating-action button + overlay */
 .srd-fab { display: none; position: fixed; right: 1em; bottom: 1em; width: 48px; height: 48px; border-radius: 50%; background: #06c; color: #fff; border: none; font-size: 1.2em; cursor: pointer; z-index: 100; box-shadow: 0 2px 6px rgba(0,0,0,.25); align-items: center; justify-content: center; }
 .srd-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 200; align-items: flex-end; justify-content: center; }
 .srd-sheet { background: #fff; width: 100%; max-width: 720px; max-height: 85vh; overflow-y: auto; border-radius: 10px 10px 0 0; padding: 1em; }
 .srd-close { float: right; background: none; border: none; font-size: 1.4em; cursor: pointer; line-height: 1; padding: 0 .3em; }

 @media (max-width: 900px) {
  .form-grid { grid-template-columns: 1fr; }
  .srd-column { display: none; }
  .srd-fab { display: flex; }
  .srd-overlay { display: flex; }
 }
</style>"""


def _layout(body: str) -> str:
    return f"<!doctype html>\n<html>\n<head>\n{_HEAD}\n</head>\n<body>\n{body}\n</body>\n</html>\n"


_NAV = """<nav>
 <a href="/">Home</a>
 <a href="/chat">Chat</a>
 <a href="/characters">Characters</a>
 <a href="/memory">Memory</a>
</nav>"""


def landing_page(
    party: list[dict[str, str]],
    character_count: int,
    memory: list[dict[str, Any]],
) -> str:
    roster = ", ".join(f"{_esc(p['name'])} (@{_esc(p['id'])})" for p in party) or "<em>empty</em>"
    mem_line = (
        "; ".join(f"{_esc(m['name'])}: {m['thread_rounds']} rounds / {m['episodes']} episodes" for m in memory)
        or "<em>no activity yet</em>"
    )
    body = f"""{_NAV}
<h1>pywf</h1>
<p>AI player-character agents for a tabletop D&amp;D 5e party.</p>
<div class="cards">
 <section class="card">
  <h2>Chat</h2>
  <div class="snapshot">Party: {roster}.</div>
  <div class="actions"><a class="btn" href="/chat">Open chat</a></div>
 </section>
 <section class="card">
  <h2>Characters</h2>
  <div class="snapshot">{character_count} character(s) in the database.</div>
  <div class="actions">
   <a class="btn" href="/characters/new">+ New character</a>
   <a href="/characters">View all</a>
  </div>
 </section>
 <section class="card">
  <h2>Memory</h2>
  <div class="snapshot">{mem_line}</div>
  <div class="actions"><a class="btn" href="/memory">Open memory</a></div>
 </section>
</div>"""
    return _layout(body)


def memory_page(stats: list[dict[str, Any]]) -> str:
    if not stats:
        rows = '<tr><td colspan="8"><em>No party loaded.</em></td></tr>'
    else:
        rows = "\n".join(
            f"""<tr>
 <td>{_esc(s.get('character_id', ''))}</td>
 <td>{_esc(s.get('name', ''))}</td>
 <td>{_esc(s.get('thread_rounds', 0))}</td>
 <td>{_esc(s.get('thread_messages', 0))}</td>
 <td>{_esc(s.get('rounds_until_archive', 0))}</td>
 <td>{_esc(s.get('episodes', 0))}</td>
 <td>{'yes' if s.get('has_chronicle') else 'no'}</td>
 <td>{_esc(s.get('archived_rounds', 0))}</td>
</tr>"""
            for s in stats
        )
    body = f"""{_NAV}
<h1>Memory</h1>
<p>Per-character thread + long-term memory stats. See <a href="/api/memory">/api/memory</a> for the JSON view.</p>
<table>
 <thead><tr>
  <th>id</th><th>name</th>
  <th>thread rounds</th><th>thread msgs</th><th>rounds until archive</th>
  <th>episodes</th><th>chronicle</th><th>archived rounds</th>
 </tr></thead>
 <tbody>{rows}</tbody>
</table>"""
    return _layout(body)


def chat_page() -> str:
    body = """<p class="back"><a href="/">← Back to home</a></p>
<h1>Chat <span id="roster"></span></h1>

<section id="picker">
 <h2>Choose party</h2>
 <div id="roster-choices"><em>loading…</em></div>
 <div class="row">
  <button id="start" type="button">Start session</button>
  <span id="picker-error" class="err"></span>
 </div>
</section>

<p id="change-party-wrap" hidden><a href="#" id="change-party">change party</a></p>
<div id="log"></div>
<form id="f" hidden>
 <input id="dm" placeholder="DM> type here (prefix @id to target one)" autofocus autocomplete="off">
 <button type="submit">send</button>
</form>
<style>
 #log { white-space: pre-wrap; min-height: 50vh; border: 1px solid #ddd; padding: 1em; margin: 0; }
 #log .speaker { font-weight: bold; }
 #log .err { color: #a00; }
 form { display: flex; gap: .5em; margin-top: 1em; }
 #dm { flex: 1; padding: .5em; font: inherit; }
 #roster { color: #666; font-weight: normal; }
 #picker { border: 1px solid #ddd; padding: 1em; margin: 0 0 1em 0; background: #fafafa; }
 #picker h2 { font-size: 1em; margin: 0 0 .5em 0; }
 #roster-choices { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: .3em .8em; margin-bottom: .5em; }
 #roster-choices label { display: flex; align-items: center; gap: .4em; cursor: pointer; }
 #picker-error { color: #a00; }
 #change-party-wrap a { color: #06c; }
 #log .speaker a, #roster a { color: inherit; text-decoration: underline; text-decoration-style: dotted; }
 #log .speaker a:hover, #roster a:hover { color: #06c; text-decoration-style: solid; }
</style>
<script>
const log = document.getElementById('log');
const esc = s => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function append(speaker, text, cls, href) {
  const div = document.createElement('div');
  const speakerHtml = href
    ? `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(speaker)}</a>`
    : esc(speaker);
  div.innerHTML = `<span class="speaker ${cls||''}">${speakerHtml}&gt;</span> <span class="${cls||''}">${esc(text)}</span>`;
  log.appendChild(div);
  window.scrollTo(0, document.body.scrollHeight);
}
async function updateRosterLine() {
  try {
    const r = await fetch('/party');
    const data = await r.json();
    const roster = document.getElementById('roster');
    if (!data.party.length) { roster.textContent = ''; return; }
    const parts = data.party.map(p =>
      `<a href="/characters/${encodeURIComponent(p.id)}/edit" target="_blank" rel="noopener">${esc(p.name)}</a> (@${esc(p.id)})`
    );
    roster.innerHTML = '— party: ' + parts.join(', ');
  } catch (e) {}
}
async function renderPicker() {
  const choices = document.getElementById('roster-choices');
  const err = document.getElementById('picker-error');
  err.textContent = '';
  choices.innerHTML = '<em>loading…</em>';
  try {
    const [allR, curR] = await Promise.all([fetch('/api/characters'), fetch('/party')]);
    const all = (await allR.json()).items || [];
    const current = new Set(((await curR.json()).party || []).map(p => p.id));
    if (!all.length) {
      choices.innerHTML = '<em>No characters in the database. <a href="/characters/new">Create one first</a>.</em>';
      document.getElementById('start').disabled = true;
      return;
    }
    document.getElementById('start').disabled = false;
    choices.innerHTML = '';
    for (const it of all) {
      const id = `pick-${it.id}`;
      const row = document.createElement('label');
      row.innerHTML = `<input type="checkbox" value="${esc(it.id)}" id="${esc(id)}" ${current.has(it.id) ? 'checked' : ''}> ${esc(it.name)} <span style="color:#888">(@${esc(it.id)})</span>`;
      choices.appendChild(row);
    }
  } catch (e) {
    err.textContent = 'failed to load characters: ' + e;
  }
}
function showPicker() {
  document.getElementById('picker').hidden = false;
  document.getElementById('change-party-wrap').hidden = true;
  document.getElementById('f').hidden = true;
  renderPicker();
}
function hidePicker() {
  document.getElementById('picker').hidden = true;
  document.getElementById('change-party-wrap').hidden = false;
  document.getElementById('f').hidden = false;
  document.getElementById('dm').focus();
}
document.getElementById('start').addEventListener('click', async () => {
  const err = document.getElementById('picker-error');
  err.textContent = '';
  const ids = Array.from(document.querySelectorAll('#roster-choices input[type=checkbox]:checked')).map(cb => cb.value);
  if (!ids.length) { err.textContent = 'pick at least one character'; return; }
  try {
    const r = await fetch('/api/party', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({character_ids: ids}),
    });
    if (!r.ok) { err.textContent = 'HTTP ' + r.status + ': ' + (await r.text()); return; }
    await updateRosterLine();
    hidePicker();
  } catch (e) { err.textContent = String(e); }
});
document.getElementById('change-party').addEventListener('click', (e) => { e.preventDefault(); showPicker(); });
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
    for (const t of data.turns) append(t.name, t.text, null, '/characters/' + encodeURIComponent(t.character_id) + '/edit');
  } catch (err) { append('error', String(err), 'err'); }
});
updateRosterLine();
renderPicker();
</script>
"""
    return _layout(body)


def characters_list_page(items: list[dict[str, str]]) -> str:
    rows = "\n".join(
        f"""<tr id="row-{i['id']}">
 <td>{_esc(i['id'])}</td>
 <td>{_esc(i['name'])}</td>
 <td class="actions">
  <a href="/characters/{_esc(i['id'])}/edit">Edit</a>
  <button class="btn btn-danger"
          hx-delete="/api/characters/{_esc(i['id'])}"
          hx-target="#row-{_esc(i['id'])}"
          hx-swap="delete"
          hx-confirm="Delete {_esc(i['name'])}?">Delete</button>
 </td>
</tr>"""
        for i in items
    )
    if not items:
        rows = '<tr><td colspan="3"><em>No characters yet.</em></td></tr>'
    body = f"""{_NAV}
<h1>Characters</h1>
<p><a class="btn" href="/characters/new">+ New character</a></p>
<table>
 <thead><tr><th>id</th><th>name</th><th></th></tr></thead>
 <tbody>{rows}</tbody>
</table>"""
    return _layout(body)


_EMPTY_FORM = {
    "id": "",
    "name": "",
    "species": "",
    "background": "",
    "alignment": "",
    "origin_feat": "",
    "armor_class": None,
    "current_hp": None,
    "max_hp": None,
    "temporary_hp": None,
    "speed_ft": None,
    "initiative_bonus": None,
    "proficiency_bonus": None,
    "notes": "",
    "classes": [],
    "abilities": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
    "feats": [],
    "saving_throw_proficiencies": [],
    "skill_proficiencies": [],
    "languages": [],
    "senses": {},
    "equipment": [],
    "features": [],
    "spells": [],
    "spell_slots": {},
    "resources": {},
    "conditions": [],
}


def _datalist(id_: str, options: list[str]) -> str:
    opts = "".join(f'<option value="{_esc(name)}">' for name in options)
    return f'<datalist id="{_esc(id_)}">{opts}</datalist>'


def _srd_datalists_html() -> str:
    spells_json = json.dumps(SPELLS).replace("</", "<\\/")
    parts = [
        f"<script>window.SRD_SPELLS = {spells_json};</script>",
        _datalist("srd-classes", CLASSES),
        _datalist("srd-species", SPECIES),
        _datalist("srd-feats", FEATS),
    ]
    for class_name, subs in SUBCLASSES.items():
        parts.append(_datalist(f"srd-subclass-{class_name}", subs))
    return "\n".join(parts)


def character_form_page(mode: str, initial: dict[str, Any] | None = None) -> str:
    assert mode in ("new", "edit")
    data = {**_EMPTY_FORM, **(initial or {})}
    # Strip timestamp fields produced by the DB readback — they're not user-editable.
    for k in ("created_at", "updated_at"):
        data.pop(k, None)
    # Pydantic Character rejects extras; keep only known keys.
    data = {k: data.get(k, _EMPTY_FORM.get(k)) for k in _EMPTY_FORM}
    data_attr = html.escape(json.dumps(data), quote=True)
    mode_attr = html.escape(json.dumps(mode), quote=True)
    srd_block = _srd_datalists_html()
    body = f"""{_NAV}
{srd_block}
<div x-data="characterForm({data_attr}, {mode_attr})" x-cloak>
<div class="form-page">
<h1>{'Edit character' if mode == 'edit' else 'New character'}</h1>
<div class="form-grid">
<div class="form-column">
 <template x-if="error">
  <div class="error" x-text="error"></div>
 </template>

 <fieldset><legend>Identity</legend>
  <div class="grid">
   <div><label>id (slug, lowercase)</label><input type="text" x-model="form.id" :readonly="mode === 'edit'"></div>
   <div><label>name</label><input type="text" x-model="form.name"></div>
   <div><label>species</label><input type="text" x-model="form.species" list="srd-species" @change="showSrd('species', form.species)"></div>
   <div><label>background</label><input type="text" x-model="form.background"></div>
   <div><label>alignment</label><input type="text" x-model="form.alignment"></div>
   <div><label>origin feat</label><input type="text" x-model="form.origin_feat"></div>
  </div>
 </fieldset>

 <fieldset><legend>Abilities</legend>
  <div class="grid">
   <template x-for="k in ['str','dex','con','int','wis','cha']" :key="k">
    <div><label x-text="k.toUpperCase()"></label><input type="number" x-model.number="form.abilities[k]"></div>
   </template>
  </div>
 </fieldset>

 <fieldset><legend>Combat</legend>
  <div class="grid">
   <div><label>armor class</label><input type="number" x-model.number="form.armor_class"></div>
   <div><label>current HP</label><input type="number" x-model.number="form.current_hp"></div>
   <div><label>max HP</label><input type="number" x-model.number="form.max_hp"></div>
   <div><label>temporary HP</label><input type="number" x-model.number="form.temporary_hp"></div>
   <div><label>speed (ft)</label><input type="number" x-model.number="form.speed_ft"></div>
   <div><label>initiative bonus</label><input type="number" x-model.number="form.initiative_bonus"></div>
   <div><label>proficiency bonus</label><input type="number" x-model.number="form.proficiency_bonus"></div>
  </div>
 </fieldset>

 <fieldset><legend>Classes</legend>
  <template x-for="(c, i) in form.classes" :key="i">
   <div class="row">
    <input placeholder="class (e.g. Fighter)" x-model="c.class" list="srd-classes" @change="showSrd('class', c.class)">
    <input type="number" placeholder="level" x-model.number="c.level" style="max-width: 6em;">
    <input placeholder="subclass (optional)" x-model="c.subclass" :list="'srd-subclass-' + (c.class || '')" @change="showSrd('subclass', c.subclass)">
    <button type="button" class="btn-danger" @click="form.classes.splice(i, 1)">x</button>
   </div>
  </template>
  <button type="button" @click="form.classes.push({{class: '', level: 1, subclass: null}})">+ Add class</button>
 </fieldset>

 <fieldset><legend>Feats</legend>
  <template x-for="(f, i) in form.feats" :key="i">
   <div class="row">
    <input placeholder="name" x-model="f.name" list="srd-feats" @change="showSrd('feat', f.name)">
    <input placeholder="source (e.g. origin)" x-model="f.source">
    <button type="button" class="btn-danger" @click="form.feats.splice(i, 1)">x</button>
   </div>
  </template>
  <button type="button" @click="form.feats.push({{name: '', source: ''}})">+ Add feat</button>
 </fieldset>

 <fieldset><legend>Equipment</legend>
  <template x-for="(e, i) in form.equipment" :key="i">
   <div class="row">
    <input placeholder="name" x-model="e.name">
    <input type="number" placeholder="qty" x-model.number="e.qty" style="max-width: 6em;">
    <button type="button" class="btn-danger" @click="form.equipment.splice(i, 1)">x</button>
   </div>
  </template>
  <button type="button" @click="form.equipment.push({{name: '', qty: 1}})">+ Add item</button>
 </fieldset>

 <fieldset><legend>Features</legend>
  <template x-for="(f, i) in form.features" :key="i">
   <div class="row">
    <input placeholder="name" x-model="f.name">
    <input placeholder="class" x-model="f.class">
    <input placeholder="species" x-model="f.species">
    <input type="number" placeholder="uses remaining" x-model.number="f.uses_remaining" style="max-width: 6em;">
    <input type="number" placeholder="uses max" x-model.number="f.uses_max" style="max-width: 6em;">
    <input placeholder="recharge" x-model="f.recharge">
    <button type="button" class="btn-danger" @click="form.features.splice(i, 1)">x</button>
   </div>
  </template>
  <button type="button" @click="form.features.push({{name: '', class: '', species: '', uses_remaining: null, uses_max: null, recharge: ''}})">+ Add feature</button>
 </fieldset>

 <fieldset><legend>Spells</legend>
  <template x-for="(s, i) in form.spells" :key="i">
   <div class="row">
    <div class="spell-picker" x-data="spellPicker(s, (name) => showSrd('spell', name))" @click.outside="open=false">
     <input placeholder="name" x-model="s.name" @focus="open=true" @change="showSrd('spell', s.name)">
     <template x-if="open">
      <div class="suggest">
       <div class="row">
        <input placeholder="search" x-model="search">
        <select x-model.number="levelFilter">
         <option value="-1">any level</option>
         <option value="0">cantrip</option>
         <option value="1">1</option>
         <option value="2">2</option>
         <option value="3">3</option>
         <option value="4">4</option>
         <option value="5">5</option>
         <option value="6">6</option>
         <option value="7">7</option>
         <option value="8">8</option>
         <option value="9">9</option>
        </select>
       </div>
       <ul>
        <template x-for="sp in filtered()" :key="sp.name">
         <li @click="pick(sp)" x-text="sp.name + ' — ' + (sp.level === 0 ? 'cantrip' : 'L' + sp.level) + ' ' + sp.school"></li>
        </template>
        <li x-show="filtered().length === 0" class="empty">no matches</li>
       </ul>
      </div>
     </template>
    </div>
    <input type="number" placeholder="level" x-model.number="s.level" style="max-width: 6em;">
    <label class="inline"><input type="checkbox" x-model="s.prepared"> prepared</label>
    <input placeholder="always_prepared source" x-model="s.always_prepared">
    <button type="button" class="btn-danger" @click="form.spells.splice(i, 1)">x</button>
   </div>
  </template>
  <button type="button" @click="form.spells.push({{name: '', level: 0, prepared: false, always_prepared: ''}})">+ Add spell</button>
 </fieldset>

 <fieldset><legend>Proficiencies, languages, conditions</legend>
  <template x-for="field in ['saving_throw_proficiencies','skill_proficiencies','languages','conditions']" :key="field">
   <div style="margin: .5em 0;">
    <label x-text="field.replace(/_/g, ' ')"></label>
    <div>
     <template x-for="(tag, i) in form[field]" :key="i">
      <span class="chip" x-text="tag">
       <button type="button" @click="form[field].splice(i, 1)">x</button>
      </span>
     </template>
    </div>
    <div class="row">
     <input :placeholder="'add to ' + field" @keydown.enter.prevent="if($event.target.value.trim()){{form[field].push($event.target.value.trim()); $event.target.value='';}}">
    </div>
   </div>
  </template>
 </fieldset>

 <fieldset><legend>Senses, spell slots, resources (key/value)</legend>
  <template x-for="dictField in ['senses','spell_slots','resources']" :key="dictField">
   <div style="margin: .5em 0;" x-data="{{ newKey: '', newVal: '' }}">
    <label x-text="dictField.replace(/_/g, ' ')"></label>
    <template x-for="(k, i) in Object.keys(form[dictField])" :key="k">
     <div class="row">
      <input :value="k" @change="renameKey(dictField, k, $event.target.value)" style="max-width: 10em;">
      <input :value="JSON.stringify(form[dictField][k])" @change="setJsonValue(dictField, k, $event.target.value)" placeholder="JSON value (e.g. 3 or [1,2] or &quot;text&quot;)">
      <button type="button" class="btn-danger" @click="delete form[dictField][k]; form[dictField] = {{...form[dictField]}}">x</button>
     </div>
    </template>
    <div class="row">
     <input :placeholder="'new key for ' + dictField" x-model="newKey" style="max-width: 10em;">
     <input placeholder="JSON value" x-model="newVal">
     <button type="button" @click="addKey(dictField, newKey, newVal); newKey=''; newVal=''">+ Add</button>
    </div>
   </div>
  </template>
 </fieldset>

 <fieldset><legend>Notes</legend>
  <textarea x-model="form.notes"></textarea>
 </fieldset>

 <div class="row">
  <button type="button" @click="submit()" x-text="submitting ? 'Saving…' : (mode === 'edit' ? 'Save changes' : 'Create character')"></button>
  <a href="/characters">Cancel</a>
 </div>
</div>
<aside class="srd-column">
 <div class="srd-panel">
  <div class="srd-head">
   <strong x-text="srd.name || 'change a class, subclass, species, feat, or spell to see its rules here'"></strong>
   <span class="loading" x-show="srd.loading"> · loading…</span>
   <span class="err" x-show="srd.error" x-text="srd.error"></span>
  </div>
  <div class="srd-body" x-html="srd.html" x-show="srd.html"></div>
 </div>
</aside>
</div>
</div>
<button class="srd-fab" @click="srdOpen = true" x-show="srd.name" title="Show rules">ⓘ</button>
<div class="srd-overlay" x-show="srdOpen" @click.self="srdOpen = false">
 <div class="srd-sheet">
  <div class="srd-head">
   <strong x-text="srd.name"></strong>
   <button class="srd-close" @click="srdOpen = false" aria-label="Close">×</button>
  </div>
  <div class="srd-body" x-html="srd.html" x-show="srd.html"></div>
 </div>
</div>
</div>

<script>
function characterForm(initial, mode) {{
  return {{
    mode: mode,
    form: initial,
    error: null,
    submitting: false,
    srd: {{ category: '', name: '', body: '', html: '', loading: false, error: null }},
    srdOpen: false,
    _srdCache: {{}},
    _renderMd(body) {{
      return (body && window.marked) ? marked.parse(body) : (body || '');
    }},
    async showSrd(category, name) {{
      name = (name || '').trim();
      if (!name) {{
        this.srd.category = ''; this.srd.name = ''; this.srd.body = ''; this.srd.html = ''; this.srd.error = null;
        return;
      }}
      const key = category + ':' + name;
      this.srd.category = category; this.srd.name = name; this.srd.error = null;
      if (this._srdCache[key] !== undefined) {{
        this.srd.html = this._srdCache[key];
        this.srd.body = this._srdCache[key] ? name : '';
        if (!this._srdCache[key]) this.srd.error = 'no SRD entry';
        return;
      }}
      this.srd.loading = true;
      try {{
        const r = await fetch('/api/srd/' + category + '/' + encodeURIComponent(name));
        if (r.status === 404) {{
          this.srd.body = ''; this.srd.html = ''; this.srd.error = 'no SRD entry'; this._srdCache[key] = '';
          return;
        }}
        if (!r.ok) {{
          this.srd.body = ''; this.srd.html = ''; this.srd.error = 'HTTP ' + r.status;
          return;
        }}
        const data = await r.json();
        this.srd.body = data.body;
        this.srd.html = this._renderMd(data.body);
        this._srdCache[key] = this.srd.html;
      }} catch (e) {{
        this.srd.error = String(e);
      }} finally {{
        this.srd.loading = false;
      }}
    }},
    renameKey(field, oldKey, newKey) {{
      if (!newKey || newKey === oldKey) return;
      const v = this.form[field][oldKey];
      delete this.form[field][oldKey];
      this.form[field][newKey] = v;
      this.form[field] = {{...this.form[field]}};
    }},
    setJsonValue(field, key, raw) {{
      try {{ this.form[field][key] = JSON.parse(raw); }}
      catch (e) {{ this.form[field][key] = raw; }}
      this.form[field] = {{...this.form[field]}};
    }},
    addKey(field, rawKey, rawVal) {{
      const k = (rawKey || '').trim();
      if (!k) return;
      let v;
      try {{ v = JSON.parse(rawVal); }}
      catch (e) {{ v = rawVal; }}
      this.form[field][k] = v;
      this.form[field] = {{...this.form[field]}};
    }},
    async submit() {{
      this.error = null;
      this.submitting = true;
      try {{
        const url = this.mode === 'edit'
          ? '/api/characters/' + encodeURIComponent(this.form.id)
          : '/api/characters';
        const method = this.mode === 'edit' ? 'PUT' : 'POST';
        const r = await fetch(url, {{
          method,
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(this.form),
        }});
        if (r.ok) {{ window.location.href = '/characters'; return; }}
        const body = await r.text();
        this.error = 'HTTP ' + r.status + ': ' + body;
      }} catch (e) {{
        this.error = String(e);
      }} finally {{
        this.submitting = false;
      }}
    }},
  }};
}}
window.spellPicker = function(row, onPick) {{
  return {{
    row,
    onPick: onPick || function() {{}},
    open: false,
    search: '',
    levelFilter: -1,
    filtered() {{
      const q = (this.search || this.row.name || '').toLowerCase();
      return (window.SRD_SPELLS || []).filter(sp =>
        (this.levelFilter < 0 || sp.level === this.levelFilter) &&
        (!q || sp.name.toLowerCase().includes(q))
      ).slice(0, 50);
    }},
    pick(sp) {{
      this.row.name = sp.name;
      this.row.level = sp.level;
      this.open = false;
      this.onPick(sp.name);
    }},
  }};
}};
</script>
"""
    return _layout(body)


def _esc(s: Any) -> str:
    text = "" if s is None else str(s)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
