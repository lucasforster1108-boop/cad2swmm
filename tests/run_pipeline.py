#!/usr/bin/env python3
"""End-to-end pipeline test: DXF -> .inp -> EPA SWMM run (.rpt) -> Chinese check report (.md).

    pip install ezdxf pyswmm
    python tests/run_pipeline.py
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with tempfile.TemporaryDirectory() as tmp:
    cmd = [sys.executable, os.path.join(ROOT, "cad2swmm.py"),
           os.path.join(ROOT, "examples", "example.dxf"),
           "--pipeline", "--outdir", tmp, "--design-flow", "50"]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)

    inp = os.path.join(tmp, "example.inp")
    rpt = os.path.join(tmp, "example.rpt")
    md_path = os.path.join(tmp, "example_校核报告.md")
    for p in (inp, rpt, md_path):
        assert os.path.exists(p), f"pipeline product missing: {p}"
    print("PASS  pipeline produced .inp, .rpt and the check report")

    rpt_text = open(rpt, encoding="utf-8").read()
    md = open(md_path, encoding="utf-8").read()

    m = re.search(r"Flow Routing Continuity.*?Continuity Error \(%\) \.+ +(-?[\d.]+)",
                  rpt_text, re.S)
    assert m, "routing continuity error not found in .rpt"
    err = m.group(1)
    assert err in md, f"continuity error {err} from .rpt not found in report"
    print(f"PASS  routing continuity error in report matches .rpt ({err}%)")

    m = re.search(r"^\s*OUT1\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
                  rpt_text, re.M)
    assert m, "outfall row not found in .rpt"
    for val in m.groups():
        assert val in md, f"outfall value {val} from .rpt not found in report"
    print(f"PASS  outfall OUT1 row in report matches .rpt {m.groups()}")

print("PASS  full pipeline: drawing -> model -> simulation -> Chinese check report")
