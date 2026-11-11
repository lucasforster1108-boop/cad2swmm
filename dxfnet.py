#!/usr/bin/env python3
"""
dxfnet — the shared DXF network-extraction core behind cad2swmm and cad2epanet.

Both converters do the same first half of the job: open a DXF, walk the node
and pipe layers, snap pipe endpoints onto nodes, and read the DN / elevation
labels scattered around the geometry. That half lives here, once. What differs
per target model — what a node *means* (manhole invert vs junction elevation
and demand), which node is the outlet or the source, and how the .inp is
written — stays in cad2swmm.py / cad2epanet.py.

Nothing in this module knows about SWMM or EPANET sections; nodes are treated
as opaque objects with .x / .y (and .name once named), links as node pairs.
"""

import math
import re
from dataclasses import dataclass, field

# DN300 / D300 / d300 / Φ300 / "300mm" -> capture group holds millimetres
DIAM_RE = re.compile(r"(?:DN|D|Φ|φ|d)\s*(\d{2,4})|(\d{2,4})\s*mm", re.IGNORECASE)


@dataclass
class Link:
    """One pipe segment between two nodes (a SWMM conduit, an EPANET pipe)."""
    name: str
    a: object  # node (converter-specific dataclass)
    b: object  # node
    length: float  # metres, after scaling
    diameter: float | None = None  # metres
    mid: tuple = field(default=(0.0, 0.0))  # drawing units, for text matching


def dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def attribs_of(insert):
    out = {}
    for a in insert.attribs:
        out[a.dxf.tag.strip().upper()] = a.dxf.text.strip()
    return out


def first_float(*vals):
    for v in vals:
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def layer_match(layer, wanted):
    layer = (layer or "").upper()
    return any(w.upper() in layer or layer in w.upper() for w in wanted)


def collect_texts(msp):
    """All TEXT/MTEXT as (x, y, string)."""
    texts = []
    for e in msp:
        if e.dxftype() == "TEXT":
            texts.append((e.dxf.insert.x, e.dxf.insert.y, e.dxf.text))
        elif e.dxftype() == "MTEXT":
            texts.append((e.dxf.insert.x, e.dxf.insert.y, e.text))
    return texts


class NodeIndex:
    """Node bookkeeping shared by both converters: the node list, unique
    J1/J2... auto names, and finding an existing node within snap distance
    (so duplicate entities and pipe endpoints merge into one node).

    What a merge does with the incoming node's *meaning* (invert, demand,
    kind...) is model-specific and stays in each converter's add_node.
    """

    def __init__(self, snap):
        self.snap = snap
        self.nodes: list = []
        self.used_names: set = set()
        self._counter = 0

    def auto_name(self):
        while True:
            self._counter += 1
            n = f"J{self._counter}"
            if n not in self.used_names:
                return n

    def claim(self, name):
        self.used_names.add(name)

    def unique_name(self, name):
        """Name for a newly created node: auto J<n> when unnamed, suffixed
        when an explicit name is already taken."""
        if name is None:
            return self.auto_name()
        if name in self.used_names:
            name = f"{name}_{self.auto_name()}"
        self.used_names.add(name)
        return name

    def find_at(self, x, y):
        for n in self.nodes:
            if dist((x, y), (n.x, n.y)) <= self.snap:
                return n
        return None

    def register(self, node):
        self.nodes.append(node)
        return node


def node_candidates(msp, node_layers):
    """Yield (entity_type, x, y, attribs) for every node entity on the node
    layers: INSERT blocks (attribs = attribute dict), POINTs and CIRCLEs
    (attribs = None). What the attributes mean is the converter's business."""
    for e in msp:
        if not layer_match(e.dxf.layer, node_layers):
            continue
        t = e.dxftype()
        if t == "INSERT":
            yield t, e.dxf.insert.x, e.dxf.insert.y, attribs_of(e)
        elif t == "POINT":
            yield t, e.dxf.location.x, e.dxf.location.y, None
        elif t == "CIRCLE":
            yield t, e.dxf.center.x, e.dxf.center.y, None


def nearest_node(nodes, p, tol):
    best, bestd = None, tol
    for n in nodes:
        d = dist(p, (n.x, n.y))
        if d < bestd:
            best, bestd = n, d
    return best


def build_links(msp, pipe_layers, nodes, add_node, snap, scale, prefix, warnings):
    """Extract pipe segments (LINE / LWPOLYLINE / POLYLINE on the pipe layers)
    as Links between nodes. Endpoints snap to the nearest node within `snap`;
    unsnapped endpoints create auto nodes via add_node(x, y, auto=True) so no
    pipe is ever silently dropped. `prefix` is the link naming prefix
    ("C" for SWMM conduits, "P" for EPANET pipes)."""
    links: list[Link] = []

    def node_at(p):
        n = nearest_node(nodes, p, snap)
        if n is None:
            n = add_node(p[0], p[1], auto=True)
            warnings.append(f"pipe endpoint at ({p[0]:.1f},{p[1]:.1f}) had no node within "
                            f"--snap; auto node {n.name} created")
        return n

    def add_segment(p, q):
        if dist(p, q) < 1e-9:
            return
        a, b = node_at(p), node_at(q)
        if a is b:
            warnings.append("a pipe segment snapped both ends to the same node; skipped")
            return
        length = dist(p, q) * scale
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        links.append(Link(f"{prefix}{len(links) + 1}", a, b, length, None, mid))

    for e in msp:
        if not layer_match(e.dxf.layer, pipe_layers):
            continue
        t = e.dxftype()
        if t == "LINE":
            add_segment((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))
        elif t in ("LWPOLYLINE", "POLYLINE"):
            pts = [(v[0], v[1]) for v in e.get_points()] if t == "LWPOLYLINE" \
                else [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if e.closed and len(pts) > 2:
                pts.append(pts[0])
            for p, q in zip(pts, pts[1:]):
                add_segment(p, q)
    return links


def assign_diameters(links, texts, scale, default_diameter, warnings, noun="pipe"):
    """Match each link to the nearest DN label (its midpoint is the anchor).
    A label counts only if it sits within 3/4 of the link's length; links
    without a plausible label get the default diameter and a warning."""
    labels = []
    for (tx, ty, s) in texts:
        m = DIAM_RE.search(s or "")
        if m:
            labels.append((tx, ty, int(m.group(1) or m.group(2)) / 1000.0))
    for link in links:
        best, bestd = None, None
        for (tx, ty, d) in labels:
            dd = dist((tx, ty), link.mid)
            if bestd is None or dd < bestd:
                best, bestd = d, dd
        if best is not None and bestd <= (link.length / scale) * 0.75:
            link.diameter = best
        else:
            link.diameter = default_diameter
            warnings.append(f"{noun} {link.name}: no diameter label found, "
                            f"default {default_diameter} m used")


def nearest_text_value(texts, x, y, radius, regex):
    """Nearest text within `radius` matching `regex` around (x, y); returns
    its first non-empty capture group as a float, or None. Used for the
    "IL=12.34" / "EL=52.30" style elevation labels near a node."""
    best, bestd = None, radius
    for (tx, ty, s) in texts:
        m = regex.search(s or "")
        if not m:
            continue
        val = next((g for g in m.groups() if g is not None), None)
        if val is None:
            continue
        d = dist((tx, ty), (x, y))
        if d < bestd:
            best, bestd = float(val), d
    return best
