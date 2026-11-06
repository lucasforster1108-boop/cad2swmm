# cad2swmm

[English](README.md) | **中文** | [한국어](README.ko.md) | [日本語](README.ja.md)

**把一张 CAD 排水图纸，一条命令变成能跑的 EPA SWMM 模型。**

GitHub 上所有 SWMM 自动化工具都从 GIS 数据开始。可工程师画排水管网不用 GIS——用的是 CAD。
`cad2swmm` 补的就是这座桥：给它一张带检查井和管道的 DXF，还你一个完整、能在 EPA SWMM 5 里
打开并运行的 `.inp` 模型文件。

```bash
pip install ezdxf
python cad2swmm.py my_network.dxf -o my_network.inp
```

## 它做什么

| 图纸里有什么 | 模型里生成什么 |
|---|---|
| 节点图层上的检查井块 / 点 / 圆 | `[JUNCTIONS]`（外加 `[OUTFALLS]`） |
| 块属性 `ID`、`INV` / `IL` / `ELEV`，或 `IL=12.34` 文字 | 节点名称与井底标高 |
| 管线图层上的 `LINE` / `LWPOLYLINE` | 带真实几何长度的 `[CONDUITS]` |
| 管道附近的 `DN300` / `D300` / `Φ300` / `300mm` 文字 | `[XSECTIONS]` 圆形管径 |
| 井底标高 | 流向自动定向（高 → 低） |

不会有东西被悄悄丢掉：管端点吸附不到井时会自动建节点；凡是不得不用默认值顶替的
（缺管径标注、缺标高），都会逐条警告，告诉你出在哪根管、哪口井。

## 快速上手

```bash
# 先生成自带示例图纸，再转换（图纸单位为米，默认）
python examples/make_example.py
python cad2swmm.py examples/example.dxf -o examples/example.inp

# 图纸单位是毫米时，加一个冒烟测试入流
python cad2swmm.py site.dxf -o site.inp --scale 0.001 --design-flow 50
```

自带示例是 5 个节点、4 根管的小管网，按工程师平时的画法画的（DXF 由
`examples/make_example.py` 生成）：

```
nodes: 5 (junctions 4 + outfall OUT1)
conduits: 4, total length 115.0 m
```

自己验证输出质量：

```bash
python tests/validate.py     # 结构校验：管长、管径、流向
pip install pyswmm
python tests/run_swmm.py     # 用真正的 EPA SWMM 引擎实跑模型
```

引擎实跑是测试的一部分，不是截图秀：生成的模型能把 50 L/s 设计入流从头输送到尾
（出水口峰值约 54 L/s，含动力波效应；流量演算连续性误差 < 0.1%）。

## 主要参数

```
--scale 0.001         图纸单位 → 米（图纸是毫米时用 0.001）
--node-layers 井,MANHOLE   放检查井/节点的图层
--pipe-layers 管线,PIPE    放管道的图层
--default-diameter 0.3     找不到 DN 标注时的默认管径（米）
--default-invert 0.0       找不到标高时的默认井底标高（米）
--outfall J9               排放口井名（不给则取标高最低的井）
--roughness 0.013          糙率（默认混凝土管）
--design-flow 50           在最高点井加恒定入流（L/s），用于冒烟测试
--snap 2.0                 管端点到井的吸附容差（图纸单位）
```

## 画图约定

按你平时的画法画就行——默认同时识别英文和中文 CAD 图层习惯：

- **节点**：块参照、点或圆，图层如 `MANHOLE`、`NODE`、`检查井`、`井`
- **管道**：直线 / 多段线，图层如 `PIPE`、`SEWER`、`管线`、`管道`、`排水`
- **排放口**：井块带属性 `TYPE=OUTFALL`，或用 `--outfall` 指定
- DWG 文件：先在 CAD 里另存为 DXF（或用 ODA File Converter 批量转换）

也可以作为 Agent Skill 使用（见 `SKILL.md`）：装进支持 SKILL.md 的工具
（Claude Code、DeepSeek Harness 等），直接说「把这张 CAD 图转成 SWMM 模型」即可。

## 路线图

- 原生读取 DWG（ODA / LibreDWG）
- 从 CAD 填充与标注生成汇水区与降雨
- 污水 + 雨水双系统、水泵/阀门块
- 可选衔接 [agentic-swmm-workflow](https://github.com/Zhonghao1995/agentic-swmm-workflow) 做模拟运行与 Word 报告

## License

MIT
