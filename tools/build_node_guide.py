"""Generate docs/node-guide.html -- the visual, searchable node
compatibility guide -- from the class dumps of both apps. Shares the
classification logic (aliases, exclusions, partial notes) with
compat_report.py. Run after Redshift updates:

    python tools/compat_report.py && python tools/build_node_guide.py
"""

import html
import os
import time

import compat_report as cr

OUT_FILE = os.path.join(cr.REPO_DIR, "docs", "node-guide.html")

CATEGORIES = [
    ("Materials", lambda c: "material" in c or c in {
        "carpaint", "skin", "incandescent", "architectural", "matteshadow",
        "sprite", "hair", "hair2", "standardvolume", "volume",
        "subsurfacescatter"}),
    ("Ramps & Gradients", lambda c: c in {"rsramp", "rsscalarramp"}),
    ("AOV", lambda c: c.startswith("store") and c.endswith("toaov")),
    ("Math", lambda c: c.startswith("rsmath") or c in {
        "rsvectormaker", "rsvectortoscalars", "rsscalarconstant",
        "unitconversion"}),
    ("Color", lambda c: c.startswith("rscolor") or c in {
        "rshsv2color", "iortometaltints", "tonemappattern"}),
    ("Attributes & User Data", lambda c: c.startswith("rsuserdata") or c in {
        "particleattributelookup", "vertexattributelookup", "state",
        "surfacetangent", "volumecolorattribute", "volumescalarattribute",
        "rshairposition", "hairrandomcolor", "c4dhairattribute",
        "golaemhsl"}),
    ("Lights & Environment", lambda c: c.startswith("light") or c in {
        "environment", "envswitch", "physicalsky", "physicalsun",
        "physicalnightsky"}),
    ("Bump & Displacement", lambda c: c in {
        "bumpmap", "bumpblender", "normalmap", "displacement",
        "displacementblender", "roundcorners"}),
    ("UV & Projection", lambda c: c in {
        "triplanar", "uvprojection", "uvcontextprojection", "cameramap"}),
    ("Switches & Logic", lambda c: "switch" in c or c in {
        "shadermerge", "reference"}),
    ("Textures & Patterns", lambda c: c in {
        "texturesampler", "maxonnoise", "rsnoise", "brick", "tiles",
        "pavement", "flakes", "wireframe", "curvature", "ambientocclusion",
        "fresnel", "distance", "distorter", "matcap", "jitter"}),
    ("OSL & Code", lambda c: c == "osl"),
]

EXCLUSIVE_NOTE = {
    "c4d": "C4D-only node: it has no Houdini counterpart and is skipped "
           "when pasting in Houdini.",
    "hou": "Houdini-only node: it has no C4D counterpart and is skipped "
           "when pasting in C4D.",
}

STATUS_LABEL = {"ok": "Portable", "partial": "Partial",
                "c4d": "C4D only", "hou": "Houdini only"}


def categorize(cls):
    for name, match in CATEGORIES:
        if match(cls):
            return name
    return "Other Utilities"


def collect():
    hou_data, c4d_data, both, aliased, c4d_only, hou_only = cr.compute()
    alias_by_c4d = dict(aliased)
    items = []
    for cls in sorted(both | c4d_only | hou_only):
        if cls in c4d_only:
            status = "c4d"
        elif cls in hou_only:
            status = "hou"
        elif cls in cr.PARTIAL_NOTES:
            status = "partial"
        else:
            status = "ok"
        label = cls
        search = cls
        if cls in alias_by_c4d:
            label = "%s / %s" % (cls, alias_by_c4d[cls])
            search = "%s %s" % (cls, alias_by_c4d[cls])
        note = cr.PARTIAL_NOTES.get(cls) or EXCLUSIVE_NOTE.get(status, "")
        items.append({"cls": cls, "label": label, "search": search,
                      "status": status, "note": note,
                      "category": categorize(cls)})
    return hou_data, c4d_data, items


def _fmt_c4d_version(v):
    s = str(v)
    return "%s.%s" % (s[:4], s[4]) if len(s) >= 5 else s


