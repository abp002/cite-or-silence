"""Builds the page for the human review: a local HTML file, never published (it carries SEP text).

Shows each picked item blind (no judge label): the sentence, the quote it cited if any, the gold
section in full and the retrieved passages folded. The verdicts are saved as a JSON download.

    uv run python scripts/review_page.py 3 17 42 ...   # item numbers from data/review/key.jsonl
"""

import html
import json
import sys
from pathlib import Path

from cite_or_silence import bench, search
from cite_or_silence.answer import passages_of

OUT = Path("data/review")
picked = [int(a) for a in sys.argv[1:]]
key = {it["item"]: it for it in map(json.loads, (OUT / "key.jsonl").read_text().splitlines())}
questions = {q["id"]: q for q in map(json.loads, Path("eval/questions.jsonl").read_text().splitlines())}
con = search.connect(Path("data/sep.duckdb"), read_only=True)


def block(passages, cls=""):
    return "".join(f'<div class="p {cls}"><b>{html.escape(p.entry)} — {html.escape(p.heading)}</b><p>{html.escape(p.text)}</p></div>' for p in passages)


cards = []
for n, i in enumerate(picked, 1):
    it = key[i]
    q = questions[it["qid"]]
    r = json.loads(Path("data/bench", it["provider"], f"{it['qid']}.json").read_text())
    quote = ""
    if it["arm"] != "bare":
        s = next((s for s in r["sentences"] if s["text"] == it["sentence"]), None)
        if s:
            quote = f'<div class="quote"><span class="lbl">Cita que dio el modelo: es su prueba, no se juzga</span><br>«{html.escape(s["quote"])}»</div>'
    gold = bench.gold_text(con, q["gold"])
    retrieved = passages_of(con, r["passages"])
    cards.append(f"""
<section data-item="{i}">
  <div class="n">{n} / {len(picked)}</div>
  <div class="q">Pregunta: {html.escape(q["question"])}</div>
  <div class="lbl">Frase a juzgar</div>
  <div class="s">{html.escape(it["sentence"])}</div>
  {quote}
  <div class="opts">
    <label><input type="radio" name="i{i}" value="supported"> Respaldada</label>
    <label><input type="radio" name="i{i}" value="unbacked"> Sin respaldo</label>
    <label><input type="radio" name="i{i}" value="contradicted"> Contradicha</label>
  </div>
  <details open><summary>Sección gold</summary>{block(gold)}</details>
  <details><summary>Pasajes recuperados ({len(retrieved)})</summary>{block(retrieved)}</details>
</section>""")

page = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisión del juez</title><style>
:root{{--bg:#fbfaf7;--fg:#1d1d1b;--mute:#6b6a65;--card:#fff;--line:#e4e1d8;--acc:#2b5d8a;--hl:#fff4cc}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161614;--fg:#e8e6e0;--mute:#9a978f;--card:#1f1f1c;--line:#34332e;--acc:#7fb0dd;--hl:#3a3420}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.55 Georgia,serif;max-width:820px;margin:0 auto;padding:24px 16px 120px}}
h1{{font-size:1.4rem}} .intro{{color:var(--mute)}}
section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin:22px 0}}
.n{{color:var(--mute);font-size:.85rem}} .q{{color:var(--mute);margin:.3em 0}}
.s{{font-size:1.15rem;font-weight:600;margin:.2em 0 .6em}}
.lbl{{color:var(--mute);font:600 .75rem system-ui,sans-serif;text-transform:uppercase;letter-spacing:.04em}}
.quote{{background:var(--hl);padding:8px 10px;border-radius:6px;font-size:.95rem}}
.opts{{display:flex;gap:18px;flex-wrap:wrap;margin:14px 0;font-family:system-ui,sans-serif}}
details{{margin-top:8px}} summary{{cursor:pointer;color:var(--acc);font-family:system-ui,sans-serif}}
.p{{border-top:1px solid var(--line);padding-top:8px;margin-top:8px;font-size:.92rem}} .p p{{white-space:pre-wrap;margin:.3em 0}}
footer{{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:12px 16px;display:flex;gap:16px;align-items:center;justify-content:center;font-family:system-ui,sans-serif}}
button{{background:var(--acc);color:var(--bg);border:0;border-radius:6px;padding:8px 16px;font-size:1rem;cursor:pointer}}
</style></head><body>
<h1>Revisión del juez</h1>
<p class="intro">Se juzga solo la <b>frase</b>: no si responde bien a la pregunta, ni si la cita es buena. Si la frase dice más que el texto (quita un «según X», un «algunos», un grupo concreto), no está respaldada. Decide contra el texto de la SEP de abajo (no contra lo que sepas): <b>Respaldada</b> si el texto lo dice o lo implica directamente, todo, sin añadir nombres, causas ni matices; <b>Sin respaldo</b> si el texto no lo zanja; <b>Contradicha</b> si dice lo contrario. Ctrl+F ayuda a buscar en los pasajes.</p>
{"".join(cards)}
<footer><span id="count">0 / {len(picked)}</span><button id="save">Guardar resultados</button></footer>
<script>
const KEY="revision-juez";
const radios=[...document.querySelectorAll('input[type=radio]')];
function state(){{const o={{}};radios.filter(r=>r.checked).forEach(r=>o[r.name.slice(1)]=r.value);return o}}
function update(){{document.getElementById('count').textContent=Object.keys(state()).length+' / {len(picked)}';try{{localStorage.setItem(KEY,JSON.stringify(state()))}}catch(e){{}}}}
try{{const s=JSON.parse(localStorage.getItem(KEY)||'{{}}');radios.forEach(r=>{{if(s[r.name.slice(1)]===r.value)r.checked=true}})}}catch(e){{}}
radios.forEach(r=>r.addEventListener('change',update));update();
document.getElementById('save').onclick=()=>{{const s=state();const lines=Object.entries(s).map(([i,l])=>JSON.stringify({{item:+i,label:l}})).join('\\n')+'\\n';
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([lines],{{type:'application/x-ndjson'}}));a.download='humano.jsonl';a.click()}};
</script></body></html>"""
(OUT / "revision.html").write_text(page)
print(f"{len(picked)} items -> {OUT / 'revision.html'}")
