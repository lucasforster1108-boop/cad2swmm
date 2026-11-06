---
name: cad2swmm
description: Convert a CAD drainage network drawing (DXF) into a runnable EPA SWMM model (.inp). Use when the user has a CAD/DWG drainage or sewer layout and wants a SWMM model, a hydraulic simulation, or asks "turn this drawing into SWMM / 把这张 CAD 图转成 SWMM 模型". Bridges the gap every GIS-based SWMM tool leaves open: engineers draw in CAD, not GIS.
---

# cad2swmm — CAD 图纸 → SWMM 模型

把工程师真正画图的格式（CAD/DXF）转成 EPA SWMM 能直接打开运行的模型文件（.inp）。
现有 SWMM 工作流工具只吃 GIS 数据，本技能补的就是 CAD 入口这一步。

## 工作流

1. **先看图层**：确认节点图层（检查井块/点/圆）和管线图层（LINE/LWPOLYLINE）的名字。
   图层名与默认值（MANHOLE/检查井、PIPE/管线 等）对不上时，用 `--node-layers` / `--pipe-layers` 指定，不要改图。
2. **确认单位**：图纸是米用 `--scale 1.0`（默认），是毫米用 `--scale 0.001`。单位错了，管长全错，先向用户确认。
3. **运行转换**：
   `python cad2swmm.py 图纸.dxf -o 模型.inp`
   需要冒烟测试时加 `--design-flow 50`（在最高点节点加 50 L/s 恒定入流）。
4. **读警告再交付**：脚本会逐条报告用默认值顶替的地方（未找到管径标注的管、未找到标高的井、端点无井自动建的节点）。
   **这些警告必须原样转告用户**，并指出在图上对应哪个位置——这是模型可信度的一部分，禁止吞掉。
5. **有条件时实跑验证**：`pip install pyswmm` 后运行 `python tests/run_swmm.py` 模式：
   用引擎打开生成的 .inp 跑一遍，确认无 ERROR、出水口有流量，再交付。

## 输入约定（脚本自动识别）

| 元素 | 图上画法 | 备注 |
|---|---|---|
| 检查井/节点 | 节点图层上的块参照、点或圆 | 井名取块属性 ID/NAME/编号，无则自动编号 J1… |
| 井底标高 | 块属性 INV/IL/ELEV，或井边 `IL=12.34` 文字 | 无则用 `--default-invert` 并给出警告 |
| 管道 | 管线图层上的 LINE / LWPOLYLINE | 多段线中间顶点自动成井 |
| 管径 | 管中点附近文字 DN300 / D300 / Φ300 / 300mm | 无则用 `--default-diameter` 并给出警告 |
| 排放口 | 块属性 TYPE=OUTFALL，或 `--outfall 井名` | 无则取标高最低的井 |

流向按标高自动定向（高→低）；管长按图纸几何 × scale 计算；糙率默认 0.013（混凝土）。

## 红线

- 不编造标高和管径：识别不到就用默认值并明确警告，绝不假装是从图上读出来的。
- 单位（米/毫米）没确认前不转换。
- 只读用户提供的图纸文件，不改原图。
- 交付物 = .inp 文件 + 转换报告（节点数、管数、总长、警告清单），缺一不可。

## 依赖

`pip install ezdxf`（转换）；`pip install pyswmm`（可选，实跑验证）。
DWG 文件先在 CAD 里另存为 DXF（或用 ODA File Converter 批量转）。
