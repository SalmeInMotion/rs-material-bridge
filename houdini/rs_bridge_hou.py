"""
Redshift Material Bridge -- Houdini side.

Serializes a Redshift VOP material (redshift_vopnet) to a JSON
interchange file and rebuilds one from that file, so materials can
travel between Houdini and Cinema 4D (both directions).

Usage (shelf tools / Python shell):

    import rs_bridge_hou
    rs_bridge_hou.copy_selected_material()   # selected material -> clipboard file
    rs_bridge_hou.paste_material()           # clipboard file -> new material in /mat

The JSON "clipboard" lives at ~/.rs_material_bridge/clipboard.json
(override with the RS_MATERIAL_BRIDGE_DIR environment variable).

Interchange conventions (shared with the C4D side):
- node "class" is the Redshift shader class in lowercase, e.g.
  "texturesampler" (Houdini type "redshift::TextureSampler",
  C4D asset "com.redshift3d.redshift4c4d.nodes.core.texturesampler").
- param / port names are lowercase RS parameter names ("base_color").
  Nested C4D ports use dots: "tex0.path", "tex0.colorspace".
  On the Houdini side "tex0.path" maps to parm "tex0" and
  "tex0.colorspace" to parm "tex0_colorSpace" (resolved
  case-insensitively).
- Ramps/curves are NOT supported yet: they are skipped with a warning.
"""

import json
import os
import re
import time

import hou

FORMAT_NAME = "rs-material-bridge"
FORMAT_VERSION = 1
TOOL_VERSION = "0.9.0-beta.1"

BRIDGE_DIR = os.environ.get(
    "RS_MATERIAL_BRIDGE_DIR",
    os.path.join(os.path.expanduser("~"), ".rs_material_bridge"),
)
CLIP_FILE = os.path.join(BRIDGE_DIR, "clipboard.json")
CLASSES_SELF_FILE = os.path.join(BRIDGE_DIR, "classes_houdini.json")
CLASSES_OTHER_FILE = os.path.join(BRIDGE_DIR, "classes_c4d.json")

BUILDER_TYPES = ("redshift_vopnet", "rs_usd_material_builder")
OUTPUT_TYPES = ("redshift_material", "redshift_usd_material")

# Same node, different class name per app (verified via the class dumps).
CLASS_ALIASES = {"osl": "rsosl"}        # interchange class -> local class
CLASS_ALIASES_OTHER = {"rsosl": "osl"}  # local class -> name in C4D

# Houdini parms that are UI/bookkeeping, not RS shader params.
_SKIP_PARM_RE = re.compile(r"^(RS_|ogl_|vm_)", re.IGNORECASE)

_TEX_PARM_RE = re.compile(r"^tex\d+$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Clipboard file
# ---------------------------------------------------------------------------

def _write_clip(data):
    if not os.path.isdir(BRIDGE_DIR):
        os.makedirs(BRIDGE_DIR)
    tmp = CLIP_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CLIP_FILE)  # atomic: never a half-written clipboard


