"""Generate COMPATIBILITY.md from the node-class dumps written by the
Houdini and C4D sides (classes_houdini.json / classes_c4d.json in the
bridge directory). Plain Python -- run from any shell:

    python tools/compat_report.py
"""

import json
import os
import sys
import time

BRIDGE_DIR = os.environ.get(
    "RS_MATERIAL_BRIDGE_DIR",
    os.path.join(os.path.expanduser("~"), ".rs_material_bridge"),
)
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(REPO_DIR, "COMPATIBILITY.md")

# Same node, different class name per app -- bridged via alias in the tool.
ALIAS_PAIRS = [("osl", "rsosl")]  # (c4d class, houdini class)

# Not shading nodes: infrastructure the bridge handles structurally.
EXCLUDED = {"output": "the material Output node -- the bridge wires "
                      "surface/displacement/volume outputs itself"}

# Node exists on both sides but some values don't travel yet.
PARTIAL_NOTES = {
    "rsramp": "node travels, but ramp/curve knot values are not carried "
              "in v1 (reset to defaults on paste)",
    "rsscalarramp": "node travels, but ramp/curve knot values are not "
                    "carried in v1 (reset to defaults on paste)",
    "osl": "aliased to Houdini's `rsosl`; the OSL source travels "
           "best-effort, dynamically created ports may not",
}


def _load(app):
    path = os.path.join(BRIDGE_DIR, "classes_%s.json" % app)
    if not os.path.isfile(path):
        sys.exit("Missing %s -- run a Copy once in %s to generate it."
                 % (path, "Houdini" if app == "houdini" else "C4D"))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _section(title, classes, note=""):
    lines = ["## %s (%d)" % (title, len(classes)), ""]
    if note:
        lines += [note, ""]
    if classes:
        for c in sorted(classes):
            extra = PARTIAL_NOTES.get(c)
            lines.append("- `%s`%s" % (c, " -- %s" % extra if extra else ""))
    else:
        lines.append("*(none)*")
    lines.append("")
    return lines


def compute():
    """Load both dumps and classify classes. Shared with the HTML guide
    generator (build_node_guide.py)."""
    hou_data = _load("houdini")
    c4d_data = _load("c4d")
    hou_classes = {c.lower() for c in hou_data["classes"]}
    c4d_classes = {c.lower() for c in c4d_data["classes"]} - set(EXCLUDED)

    both = hou_classes & c4d_classes
    hou_only = hou_classes - c4d_classes
    c4d_only = c4d_classes - hou_classes

    aliased = []
    for c4d_cls, hou_cls in ALIAS_PAIRS:
        if c4d_cls in c4d_only and hou_cls in hou_only:
            c4d_only.discard(c4d_cls)
            hou_only.discard(hou_cls)
            both.add(c4d_cls)
            aliased.append((c4d_cls, hou_cls))
    return hou_data, c4d_data, both, aliased, c4d_only, hou_only


def main():
    hou_data, c4d_data, both, aliased, c4d_only, hou_only = compute()

    lines = [
        "# RS Material Bridge -- node compatibility",
        "",
        "Generated %s by tools/compat_report.py from the real node "
        "inventories of both apps:" % time.strftime("%Y-%m-%d %H:%M"),
        "",
        "- Houdini %s (dumped %s): %d RS node classes"
        % (hou_data.get("app_version", "?"), hou_data.get("dumped_at", "?"),
           len(hou_classes)),
        "- C4D %s (dumped %s): %d RS node classes"
        % (c4d_data.get("app_version", "?"), c4d_data.get("dumped_at", "?"),
           len(c4d_classes)),
        "",
        "A class listed as portable means the *node* exists on both "
        "sides; individual parameters may still raise paste warnings "
        "(ramps, odd enums). Re-generate after Redshift updates -- the "
        "dumps refresh automatically on every Copy.",
        "",
    ]
    lines += _section("Portable (exists in both)", both)
    if aliased:
        lines += ["Aliased pairs (same node, different class name, bridged "
                  "automatically): "
                  + ", ".join("`%s` (C4D) = `%s` (Houdini)" % p
                              for p in aliased), ""]
    lines += _section(
        "C4D only -- will NOT travel to Houdini", c4d_only,
        "C4D-native integrations without a Houdini counterpart.")
    lines += _section(
        "Houdini only -- will NOT travel to C4D", hou_only)
    lines += ["## Not counted", ""]
    lines += ["- `%s` -- %s" % (k, v) for k, v in sorted(EXCLUDED.items())]
    lines.append("")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Wrote %s (portable=%d, c4d_only=%d, houdini_only=%d)"
          % (OUT_FILE, len(both), len(c4d_only), len(hou_only)))


if __name__ == "__main__":
    main()
