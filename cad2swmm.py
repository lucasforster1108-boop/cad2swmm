#!/usr/bin/env python3
"""
cad2swmm — Convert a CAD drainage network (DXF) into a runnable EPA SWMM model (.inp).

Why this exists: every SWMM workflow tool on GitHub starts from GIS data.
Nobody bridges the format engineers actually draw in — CAD. This script is that bridge.

Input conventions (all configurable, see --help):
  * Junctions/manholes : INSERT blocks, POINTs or CIRCLEs on the node layers.
                          Node name from block attribute ID / NAME / 编号, else auto (J1, J2 ...).
                          Invert elevation from block attribute INV / IL / ELEV, else an
                          "IL=12.34" style TEXT near the node, else --default-invert.
  * Pipes               : LINE / LWPOLYLINE on the pipe layers. Polyline interior
                          vertices become intermediate nodes automatically.
  * Pipe diameter       : TEXT / MTEXT near the pipe midpoint: DN300, D300, d300,
                          Φ300 or "300mm" -> 0.300 m. Fallback: --default-diameter.
  * Outfall             : node with block attribute TYPE=OUTFALL, or --outfall NAME,
                          else the node with the lowest invert elevation.

Endpoints are snapped to the nearest node within --snap (drawing units);
unsnapped endpoints create auto nodes so no pipe is ever silently dropped.
Flow direction is set from higher invert to lower invert.

Output: a complete .inp ([OPTIONS], [JUNCTIONS], [OUTFALLS], [CONDUITS],
[XSECTIONS], [COORDINATES], [MAP], [REPORT]) that opens and runs in EPA SWMM 5.
With --design-flow LPS a constant inflow is added at the most upstream junction
so the model produces real routed flow, not just an empty run.

Pipeline: with --pipeline (or --run / --report) the same script keeps going —
it runs the .inp in the real EPA SWMM engine (via pyswmm) and turns the .rpt
into a Chinese check report (Markdown) using the vendored swmm_report_cn
package in this repo:  DXF -> .inp -> .rpt -> 校核报告.md.  An existing .inp
or .rpt can also be passed as input to use just the later stages.

Requires: ezdxf  (pip install ezdxf);  pyswmm for --run/--pipeline.
License: MIT
"""

import argparse
import math
import os
import re
import shutil
import sys
from dataclasses import dataclass, field

import ezdxf

