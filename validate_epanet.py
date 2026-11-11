#!/usr/bin/env python3
"""Validate examples/example_epanet.inp against what make_example_epanet.py drew.
Run:  python tests/validate.py     (exit 0 = all checks pass)"""
import re
import sys

inp = open("examples/example_epanet.inp", encoding="utf-8").read()

def section(name):
    m = re.search(rf"\[{name}\](.*?)(?=\n\[|\Z)", inp, re.S)
    return [ln.split() for ln in m.group(1).strip().splitlines()
            if ln.strip() and not ln.startswith(";")] if m else []

checks = []
def check(label, ok):
    checks.append((label, ok))
    print(("PASS " if ok else "FAIL ") + label)

j = {r[0]: r for r in section("JUNCTIONS")}
r_ = {r[0]: r for r in section("RESERVOIRS")}
p = {r[0]: r for r in section("PIPES")}
coords = {r[0] for r in section("COORDINATES")}

check("4 junctions J1..J4", sorted(j) == ["J1", "J2", "J3", "J4"])
check("reservoir is R1", list(r_) == ["R1"])
check("reservoir head read from HEAD attribute (60.00)", abs(float(r_["R1"][1]) - 60.0) < 1e-6)
check("4 pipes", len(p) == 4)
lengths = sorted(float(r[3]) for r in p.values())
check("lengths are 25/30/30/30 m", lengths == [25.0, 30.0, 30.0, 30.0])
diams = sorted(int(r[4]) for r in p.values())
check("diameters are 100/150/200/200 mm", diams == [100, 150, 200, 200])
rough = {r[5] for r in p.values()}
check("roughness is Hazen-Williams C=130 everywhere", rough == {"130"})
check("elevation of J1 read from attribute (48.00)", abs(float(j["J1"][1]) - 48.0) < 1e-6)
demands = {k: float(v[2]) for k, v in j.items()}
check("demands are J1=5, J2=8, J3=0, J4=3 L/s",
      demands == {"J1": 5.0, "J2": 8.0, "J3": 0.0, "J4": 3.0})
check("coordinates written for all 5 nodes", coords == {"R1", "J1", "J2", "J3", "J4"})
check("options are Units LPS + Headloss H-W",
      "Units            LPS" in inp and "Headloss         H-W" in inp)
check("[END] present", "[END]" in inp)

# connectivity: every junction reachable from the reservoir through pipes
graph = {}
for r in p.values():
    graph.setdefault(r[1], set()).add(r[2])
    graph.setdefault(r[2], set()).add(r[1])
seen, stack = set(), ["R1"]
while stack:
    n = stack.pop()
    if n not in seen:
        seen.add(n)
        stack.extend(graph.get(n, ()))
check("all junctions reachable from reservoir R1", set(j) <= seen)

bad = [label for label, ok in checks if not ok]
print(f"\n{len(checks) - len(bad)}/{len(checks)} checks passed")
sys.exit(1 if bad else 0)