PAGE = """<title>RS Material Bridge — Node Compatibility</title>
<style>
:root{
  --bg:#f6f4f1; --surface:#ffffff; --ink:#23201d; --muted:#71685f;
  --line:#e5ded6; --accent:#d04a27;
  --ok:#2e8f5b; --warn:#b57a1c; --bad:#c23b3b;
  --mono:ui-monospace,"Cascadia Code",Consolas,"SF Mono",Menlo,monospace;
  --sans:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,sans-serif;
}
@media (prefers-color-scheme: dark){:root{
  --bg:#17130f; --surface:#211c16; --ink:#ece6dd; --muted:#9d9186;
  --line:#383128; --accent:#f06a41;
  --ok:#4ec98a; --warn:#e0a23e; --bad:#e46060;
}}
:root[data-theme="dark"]{
  --bg:#17130f; --surface:#211c16; --ink:#ece6dd; --muted:#9d9186;
  --line:#383128; --accent:#f06a41;
  --ok:#4ec98a; --warn:#e0a23e; --bad:#e46060;
}
:root[data-theme="light"]{
  --bg:#f6f4f1; --surface:#ffffff; --ink:#23201d; --muted:#71685f;
  --line:#e5ded6; --accent:#d04a27;
  --ok:#2e8f5b; --warn:#b57a1c; --bad:#c23b3b;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--sans)}
.wrap{max-width:1080px;margin:0 auto;padding:36px 24px 72px}
.eyebrow{font:600 11px/1 var(--mono);letter-spacing:.18em;color:var(--accent);
  text-transform:uppercase;margin:0}
h1{font-size:clamp(26px,4vw,34px);font-weight:650;letter-spacing:-.02em;
  text-wrap:balance;margin:10px 0 10px}
.sub{color:var(--muted);max-width:64ch;margin:0 0 6px}
.meta{font:12.5px/1.6 var(--mono);color:var(--muted);margin:0}
.controls{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;
  gap:10px;align-items:center;padding:14px 0;margin-top:22px;
  background:var(--bg);border-bottom:1px solid var(--line)}
#q{flex:1 1 230px;padding:9px 13px;border:1px solid var(--line);
  border-radius:8px;background:var(--surface);color:var(--ink);
  font:14px var(--sans)}
#q:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.fbtn{display:inline-flex;align-items:center;gap:7px;padding:8px 13px;
  border:1px solid var(--line);border-radius:999px;background:var(--surface);
  color:var(--ink);font:500 13px/1 var(--sans);cursor:pointer}
.fbtn:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.fbtn[aria-pressed="true"]{border-color:var(--accent);
  box-shadow:inset 0 0 0 1px var(--accent)}
.fbtn .n{font-family:var(--mono);font-variant-numeric:tabular-nums;
  color:var(--muted);font-size:12px}
.dot{width:8px;height:8px;border-radius:50%;flex:none}
.st-ok{background:var(--ok)} .st-partial{background:var(--warn)}
.st-c4d,.st-hou{background:var(--bad)}
#shown{font:12.5px var(--mono);font-variant-numeric:tabular-nums;
  color:var(--muted);margin-left:auto}
main section h2{display:flex;align-items:baseline;gap:9px;
  font:600 12px var(--mono);letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);margin:30px 0 11px}
main section h2 .n{font-weight:500;font-variant-numeric:tabular-nums}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:8px;
  font:500 12.5px/1 var(--mono);padding:8px 11px;border:1px solid var(--line);
  border-radius:7px;background:var(--surface)}
.chip.has-note{border-style:dashed;cursor:help}
.hidden{display:none}
.notes{margin-top:44px;border-top:1px solid var(--line);padding-top:20px}
.notes h2{font:600 12px var(--mono);letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);margin:0 0 12px}
.notes ul{margin:0;padding:0;list-style:none;display:grid;gap:9px}
.notes li{max-width:78ch}
.notes .nm{font:600 12.5px var(--mono)}
footer{margin-top:48px;color:var(--muted);font:12.5px/1.7 var(--mono)}
footer code{color:var(--ink)}
@media (prefers-reduced-motion: no-preference){
  .chip,.fbtn{transition:border-color .15s}
}
</style>
<div class="wrap">
<header>
  <p class="eyebrow">RS Material Bridge</p>
  <h1>Node compatibility guide</h1>
  <p class="sub">Which Redshift nodes survive the copy/paste trip between
  Houdini and Cinema 4D. Built from the real node inventories of both
  installs — not from documentation.</p>
  <p class="meta">__META__</p>
</header>
<div class="controls">
  <input id="q" type="search" placeholder="Search nodes…"
         aria-label="Search nodes">
  __FILTERS__
  <span id="shown"></span>
</div>
<main>
__SECTIONS__
</main>
<section class="notes">
  <h2>Notes</h2>
  <ul>
__NOTES__
  </ul>
</section>
<footer>Generated __DATE__ · regenerate with
<code>python tools/build_node_guide.py</code> after Redshift updates —
the inventories refresh automatically on every Copy.</footer>
</div>
<script>
(function(){
  var chips=[].slice.call(document.querySelectorAll('.chip'));
  var secs=[].slice.call(document.querySelectorAll('main section'));
  var btns=[].slice.call(document.querySelectorAll('.fbtn'));
  var shown=document.getElementById('shown');
  var st='all', q='';
  function apply(){
    var n=0;
    chips.forEach(function(c){
      var on=(st==='all'||c.dataset.st===st)&&c.dataset.name.indexOf(q)>-1;
      c.classList.toggle('hidden',!on); if(on)n++;
    });
    secs.forEach(function(s){
      s.classList.toggle('hidden',!s.querySelector('.chip:not(.hidden)'));
    });
    shown.textContent=n+' / '+chips.length+' nodes';
  }
  document.getElementById('q').addEventListener('input',function(e){
    q=e.target.value.toLowerCase().trim(); apply();
  });
  btns.forEach(function(b){
    b.addEventListener('click',function(){
      st=b.dataset.f;
      btns.forEach(function(x){x.setAttribute('aria-pressed',x===b);});
      apply();
    });
  });
  apply();
})();
</script>
"""


