"""EPA SWMM 5.x .rpt 报告文件解析器。

把 .rpt 里的各汇总段落解析成结构化数据（dataclass），供校核与报告生成使用。
解析原则：某个段落缺失时返回 None，不抛异常——不同模型的 .rpt 本来就不完整
（没有子汇水区就没有 Runoff Continuity，没有溢流就没有溢流表），
缺失情况由报告生成层注明。

每个表格行同时保留 float 值（用于校核/排序）和原始字符串 token（raw，
用于报告里原样呈现，避免格式化后与 .rpt 原文对不上）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ContinuityRow:
    label: str
    value1: float | None
    value2: float | None
    raw1: str = ""
    raw2: str = ""


@dataclass
class ContinuityBlock:
    """一个连续性平衡段（径流或水流演算）。"""

    kind: str  # "runoff" | "routing"
    unit1: str  # 第一列单位，如 hectare-m
    unit2: str  # 第二列单位，如 mm / 10^6 ltr
    rows: list[ContinuityRow] = field(default_factory=list)
    error_pct: float | None = None
    error_raw: str = ""


@dataclass
class OutfallRow:
    name: str
    flow_freq_pct: float
    avg_flow: float
    max_flow: float
    total_volume: float
    raw: tuple = ()


@dataclass
class NodeDepthRow:
    name: str
    node_type: str
    avg_depth: float
    max_depth: float
    max_hgl: float
    day: int
    time: str
    reported_max_depth: float
    raw: tuple = ()


@dataclass
class NodeInflowRow:
    name: str
    node_type: str
    max_lateral_inflow: float
    max_total_inflow: float
    day: int
    time: str
    lateral_volume: float
    total_volume: float
    balance_error: str  # 原文字符串，单位随模型而变（如 "0.128" 或 "0.000 ltr"）
    raw: tuple = ()


@dataclass
class NodeSurchargeRow:
    name: str
    node_type: str
    hours_surcharged: float
    max_height_above_crown: float
    min_depth_below_rim: float
    raw: tuple = ()


@dataclass
class NodeFloodingRow:
    name: str
    hours_flooded: float
    max_rate: float
    day: int
    time: str
    total_volume: float  # 溢流体积，单位同 volume_unit（一般 10^6 ltr / 10^6 gal）
    max_ponded_depth: float
    raw: tuple = ()


@dataclass
class LinkFlowRow:
    name: str
    link_type: str
    max_flow: float
    day: int
    time: str
    max_velocity: float
    max_full_flow: float  # Max/Full Flow，>1 表示超载
    max_full_depth: float  # Max/Full Depth
    raw: tuple = ()


@dataclass
class ConduitSurchargeRow:
    name: str
    hours_both_ends: float
    hours_upstream: float
    hours_downstream: float
    hours_above_full_normal: float
    hours_capacity_limited: float
    raw: tuple = ()


@dataclass
class FlowClassRow:
    name: str
    adj_length_ratio: float
    fractions: tuple = ()  # 9 个流态时间占比，顺序同 .rpt 表头


@dataclass
class RptData:
    """一份 .rpt 的全部解析结果。段落缺失时对应字段为 None。"""

    source_path: str = ""
    version: str | None = None  # 如 "5.2 (Build 5.2.4)"
    title_lines: list[str] = field(default_factory=list)
    options: dict = field(default_factory=dict)  # Analysis Options 键值对
    flow_units: str | None = None
    unit_system: str = "SI"  # "SI" | "US"，由流量单位推定
    length_unit: str = "m"  # 水深/长度单位标注
    volume_unit: str = "10^6 ltr"  # 体积单位标注（出口/入流汇总）
    start_datetime: str | None = None
    end_datetime: str | None = None

    runoff_continuity: ContinuityBlock | None = None
    routing_continuity: ContinuityBlock | None = None
    outfalls: list[OutfallRow] | None = None
    outfall_system: OutfallRow | None = None
    node_depth: list[NodeDepthRow] | None = None
    node_inflow: list[NodeInflowRow] | None = None
    # 以下三段：None = .rpt 无此段；[] = 有此段但结论为 "No ... were ..."
    node_surcharge: list[NodeSurchargeRow] | None = None
    node_flooding: list[NodeFloodingRow] | None = None
    link_flow: list[LinkFlowRow] | None = None
    conduit_surcharge: list[ConduitSurchargeRow] | None = None
    flow_classification: list[FlowClassRow] | None = None

    @property
    def missing_sections(self) -> list[str]:
        """返回缺失段落的中文名清单（供报告中注明）。"""
        pairs = [
            ("径流连续性（Runoff Continuity）", self.runoff_continuity),
            ("水流演算连续性（Flow Routing Continuity）", self.routing_continuity),
            ("出口流量汇总（Outfall Loading Summary）", self.outfalls),
            ("节点水深汇总（Node Depth Summary）", self.node_depth),
            ("节点入流汇总（Node Inflow Summary）", self.node_inflow),
            ("节点超载汇总（Node Surcharge Summary）", self.node_surcharge),
            ("节点溢流汇总（Node Flooding Summary）", self.node_flooding),
            ("管道流量汇总（Link Flow Summary）", self.link_flow),
            ("管道超载汇总（Conduit Surcharge Summary）", self.conduit_surcharge),
            ("流态分类汇总（Flow Classification Summary）", self.flow_classification),
        ]
        return [name for name, val in pairs if val is None]


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

_BANNER_RE = re.compile(r"^\s*\*+\s*$")
_DASH_RE = re.compile(r"^\s*-{5,}\s*$")


def _to_float(token: str):
    try:
        return float(token)
    except (TypeError, ValueError):
        return None


def _section_body(lines: list[str], title: str) -> list[str] | None:
    """定位以 title 为标题的段落，返回其内容行（去掉星号横幅行）。

    .rpt 段落形如：
        ******************
        Node Depth Summary
        ******************
        <内容...>
    内容到下一个段落横幅或 "Analysis begun on" 为止。
    """
    idx = None
    for i, line in enumerate(lines):
        if line.strip() == title:
            idx = i
            break
    if idx is None:
        return None
    body = []
    for line in lines[idx + 1 :]:
        if _BANNER_RE.match(line):
            if body:
                break
            continue  # 标题下方的横幅行，跳过
        if line.startswith("Analysis begun on"):
            break
        body.append(line)
    return body


def _table_rows(body: list[str]) -> list[str]:
    """从段落内容里提取候选数据行：第一个虚线行之后的非空行。

    多行表头分布在两个虚线行之间，会混进候选行，但各段落的行解析
    都带 token 数与数值校验，表头行会被自然排除；
    "No nodes were surcharged." 这类无数据的段落则返回空列表。
    """
    first_dash = -1
    for i, line in enumerate(body):
        if _DASH_RE.match(line):
            first_dash = i
            break
    if first_dash < 0:
        return []
    rows = []
    for line in body[first_dash + 1 :]:
        if not line.strip():
            if rows:
                break
            continue
        if _DASH_RE.match(line):
            continue  # 出口汇总中 System 行前的虚线
        rows.append(line)
    return rows


# ---------------------------------------------------------------------------
# 各段落解析
# ---------------------------------------------------------------------------

_DOTTED_ROW_RE = re.compile(
    r"^\s*(.+?)\s*\.{2,}\s+(-?\d+(?:\.\d+)?)\s*(-?\d+(?:\.\d+)?)?\s*$"
)


def _parse_options(lines: list[str]) -> dict:
    body = _section_body(lines, "Analysis Options") or []
    options = {}
    for line in body:
        m = _DOTTED_ROW_RE.match(line)
        if m:
            # Analysis Options 的值可能是字符串（如 DYNWAVE），单独处理见下
            options[m.group(1).strip()] = m.group(2).strip()
    # 点线行里值非数字的（如 Flow Routing Method ...... DYNWAVE）再扫一遍
    for line in body:
        m = re.match(r"^\s*(.+?)\s*\.{3,}\s+(\S.*?)\s*$", line)
        if m:
            options.setdefault(m.group(1).strip(), m.group(2).strip())
            options[m.group(1).strip()] = m.group(2).strip()
    return options


def _parse_continuity(text: str, kind: str, title: str) -> ContinuityBlock | None:
    m = re.search(re.escape(title) + r"\s+(\S+)\s+(.+?)\s*$", text, re.MULTILINE)
    if not m:
        return None
    block = ContinuityBlock(kind=kind, unit1=m.group(1), unit2=m.group(2).strip())
    tail = text[m.end() :]
    for line in tail.splitlines():
        if not line.strip():
            if block.rows or block.error_pct is not None:
                break
            continue
        rm = _DOTTED_ROW_RE.match(line)
        if rm:
            label = rm.group(1).strip()
            v1 = _to_float(rm.group(2))
            v2 = _to_float(rm.group(3)) if rm.group(3) else None
            if label.startswith("Continuity Error"):
                block.error_pct = v1
                block.error_raw = rm.group(2)
            else:
                block.rows.append(
                    ContinuityRow(label, v1, v2, rm.group(2), rm.group(3) or "")
                )
    return block


def _parse_outfalls(lines: list[str]):
    body = _section_body(lines, "Outfall Loading Summary")
    if body is None:
        return None, None
    rows, system = [], None
    for line in _table_rows(body):
        t = line.split()
        if len(t) != 5:
            continue
        vals = [_to_float(x) for x in t[1:]]
        if any(v is None for v in vals):
            continue
        row = OutfallRow(t[0], *vals, raw=tuple(t[1:]))
        if t[0] == "System":
            system = row
        else:
            rows.append(row)
    return rows, system


def _parse_node_depth(lines: list[str]):
    body = _section_body(lines, "Node Depth Summary")
    if body is None:
        return None
    out = []
    for line in _table_rows(body):
        t = line.split()
        if len(t) != 8:
            continue
        nums = [_to_float(t[i]) for i in (2, 3, 4, 7)]
        day = _to_float(t[5])
        if any(v is None for v in nums) or day is None:
            continue
        out.append(
            NodeDepthRow(
                t[0], t[1], nums[0], nums[1], nums[2], int(day), t[6], nums[3],
                raw=(t[2], t[3], t[4], t[7]),
            )
        )
    return out


def _parse_node_inflow(lines: list[str]):
    body = _section_body(lines, "Node Inflow Summary")
    if body is None:
        return None
    out = []
    for line in _table_rows(body):
        t = line.split()
        if len(t) < 8:
            continue
        nums = [_to_float(t[i]) for i in (2, 3, 6, 7)]
        day = _to_float(t[4])
        if any(v is None for v in nums) or day is None:
            continue
        out.append(
            NodeInflowRow(
                t[0], t[1], nums[0], nums[1], int(day), t[5], nums[2], nums[3],
                balance_error=" ".join(t[8:]),
                raw=(t[2], t[3], t[6], t[7]),
            )
        )
    return out


def _parse_node_surcharge(lines: list[str]):
    body = _section_body(lines, "Node Surcharge Summary")
    if body is None:
        return None
    out = []
    for line in _table_rows(body):
        t = line.split()
        if len(t) != 5:
            continue
        nums = [_to_float(x) for x in t[2:]]
        if any(v is None for v in nums):
            continue
        out.append(NodeSurchargeRow(t[0], t[1], *nums, raw=tuple(t[2:])))
    return out


def _parse_node_flooding(lines: list[str]):
    body = _section_body(lines, "Node Flooding Summary")
    if body is None:
        return None
    out = []
    for line in _table_rows(body):
        t = line.split()
        if len(t) != 7:
            continue
        nums = [_to_float(t[i]) for i in (1, 2, 5, 6)]
        day = _to_float(t[3])
        if any(v is None for v in nums) or day is None:
            continue
        out.append(
            NodeFloodingRow(
                t[0], nums[0], nums[1], int(day), t[4], nums[2], nums[3],
                raw=(t[1], t[2], t[5], t[6]),
            )
        )
    return out


def _parse_link_flow(lines: list[str]):
    body = _section_body(lines, "Link Flow Summary")
    if body is None:
        return None
    out = []
    for line in _table_rows(body):
        t = line.split()
        if len(t) != 8:
            continue
        nums = [_to_float(t[i]) for i in (2, 5, 6, 7)]
        day = _to_float(t[3])
        if any(v is None for v in nums) or day is None:
            continue
        out.append(
            LinkFlowRow(
                t[0], t[1], nums[0], int(day), t[4], nums[1], nums[2], nums[3],
                raw=(t[2], t[5], t[6], t[7]),
            )
        )
    return out


def _parse_conduit_surcharge(lines: list[str]):
    body = _section_body(lines, "Conduit Surcharge Summary")
    if body is None:
        return None
    out = []
    for line in _table_rows(body):
        t = line.split()
        if len(t) != 6:
            continue
        nums = [_to_float(x) for x in t[1:]]
        if any(v is None for v in nums):
            continue
        out.append(ConduitSurchargeRow(t[0], *nums, raw=tuple(t[1:])))
    return out


def _parse_flow_classification(lines: list[str]):
    body = _section_body(lines, "Flow Classification Summary")
    if body is None:
        return None
    out = []
    for line in _table_rows(body):
        t = line.split()
        if len(t) != 11:
            continue
        nums = [_to_float(x) for x in t[1:]]
        if any(v is None for v in nums):
            continue
        out.append(FlowClassRow(t[0], nums[0], tuple(nums[1:])))
    return out


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

_US_FLOW_UNITS = {"CFS", "GPM", "MGD", "AFD", "CFSX"}


def parse_rpt(path) -> RptData:
    """解析一份 SWMM .rpt 文件，返回 RptData。缺失段落为 None，不抛错。"""
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    data = RptData(source_path=str(p))

    m = re.search(r"VERSION\s+([\d.]+)\s*\(Build\s+([\d.]+)\)", text)
    if m:
        data.version = f"{m.group(1)} (Build {m.group(2)})"

    # 标题：版本行下方的虚线与第一个段落横幅之间的非空行
    for i, line in enumerate(lines):
        if _DASH_RE.match(line):
            for follow in lines[i + 1 :]:
                s = follow.strip()
                if _BANNER_RE.match(follow) or follow.startswith("Analysis begun"):
                    break
                if s.startswith(("WARNING", "ERROR")):
                    break  # 标题后紧跟的引擎警告行不属于标题
                if s:
                    data.title_lines.append(s)
            break

    data.options = _parse_options(lines)
    data.flow_units = data.options.get("Flow Units")
    data.start_datetime = data.options.get("Starting Date")
    data.end_datetime = data.options.get("Ending Date")
    if data.flow_units and data.flow_units.upper() in _US_FLOW_UNITS:
        data.unit_system = "US"
        data.length_unit = "ft"
        data.volume_unit = "10^6 gal"
    else:
        data.unit_system = "SI"
        data.length_unit = "m"
        data.volume_unit = "10^6 ltr"

    data.runoff_continuity = _parse_continuity(text, "runoff", "Runoff Quantity Continuity")
    data.routing_continuity = _parse_continuity(text, "routing", "Flow Routing Continuity")
    data.outfalls, data.outfall_system = _parse_outfalls(lines)
    data.node_depth = _parse_node_depth(lines)
    data.node_inflow = _parse_node_inflow(lines)
    data.node_surcharge = _parse_node_surcharge(lines)
    data.node_flooding = _parse_node_flooding(lines)
    data.link_flow = _parse_link_flow(lines)
    data.conduit_surcharge = _parse_conduit_surcharge(lines)
    data.flow_classification = _parse_flow_classification(lines)
    return data


# ---------------------------------------------------------------------------
# 可选：.inp 概要（工程概况用）
# ---------------------------------------------------------------------------

_INP_SECTIONS = {
    "junctions": ("[JUNCTIONS]", "检查井/节点"),
    "outfalls": ("[OUTFALLS]", "排放口"),
    "conduits": ("[CONDUITS]", "管道"),
    "subcatchments": ("[SUBCATCHMENTS]", "子汇水区"),
    "pumps": ("[PUMPS]", "水泵"),
    "orifices": ("[ORIFICES]", "孔口"),
    "weirs": ("[WEIRS]", "堰"),
}


def parse_inp(path) -> dict:
    """读取 .inp 的粗略概要：标题、流量单位、各要素数量、汇水面积合计。

    只做统计，不做完整解析；失败返回空 dict。
    """
    info: dict = {"counts": {}}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return info

    current = None
    counts = {key: 0 for key in _INP_SECTIONS}
    total_area = 0.0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            current = s.upper()
            continue
        if not s or s.startswith(";"):
            continue
        if current == "[TITLE]":
            info.setdefault("title", s)
        elif current == "[OPTIONS]":
            parts = s.split()
            if len(parts) >= 2 and parts[0].upper() == "FLOW_UNITS":
                info["flow_units"] = parts[1]
        else:
            for key, (header, _label) in _INP_SECTIONS.items():
                if current == header:
                    counts[key] += 1
                    if key == "subcatchments":
                        parts = s.split()
                        if len(parts) >= 4:
                            area = _to_float(parts[3])
                            if area is not None:
                                total_area += area
                    break
    info["counts"] = {k: v for k, v in counts.items() if v > 0}
    if total_area > 0:
        info["total_area"] = total_area
    info["labels"] = {k: _INP_SECTIONS[k][1] for k in info["counts"]}
    return info
