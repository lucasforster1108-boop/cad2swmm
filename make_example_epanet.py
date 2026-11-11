#!/usr/bin/env python3
"""Generate example_epanet.dxf — a tiny water-supply network drawn the way engineers
draw it: node blocks (with ID / ELEV / DEMAND / TYPE / HEAD attributes) on
layer NODE, pipe lines on layer PIPE, and DN labels as plain text near each
pipe.

           J4 (60,25)
           |  DN100
   R1 --DN200-- J1 --DN200-- J2 --DN150-- J3
  (0,0)        (30,0)       (60,0)        (90,0)
"""
import ezdxf

doc = ezdxf.new("R2010")
msp = doc.modelspace()
doc.layers.add("NODE")
doc.layers.add("PIPE")

# node block with attributes
blk = doc.blocks.new("WN")
blk.add_circle((0, 0), radius=1.0)
blk.add_attdef("ID", (2, 2))
blk.add_attdef("ELEV", (2, -2))
blk.add_attdef("DEMAND", (2, -4))
blk.add_attdef("TYPE", (2, -6))
blk.add_attdef("HEAD", (2, -8))

NODES = [  # name, x, y, ground elevation, base demand (L/s), type, total head
    ("R1", 0, 0, 50.00, 0, "RESERVOIR", 60.00),
    ("J1", 30, 0, 48.00, 5, "", None),
    ("J2", 60, 0, 46.50, 8, "", None),
    ("J3", 90, 0, 45.00, 0, "", None),
    ("J4", 60, 25, 47.50, 3, "", None),
]
pos = {}
for name, x, y, elev, dem, typ, head in NODES:
    ref = msp.add_blockref("WN", (x, y), dxfattribs={"layer": "NODE"})
    ref.add_attrib("ID", name, (x + 2, y + 2))
    ref.add_attrib("ELEV", f"{elev:.2f}", (x + 2, y - 2))
    if dem:
        ref.add_attrib("DEMAND", f"{dem:g}", (x + 2, y - 4))
    if typ:
        ref.add_attrib("TYPE", typ, (x + 2, y - 6))
    if head is not None:
        ref.add_attrib("HEAD", f"{head:.2f}", (x + 2, y - 8))
    pos[name] = (x, y)

PIPES = [  # from, to, label, label position
    ("R1", "J1", "DN200", (15, 2)),
    ("J1", "J2", "DN200", (45, 2)),
    ("J2", "J3", "DN150", (75, 2)),
    ("J2", "J4", "DN100", (62, 12)),
]
for a, b, label, (lx, ly) in PIPES:
    msp.add_line(pos[a], pos[b], dxfattribs={"layer": "PIPE"})
    msp.add_text(label, dxfattribs={"height": 2.0}).set_placement((lx, ly))

doc.saveas("example_epanet.dxf")
print("example_epanet.dxf written: 5 nodes (1 reservoir + 4 junctions), 4 pipes")
