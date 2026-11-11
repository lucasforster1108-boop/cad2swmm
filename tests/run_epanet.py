#!/usr/bin/env python3
"""Run examples/example_epanet.inp through the real EPA EPANET engine (via WNTR's
bundled EPANET toolkit) and verify the hydraulics are sane: the reservoir
supplies exactly the total base demand, and every junction ends up with a
reasonable positive pressure.

    pip install wntr
    python tests/run_epanet.py
"""
import os
import tempfile

import wntr

INP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples", "example_epanet.inp")

wn = wntr.network.WaterNetworkModel(INP)
sim = wntr.sim.EpanetSimulator(wn)
# the EPANET toolkit drops temp.* files in the CWD; keep them out of the repo
with tempfile.TemporaryDirectory() as td:
    os.chdir(td)
    results = sim.run_sim()

t0 = results.node["pressure"].index[0]
pressure = results.node["pressure"].loc[t0]          # metres of head
flow = results.link["flowrate"].loc[t0] * 1000.0     # m^3/s -> L/s

junctions = ["J1", "J2", "J3", "J4"]
pressures = {j: float(pressure[j]) for j in junctions}
outflow = float(flow["P1"])  # the only pipe out of reservoir R1

print("simulation finished with no engine errors")
for j in junctions:
    print(f"pressure at {j}: {pressures[j]:.2f} m")
print(f"reservoir outflow through P1: {outflow:.2f} L/s (total base demand is 16 L/s)")

assert abs(outflow - 16.0) < 0.05, "reservoir outflow does not match total demand"
assert all(2.0 < v < 40.0 for v in pressures.values()), "junction pressure out of sane range"
print("PASS  model runs, demand is supplied, pressures are reasonable")
