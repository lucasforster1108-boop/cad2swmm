#!/usr/bin/env python3
"""Generate example.dxf — a tiny drainage network drawn the way engineers draw it:
manhole blocks (with ID / INV attributes) on layer MANHOLE, pipe lines on layer
PIPE, and DN labels as plain text near each pipe.

    J4 (0,25)
    |  DN300
    J1 --DN300-- J2 --DN400-- J3 --DN500-- OUT1
   (0,0)       (30,0)      (60,0)       (90,0)
"""
import ezdxf

doc = ezdxf.new("R2010")
msp = doc.modelspace()
doc.layers.add("MANHOLE")
doc.layers.add("PIPE")

# manhole block with attributes
blk = doc.blocks.new("MH")
blk.add_circle((0, 0), radius=1.0)
blk.add_attdef("ID", (2, 2))
blk.add_attdef("INV", (2, -2))
blk.add_attdef("TYPE", (2, -4))

NODES = [  # name, x, y, invert, type
    ("J1", 0, 0, 10.00, ""),
    ("J2", 30, 0, 9.70, ""),
    ("J3", 60, 0, 9.40, ""),
    ("J4", 30, 25, 10.40, ""),
    ("OUT1", 90, 0, 9.10, "OUTFALL"),
]
pos = {}
for name, x, y, inv, typ in NODES:
    ref = msp.add_blockref("MH", (x, y), dxfattribs={"layer": "MANHOLE"})
    ref.add_attrib("ID", name, (x + 2, y + 2))
    ref.add_attrib("INV", f"{inv:.2f}", (x + 2, y - 2))
    if typ:
        ref.add_attrib("TYPE", typ, (x + 2, y - 4))
    pos[name] = (x, y)

PIPES = [  # from, to, label, label position
    ("J1", "J2", "DN300", (15, 2)),
    ("J2", "J3", "DN400", (45, 2)),
    ("J3", "OUT1", "DN500", (75, 2)),
    ("J4", "J2", "DN300", (32, 12)),
]
for a, b, label, (lx, ly) in PIPES:
    msp.add_line(pos[a], pos[b], dxfattribs={"layer": "PIPE"})
    msp.add_text(label, dxfattribs={"height": 2.0}).set_placement((lx, ly))

doc.saveas("example.dxf")
print("example.dxf written: 5 nodes, 4 pipes")
