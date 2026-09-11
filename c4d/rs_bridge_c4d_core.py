"""
Redshift Material Bridge -- Cinema 4D side (core module).

Serializes the active Redshift node material to the shared JSON
interchange file and rebuilds one from that file. Companion of
rs_bridge_hou.py (Houdini); see that module's docstring for the
interchange conventions.

Verified against C4D 2024+ / Redshift node materials (maxon graph API):
- read port values with GetPortValue (GetDefaultValue is deprecated),
- write inside graph.BeginTransaction() ... txn.Commit(),
- texture paths are maxon.Url ("file:///D:/..." forward slashes).

Run via the thin wrapper scripts rs_mat_copy.py / rs_mat_paste.py.
"""

import json
import os
import re
import time
import traceback

import c4d
import maxon
from c4d import gui

FORMAT_NAME = "rs-material-bridge"
FORMAT_VERSION = 2
TOOL_VERSION = "0.9.0-beta.2"

# Ramps. Each application names its interpolation modes differently, so the
# interchange uses a neutral vocabulary and each side maps to its own.
# The C4D names are the real enum, read from Redshift's node database.
RAMP_KIND = "ramp"
C4D_INTERP_TO_CANON = {
    "none": "constant",
    "linearknot": "linear",
    "cubicknot": "cubic",
    "smoothknot": "smooth",
    "cubicbias": "cubic",     # bias travels alongside, unused elsewhere
    "blend": "smooth",
}
CANON_TO_C4D_INTERP = {
    "constant": "none",
    "linear": "linearknot",
    "cubic": "cubicknot",
    "smooth": "smoothknot",
}

BRIDGE_DIR = os.environ.get(
    "RS_MATERIAL_BRIDGE_DIR",
    os.path.join(os.path.expanduser("~"), ".rs_material_bridge"),
)
CLIP_FILE = os.path.join(BRIDGE_DIR, "clipboard.json")
CLASSES_SELF_FILE = os.path.join(BRIDGE_DIR, "classes_c4d.json")
CLASSES_OTHER_FILE = os.path.join(BRIDGE_DIR, "classes_houdini.json")

# Same node, different class name per app (verified via the class dumps).
CLASS_ALIASES = {"rsosl": "osl"}        # interchange class -> local class
CLASS_ALIASES_OTHER = {"osl": "rsosl"}  # local class -> name in Houdini

RS_NODESPACE_ID = "com.redshift3d.redshift4c4d.class.nodespace"
RS_NODE_PREFIX = "com.redshift3d.redshift4c4d.nodes.core."
RS_OUTPUT_ID = "com.redshift3d.redshift4c4d.node.output"

VERBOSE = True

# C4D texture slots (tex0, tex1...) carry C4D-specific sub-ports for image
# sequence playback (animation, timing, framestart...). Only these children
# mean anything cross-DCC; the rest are per-app wrappers (Houdini does
# sequences with $F tokens in the path instead).
_TEX_GROUP_RE = re.compile(r"^tex\d+$", re.IGNORECASE)
_TEX_CHILDREN_KEEP = ("path", "colorspace")


def _log(msg):
    if VERBOSE:
        print("[RS Bridge] %s" % msg)


# ---------------------------------------------------------------------------
# Clipboard file
# ---------------------------------------------------------------------------

def write_clip(data):
    if not os.path.isdir(BRIDGE_DIR):
        os.makedirs(BRIDGE_DIR)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    tmp = CLIP_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, CLIP_FILE)  # atomic: never a half-written clipboard
    # Also on the system clipboard: reporting a problem is then just
    # Ctrl+V, with no hunting for the file.
    try:
        c4d.CopyStringToClipboard(text)
    except Exception as e:
        _log("note: could not put the copy on the system clipboard (%s)" % e)


def read_clip():
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


# ---------------------------------------------------------------------------
# Graph access helpers (patterns verified in path_remapper_v3.py)
# ---------------------------------------------------------------------------

def get_rs_graph(mat):
    rs_id = maxon.Id(RS_NODESPACE_ID)
    try:
        nimbus = mat.GetNimbusRef(rs_id)
    except Exception:
        nimbus = None
    if nimbus is not None and not _is_null(nimbus):
        for meth in ("GetGraph", "GetNodesGraph"):
            g = _try_call(nimbus, meth)
            if g is not None and not _is_null(g):
                return g
    try:
        nm = mat.GetNodeMaterialReference()
        if nm is not None and not _is_null(nm) and nm.HasSpace(rs_id):
            g = nm.GetGraph(rs_id)
            if g is not None and not _is_null(g):
                return g
    except Exception:
        pass
    return None


def _is_null(obj):
    try:
        return hasattr(obj, "IsNullValue") and obj.IsNullValue()
    except Exception:
        return False


def _try_call(obj, name, *args):
    try:
        meth = getattr(obj, name, None)
        if meth is None:
            return None
        return meth(*args)
    except Exception:
        return None


def _children(parent):
    out = []
    try:
        def cb(c):
            out.append(c)
            return True
        parent.GetChildren(cb)
        if out:
            return out
    except Exception:
        pass
    try:
        for c in parent.GetChildren():
            out.append(c)
    except Exception:
        pass
    return out


