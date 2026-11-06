#!/usr/bin/env python3
"""Run examples/example.inp through the real EPA SWMM engine (via pyswmm)
and verify the outfall actually receives the design inflow.

    pip install pyswmm
    python tests/run_swmm.py
"""
from pyswmm import Simulation, Nodes

with Simulation("examples/example.inp") as sim:
    outfall = Nodes(sim)["OUT1"]
    peak = 0.0
    for _ in sim:
        peak = max(peak, outfall.total_inflow)
print(f"simulation finished with no engine errors")
print(f"peak inflow at OUT1: {peak:.1f} LPS (design inflow was 50 LPS at J4)")
assert peak > 49.0, "outfall did not receive the design flow"
print("PASS  model runs and routes flow end-to-end")