def _read_clip():
    if not os.path.isfile(CLIP_FILE):
        raise RuntimeError("Bridge clipboard not found: %s\n"
                           "Copy a material first (from Houdini or C4D)."
                           % CLIP_FILE)
    try:
        with open(CLIP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except ValueError:
        raise RuntimeError("Bridge clipboard is corrupt: %s\n"
                           "Run Copy again." % CLIP_FILE)
    if data.get("format") != FORMAT_NAME:
        raise RuntimeError("Not a %s file: %s" % (FORMAT_NAME, CLIP_FILE))
    if data.get("version", 1) > FORMAT_VERSION:
        raise RuntimeError("Clipboard was written by a newer bridge "
                           "(format v%s, this side reads v%s). Update the "
                           "bridge on this side."
                           % (data.get("version"), FORMAT_VERSION))
    return data


def _ui_status(msg):
    try:
        if hou.isUIAvailable():
            hou.ui.setStatusMessage(msg)
    except Exception:
        pass


def _ui_error(msg):
    print(msg)
    try:
        if hou.isUIAvailable():
            hou.ui.displayMessage(msg, severity=hou.severityType.Error)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# RS type lookup
# ---------------------------------------------------------------------------

def _rs_type_map():
    """lowercase RS class -> full Houdini VOP type name."""
    out = {}
    for name in hou.vopNodeTypeCategory().nodeTypes():
        if name.startswith("redshift::"):
            out[name[len("redshift::"):].lower()] = name
    return out


def dump_node_classes(verbose=True):
    """Write the RS node classes this Houdini build offers. The C4D side
    reads this to warn at copy time; tools/compat_report.py builds
    COMPATIBILITY.md from both dumps. Refreshed on every copy."""
    classes = sorted(_rs_type_map())
    if not os.path.isdir(BRIDGE_DIR):
        os.makedirs(BRIDGE_DIR)
    with open(CLASSES_SELF_FILE, "w", encoding="utf-8") as f:
        json.dump({"app": "houdini",
                   "app_version": hou.applicationVersionString(),
                   "dumped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "classes": classes}, f, indent=2)
    if verbose:
        print("[RS Bridge] Dumped %d RS node classes -> %s"
              % (len(classes), CLASSES_SELF_FILE))
    return classes


def _other_app_classes():
    """Classes available in the other app (from its dump), or None."""
    try:
        with open(CLASSES_OTHER_FILE, "r", encoding="utf-8") as f:
            return {c.lower() for c in json.load(f).get("classes") or []}
    except (IOError, OSError, ValueError):
        return None


def _find_builder(node):
    """Walk up from `node` to the enclosing RS material builder."""
    n = node
    while n is not None:
        if n.type().name() in BUILDER_TYPES:
            return n
        n = n.parent()
    return None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _export_parms(node, warnings):
    params = {}
    for pt in node.parmTuples():
        template = pt.parmTemplate()
        ttype = template.type()
        if ttype in (hou.parmTemplateType.Folder,
                     hou.parmTemplateType.FolderSet,
                     hou.parmTemplateType.Separator,
                     hou.parmTemplateType.Label,
                     hou.parmTemplateType.Button):
            continue
        if ttype == hou.parmTemplateType.Ramp:
            if not pt.isAtDefault():
                warnings.append("%s: ramp parm '%s' not supported, skipped"
                                % (node.name(), pt.name()))
            continue
        if pt.isAtDefault():
            continue
        if _SKIP_PARM_RE.match(pt.name()):
            continue
        try:
            val = pt.eval()
        except hou.Error:
            continue
        val = list(val)
        if len(val) == 1:
            val = val[0]
        name = pt.name().lower()
        # Texture file parms map to the nested C4D port tex0 > path.
        if _TEX_PARM_RE.match(name) and isinstance(val, str):
            name = name + ".path"
        elif re.match(r"^tex\d+_colorspace$", name):
            name = name.replace("_colorspace", ".colorspace")
        params[name] = val
    return params


def _connection_record(conn, dst, warnings=None):
    """Return (src_node, src_out_name, dst_in_name) for a connection
    feeding `dst`, resolving hou.NodeConnection's ambiguous naming by
    validating names against the actual connector lists."""
    n_a, n_b = conn.inputNode(), conn.outputNode()
    src = n_a if n_b == dst else n_b
    if src is None or src == dst:
        return None

    names = []
    for getter in ("inputName", "outputName"):
        try:
            names.append(getattr(conn, getter)())
        except (AttributeError, hou.Error):
            names.append(None)

    dst_inputs = list(dst.inputNames())
    src_outputs = list(src.outputNames())
    dst_in = next((n for n in names if n in dst_inputs), None)
    src_out = next((n for n in names if n in src_outputs and n != dst_in),
                   None)
    if src_out is None and src_outputs:
        src_out = src_outputs[0]
        if warnings is not None and len(src_outputs) > 1:
            warnings.append("%s: source output of the wire from '%s' could "
                            "not be resolved by name, assuming its first "
                            "output '%s' -- verify this connection"
                            % (dst.name(), src.name(), src_out))
    if dst_in is None:
        # Last resort: index-based lookup (inputIndex first: it indexes
        # the destination's input connectors under standard semantics).
        for getter in ("inputIndex", "outputIndex"):
            try:
                idx = getattr(conn, getter)()
                if 0 <= idx < len(dst_inputs):
                    dst_in = dst_inputs[idx]
                    break
            except (AttributeError, hou.Error):
                continue
    if dst_in is None:
        return None
    return (src, src_out, dst_in)


def export_material(builder):
    warnings = []
    nodes = []
    connections = []
    outputs = {}
    key_by_path = {}

    children = list(builder.children())
    rs_children = [c for c in children
                   if c.type().name().startswith("redshift::")]
    out_nodes = [c for c in children if c.type().name() in OUTPUT_TYPES]

    for c in children:
        tname = c.type().name()
        if not tname.startswith("redshift::") and tname not in OUTPUT_TYPES:
            warnings.append("non-Redshift node '%s' (%s) is not exported"
                            % (c.name(), tname))

    for i, c in enumerate(rs_children):
        key = "n%d" % i
        key_by_path[c.path()] = key
        nodes.append({
            "key": key,
            "class": c.type().name()[len("redshift::"):].lower(),
            "name": c.name(),
            "pos": list(c.position()),
            "params": _export_parms(c, warnings),
        })

    for c in rs_children:
        for conn in c.inputConnections():
            rec = _connection_record(conn, c, warnings)
            if rec is None:
                warnings.append("%s: could not resolve an input connection"
                                % c.name())
                continue
            src, src_out, dst_in = rec
            if src.path() not in key_by_path:
                warnings.append("%s: input '%s' fed by non-exported node "
                                "'%s' -- connection dropped"
                                % (c.name(), dst_in, src.name()))
                continue
            connections.append({
                "src": key_by_path[src.path()],
                "src_port": (src_out or "").lower(),
                "dst": key_by_path[c.path()],
                "dst_port": dst_in.lower(),
            })

    if out_nodes:
        out = out_nodes[0]
        for conn in out.inputConnections():
            rec = _connection_record(conn, out, warnings)
            if rec is None:
                continue
            src, _src_out, dst_in = rec
            if src.path() not in key_by_path:
                warnings.append("material output '%s' fed by non-exported "
                                "node '%s' -- dropped"
                                % (dst_in, src.name()))
                continue
            slot = dst_in.lower()
            for role in ("surface", "displacement", "volume", "environment"):
                if role in slot:
                    outputs[role] = key_by_path[src.path()]
                    break
    else:
        warnings.append("no output node (redshift_material) found in %s"
                        % builder.path())

    other = _other_app_classes()
    if other:
        for nd in nodes:
            if (nd["class"] not in other
                    and CLASS_ALIASES_OTHER.get(nd["class"]) not in other):
                warnings.append("node '%s' (class '%s') does not exist in "
                                "C4D -- it will be skipped on paste"
                                % (nd["name"], nd["class"]))

    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "tool_version": TOOL_VERSION,
        "source_app": "houdini",
        "source_version": hou.applicationVersionString(),
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "material": {
            "name": builder.name(),
            "nodes": nodes,
            "connections": connections,
            "outputs": outputs,
        },
        "warnings": warnings,
    }


def copy_selected_material():
    try:
        dump_node_classes(verbose=False)
    except (hou.Error, OSError) as e:
        print("[RS Bridge] note: could not refresh the node inventory (%s)"
              % e)
    sel = hou.selectedNodes()
    builder = _find_builder(sel[0]) if sel else None
    if builder is None:
        _ui_error("[RS Bridge] Select a Redshift material "
                  "(redshift_vopnet) first.")
        return None

    data = export_material(builder)
    _write_clip(data)

    mat = data["material"]
    msg = ("[RS Bridge] Copied '%s': %d nodes, %d connections -> %s"
           % (mat["name"], len(mat["nodes"]), len(mat["connections"]),
              CLIP_FILE))
    print(msg)
    for w in data["warnings"]:
        print("[RS Bridge]   warning: %s" % w)
    _ui_status(msg)
    return data


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _resolve_parm_name(node, name):
    """Map an interchange param name to an actual parm tuple on `node`.
    Handles 'tex0.path' -> 'tex0', dotted -> underscore, case."""
    lut = {pt.name().lower(): pt for pt in node.parmTuples()}
    cands = [name]
    if name.endswith(".path"):
        cands.append(name[:-len(".path")])
    cands.append(name.replace(".", "_"))
    for c in cands:
        pt = lut.get(c.lower())
        if pt is not None:
            return pt
    return None


def _set_parm(pt, value, node_label, warnings):
    vals = value if isinstance(value, list) else [value]
    if not vals:
        warnings.append("%s: empty value for parm '%s' -- skipped"
                        % (node_label, pt.name()))
        return False
    n = len(pt)
    if len(vals) < n:
        pad = [vals[-1]] * (n - len(vals))
        if len(vals) == 3 and n == 4:
            pad = [1.0]  # RGB -> RGBA: alpha defaults to opaque
        vals = vals + pad
    vals = vals[:n]
    try:
        pt.set(tuple(vals))
        return True
    except (hou.Error, TypeError):
        pass
    # Typed coercion fallbacks. String parms only accept str -- but feeding
    # a menu parm the repr of a number would corrupt it silently, so menu
    # tokens are validated and every coerced set is reported for review.
    is_string = (pt.parmTemplate().type() == hou.parmTemplateType.String)
    for conv in ((str,) if is_string else (float, int)):
        try:
            coerced = tuple(conv(v) for v in vals)
        except (TypeError, ValueError):
            continue
        if is_string:
            try:
                menu = pt[0].menuItems()
            except hou.Error:
                menu = ()
            if menu and coerced[0] not in menu:
                break  # not a valid menu token: warn below instead
        try:
            pt.set(coerced)
            warnings.append("%s: parm '%s' set from %r via %s coercion -- "
                            "verify the value"
                            % (node_label, pt.name(), value, conv.__name__))
            return True
        except (hou.Error, TypeError, ValueError):
            continue
    warnings.append("%s: could not set parm '%s' to %r"
                    % (node_label, pt.name(), value))
    return False


def _named_input_index(node, name):
    for i, n in enumerate(node.inputNames()):
        if n.lower() == name.lower():
            return i
    return None


def _named_output_index(node, name, warnings=None):
    outs = list(node.outputNames())
    for i, n in enumerate(outs):
        if n.lower() == (name or "").lower():
            return i
    if warnings is not None and len(outs) > 1:
        warnings.append("%s: output '%s' not found, assuming first output "
                        "'%s' -- verify this connection"
                        % (node.name(), name, outs[0]))
    return 0 if outs else None


def import_material(data, dest="/mat"):
    warnings = list(data.get("warnings", []))
    mat = data["material"]
    type_map = _rs_type_map()
    if not type_map:
        raise RuntimeError("No Redshift VOP node types found -- is "
                           "Redshift for Houdini installed and licensed?")

    matnet = hou.node(dest)
    if matnet is None:
        raise RuntimeError("Destination network not found: %s" % dest)

    safe = re.sub(r"[^A-Za-z0-9_]", "_", mat.get("name") or "rs_bridge_mat")
    safe = re.sub(r"^(?=\d)", "_", safe)  # node names can't start with a digit
    builder = matnet.createNode("redshift_vopnet", safe)

    # Drop the default shading nodes; keep the output collect node.
    out_node = None
    for c in list(builder.children()):
        if c.type().name() in OUTPUT_TYPES:
            out_node = c
        else:
            c.destroy()
    if out_node is None:
        out_node = builder.createNode("redshift_material")

    built = {}
    has_pos = False
    for nd in mat["nodes"]:
        cls = nd["class"]
        type_name = (type_map.get(cls)
                     or type_map.get(CLASS_ALIASES.get(cls, "")))
        if type_name is None:
            warnings.append("no Houdini RS node type for class '%s' "
                            "(node '%s' skipped)" % (cls, nd.get("name")))
            continue
        name = re.sub(r"[^A-Za-z0-9_]", "_", nd.get("name") or cls)
        name = re.sub(r"^(?=\d)", "_", name)
        node = builder.createNode(type_name, name)
        built[nd["key"]] = node
        if nd.get("pos"):
            node.setPosition(hou.Vector2(*nd["pos"][:2]))
            has_pos = True
        for pname, pval in nd.get("params", {}).items():
            pt = _resolve_parm_name(node, pname)
            if pt is None:
                warnings.append("%s: no parm matches '%s'"
                                % (node.name(), pname))
                continue
            _set_parm(pt, pval, node.name(), warnings)

    for conn in mat.get("connections", []):
        src = built.get(conn["src"])
        dst = built.get(conn["dst"])
        if src is None or dst is None:
            continue
        in_idx = _named_input_index(dst, conn["dst_port"])
        out_idx = _named_output_index(src, conn.get("src_port"), warnings)
        if in_idx is None or out_idx is None:
            warnings.append("could not connect %s.%s -> %s.%s"
                            % (src.name(), conn.get("src_port"),
                               dst.name(), conn["dst_port"]))
            continue
        try:
            dst.setInput(in_idx, src, out_idx)
        except hou.Error as e:
            warnings.append("connect %s -> %s.%s failed: %s"
                            % (src.name(), dst.name(), conn["dst_port"], e))

    for role, key in (mat.get("outputs") or {}).items():
        src = built.get(key)
        if src is None:
            continue
        in_idx = next((i for i, n in enumerate(out_node.inputNames())
                       if role in n.lower()), None)
        if in_idx is None:
            warnings.append("output node has no '%s' input" % role)
            continue
        try:
            out_node.setInput(in_idx, src, 0)
        except hou.Error as e:
            warnings.append("connect %s -> output %s failed: %s"
                            % (src.name(), role, e))

    if not has_pos:
        builder.layoutChildren()
    builder.setMaterialFlag(True)
    return builder, warnings


def paste_material(dest="/mat"):
    data = _read_clip()
    builder, warnings = import_material(data, dest)
    msg = ("[RS Bridge] Pasted '%s' (from %s) as %s"
           % (data["material"].get("name"), data.get("source_app"),
              builder.path()))
    print(msg)
    for w in warnings:
        print("[RS Bridge]   warning: %s" % w)
    _ui_status(msg)
    if warnings:
        print("[RS Bridge] %d warning(s) -- see above." % len(warnings))
    return builder
