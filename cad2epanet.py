#!/usr/bin/env python3
"""
cad2epanet — Convert a CAD water-supply network (DXF) into a runnable EPANET model (.inp).

Why this exists: the EPANET workflow tools on GitHub start from GIS data or
hand-built network files. Nobody bridges the format engineers actually draw
in — CAD. This script is that bridge. It is the water-supply sibling of
cad2swmm (which does the same job for drainage / SWMM), and since the two
were merged it lives in the cad2swmm repo: both converters share the
DXF-reading core in dxfnet.py, and each keeps only its own model's
semantics and .inp layout.

Input conventions (all configurable, see --help):
  * Nodes (junctions)   : INSERT blocks, POINTs or CIRCLEs on the node layers.
                          Node name from block attribute ID / NAME / 编号, else auto (J1, J2 ...).
                          Ground elevation from block attribute ELEV / EL / INV / IL, else an
                          "EL=52.30" style TEXT near the node, else --default-elevation.
                          Base demand (L/s) from block attribute DEMAND, else 0.
  * Source (reservoir)  : node with block attribute TYPE=RESERVOIR, or --reservoir NAME,
                          else the node with the highest ground elevation.
                          Total head from block attribute HEAD, else that node's
                          elevation + --source-head.
  * Tank                : node with block attribute TYPE=TANK becomes a [TANKS] entry
                          (levels/diameter from --tank-* options).
  * Pipes               : LINE / LWPOLYLINE on the pipe layers. Polyline interior
                          vertices become intermediate nodes automatically.
  * Pipe diameter       : TEXT / MTEXT near the pipe midpoint: DN300, D300, d300,
                          Φ300 or "300mm" -> 300 mm. Fallback: --default-diameter.

Endpoints are snapped to the nearest node within --snap (drawing units);
unsnapped endpoints create auto nodes so no pipe is ever silently dropped.
Water supply is pressurised flow: pipes carry flow either way and EPANET
decides the direction from the hydraulics, so — unlike drainage — nothing
here is oriented by elevation.

Output: a complete EPANET 2.2 .inp ([TITLE], [JUNCTIONS], [RESERVOIRS],
[TANKS], [PIPES], [COORDINATES], [OPTIONS] with Units LPS / Headloss H-W,
[TIMES], [REPORT], [END]) that opens and runs in EPANET.

Requires: ezdxf  (pip install ezdxf)
License: MIT
"""

import argparse
import re
import sys
from dataclasses import dataclass

import ezdxf

from dxfnet import (NodeIndex, assign_diameters, build_links, collect_texts,
                    first_float, nearest_text_value, node_candidates)

