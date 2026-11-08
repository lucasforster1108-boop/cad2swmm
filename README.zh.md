# cad2swmm

[English](README.md) | **中文** | [한국어](README.ko.md) | [日本語](README.ja.md)

我是做建筑给排水设计的。每个项目到最后都一样：CAD 图画完了，然后坐到
SWMM 里，把检查井、管道、管径、井底标高再敲一遍——这些数据明明都在图里。
敲烦了，就写了这个小东西。

cad2swmm 读一张 DXF 排水图纸，生成一个能在 EPA SWMM 5 里直接打开、能跑的
`.inp` 文件。它只干这一件事，但省掉的是最烦的那一个小时。GitHub 上其他
SWMM 工具都从 GIS 数据开始，可工程师画管网不用 GIS，CAD 这一步一直没人补。

```bash
pip install ezdxf
python cad2swmm.py my_network.dxf -o my_network.inp
```

## 它从图里读什么

- 检查井：节点图层上的块、点、圆，生成节点和排放口
- 井名和井底标高：来自块属性（`ID`、`INV` / `IL` / `ELEV`），或 `IL=12.34`
  这样的文字
- 管道：管线图层上的直线、多段线，生成管道，长度按几何实测
- 管径：管道附近的 `DN300` / `D300` / `Φ300` / `300mm` 标注
- 流向：按标高自动定向，高往低流

管端点吸附不到井时，它会自己补一个节点。凡是猜出来的值——缺管径标注、
缺标高——都会逐条打印警告，写明是哪根管、哪口井，不会闷声瞎填。

## 先跑个例子

`examples` 里有个 5 节点、4 根管的小管网，按平时画图的样子画的（DXF 是
脚本生成的，先跑第一条命令）：

```bash
python examples/make_example.py
python cad2swmm.py examples/example.dxf -o examples/example.inp

# 图纸单位是毫米时，再加一个 50 L/s 的测试入流
python cad2swmm.py site.dxf -o site.inp --scale 0.001 --design-flow 50
```

示例转换结果：

```
nodes: 5 (junctions 4 + outfall OUT1)
conduits: 4, total length 115.0 m
```

仓库里有三个测试脚本，因为我要的是证据，不是截图。`tests/validate.py`
查结构（管长、管径、流向）；`tests/run_swmm.py` 用 pyswmm 调真正的 EPA
SWMM 引擎实跑生成的模型：50 L/s 设计入流从头输到尾，出水口峰值约 54 L/s
（含动力波效应），流量演算连续性误差小于 0.1%；`tests/run_pipeline.py`
验下面这条一条龙流程，三件产物齐全、报告数字与 .rpt 原文对得上才算过。

## 一条龙：图纸 → 模拟 → 中文校核报告

转换只是第一步。加上 `--pipeline`，同一个脚本会把流程走完：转出
`.inp` 后用 pyswmm 调真正的 SWMM 引擎实跑，再把 `.rpt` 变成一份中文
校核报告（Markdown）——连续性误差判定、出口流量汇总、节点溢流/超载、
管道满流比，结论逐条给出，数值全部取自 .rpt 原文。

```bash
pip install pyswmm
python cad2swmm.py examples/example.dxf --pipeline --outdir examples/pipeline --design-flow 50
```

`examples/pipeline/` 里就是上面这条命令的真实产物：`example.inp`、
`example.rpt`、`example_校核报告.md`。分步开关也有：`--run` 只跑模拟、
`--report` 只出报告。已经有 `.inp` 或 `.rpt` 时，把文件直接当输入传
进来就能用后半段：

```bash
python cad2swmm.py model.inp --run --report
python cad2swmm.py model.rpt            # 只出校核报告
```

报告生成用的是仓库内置的 `swmm_report_cn/` 包（源自 swmm-report-cn，
MIT，纯标准库、零第三方依赖），不用另外安装。

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
--pipeline                 一条龙：转换 → 实跑 → 中文校核报告（等同 --run --report）
--run                      转换后用 pyswmm 实跑 .inp，产出 .rpt
--report                   由 .rpt 生成中文校核报告（.md）
--outdir DIR               一条龙产物目录（.inp / .rpt / 报告）
--report-output PATH       校核报告的指定输出路径
```

## 图要怎么画

按你平时的画法就行，默认同时认英文和中文图层名：

- 节点：块参照、点或圆，图层如 `MANHOLE`、`NODE`、`检查井`、`井`
- 管道：直线 / 多段线，图层如 `PIPE`、`SEWER`、`管线`、`管道`、`排水`
- 排放口：井块带属性 `TYPE=OUTFALL`，或用 `--outfall` 指定
- DWG 文件：先在 CAD 里另存为 DXF（或用 ODA File Converter 批量转）

## 还做不到的

- 直接读 DWG
- 汇水区和降雨——这部分还得你自己划
- 水泵、阀门、雨污双系统

它也能当 Agent Skill 用（见 `SKILL.md`）：装进支持 SKILL.md 的工具
（Claude Code、DeepSeek Harness 等），直接说「把这张 CAD 图转成 SWMM
模型」就行。

## License

MIT