def graph_nodes(graph):
    """All true nodes (NODE_KIND.NODE) of the graph."""
    for root_meth in ("GetViewRoot", "GetRoot"):
        root = _try_call(graph, root_meth)
        if root is None or _is_null(root):
            continue
        nodes = []
        try:
            maxon.GraphModelHelper.GetAllChildren(nodes, root,
                                                  maxon.NODE_KIND.NODE)
        except Exception:
            nodes = []
        if not nodes:
            for c in _children(root):
                try:
                    if c.GetKind() == maxon.NODE_KIND.NODE:
                        nodes.append(c)
                except Exception:
                    nodes.append(c)
        if nodes:
            return _with_grouped_nodes(nodes)
    return []


def _with_grouped_nodes(nodes, depth=0):
    """Flatten node groups into the list. Grouping is organisation, not
    shading -- but the shader nodes inside a group are real, and leaving
    them behind silently loses part of the material."""
    if depth > 12:
        return nodes
    out = []
    for n in nodes:
        out.append(n)
        nested = child_nodes(n)
        if nested:
            out.extend(_with_grouped_nodes(nested, depth + 1))
    return out


def node_uid(node):
    """Identity of a graph node, unique across the whole material.

    Ids are only unique within their enclosing group, so copies of the
    same group hold nodes with identical ids -- flattening them by id
    collapses three nodes into one and every connection lands on the same
    node. The path carries the enclosing groups, so it does not."""
    path = _try_call(node, "GetPath")
    if path is not None and not _is_null(path):
        text = str(path)
        if text:
            return text
    return str(_try_call(node, "GetId") or "")


def node_kind(node):
    """Leading part of a graph node's id: 'texturesampler', 'reroute',
    'group', 'scaffold', 'type'..."""
    nid = str(_try_call(node, "GetId") or "")
    return nid.split("@")[0] if "@" in nid else nid


def child_nodes(node):
    """Nodes nested inside `node` -- non-empty only for groups, whose other
    children are the two port containers."""
    out = []
    for c in _children(node):
        try:
            if c.GetKind() == maxon.NODE_KIND.NODE:
                out.append(c)
        except Exception:
            continue
    return out


def node_asset_id(node):
    """Full asset id string of a graph node, e.g.
    'com.redshift3d.redshift4c4d.nodes.core.texturesampler'."""
    candidates = []
    for attr in ("net.maxon.node.attribute.assetid",):
        v = _try_call(node, "GetValue", attr)
        if v is not None:
            candidates.append(str(v))
    if hasattr(maxon, "NODE"):
        try:
            v = node.GetValue(maxon.NODE.ATTRIBUTE.ASSETID)
            if v is not None:
                candidates.append(str(v))
        except Exception:
            pass
    candidates.append(str(_try_call(node, "GetId") or ""))
    for s in candidates:
        m = re.search(r"(com\.redshift3d\.[A-Za-z0-9_.]+)", s)
        if m:
            return m.group(1).rstrip(".")
    return None


def node_display_name(node):
    for attr in ("net.maxon.node.base.name",):
        v = _try_call(node, "GetValue", attr)
        if v:
            return str(v)
    aid = node_asset_id(node)
    return aid.split(".")[-1] if aid else "node"


def _last_segment(port):
    pid = str(_try_call(port, "GetId") or "")
    return pid.split(".")[-1].split("#")[0]


def _port_value(port):
    for meth in ("GetPortValue", "GetEffectiveValue", "GetDefaultValue"):
        try:
            m = getattr(port, meth, None)
            if m is None:
                continue
            v = m()
            if v is not None:
                return v
        except Exception:
            continue
    return None


def _port_write(port, value):
    for meth in ("SetPortValue", "SetDefaultValue"):
        try:
            m = getattr(port, meth, None)
            if m is None:
                continue
            m(value)
            return True
        except Exception:
            continue
    return False


def walk_ports(container, prefix=()):
    """Yield (dotted_name_parts, port, is_leaf) for every descendant port."""
    for child in _children(container):
        name = _last_segment(child)
        kids = _children(child)
        yield (prefix + (name,), child, not kids)
        if kids:
            for item in walk_ports(child, prefix + (name,)):
                yield item


def find_port(container, dotted):
    """Find a port by interchange name like 'base_color' or 'tex0.path'.
    Case-insensitive on each segment."""
    parts = [p for p in dotted.split(".") if p]
    cur = container
    for part in parts:
        nxt = None
        for c in _children(cur):
            if _last_segment(c).lower() == part.lower():
                nxt = c
                break
        if nxt is None:
            return None
        cur = nxt
    return cur


# ---------------------------------------------------------------------------
# Node class inventory (for the compatibility report / copy-time checks)
# ---------------------------------------------------------------------------

