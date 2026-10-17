"""Blind listening test for voices: one page, unlabelled samples in a seeded random order, ratings, then a reveal.

Standard library only. The samples are audio files you already made (``voice.py speak``, an engine's own script, a cloud download); nothing here
runs an engine or sends text anywhere. The page embeds the audio, so it works from a file with no server. The key (which sample is which voice)
sits in the page's data and is shown only after the ratings are exported, which hides it from a casual look, not from someone reading the source.

A hidden anchor (a voice known to be poor) and a hidden repeat (the same file twice) are added on request so a rating can be checked against them:
a rater who scores the anchor high, or the two copies far apart, is not discriminating.

Command: build
"""
from __future__ import annotations
import argparse
import base64
import html
import json
import random
import sys
from pathlib import Path

SCHEMA = 1
MAX_BYTES = 16 * 1024 * 1024
AUDIO_TYPES = {'.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.flac': 'audio/flac'}


class BlindTestError(ValueError):
    pass


def load_samples(entries: list[dict]) -> list[dict]:
    """Validate ``[{id, label, file, role?}]``; ``role`` is ``candidate`` (default), ``anchor`` or ``repeat``."""
    if len(entries) < 2:
        raise BlindTestError('a blind test needs at least two samples')
    seen, samples = set(), []
    for entry in entries:
        ident, label, path = str(entry.get('id', '')), str(entry.get('label', '')), Path(str(entry.get('file', '')))
        if not ident or not label:
            raise BlindTestError(f'every sample needs an id and a label: {entry}')
        if ident in seen:
            raise BlindTestError(f'duplicate sample id: {ident}')
        seen.add(ident)
        if path.suffix.lower() not in AUDIO_TYPES:
            raise BlindTestError(f'{path.name}: unsupported audio type (use {", ".join(AUDIO_TYPES)})')
        if not path.is_file():
            raise BlindTestError(f'{path}: file not found')
        role = entry.get('role', 'candidate')
        if role not in ('candidate', 'anchor', 'repeat'):
            raise BlindTestError(f'{ident}: role must be candidate, anchor or repeat')
        samples.append({'id': ident, 'label': label, 'file': path, 'role': role, 'note': str(entry.get('note', ''))})
    return samples


def shuffled(samples: list[dict], seed: int) -> list[dict]:
    order = list(samples)
    random.Random(seed).shuffle(order)
    return order