ELEV_RE = re.compile(r"(?<![A-Za-z])(?:ELEV|EL|INV|IL)\s*[=:：]?\s*(-?\d+(?:\.\d+)?)"
                     r"|(?:标高|高程)\s*[=:：]?\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)

DEFAULT_NODE_LAYERS = ["NODE", "JUNCTION", "水源", "节点", "给水"]
DEFAULT_PIPE_LAYERS = ["PIPE", "MAIN", "管线", "管道", "给水"]


@dataclass
class Node:
    name: str
    x: float
    y: float
    elevation: float | None = None   # ground elevation, metres
    demand: float = 0.0              # base demand, L/s (junctions only)
    kind: str = "junction"           # junction | reservoir | tank
    head: float | None = None        # total head, reservoirs only
    auto: bool = False


def build_nodes(msp, node_layers, texts, args, warnings):
    idx = NodeIndex(args.snap)

    def add_node(x, y, name=None, elevation=None, demand=0.0, kind="junction",
                 head=None, auto=False):
        n = idx.find_at(x, y)  # merge duplicates within snap tolerance
        if n is not None:
            if name and n.auto:
                n.name, n.auto = name, False
                idx.claim(name)
            if elevation is not None and n.elevation is None:
                n.elevation = elevation
            if demand:
                n.demand = demand
            if kind != "junction":
                n.kind = kind
            if head is not None:
                n.head = head
            return n
        node = Node(idx.unique_name(name), x, y, elevation, demand, kind, head, auto)
        return idx.register(node)

    for t, x, y, at in node_candidates(msp, node_layers):
        if t == "INSERT":
            name = at.get("ID") or at.get("NAME") or at.get("编号")
            elevation = first_float(at.get("ELEV"), at.get("EL"), at.get("INV"), at.get("IL"))
            demand = first_float(at.get("DEMAND")) or 0.0
            typ = at.get("TYPE", "").upper()
            kind = {"RESERVOIR": "reservoir", "TANK": "tank"}.get(typ, "junction")
            if name and args.reservoir and name.upper() == args.reservoir.upper():
                kind = "reservoir"
            head = first_float(at.get("HEAD"))
            add_node(x, y, name, elevation, demand, kind, head)
        else:  # POINT / CIRCLE
            add_node(x, y)

    nodes = idx.nodes
    # ground elevations from nearby "EL=..." texts
    for n in nodes:
        if n.elevation is None:
            v = nearest_text_value(texts, n.x, n.y, args.text_radius, ELEV_RE)
            if v is not None:
                n.elevation = v
    for n in nodes:
        if n.elevation is None:
            n.elevation = args.default_elevation
            warnings.append(f"node {n.name}: no elevation found, default {args.default_elevation} m used")
    return nodes, add_node


def resolve_sources(nodes, args, warnings):
    """Decide which nodes are reservoirs and fix their total heads.
    Returns the list of reservoir nodes (never empty if nodes exist)."""
    reservoirs = [n for n in nodes if n.kind == "reservoir"]
    if args.reservoir:
        named = [n for n in nodes if n.name.upper() == args.reservoir.upper()]
        if named:
            if named[0] not in reservoirs:
                named[0].kind = "reservoir"
                reservoirs.append(named[0])
        else:
            warnings.append(f"--reservoir {args.reservoir} not found; falling back to marked/highest node")
    if not reservoirs:
        top = max(nodes, key=lambda n: n.elevation)
        top.kind = "reservoir"
        reservoirs = [top]
        warnings.append(f"no reservoir marked (TYPE=RESERVOIR or --reservoir); "
                        f"highest node {top.name} used as the source")
    for r in reservoirs:
        if r.head is None:
            r.head = r.elevation + args.source_head
            warnings.append(f"reservoir {r.name}: no HEAD attribute, total head set to "
                            f"elevation {r.elevation:.2f} + --source-head {args.source_head} "
                            f"= {r.head:.2f} m")
    for n in nodes:
        if n.kind == "tank":
            warnings.append(f"tank {n.name}: levels/diameter taken from --tank-* defaults "
                            f"(init {args.tank_init_level} m, max {args.tank_max_level} m, "
                            f"diameter {args.tank_diameter} m)")
    return reservoirs


def write_inp(nodes, pipes, args):
    junctions = [n for n in nodes if n.kind == "junction"]
    reservoirs = [n for n in nodes if n.kind == "reservoir"]
    tanks = [n for n in nodes if n.kind == "tank"]

    L = []
    L.append("[TITLE]")
    L.append(f"cad2epanet model generated from {args.input}")
    L.append("")
    L.append("[JUNCTIONS]")
    L.append(";ID              Elevation    Demand       Pattern")
    for n in junctions:
        L.append(f"{n.name:<16} {n.elevation:<12.3f} {n.demand:<12g}")
    L.append("")
    L.append("[RESERVOIRS]")
    L.append(";ID              Head         Pattern")
    for n in reservoirs:
        L.append(f"{n.name:<16} {n.head:<12.3f}")
    L.append("")
    if tanks:
        L.append("[TANKS]")
        L.append(";ID              Elevation    InitLevel    MinLevel     MaxLevel     Diameter     MinVolume")
        for n in tanks:
            L.append(f"{n.name:<16} {n.elevation:<12.3f} {args.tank_init_level:<12g} "
                     f"0            {args.tank_max_level:<12g} {args.tank_diameter:<12g} 0")
        L.append("")
    L.append("[PIPES]")
    L.append(";ID              Node1            Node2            Length       Diameter     Roughness    MinorLoss    Status")
    for p in pipes:
        L.append(f"{p.name:<16} {p.a.name:<16} {p.b.name:<16} {p.length:<12.2f} "
                 f"{int(round(p.diameter * 1000)):<12d} {args.roughness_c:<12g} 0            OPEN")
    L.append("")
    L.append("[COORDINATES]")
    L.append(";Node            X-Coord          Y-Coord")
    for n in nodes:
        L.append(f"{n.name:<16} {n.x * args.scale:<16.2f} {n.y * args.scale:.2f}")
    L.append("")
    L.append("[OPTIONS]")
    L.append("Units            LPS")
    L.append("Headloss         H-W")
    L.append("Specific Gravity 1.0")
    L.append("Viscosity        1.0")
    L.append("Trials           200")
    L.append("Accuracy         0.001")
    L.append("Unbalanced       Continue 10")
    L.append("Demand Multiplier 1.0")
    L.append("Quality          None")
    L.append("")
    L.append("[TIMES]")
    L.append("Duration         0:00")
    L.append("Hydraulic Timestep 1:00")
    L.append("Report Timestep  1:00")
    L.append("")
    L.append("[REPORT]")
    L.append("Status           No")
    L.append("Summary          Yes")
    L.append("Nodes            All")
    L.append("Links            All")
    L.append("")
    L.append("[END]")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert a CAD (DXF) water-supply network to an EPANET .inp model.")
    ap.add_argument("input", help="input .dxf file (export DWG to DXF first if needed)")
    ap.add_argument("-o", "--output", default=None, help="output .inp path (default: input name with .inp)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="drawing-unit -> metre factor (1.0 = drawing already in metres, 0.001 = millimetres)")
    ap.add_argument("--snap", type=float, default=2.0, help="endpoint snap tolerance, drawing units")
    ap.add_argument("--text-radius", type=float, default=10.0, help="search radius for EL= texts, drawing units")
    ap.add_argument("--node-layers", default=",".join(DEFAULT_NODE_LAYERS))
    ap.add_argument("--pipe-layers", default=",".join(DEFAULT_PIPE_LAYERS))
    ap.add_argument("--default-diameter", type=float, default=0.3, help="metres, when no DN label is found")
    ap.add_argument("--default-elevation", type=float, default=0.0, help="metres, when no elevation is found")
    ap.add_argument("--roughness-c", type=float, default=130.0, help="Hazen-Williams C (130 = new cast iron / DI)")
    ap.add_argument("--reservoir", default=None, help="name of the source (reservoir) node")
    ap.add_argument("--source-head", type=float, default=10.0,
                    help="metres added to a reservoir's ground elevation to get its total head "
                         "when the block has no HEAD attribute")
    ap.add_argument("--tank-diameter", type=float, default=10.0, help="metres, for TYPE=TANK nodes")
    ap.add_argument("--tank-init-level", type=float, default=2.0, help="metres, for TYPE=TANK nodes")
    ap.add_argument("--tank-max-level", type=float, default=5.0, help="metres, for TYPE=TANK nodes")
    args = ap.parse_args(argv)
    args.output = args.output or args.input.rsplit(".", 1)[0] + ".inp"

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
    pipes = build_links(msp, args.pipe_layers.split(","), nodes, add_node,
                        args.snap, args.scale, "P", warnings)
    if not pipes:
        print("error: no pipes found — check --pipe-layers against your drawing", file=sys.stderr)
        return 1
    assign_diameters(pipes, texts, args.scale, args.default_diameter, warnings, noun="pipe")
    reservoirs = resolve_sources(nodes, args, warnings)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(write_inp(nodes, pipes, args))

    junctions = [n for n in nodes if n.kind == "junction"]
    tanks = [n for n in nodes if n.kind == "tank"]
    total_len = sum(p.length for p in pipes)
    total_demand = sum(n.demand for n in junctions)
    kinds = f"junctions {len(junctions)} + reservoir {reservoirs[0].name}"
    if len(reservoirs) > 1:
        kinds += f" (+{len(reservoirs) - 1} more)"
    if tanks:
        kinds += f" + tanks {len(tanks)}"
    print(f"OK  {args.input} -> {args.output}")
    print(f"    nodes: {len(nodes)} ({kinds})")
    print(f"    pipes: {len(pipes)}, total length {total_len:.1f} m")
    print(f"    total base demand: {total_demand:g} L/s")
    for w in warnings:
        print(f"    warning: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