def _enumerate_rs_assets():
    """Full asset ids of every Redshift node available in this build."""
    repo = None
    for getter in ("GetUserPrefsRepository", "GetBuiltinRepository"):
        repo = _try_call(maxon.AssetInterface, getter)
        if repo is not None and not _is_null(repo):
            break
        repo = None
    if repo is None:
        raise RuntimeError("could not get an asset repository")

    type_ids = []
    try:
        type_ids.append(maxon.AssetTypes.NodeTemplate().GetId())
    except Exception:
        pass
    type_ids.append(maxon.Id("net.maxon.node.assettype.nodetemplate"))

    found = set()
    last_err = None
    for tid in type_ids:
        try:
            descs = repo.FindAssets(tid, maxon.Id(), maxon.Id(),
                                    maxon.ASSET_FIND_MODE.LATEST)
        except Exception as e:
            last_err = e
            continue
        for d in descs or []:
            s = str(_try_call(d, "GetId") or "")
            if s.startswith("com.redshift3d."):
                found.add(s)
        if found:
            break
    if not found and last_err is not None:
        raise RuntimeError("FindAssets failed: %s" % last_err)
    return sorted(found)


def dump_node_classes(verbose=True):
    """Write the RS node classes this C4D build offers. The Houdini side
    reads this to warn at copy time; tools/compat_report.py builds
    COMPATIBILITY.md from both dumps. Refreshed on every copy."""
    ids = _enumerate_rs_assets()
    classes = sorted({i.split(".")[-1].lower() for i in ids})
    if not os.path.isdir(BRIDGE_DIR):
        os.makedirs(BRIDGE_DIR)
    with open(CLASSES_SELF_FILE, "w", encoding="utf-8") as f:
        json.dump({"app": "c4d",
                   "app_version": str(c4d.GetC4DVersion()),
                   "dumped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "classes": classes,
                   "asset_ids": ids}, f, indent=2)
    if verbose:
        _log("Dumped %d RS node classes -> %s"
             % (len(classes), CLASSES_SELF_FILE))
    return classes


