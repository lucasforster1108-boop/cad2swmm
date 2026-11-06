#!/usr/bin/env python3
"""Validate examples/example.inp against what make_example.py drew.
Run:  python tests/validate.py     (exit 0 = all checks pass)"""
import re
import sys

inp = open("examples/example.inp", encoding="utf-8").read()

def section(name):
    m = re.search(rf"\[{name}\](.*?)(?=\n\[|\Z)", inp, re.S)
    return [ln.split() for ln in m.group(1).strip().splitlines()
            if ln.strip() and not ln.startswith(";")] if m else []

checks = []
def check(label, ok):
    checks.append((label, ok))
    print(("PASS " if ok else "FAIL ") + label)

j = {r[0]: r for r in section("JUNCTIONS")}
o = {r[0]: r for r in section("OUTFALLS")}
c = {r[0]: r for r in section("CONDUITS")}
x = {r[0]: r for r in section("XSECTIONS")}

check("4 junctions J1..J4", sorted(j) == ["J1", "J2", "J3", "J4"])
check("outfall is OUT1", list(o) == ["OUT1"])
check("4 conduits", len(c) == 4)
lengths = sorted(float(r[3]) for r in c.values())
check("lengths are 25/30/30/30 m", lengths == [25.0, 30.0, 30.0, 30.0])
diams = sorted(float(r[2]) for r in x.values())
check("diameters are 0.3/0.3/0.4/0.5 m", diams == [0.3, 0.3, 0.4, 0.5])
routes = {(r[1], r[2]) for r in c.values()}
check("flow follows falling inverts (J4->J2, J1->J2, J2->J3, J3->OUT1)",
      routes == {("J4", "J2"), ("J1", "J2"), ("J2", "J3"), ("J3", "OUT1")})
check("invert of J1 read from attribute (10.00)", abs(float(j["J1"][1]) - 10.0) < 1e-6)
check("design inflow present", "[INFLOWS]" in inp)

bad = [label for label, ok in checks if not ok]
print(f"\n{len(checks) - len(bad)}/{len(checks)} checks passed")
sys.exit(1 if bad else 0)
