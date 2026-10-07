"""HTML page templates for the FastAPI frontend.

Rendered as Python strings; no templating engine. Alpine.js + HTMX via CDN.
"""
import html
import json
from typing import Any


_HEAD = """<meta charset="utf-8">
<title>pywf</title>
<script defer src="https://unpkg.com/alpinejs@3.14.1/dist/cdn.min.js"></script>
<script src="https://unpkg.com/htmx.org@2.0.3"></script>
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
</style>"""


def _layout(body: str) -> str:
    return f"<!doctype html>\n<html>\n<head>\n{_HEAD}\n</head>\n<body>\n{body}\n</body>\n</html>\n"


_NAV = """<nav>
 <a href="/">Chat</a>
 <a href="/characters">Characters</a>
</nav>"""


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
    body = f"""{_NAV}
<h1>{'Edit character' if mode == 'edit' else 'New character'}</h1>
<div x-data="characterForm({data_attr}, {mode_attr})" x-cloak>
 <template x-if="error">
  <div class="error" x-text="error"></div>
 </template>

 <fieldset><legend>Identity</legend>
  <div class="grid">
   <div><label>id (slug, lowercase)</label><input type="text" x-model="form.id" :readonly="mode === 'edit'"></div>
   <div><label>name</label><input type="text" x-model="form.name"></div>
   <div><label>species</label><input type="text" x-model="form.species"></div>
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
    <input placeholder="class (e.g. Fighter)" x-model="c.class">
    <input type="number" placeholder="level" x-model.number="c.level" style="max-width: 6em;">
    <input placeholder="subclass (optional)" x-model="c.subclass">
    <button type="button" class="btn-danger" @click="form.classes.splice(i, 1)">x</button>
   </div>
  </template>
  <button type="button" @click="form.classes.push({{class: '', level: 1, subclass: null}})">+ Add class</button>
 </fieldset>

 <fieldset><legend>Feats</legend>
  <template x-for="(f, i) in form.feats" :key="i">
   <div class="row">
    <input placeholder="name" x-model="f.name">
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
    <input placeholder="name" x-model="s.name">
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

<script>
function characterForm(initial, mode) {{
  return {{
    mode: mode,
    form: initial,
    error: null,
    submitting: false,
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