def _other_app_classes():
    """Classes available in the other app (from its dump), or None."""
    try:
        with open(CLASSES_OTHER_FILE, "r", encoding="utf-8") as f:
            return {c.lower() for c in json.load(f).get("classes") or []}
    except (IOError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Connections (API varies across 2024.x -- try several strategies)
# ---------------------------------------------------------------------------

def _owning_node(port):
    n = _try_call(port, "GetAncestor", maxon.NODE_KIND.NODE)
    if n is not None and not _is_null(n):
        return n
    cur = port
    for _ in range(16):
        cur = _try_call(cur, "GetParent")
        if cur is None or _is_null(cur):
            return None
        try:
            if cur.GetKind() == maxon.NODE_KIND.NODE:
                return cur
        except Exception:
            continue
    return None


def input_sources(port):
    """Source OUTPUT ports connected into `port`. Returns [] when the
    connection query API is unavailable (logged once)."""
    results = []
    attempts = (
        lambda: port.GetConnections(maxon.PORT_DIR.INPUT),
        lambda: _via_out_list(port, maxon.PORT_DIR.INPUT),
    )
    for attempt in attempts:
        try:
            conns = attempt()
        except Exception:
            continue
        if not conns:
            continue
        for c in conns:
            src = c
            if isinstance(c, (tuple, list)) and c:
                src = c[0]
            if src is not None and not _is_null(src):
                results.append(src)
        if results:
            return results
    return results


def _via_out_list(port, direction):
    conns = []
    port.GetConnections(direction, conns)
    return conns


def trace_source(port, depth=0):
    """Follow a connection back through wiring. Returns
    (shader_port, last_port_seen).

    Cinema 4D graphs are full of wiring that carries no shading: reroutes,
    type converters, and group boundaries (which nest). None of those
    exist in Houdini, so a connection passing through one has to be traced
    to whatever actually produces the value, or it is lost along with
    everything upstream. When the trail ends on a port holding a plain
    value instead of a node -- a group input exposing a constant -- that
    port is handed back so the value can travel as a parameter."""
    if port is None or depth > 24:
        return None, None
    node = _owning_node(port)
    if node is None:
        return None, port
    if node_asset_id(node) is not None:
        return port, port            # a real shader node: done

    # Group boundary ports answer on the port itself, in both directions.
    for src in input_sources(port):
        found, last = trace_source(src, depth + 1)
        if found is not None:
            return found, last

    # Pass-through node (reroute, type converter): continue from its input.
    inputs = _try_call(node, "GetInputs")
    if inputs is not None and not _is_null(inputs):
        for _parts, p, _leaf in walk_ports(inputs):
            for src in input_sources(p):
                found, last = trace_source(src, depth + 1)
                if found is not None:
                    return found, last
            if _port_value(p) is not None:
                port = p           # remember the deepest value we saw
    return None, port


def resolve_source(port, depth=0):
    """Shader port feeding `port`, or None when the wiring carries a plain
    value rather than a node."""
    return trace_source(port, depth)[0]


def _src_port_dotted(port):
    """Dotted path of an output port below its owning node (e.g.
    'outcolor.r'), so nested sub-outputs survive the round-trip. Climbs
    parents until the node, skipping the ports-root container."""
    segs = []
    cur = port
    for _ in range(12):
        if cur is None or _is_null(cur):
            break
        try:
            kind = cur.GetKind()
        except Exception:
            kind = None
        if kind == maxon.NODE_KIND.NODE:
            break
        if kind is None or kind == getattr(maxon.NODE_KIND, "PORT", kind):
            segs.append(_last_segment(cur))
        cur = _try_call(cur, "GetParent")
    segs.reverse()
    # The first segment is the port container itself ('>' for outputs,
    # '<' for inputs), which is not part of the port's name.
    while segs and segs[0] in (">", "<"):
        segs.pop(0)
    if segs:
        return ".".join(segs).lower()
    return _last_segment(port).lower()


_CONN_API_WARNED = [False]


def _warn_conn_api_once(warnings):
    if not _CONN_API_WARNED[0]:
        _CONN_API_WARNED[0] = True
        warnings.append("no connections found -- either this material has "
                        "none, or this C4D build's connection API is "
                        "unsupported (if nodes ARE wired, please report "
                        "this with the console output)")


# ---------------------------------------------------------------------------
# Value conversion
# ---------------------------------------------------------------------------

def _url_from_path(path):
    s = str(path)
    if s.lower().startswith(("file:", "asset:", "http:", "https:")):
        return maxon.Url(s)
    # SetSystemPath handles UNC shares, relative paths and characters that
    # a URL string would misparse (#, %, spaces).
    try:
        u = maxon.Url()
        u.SetSystemPath(maxon.String(s))
        if str(u):
            return u
    except Exception:
        pass
    p = s.replace("\\", "/")
    if p.startswith("//"):
        return maxon.Url("file:" + p)  # UNC: keep the server part intact
    return maxon.Url("file:///" + p.lstrip("/"))


_KNOT_RE = re.compile(r"^_(\d+)$")


def ramp_knot_ports(port):
    """Knot ports of a ramp container, in index order, or None if `port`
    is not a ramp. A ramp is an array port whose children are _0, _1..."""
    kids = _children(port)
    if not kids:
        return None
    indexed = []
    for c in kids:
        m = _KNOT_RE.match(_last_segment(c))
        if m is None:
            return None
        indexed.append((int(m.group(1)), c))
    return [c for _i, c in sorted(indexed)]


def export_ramp(port, node_name, warnings):
    """Ramp container port -> interchange dict, knots sorted by position."""
    knots = []
    is_color = False
    for knot in ramp_knot_ports(port) or []:
        fields = {}
        for parts, p, leaf in walk_ports(knot):
            if leaf:
                fields[parts[-1].lower()] = _port_value(p)
        pos = to_jsonable(fields.get("position"))
        if pos is None:
            continue
        if "color" in fields:
            is_color = True
            value = to_jsonable(fields["color"])
        else:
            value = to_jsonable(fields.get("value"))
        raw_interp = fields.get("interpolation")
        interp_name = str(raw_interp).strip().lower() if raw_interp is not None else ""
        canon = C4D_INTERP_TO_CANON.get(interp_name)
        if canon is None and interp_name:
            canon = "linear"
            warnings.append("%s: ramp interpolation '%s' is unknown, sent "
                            "as linear" % (node_name, interp_name))
        knot = {"pos": float(pos), "value": value,
                "interp": canon or "linear"}
        bias = to_jsonable(fields.get("bias"))
        if bias is not None:
            knot["bias"] = float(bias)
        knots.append(knot)
    knots.sort(key=lambda k: k["pos"])
    return {"_kind": RAMP_KIND, "color": is_color, "knots": knots}


def import_ramp(port, ramp_json, node_name, warnings):
    """Write an interchange ramp into a C4D ramp container port. Must be
    called inside a graph transaction."""
    knots = ramp_json.get("knots") or []
    if not knots:
        return
    existing = ramp_knot_ports(port) or []
    if len(existing) > len(knots):
        warnings.append("%s: ramp has %d knots but only %d were sent; the "
                        "extra ones keep their previous values"
                        % (node_name, len(existing), len(knots)))
    # Knot ports cannot be removed, only added -- indices must stay unique.
    next_index = 0
    for c in existing:
        m = _KNOT_RE.match(_last_segment(c))
        if m:
            next_index = max(next_index, int(m.group(1)) + 1)
    while len(existing) < len(knots):
        try:
            port.AddPort("_%d" % next_index)
        except Exception as e:
            warnings.append("%s: could not add ramp knot %d (%s)"
                            % (node_name, next_index, e))
            break
        next_index += 1
        existing = ramp_knot_ports(port) or []

    for knot_port, knot in zip(existing, knots):
        sub = {}
        for parts, p, leaf in walk_ports(knot_port):
            if leaf:
                sub[parts[-1].lower()] = p

        def _write(field, value):
            p = sub.get(field)
            if p is None or value is None:
                return
            _port_write(p, convert_like(_port_value(p), value))

        _write("position", knot.get("pos"))
        value = knot.get("value")
        if "color" in sub:
            if isinstance(value, (int, float)):
                value = [float(value)] * 3   # scalar ramp -> colour ramp
            _write("color", value)
        elif "value" in sub:
            if isinstance(value, (list, tuple)) and value:
                value = sum(float(x) for x in value[:3]) / min(3, len(value))
            _write("value", value)
        _write("bias", knot.get("bias"))

        interp_port = sub.get("interpolation")
        if interp_port is not None:
            canon = (knot.get("interp") or "linear").lower()
            name = CANON_TO_C4D_INTERP.get(canon)
            if name is None:
                name = "linearknot"
                warnings.append("%s: ramp interpolation '%s' has no Cinema "
                                "4D equivalent, used linear"
                                % (node_name, canon))
            try:
                _port_write(interp_port, maxon.InternedId(name))
            except Exception as e:
                warnings.append("%s: could not set ramp interpolation (%s)"
                                % (node_name, e))


def _wrapped_bool(v):
    """Real value of a non-Python boolean wrapper, or None if it cannot be
    read -- None is reported as an unserializable value, which is far
    better than guessing and silently changing how a material renders."""
    for conv in (int, float):
        try:
            return bool(conv(v))
        except (TypeError, ValueError):
            continue
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    return None


def to_jsonable(v):
    """maxon/c4d value -> plain JSON value, or None if not serializable."""
    if isinstance(v, bool) or isinstance(v, int) or isinstance(v, float):
        return v
    if isinstance(v, str):
        return v
    if isinstance(v, maxon.Url):
        try:
            s = v.GetSystemPath()
        except Exception:
            s = None
        if not s:
            s = str(v)  # asset:/// etc.: keep the raw URL rather than drop
        return s or None
    # maxon scalar/string wrappers (maxon.String, maxon.Int32, ...) are not
    # subclasses of the Python types, so isinstance() above misses them.
    tn = type(v).__name__.lower()
    if tn == "string":
        return str(v)
    if tn == "bool":
        # NEVER bool(v) here: on a wrapper object that asks "does this
        # object exist", which is always True, so every checkbox came
        # across ticked. int()/str() consult the actual value instead.
        return _wrapped_bool(v)
    if tn in ("int", "int32", "int64", "uint", "uint32", "uint64"):
        return int(v)
    if tn in ("float", "float32", "float64"):
        return float(v)
    if tn == "internedid":
        # Enum values ("smoothknot", "sRGB"...) are plain ids with no dot,
        # so they must be taken by type rather than by the pattern below.
        return str(v)
    for fields in (("r", "g", "b", "a"), ("r", "g", "b"),
                   ("x", "y", "z", "w"), ("x", "y", "z"), ("x", "y")):
        if all(hasattr(v, f) for f in fields):
            try:
                return [float(getattr(v, f)) for f in fields]
            except Exception:
                break
    # InternedId / Id / enums-as-ids
    s = str(v)
    if re.match(r"^[A-Za-z0-9_.]+$", s) and "." in s:
        return s
    try:
        return float(v)
    except Exception:
        pass
    return None


def convert_like(current, value):
    """Convert a JSON `value` to the type of the port's current value."""
    if isinstance(current, maxon.Url) or (
            isinstance(value, str) and isinstance(current, maxon.Url)):
        return _url_from_path(value)
    if isinstance(current, bool):
        if isinstance(value, (bool, int, float)):
            return bool(value)
        return value  # let the port write fail loudly rather than guess
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return value
    if isinstance(current, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if isinstance(current, str):
        return str(value)
    if type(current).__name__.lower() == "string":
        # maxon.String port: hand back the same wrapper type.
        try:
            return maxon.String(str(value))
        except Exception:
            return str(value)
    t = type(current)
    if isinstance(value, (list, tuple)):
        if len(value) == 3 and hasattr(current, "a"):
            value = list(value) + [1.0]  # RGB -> RGBA: opaque, not invisible
        for n in (len(value), 4, 3, 2):
            try:
                return t(*[float(x) for x in value[:n]])
            except Exception:
                continue
        return value
    try:
        return t(value)
    except Exception:
        return value


# ---------------------------------------------------------------------------
# Export (C4D -> JSON)
# ---------------------------------------------------------------------------

def build_material(mat, warnings):
    """Serialize one Redshift node material into an interchange dict."""
    graph = get_rs_graph(mat)
    if graph is None:
        raise RuntimeError("'%s' has no Redshift node graph. Select a "
                           "Redshift node material." % mat.GetName())

    nodes_json = []
    connections = []
    outputs = {}

    all_nodes = graph_nodes(graph)
    if not all_nodes:
        raise RuntimeError("Could not enumerate graph nodes of '%s'."
                           % mat.GetName())

    keys = {}       # str(GetId()) -> key
    out_node = None
    exportable = []
    for node in all_nodes:
        aid = node_asset_id(node)
        if aid is None:
            # Wiring and decoration, not shading: reroutes and type
            # converters are traced through when resolving connections,
            # groups are flattened, scaffolds are just backdrops. None of
            # them is a loss, so none of them is worth a warning.
            kind = node_kind(node)
            if kind not in ("reroute", "type", "group", "scaffold", ""):
                warnings.append("node of unknown kind '%s' skipped (%s)"
                                % (kind, str(_try_call(node, "GetId"))))
            continue
        if aid == RS_OUTPUT_ID or aid.endswith("node.output"):
            out_node = node
            continue
        exportable.append((node, aid))

    if not exportable and len(all_nodes) > (1 if out_node is not None
                                            else 0):
        raise RuntimeError("could not identify any shader node in the "
                           "graph (asset id API mismatch?) -- please "
                           "report this with your C4D/Redshift versions")

    got_any_connection = [False]

    for i, (node, aid) in enumerate(exportable):
        key = "n%d" % i
        keys[node_uid(node)] = key
        cls = aid.split(".")[-1]
        params = {}
        unserializable = []
        inputs = _try_call(node, "GetInputs")
        if inputs is not None and not _is_null(inputs):
            ramp_roots = set()
            for parts, port, is_leaf in walk_ports(inputs):
                if parts[0] in ramp_roots:
                    continue  # already carried inside its ramp
                if not is_leaf and ramp_knot_ports(port) is not None:
                    ramp_roots.add(parts[0])
                    params[".".join(parts).lower()] = export_ramp(
                        port, node_display_name(node), warnings)
                    continue
                if (len(parts) > 1 and _TEX_GROUP_RE.match(parts[0])
                        and parts[-1].lower() not in _TEX_CHILDREN_KEEP):
                    continue
                dotted = ".".join(parts)
                srcs = input_sources(port)
                if srcs:
                    got_any_connection[0] = True
                    for src_port in srcs:
                        real, last = trace_source(src_port)
                        if real is None:
                            # Wiring carrying a constant (a group input
                            # exposing a value): keep the value, which is
                            # what the material actually renders with.
                            val = to_jsonable(_port_value(last)) \
                                if last is not None else None
                            if val is not None:
                                params[dotted.lower()] = val
                            else:
                                warnings.append(
                                    "%s: input '%s' comes through wiring "
                                    "with nothing behind it"
                                    % (node_display_name(node), dotted))
                            continue
                        src_node = _owning_node(real)
                        if src_node is None:
                            continue
                        connections.append({
                            "_dst_gid": node_uid(node),
                            "_src_gid": node_uid(src_node),
                            "src_port": _src_port_dotted(real),
                            "dst_port": dotted.lower(),
                        })
                    continue
                if not is_leaf:
                    continue
                raw = _port_value(port)
                val = to_jsonable(raw)
                if val is None:
                    if raw is not None:
                        unserializable.append(dotted)
                    continue
                params[dotted.lower()] = val
        nname = node_display_name(node)
        if unserializable:
            shown = ", ".join(unserializable[:6])
            if len(unserializable) > 6:
                shown += ", ... (%d total)" % len(unserializable)
            warnings.append("%s: value(s) not serializable, skipped: %s"
                            % (nname, shown))
        nodes_json.append({
            "key": key,
            "class": cls,
            "c4d_id": aid,
            "name": nname,
            "params": params,
        })

    # Resolve node keys on connections now that all keys exist.
    resolved = []
    for c in connections:
        src = keys.get(c.pop("_src_gid"))
        dst_gid = c.pop("_dst_gid")
        dst = keys.get(dst_gid)
        if src is None or dst is None:
            continue
        c["src"], c["dst"] = src, dst
        resolved.append(c)

    if out_node is not None:
        out_inputs = _try_call(out_node, "GetInputs")
        if out_inputs is not None and not _is_null(out_inputs):
            for parts, port, is_leaf in walk_ports(out_inputs):
                srcs = input_sources(port)
                if not srcs:
                    continue
                got_any_connection[0] = True
                slot = parts[-1].lower()
                for role in ("surface", "displacement", "volume",
                             "environment"):
                    if role in slot:
                        real = resolve_source(srcs[0])
                        src_node = _owning_node(real) if real else None
                        if src_node is not None:
                            k = keys.get(node_uid(src_node))
                            if k:
                                outputs[role] = k
                        break
    else:
        warnings.append("no Output node found in the graph")

    if not got_any_connection[0] and len(exportable) > 1:
        _warn_conn_api_once(warnings)

    other = _other_app_classes()
    if other:
        for nd in nodes_json:
            cls = nd["class"].lower()
            if cls not in other and CLASS_ALIASES_OTHER.get(cls) not in other:
                warnings.append("node '%s' (class '%s') does not exist in "
                                "Houdini -- it will be skipped on paste"
                                % (nd["name"], nd["class"]))

    return {
        "name": mat.GetName(),
        "nodes": nodes_json,
        "connections": resolved,
        "outputs": outputs,
    }


def export_materials(mats):
    """Serialize one or more materials into a clipboard payload. A failing
    material is reported and skipped rather than losing the whole copy."""
    warnings = []
    materials = []
    for mat in mats:
        try:
            materials.append(build_material(mat, warnings))
        except Exception as e:
            warnings.append("'%s' was not copied: %s" % (mat.GetName(), e))
    if not materials:
        raise RuntimeError(
            "Nothing could be copied.\n\n"
            + ("\n".join(warnings) if warnings else
               "Select a Redshift node material."))
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "tool_version": TOOL_VERSION,
        "source_app": "c4d",
        "source_version": str(c4d.GetC4DVersion()),
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "materials": materials,
        "warnings": warnings,
    }


def export_material(mat):
    """Single-material convenience wrapper."""
    return export_materials([mat])


def clipboard_materials(data):
    """Materials held in a clipboard payload, tolerating the single
    'material' key written by earlier versions."""
    materials = data.get("materials")
    if materials:
        return materials
    single = data.get("material")
    return [single] if single else []


# ---------------------------------------------------------------------------
# Import (JSON -> C4D)
# ---------------------------------------------------------------------------

def _class_to_asset_id(node_json):
    if node_json.get("c4d_id"):
        return node_json["c4d_id"]
    cls = node_json["class"].lower()
    return RS_NODE_PREFIX + CLASS_ALIASES.get(cls, cls)


def build_c4d_material(mat_json, warnings):
    """Rebuild one material from its interchange dict (not inserted yet).
    Returns (material, nodes_built, connections_wired)."""
    mat = c4d.BaseMaterial(c4d.Mmaterial)
    mat.SetName(mat_json.get("name") or "RS Bridge Material")
    nm = mat.GetNodeMaterialReference()
    if nm is None:
        raise RuntimeError("GetNodeMaterialReference() failed")
    graph = nm.CreateDefaultGraph(maxon.Id(RS_NODESPACE_ID))
    if graph is None or _is_null(graph):
        raise RuntimeError("CreateDefaultGraph() failed -- is Redshift "
                           "the active node space?")

    # Locate default nodes: keep the Output, remove the default material.
    out_node = None
    default_nodes = []
    for node in graph_nodes(graph):
        aid = node_asset_id(node) or ""
        if aid == RS_OUTPUT_ID or aid.endswith("node.output"):
            out_node = node
        else:
            default_nodes.append(node)

    built = {}
    wired = 0
    with graph.BeginTransaction() as txn:
        for node in default_nodes:
            try:
                node.Remove()
            except Exception as e:
                warnings.append("could not remove a default graph node "
                                "(%s) -- it may stay wired to the Output"
                                % e)

        for nd in mat_json["nodes"]:
            aid = _class_to_asset_id(nd)
            node = None
            try:
                node = graph.AddChild(maxon.Id(), maxon.Id(aid),
                                      maxon.DataDictionary())
            except Exception as e:
                warnings.append("AddChild failed for '%s' (%s): %s"
                                % (nd["class"], aid, e))
            if node is None or _is_null(node):
                warnings.append("could not create node '%s' (%s)"
                                % (nd.get("name"), aid))
                continue
            built[nd["key"]] = node
            try:
                node.SetValue("net.maxon.node.base.name",
                              maxon.String(nd.get("name") or nd["class"]))
            except Exception:
                pass

            inputs = _try_call(node, "GetInputs")
            if inputs is None or _is_null(inputs):
                continue
            for pname, pval in nd.get("params", {}).items():
                port = find_port(inputs, pname)
                if port is None:
                    warnings.append("%s: no port matches '%s'"
                                    % (nd.get("name"), pname))
                    continue
                if isinstance(pval, dict) and pval.get("_kind") == RAMP_KIND:
                    import_ramp(port, pval, nd.get("name") or "", warnings)
                    continue
                current = _port_value(port)
                converted = convert_like(current, pval)
                if current is None and isinstance(pval, str) \
                        and pname.endswith(("path", "filename")):
                    converted = _url_from_path(pval)
                if not _port_write(port, converted):
                    warnings.append("%s: could not set '%s' to %r"
                                    % (nd.get("name"), pname, pval))

        for conn in mat_json.get("connections", []):
            src = built.get(conn["src"])
            dst = built.get(conn["dst"])
            if src is None or dst is None:
                warnings.append("connection %s.%s -> %s.%s dropped (its "
                                "node was not created)"
                                % (conn.get("src"), conn.get("src_port"),
                                   conn.get("dst"), conn.get("dst_port")))
                continue
            src_outs = _try_call(src, "GetOutputs")
            dst_ins = _try_call(dst, "GetInputs")
            if src_outs is None or dst_ins is None:
                continue
            wanted = conn.get("src_port") or ""
            src_port = find_port(src_outs, wanted)
            if src_port is None:
                leaves = [(p_parts, p) for p_parts, p, leaf
                          in walk_ports(src_outs) if leaf]
                if leaves:
                    src_port = leaves[0][1]
                    if wanted and len(leaves) > 1:
                        warnings.append(
                            "source port '%s' not found, connected first "
                            "output '%s' instead -- verify this wire"
                            % (wanted, ".".join(leaves[0][0])))
            dst_port = find_port(dst_ins, conn["dst_port"])
            if src_port is None or dst_port is None:
                warnings.append("could not connect %s.%s -> %s.%s"
                                % (conn["src"], conn.get("src_port"),
                                   conn["dst"], conn["dst_port"]))
                continue
            try:
                src_port.Connect(dst_port)
                wired += 1
            except Exception as e:
                warnings.append("Connect failed %s -> %s: %s"
                                % (conn.get("src_port"), conn["dst_port"], e))

        if out_node is not None:
            out_ins = _try_call(out_node, "GetInputs")
            outputs_json = mat_json.get("outputs") or {}
            if not outputs_json:
                warnings.append("clipboard carries no output wiring -- "
                                "nothing is connected to the Output node")
            for role, key in outputs_json.items():
                src = built.get(key)
                if src is None or out_ins is None:
                    warnings.append("could not wire material output '%s' "
                                    "(its source node was not created)"
                                    % role)
                    continue
                dst_port = None
                for parts, port, _leaf in walk_ports(out_ins):
                    if role in parts[-1].lower():
                        dst_port = port
                        break
                src_outs = _try_call(src, "GetOutputs")
                leaves = ([p for _, p, leaf in walk_ports(src_outs) if leaf]
                          if src_outs is not None else [])
                if dst_port is None or not leaves:
                    warnings.append("could not wire material output '%s'"
                                    % role)
                    continue
                try:
                    leaves[0].Connect(dst_port)
                except Exception as e:
                    warnings.append("output connect '%s' failed: %s"
                                    % (role, e))
        else:
            warnings.append("default graph has no Output node?!")

        txn.Commit()

    return mat, len(built), wired


def import_materials(data, doc):
    """Rebuild every material held in the clipboard into `doc`."""
    warnings = list(data.get("warnings", []))
    materials_json = clipboard_materials(data)
    if not materials_json:
        raise RuntimeError("The clipboard holds no material.")

    built, stats = [], {"nodes": 0, "nodes_total": 0,
                        "connections": 0, "connections_total": 0,
                        "materials": 0,
                        "materials_total": len(materials_json)}
    doc.StartUndo()
    try:
        for mat_json in materials_json:
            stats["nodes_total"] += len(mat_json.get("nodes", []))
            stats["connections_total"] += len(mat_json.get("connections",
                                                           []))
            try:
                mat, n_nodes, n_wires = build_c4d_material(mat_json,
                                                           warnings)
            except Exception as e:
                warnings.append("'%s' could not be pasted: %s"
                                % (mat_json.get("name"), e))
                continue
            doc.InsertMaterial(mat)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, mat)
            built.append(mat)
            stats["nodes"] += n_nodes
            stats["connections"] += n_wires
            stats["materials"] += 1
    finally:
        doc.EndUndo()
        c4d.EventAdd()

    if not built:
        raise RuntimeError("No material could be rebuilt.\n\n"
                           + "\n".join(warnings[-5:]))
    return built, warnings, stats