def build_page(samples: list[dict], title: str, paragraph: str, seed: int = 1) -> tuple[str, dict]:
    """Return the page and its key. Embedded audio over 16 MB in all is refused."""
    order = shuffled(samples, seed)
    total = sum(s['file'].stat().st_size for s in order)
    if total > MAX_BYTES:
        raise BlindTestError(f'the audio is {total / 1048576:.1f} MB; the limit for one page is {MAX_BYTES // 1048576} MB (use fewer or shorter samples)')
    cards, key = [], []
    for index, sample in enumerate(order, start=1):
        data = base64.b64encode(sample['file'].read_bytes()).decode('ascii')
        mime = AUDIO_TYPES[sample['file'].suffix.lower()]
        key.append({'sample': index, 'id': sample['id'], 'label': sample['label'], 'role': sample['role'], 'file': sample['file'].name, 'note': sample['note']})
        cards.append(
            f'<section class="card" data-sample="{index}"><h2>Sample {index}</h2>'
            f'<audio controls preload="none" src="data:{mime};base64,{data}"></audio>'
            f'<fieldset><legend>How natural and pleasant is this as a voice for a 20 minute lecture?</legend>'
            + ''.join(f'<label><input type="radio" name="r{index}" value="{v}"> {v}</label>' for v in range(1, 6))
            + '</fieldset>'
            f'<fieldset><legend>Would you keep listening?</legend>'
            + ''.join(f'<label><input type="radio" name="k{index}" value="{v}"> {v}</label>' for v in ('yes', 'maybe', 'no'))
            + '</fieldset>'
            f'<label class="note">Notes (pace, pauses, stress, technical words, tiredness)<textarea name="n{index}" rows="2"></textarea></label></section>')
    page = PAGE.replace('{{TITLE}}', html.escape(title)).replace('{{PARAGRAPH}}', html.escape(paragraph)).replace('{{CARDS}}', '\n'.join(cards))
    page = page.replace('{{KEY}}', json.dumps({'schema': SCHEMA, 'seed': seed, 'key': key}).replace('</', '<\\/'))
    return page, {'schema': SCHEMA, 'seed': seed, 'key': key}


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--bg:#f6f4ef;--fg:#1d1d1b;--card:#fff;--line:#c9c5b8;--accent:#1f5f8b}
@media (prefers-color-scheme:dark){:root{--bg:#171a1c;--fg:#e8e6df;--card:#20252a;--line:#3a4249;--accent:#7cb7e0}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:46rem;margin:0 auto;padding:1rem 16px 4rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:1rem;margin:1rem 0}
h1{font-size:1.4rem}h2{font-size:1.1rem;margin:.1rem 0 .6rem}audio{width:100%}
fieldset{border:0;padding:0;margin:.7rem 0 0}legend{font-size:.9rem;opacity:.85}
fieldset label{margin-right:1rem;display:inline-block;padding:.25rem 0}
.note{display:block;margin-top:.7rem;font-size:.9rem}textarea{width:100%;box-sizing:border-box;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:.4rem}
button{background:var(--accent);color:var(--bg);border:0;border-radius:8px;padding:.6rem 1rem;font:inherit;cursor:pointer;margin-right:.5rem}
blockquote{border-left:3px solid var(--line);margin:0;padding:0 1rem;opacity:.9}
table{border-collapse:collapse;width:100%}td,th{border:1px solid var(--line);padding:.35rem .5rem;text-align:left;font-size:.9rem}
#result{display:none}
</style></head>
<body><main>
<h1>{{TITLE}}</h1>
<p>Every sample says the same paragraph. Listen to all of them in any order, rate each, then press <b>Reveal</b>. Use headphones or speakers at the volume you would really use. Rate how it would feel over twenty minutes, not how impressive the first ten seconds are.</p>
<blockquote>{{PARAGRAPH}}</blockquote>
{{CARDS}}
<p><button id="reveal" type="button">Reveal and export</button><span id="status" role="status"></span></p>
<section id="result" class="card"><h2>Result</h2><div id="table"></div>
<p><button id="download" type="button">Download results (JSON)</button><button id="copy" type="button">Copy results</button></p><pre id="json"></pre></section>
</main>
<script type="application/json" id="key">{{KEY}}</script>
<script>
(function(){
var KEY=JSON.parse(document.getElementById('key').textContent);
var STORE='voice-blind-'+KEY.seed+'-'+KEY.key.length;
function load(){try{return JSON.parse(localStorage.getItem(STORE)||'{}')}catch(e){return {}}}
function save(o){try{localStorage.setItem(STORE,JSON.stringify(o))}catch(e){}}
var saved=load();
function read(){
  var out={};
  KEY.key.forEach(function(k){var n=k.sample;
    var r=document.querySelector('input[name=r'+n+']:checked'),c=document.querySelector('input[name=k'+n+']:checked');
    out[n]={rating:r?Number(r.value):null,keep:c?c.value:null,note:document.querySelector('textarea[name=n'+n+']').value};});
  return out;
}
Object.keys(saved).forEach(function(n){var s=saved[n];if(!s)return;
  if(s.rating){var r=document.querySelector('input[name=r'+n+'][value="'+s.rating+'"]');if(r)r.checked=true;}
  if(s.keep){var c=document.querySelector('input[name=k'+n+'][value="'+s.keep+'"]');if(c)c.checked=true;}
  var t=document.querySelector('textarea[name=n'+n+']');if(t&&s.note)t.value=s.note;});
document.addEventListener('input',function(){save(read())});
document.addEventListener('play',function(e){document.querySelectorAll('audio').forEach(function(a){if(a!==e.target)a.pause()})},true);
var report;
function esc(s){var d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML}
document.getElementById('reveal').addEventListener('click',function(){
  var got=read(),missing=KEY.key.filter(function(k){return !got[k.sample].rating});
  if(missing.length){document.getElementById('status').textContent=' Rate every sample first ('+missing.length+' left).';return}
  document.getElementById('status').textContent='';
  var rows=KEY.key.map(function(k){return {sample:k.sample,id:k.id,label:k.label,role:k.role,file:k.file,rating:got[k.sample].rating,keep:got[k.sample].keep,note:got[k.sample].note}});
  rows.sort(function(a,b){return b.rating-a.rating||a.sample-b.sample});
  var repeats={};
  rows.filter(function(r){return r.role==='repeat'}).forEach(function(r){var twin=rows.filter(function(x){return x.role==='candidate'&&x.id===r.id.replace(/-repeat$/,'')})[0];if(twin)repeats[r.id]={repeat:r.rating,original:twin.rating,difference:Math.abs(r.rating-twin.rating)}});
  report={schema:KEY.schema,seed:KEY.seed,rows:rows,anchor_check:rows.filter(function(r){return r.role==='anchor'}).map(function(a){return {id:a.id,rating:a.rating}}),repeat_check:repeats};
  var h='<table><tr><th>Rating</th><th>Sample</th><th>Voice</th><th>Role</th><th>Keep listening</th><th>Notes</th></tr>';
  rows.forEach(function(r){h+='<tr><td>'+r.rating+'</td><td>'+r.sample+'</td><td>'+esc(r.label)+'</td><td>'+r.role+'</td><td>'+esc(r.keep)+'</td><td>'+esc(r.note)+'</td></tr>'});
  document.getElementById('table').innerHTML=h+'</table>';
  document.getElementById('json').textContent=JSON.stringify(report,null,2);
  document.getElementById('result').style.display='block';document.getElementById('result').scrollIntoView();
});
document.getElementById('download').addEventListener('click',function(){
  var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));a.download='voice-blind-results.json';a.click();});
document.getElementById('copy').addEventListener('click',function(){try{navigator.clipboard.writeText(JSON.stringify(report,null,2))}catch(e){}});
})();
</script></body></html>
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build', help='build the blind test page from a manifest')
    b.add_argument('manifest', help='JSON: {"title": ..., "paragraph": ..., "samples": [{"id","label","file","role"?}]}; files are relative to the manifest')
    b.add_argument('out', help='the HTML page to write (an existing file is not overwritten)')
    b.add_argument('--seed', type=int, default=1)
    args = parser.parse_args(argv)
    manifest_path = Path(args.manifest)
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        entries = [dict(e, file=str((manifest_path.parent / e['file']).resolve())) for e in manifest['samples']]
        samples = load_samples(entries)
        out = Path(args.out)
        if out.exists():
            raise BlindTestError(f'{out} already exists; choose a new name')
        page, key = build_page(samples, manifest.get('title', 'Voice listening test'), manifest.get('paragraph', ''), args.seed)
    except (BlindTestError, OSError, KeyError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    out.write_text(page, encoding='utf-8')
    key_path = out.with_suffix('.key.json')
    key_path.write_text(json.dumps(key, indent=2), encoding='utf-8')
    print(json.dumps({'page': str(out), 'key': str(key_path), 'samples': len(samples), 'bytes': out.stat().st_size}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