DIAM_RE = re.compile(r"(?:DN|D|Φ|φ|d)\s*(\d{2,4})|(\d{2,4})\s*mm", re.IGNORECASE)
INVERT_RE = re.compile(r"(?:IL|INV|INVERT|管底|标高)\s*[=:：]?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)

DEFAULT_NODE_LAYERS = ["JUNCTION", "MANHOLE", "NODE", "检查井", "井"]
DEFAULT_PIPE_LAYERS = ["PIPE", "CONDUIT", "SEWER", "管线", "管道", "排水"]


@dataclass
class Node:
    name: str
    x: float
    y: float
    invert: float | None = None
    is_outfall: bool = False
    auto: bool = False


@dataclass
class Conduit:
    name: str
    a: Node
    b: Node
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


def build_nodes(msp, node_layers, texts, args, warnings):
    nodes: list[Node] = []
    used_names = set()
    counter = [0]

    def auto_name():
        while True:
            counter[0] += 1
            n = f"J{counter[0]}"
            if n not in used_names:
                return n

    def add_node(x, y, name=None, invert=None, is_outfall=False, auto=False):
        for n in nodes:  # merge duplicates within snap tolerance
            if dist((x, y), (n.x, n.y)) <= args.snap:
                if name and n.auto:
                    n.name, n.auto = name, False
                    used_names.add(name)
                if invert is not None and n.invert is None:
                    n.invert = invert
                n.is_outfall = n.is_outfall or is_outfall
                return n
        if not name:
            name = auto_name()
        else:
            if name in used_names:
                name = f"{name}_{auto_name()}"
            used_names.add(name)
        node = Node(name, x, y, invert, is_outfall, auto)
        nodes.append(node)
        return node

    for e in msp:
        if not layer_match(e.dxf.layer, node_layers):
            continue
        t = e.dxftype()
        if t == "INSERT":
            at = attribs_of(e)
            name = at.get("ID") or at.get("NAME") or at.get("编号")
            invert = first_float(at.get("INV"), at.get("IL"), at.get("ELEV"))
            is_out = (at.get("TYPE", "").upper() == "OUTFALL") or (
                name and args.outfall and name.upper() == args.outfall.upper()
            )
            add_node(e.dxf.insert.x, e.dxf.insert.y, name, invert, bool(is_out))
        elif t == "POINT":
            add_node(e.dxf.location.x, e.dxf.location.y)
        elif t == "CIRCLE":
            add_node(e.dxf.center.x, e.dxf.center.y)

    # invert elevations from nearby "IL=..." texts
    for n in nodes:
        if n.invert is not None:
            continue
        best, bestd = None, args.text_radius
        for (tx, ty, s) in texts:
            m = INVERT_RE.search(s or "")
            if m and dist((tx, ty), (n.x, n.y)) < bestd:
                best, bestd = float(m.group(1)), dist((tx, ty), (n.x, n.y))
        if best is not None:
            n.invert = best
    for n in nodes:
        if n.invert is None:
            n.invert = args.default_invert
            warnings.append(f"node {n.name}: no invert found, default {args.default_invert} m used")
    return nodes, add_node


def nearest_node(nodes, p, tol):
    best, bestd = None, tol
    for n in nodes:
        d = dist(p, (n.x, n.y))
        if d < bestd:
            best, bestd = n, d
    return best


def build_conduits(msp, pipe_layers, nodes, add_node, args, warnings):
    conduits: list[Conduit] = []

    def node_at(p):
        n = nearest_node(nodes, p, args.snap)
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
        length = dist(p, q) * args.scale
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        conduits.append(Conduit(f"C{len(conduits) + 1}", a, b, length, None, mid))

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
    return conduits


def assign_diameters(conduits, texts, args, warnings):
    labels = []
    for (tx, ty, s) in texts:
        m = DIAM_RE.search(s or "")
        if m:
            labels.append((tx, ty, int(m.group(1) or m.group(2)) / 1000.0))
    for c in conduits:
        best, bestd = None, None
        for (tx, ty, d) in labels:
            dd = dist((tx, ty), c.mid)
            if bestd is None or dd < bestd:
                best, bestd = d, dd
        # accept the nearest label only if it sits within half the pipe length (drawing units)
        if best is not None and bestd <= (c.length / args.scale) * 0.75:
            c.diameter = best
        else:
            c.diameter = args.default_diameter
            warnings.append(f"conduit {c.name}: no diameter label found, "
                            f"default {args.default_diameter} m used")


def pick_outfall(nodes, args, warnings):
    marked = [n for n in nodes if n.is_outfall]
    if args.outfall:
        for n in nodes:
            if n.name.upper() == args.outfall.upper():
                return n
        warnings.append(f"--outfall {args.outfall} not found; falling back to lowest node")
    if marked:
        return marked[0]
    return min(nodes, key=lambda n: n.invert)


def write_inp(nodes, conduits, outfall, args):
    junctions = [n for n in nodes if n is not outfall]
    max_depth = {n.name: args.default_rim - n.invert for n in nodes}

    def ordered(c):  # flow from higher invert to lower invert
        return (c.a, c.b) if c.a.invert >= c.b.invert else (c.b, c.a)

    L = []
    L.append("[TITLE]")
    L.append(f";;Generated by cad2swmm from {args.input}")
    L.append("")
    L.append("[OPTIONS]")
    L.append("FLOW_UNITS           LPS")
    L.append("INFILTRATION          HORTON")
    L.append("FLOW_ROUTING          DYNWAVE")
    L.append("START_DATE            01/01/2026")
    L.append("START_TIME            00:00:00")
    L.append("END_DATE              01/01/2026")
    L.append("END_TIME              06:00:00")
    L.append("REPORT_STEP           00:05:00")
    L.append("ROUTING_STEP          00:00:30")
    L.append("ALLOW_PONDING         NO")
    L.append("MIN_SLOPE             0")
    L.append("")
    L.append("[EVAPORATION]")
    L.append(";;Type       Parameters")
    L.append("CONSTANT     0.0")
    L.append("")
    L.append("[JUNCTIONS]")
    L.append(";;Name           InvertElev   MaxDepth     InitDepth    SurchargeDepth  PondedArea")
    for n in junctions:
        L.append(f"{n.name:<16} {n.invert:<12.3f} {max_depth[n.name]:<12.3f} 0            0               0")
    L.append("")
    L.append("[OUTFALLS]")
    L.append(";;Name           InvertElev   Type         StageOrTimeseries   TideGate")
    L.append(f"{outfall.name:<16} {outfall.invert:<12.3f} FREE                         NO")
    L.append("")
    if args.design_flow > 0 and junctions:
        upstream = max(junctions, key=lambda n: n.invert)
        L.append("[INFLOWS]")
        L.append(";;Node           Constituent      TimeSeries       Type     Mfactor  Sfactor  Baseline  Pattern")
        L.append(f'{upstream.name:<16} FLOW             ""               FLOW     1.0      1.0      {args.design_flow:g}')
        L.append("")
    L.append("[CONDUITS]")
    L.append(";;Name           FromNode         ToNode           Length     Roughness    InOffset   OutOffset  InitFlow   MaxFlow")
    for c in conduits:
        a, b = ordered(c)
        L.append(f"{c.name:<16} {a.name:<16} {b.name:<16} {c.length:<10.2f} {args.roughness:<12} 0          0          0          0")
    L.append("")
    L.append("[XSECTIONS]")
    L.append(";;Link           Shape            Geom1            Geom2      Geom3      Geom4      Barrels")
    for c in conduits:
        L.append(f"{c.name:<16} CIRCULAR         {c.diameter:<16.3f} 0          0          0          1")
    L.append("")
    L.append("[COORDINATES]")
    L.append(";;Node           X-Coord          Y-Coord")
    for n in nodes:
        L.append(f"{n.name:<16} {n.x * args.scale:<16.2f} {n.y * args.scale:.2f}")
    L.append("")
    L.append("[MAP]")
    L.append(f"DIMENSIONS       0.00 0.00 {max(n.x for n in nodes) * args.scale:.1f} {max(n.y for n in nodes) * args.scale:.1f}")
    L.append("Units            Meters")
    L.append("")
    L.append("[REPORT]")
    L.append("INPUT            NO")
    L.append("CONTROLS         NO")
    L.append("SUBCATCHMENTS    NONE")
    L.append("NODES            ALL")
    L.append("LINKS            ALL")
    return "\n".join(L) + "\n"


def run_simulation(inp_path):
    """Run inp_path in the EPA SWMM engine via pyswmm; return the .rpt path.

    pyswmm writes the .rpt (and binary .out) next to the .inp, same stem.
    Raises RuntimeError with a readable message on any failure.
    """
    try:
        from pyswmm import Simulation
    except ImportError:
        raise RuntimeError("pyswmm is not installed — pip install pyswmm "
                           "(needed for --run / --pipeline)")
    with Simulation(inp_path) as sim:
        for _ in sim:
            pass
    rpt_path = os.path.splitext(inp_path)[0] + ".rpt"
    if not os.path.exists(rpt_path):
        raise RuntimeError(f"simulation produced no report file (expected {rpt_path})")
    with open(rpt_path, encoding="utf-8", errors="replace") as f:
        errors = [ln.strip() for ln in f if ln.startswith("ERROR")]
    if errors:
        raise RuntimeError("SWMM reported errors:\n    " + "\n    ".join(errors[:5]))
    return rpt_path


def make_report(rpt_path, inp_path, report_path):
    """Generate the Chinese check report (.md) for a .rpt.

    Uses the vendored swmm_report_cn package that ships in this repo
    (swmm_report_cn/, MIT, zero third-party dependencies).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from swmm_report_cn import generate_report, parse_inp, parse_rpt

    data = parse_rpt(rpt_path)
    inp_info = parse_inp(inp_path) if inp_path and os.path.exists(inp_path) else {}
    md = generate_report(data, inp_info=inp_info)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    return report_path


def relocate(outdir, path):
    """Move a run product (and its .out sibling) into outdir; return its new path."""
    os.makedirs(outdir, exist_ok=True)
    if os.path.dirname(os.path.abspath(path)) == os.path.abspath(outdir):
        return path
    new_path = os.path.join(outdir, os.path.basename(path))
    shutil.move(path, new_path)
    out_sibling = os.path.splitext(path)[0] + ".out"
    if os.path.exists(out_sibling):
        shutil.move(out_sibling, os.path.join(outdir, os.path.basename(out_sibling)))
    return new_path


def resolve_report_path(args, inp_path, rpt_path):
    if args.report_output:
        return args.report_output
    stem = os.path.splitext(os.path.basename(inp_path))[0]
    d = args.outdir or os.path.dirname(rpt_path)
    name = stem + "_校核报告.md"
    return os.path.join(d, name) if d else name


def finish_pipeline(args, inp_path):
    """Shared pipeline tail: optionally run the model, optionally write the report."""
    rpt_path = None
    if args.run:
        try:
            rpt_path = run_simulation(inp_path)
        except Exception as e:
            print(f"error: simulation failed: {e}", file=sys.stderr)
            return 1
        print(f"    ran in the EPA SWMM engine -> {rpt_path}")
        if args.outdir:
            rpt_path = relocate(args.outdir, rpt_path)
    if args.report:
        if rpt_path is None:
            cand = os.path.splitext(inp_path)[0] + ".rpt"
            if not os.path.exists(cand):
                print("error: --report needs a .rpt — add --run (or --pipeline), "
                      "or put an existing .rpt next to the .inp", file=sys.stderr)
                return 1
            rpt_path = cand
            print(f"    using existing report file {rpt_path}")
        report_path = resolve_report_path(args, inp_path, rpt_path)
        try:
            make_report(rpt_path, inp_path, report_path)
        except Exception as e:
            print(f"error: report generation failed: {e}", file=sys.stderr)
            return 1
        print(f"    check report -> {report_path}")
    return 0


def report_only(args):
    """Input is an existing .rpt: just generate the Chinese check report."""
    if not os.path.exists(args.input):
        print(f"error: cannot read {args.input}", file=sys.stderr)
        return 1
    inp_sibling = os.path.splitext(args.input)[0] + ".inp"
    stem = os.path.splitext(os.path.basename(args.input))[0]
    if args.report_output:
        report_path = args.report_output
    else:
        d = args.outdir or os.path.dirname(args.input)
        name = stem + "_校核报告.md"
        report_path = os.path.join(d, name) if d else name
    try:
        make_report(args.input, inp_sibling, report_path)
    except Exception as e:
        print(f"error: report generation failed: {e}", file=sys.stderr)
        return 1
    print(f"OK  {args.input} -> {report_path}")
    print("    Chinese check report generated from the existing .rpt (no conversion, no run)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert a CAD (DXF) drainage network to a SWMM .inp model.")
    ap.add_argument("input", help="input .dxf file (export DWG to DXF first if needed); "
                                  "an existing .inp (use with --run/--report) or .rpt (report only) also works")
    ap.add_argument("-o", "--output", default=None, help="output .inp path (default: input name with .inp)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="drawing-unit -> metre factor (1.0 = drawing already in metres, 0.001 = millimetres)")
    ap.add_argument("--snap", type=float, default=2.0, help="endpoint snap tolerance, drawing units")
    ap.add_argument("--text-radius", type=float, default=10.0, help="search radius for IL= texts, drawing units")
    ap.add_argument("--node-layers", default=",".join(DEFAULT_NODE_LAYERS))
    ap.add_argument("--pipe-layers", default=",".join(DEFAULT_PIPE_LAYERS))
    ap.add_argument("--default-diameter", type=float, default=0.3, help="metres, when no DN label is found")
    ap.add_argument("--default-invert", type=float, default=0.0, help="metres, when no invert is found")
    ap.add_argument("--default-rim", type=float, default=5.0,
                    help="rim/ground elevation used to derive MaxDepth = rim - invert (only invert + 5 m by default if rim < invert)")
    ap.add_argument("--roughness", type=float, default=0.013, help="Manning's n (0.013 = concrete)")
    ap.add_argument("--outfall", default=None, help="name of the outfall node")
    ap.add_argument("--design-flow", type=float, default=0.0,
                    help="optional constant inflow (LPS) at the most upstream junction, for a smoke-test run")
    ap.add_argument("--run", action="store_true",
                    help="after conversion, run the .inp in the EPA SWMM engine (pyswmm), producing a .rpt")
    ap.add_argument("--report", action="store_true",
                    help="generate a Chinese check report (.md) from the .rpt (vendored swmm_report_cn); "
                         "uses the .rpt from --run, an existing .rpt next to a .inp input, or a .rpt input directly")
    ap.add_argument("--pipeline", action="store_true",
                    help="full pipeline in one go: DXF -> .inp -> run -> Chinese check report (implies --run --report)")
    ap.add_argument("--outdir", default=None,
                    help="directory for pipeline products (.inp unless -o points elsewhere, plus .rpt and the report)")
    ap.add_argument("--report-output", default=None, help="explicit path for the check report .md")
    args = ap.parse_args(argv)
    if args.pipeline:
        args.run = args.report = True
    ext = os.path.splitext(args.input)[1].lower()
    if ext == ".rpt":
        return report_only(args)
    if ext == ".inp":
        if not (args.run or args.report):
            print("error: input is already a .inp — nothing to convert; add --run and/or --report",
                  file=sys.stderr)
            return 1
        if not os.path.exists(args.input):
            print(f"error: cannot read {args.input}", file=sys.stderr)
            return 1
        print(f"OK  {args.input} (existing model, conversion skipped)")
        return finish_pipeline(args, args.input)
    if ext != ".dxf":
        print(f"error: unsupported input {args.input} (expected .dxf, .inp or .rpt)", file=sys.stderr)
        return 1
    if args.output is None and args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(args.input))[0]
        args.output = os.path.join(args.outdir, stem + ".inp")
    args.output = args.output or args.input.rsplit(".", 1)[0] + ".inp"
    # sane MaxDepth even when a user supplies inverts above the rim default
    args.default_rim = max(args.default_rim, args.default_invert + 5.0)

    try:
        doc = ezdxf.readfile(args.input)
    except Exception as e:
        print(f"error: cannot read {args.input}: {e}", file=sys.stderr)
        return 1
    msp = doc.modelspace()
    warnings: list[str] = []
    texts = collect_texts(msp)
    nodes, add_node = build_nodes(msp, args.node_layers.split(","), texts, args, warnings)
    if not nodes:
        print("error: no nodes found — check --node-layers against your drawing", file=sys.stderr)
        return 1
    conduits = build_conduits(msp, args.pipe_layers.split(","), nodes, add_node, args, warnings)
    if not conduits:
        print("error: no pipes found — check --pipe-layers against your drawing", file=sys.stderr)
        return 1
    assign_diameters(conduits, texts, args, warnings)
    outfall = pick_outfall(nodes, args, warnings)
    args.default_rim = max([args.default_rim] + [n.invert + 1.0 for n in nodes])

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(write_inp(nodes, conduits, outfall, args))

    total_len = sum(c.length for c in conduits)
    print(f"OK  {args.input} -> {args.output}")
    print(f"    nodes: {len(nodes)} (junctions {len(nodes) - 1} + outfall {outfall.name})")
    print(f"    conduits: {len(conduits)}, total length {total_len:.1f} m")
    for w in warnings:
        print(f"    warning: {w}")
    return finish_pipeline(args, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
