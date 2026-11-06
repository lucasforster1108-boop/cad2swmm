# cad2swmm

**English** | [中文](README.zh.md) | [한국어](README.ko.md) | [日本語](README.ja.md)

**Turn a CAD drainage drawing into a runnable EPA SWMM model — in one command.**

Every SWMM automation tool on GitHub starts from GIS data. But engineers don't draw
drainage networks in GIS — they draw them in CAD. `cad2swmm` is the missing bridge:
give it a DXF with manholes and pipes, get back a complete `.inp` that opens and
runs in EPA SWMM 5.

```bash
pip install ezdxf
python cad2swmm.py my_network.dxf -o my_network.inp
```

## What it does

| From your drawing | To the SWMM model |
|---|---|
| Manhole blocks / points / circles on the node layer | `[JUNCTIONS]` (+ `[OUTFALLS]`) |
| Block attributes `ID`, `INV` / `IL` / `ELEV`, or `IL=12.34` text | Node names & invert elevations |
| `LINE` / `LWPOLYLINE` on the pipe layer | `[CONDUITS]` with true geometric lengths |
| `DN300` / `D300` / `Φ300` / `300mm` text near a pipe | `[XSECTIONS]` circular diameters |
| Invert elevations | Flow direction (high → low), automatically |

Nothing is silently dropped: unsnapped pipe endpoints create auto nodes, and every
value that had to be defaulted (a missing diameter label, a missing invert) is
reported as a warning with the element it belongs to.

## Quick start

```bash
# generate the bundled example drawing, then convert it (drawing in metres, the default)
python examples/make_example.py
python cad2swmm.py examples/example.dxf -o examples/example.inp

# drawing in millimetres, with a 50 L/s smoke-test inflow
python cad2swmm.py site.dxf -o site.inp --scale 0.001 --design-flow 50
```

Try the bundled example — a 5-node, 4-pipe network drawn exactly the way
engineers draw it (the DXF is generated, run `python examples/make_example.py` first):

```
nodes: 5 (junctions 4 + outfall OUT1)
conduits: 4, total length 115.0 m
```

Verify the output yourself:

```bash
python tests/validate.py     # structural checks: lengths, diameters, flow directions
pip install pyswmm
python tests/run_swmm.py     # runs the model in the real EPA SWMM engine
```

The engine run is part of the test suite, not a screenshot: the generated model
routes the 50 L/s design inflow end-to-end (peak outfall inflow ≈ 54 L/s
including dynamic-wave effects, flow-routing continuity error < 0.1%).

## Key options

```
--scale 0.001         drawing units -> metres (0.001 if the drawing is in mm)
--node-layers 井,MANHOLE   layers that hold manholes/nodes
--pipe-layers 管线,PIPE    layers that hold pipes
--default-diameter 0.3     fallback diameter (m) when no DN label is found
--default-invert 0.0       fallback invert elevation (m)
--outfall J9               name of the outfall node (else: lowest node)
--roughness 0.013          Manning's n (default: concrete pipe)
--design-flow 50           add a constant inflow (L/s) at the highest junction
--snap 2.0                 endpoint-to-node snap tolerance (drawing units)
```

## Drawing conventions

Draw the way you already draw — the defaults recognise both English and Chinese
CAD layer conventions:

- **Nodes**: block references, points, or circles on layers like `MANHOLE`, `NODE`, `检查井`, `井`
- **Pipes**: lines / polylines on layers like `PIPE`, `SEWER`, `管线`, `管道`, `排水`
- **Outfall**: a node block with attribute `TYPE=OUTFALL`, or pass `--outfall`
- DWG files: save-as DXF in your CAD package first (or batch-convert with ODA File Converter)

## Roadmap

- Native DWG reading (ODA / LibreDWG)
- Subcatchments & rainfall from CAD hatches and annotation
- Sewer + stormwater dual drainage, pump/valve blocks
- Optional hand-off to [agentic-swmm-workflow](https://github.com/Zhonghao1995/agentic-swmm-workflow) for simulation runs and Word reports

## 中文说明

工程师画排水管网用的是 CAD，可 GitHub 上所有 SWMM 自动化工具都只吃 GIS 数据——
这一步没人补。`cad2swmm` 干的就是这件事：把 DXF 图纸里的检查井、管道、管径标注、
井底标高自动提取出来，一条命令生成 EPA SWMM 能直接打开、能跑的 `.inp` 模型文件。
识别不到的值（缺管径标注、缺标高）不会瞎编，会逐条警告告诉你哪根管、哪口井用了默认值。

```bash
pip install ezdxf
python cad2swmm.py 图纸.dxf -o 模型.inp --scale 0.001   # 图纸单位是毫米时
```

也可以作为 Agent Skill 使用（见 `SKILL.md`），在 Claude Code / DeepSeek Harness 等
支持 SKILL.md 的工具里装上后，直接说「把这张 CAD 图转成 SWMM 模型」即可。

## License

MIT