def build():
    hou_data, c4d_data, items = collect()

    counts = {"all": len(items)}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1

    filters = ['<button class="fbtn" data-f="all" aria-pressed="true">'
               'All <span class="n">%d</span></button>' % counts["all"]]
    for st in ("ok", "partial", "c4d", "hou"):
        filters.append(
            '<button class="fbtn" data-f="%s" aria-pressed="false">'
            '<i class="dot st-%s"></i>%s <span class="n">%d</span></button>'
            % (st, st, STATUS_LABEL[st], counts.get(st, 0)))

    order = [name for name, _ in CATEGORIES] + ["Other Utilities"]
    sections = []
    for cat in order:
        cat_items = [i for i in items if i["category"] == cat]
        if not cat_items:
            continue
        chips = []
        for it in cat_items:
            note = (' title="%s"' % html.escape(it["note"], quote=True)
                    if it["note"] else "")
            chips.append(
                '<span class="chip%s" data-st="%s" data-name="%s"%s>'
                '<i class="dot st-%s"></i>%s</span>'
                % (" has-note" if it["note"] else "", it["status"],
                   html.escape(it["search"]), note, it["status"],
                   html.escape(it["label"])))
        sections.append(
            "<section><h2>%s <span class=\"n\">%d</span></h2>"
            "<div class=\"chips\">%s</div></section>"
            % (html.escape(cat), len(cat_items), "\n".join(chips)))

    notes = ["    <li><span class=\"nm st\">%s</span> — %s</li>"
             % (html.escape(it["label"]), html.escape(it["note"]))
             for it in items if it["note"]]
    notes.append("    <li><span class=\"nm\">output</span> — %s</li>"
                 % html.escape(cr.EXCLUDED["output"]))

    meta = ("Houdini %s · Cinema 4D %s · %d node classes compared"
            % (hou_data.get("app_version", "?"),
               _fmt_c4d_version(c4d_data.get("app_version", "?")),
               len(items)))

    page = (PAGE
            .replace("__META__", html.escape(meta))
            .replace("__FILTERS__", "\n  ".join(filters))
            .replace("__SECTIONS__", "\n".join(sections))
            .replace("__NOTES__", "\n".join(notes))
            .replace("__DATE__", time.strftime("%Y-%m-%d")))

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(page)
    print("Wrote %s (%d nodes, %d categories)"
          % (OUT_FILE, len(items), len(sections)))


if __name__ == "__main__":
    build()