def import_material(data, doc):
    """Single-material convenience wrapper."""
    mats, warnings, stats = import_materials(data, doc)
    return mats[0], warnings, stats


# ---------------------------------------------------------------------------
# Entry points used by the wrapper scripts
# ---------------------------------------------------------------------------

def run_copy():
    try:
        dump_node_classes(verbose=False)
    except Exception:
        pass  # inventory is a nice-to-have; never block the copy
    doc = c4d.documents.GetActiveDocument()
    mats = _try_call(doc, "GetActiveMaterials") or []
    if not mats:
        single = doc.GetActiveMaterial()
        mats = [single] if single is not None else []
    if not mats:
        gui.MessageDialog("Select one or more Redshift node materials "
                          "first.")
        return
    try:
        data = export_materials(mats)
    except Exception as e:
        traceback.print_exc()
        gui.MessageDialog("Copy failed:\n%s\n\nDetails in the Console." % e)
        return
    write_clip(data)

    copied = data["materials"]
    nodes = sum(len(m["nodes"]) for m in copied)
    wires = sum(len(m["connections"]) for m in copied)
    names = ", ".join(m["name"] for m in copied[:4])
    if len(copied) > 4:
        names += ", ... (%d total)" % len(copied)
    _log("Copied %d material(s) [%s]: %d nodes, %d connections -> %s"
         % (len(copied), names, nodes, wires, CLIP_FILE))
    for w in data["warnings"]:
        _log("  warning: %s" % w)
    gui.MessageDialog(
        "Copied to the bridge clipboard.\n\n"
        "Materials: %d (%s)\nNodes: %d\nConnections: %d\nWarnings: %d%s"
        % (len(copied), names, nodes, wires, len(data["warnings"]),
           "\n\nSee the Console for warning details."
           if data["warnings"] else ""))


def run_paste():
    doc = c4d.documents.GetActiveDocument()
    try:
        data = read_clip()
        mats, warnings, stats = import_materials(data, doc)
    except Exception as e:
        traceback.print_exc()
        gui.MessageDialog("Paste failed:\n%s\n\nDetails in the Console." % e)
        return
    names = ", ".join(m.GetName() for m in mats[:4])
    if len(mats) > 4:
        names += ", ... (%d total)" % len(mats)
    _log("Pasted %d material(s) [%s] (from %s, bridge %s)"
         % (len(mats), names, data.get("source_app"),
            data.get("tool_version", "?")))
    for w in warnings:
        _log("  warning: %s" % w)
    gui.MessageDialog(
        "Pasted from %s.\n\n"
        "Materials: %d of %d (%s)\nNodes: %d of %d\nConnections: %d of %d\n"
        "Warnings: %d%s"
        % (data.get("source_app", "?"),
           stats["materials"], stats["materials_total"], names,
           stats["nodes"], stats["nodes_total"],
           stats["connections"], stats["connections_total"], len(warnings),
           "\n\nSee the Console for warning details." if warnings else ""))
