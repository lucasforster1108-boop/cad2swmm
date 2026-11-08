"""中文校核报告生成：把 RptData + 校核结果渲染成 Markdown。

generate_report(data, inp_info=None, checks=None) -> str
- data：parser.parse_rpt 的结果
- inp_info：可选，parser.parse_inp 的结果（工程概况里的要素统计）
- checks：可选，checks.run_checks 的结果；不传则自动计算

表格里的数值一律用 .rpt 原始字符串呈现，保证与原文逐字一致；
缺失的段落会在对应章节注明"无此项数据"，不硬凑。
"""

from __future__ import annotations

from datetime import datetime

from .checks import run_checks
from .parser import RptData

_MISSING = "> 注：.rpt 中无此段落，无此项数据。"


def _fmt_duration(start: str | None, end: str | None) -> str | None:
    if not start or not end:
        return None
    try:
        t0 = datetime.strptime(start, "%m/%d/%Y %H:%M:%S")
        t1 = datetime.strptime(end, "%m/%d/%Y %H:%M:%S")
    except ValueError:
        return None
    seconds = int((t1 - t0).total_seconds())
    if seconds < 0:
        return None
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days} 天")
    if hours:
        parts.append(f"{hours} 小时")
    if minutes:
        parts.append(f"{minutes} 分")
    return " ".join(parts) if parts else "不足 1 分钟"


def _continuity_table(block, checks_map) -> list[str]:
    lines = []
    title = (
        "径流连续性（Runoff Continuity）"
        if block.kind == "runoff"
        else "水流演算连续性（Flow Routing Continuity）"
    )
    lines.append(f"### {title}")
    lines.append("")
    lines.append(f"| 项目 | 体积（{block.unit1}） | {block.unit2} |")
    lines.append("| --- | ---: | ---: |")
    for row in block.rows:
        lines.append(f"| {row.label} | {row.raw1} | {row.raw2} |")
    if block.error_pct is not None:
        grade = checks_map.get(block.kind, "")
        lines.append(
            f"| **连续性误差** | **{block.error_raw}%** | 判定：**{grade}** |"
        )
    lines.append("")
    return lines


def generate_report(data: RptData, inp_info: dict | None = None,
                    checks=None) -> str:
    if checks is None:
        checks = run_checks(data)
    checks_map = {}
    for it in checks.items:
        if "径流" in it.name:
            checks_map["runoff"] = it.verdict
        if "水流演算" in it.name:
            checks_map["routing"] = it.verdict

    L: list[str] = []
    L.append("# SWMM 模型校核报告")
    L.append("")
    L.append(f"- 数据来源：`{data.source_path}`")
    if data.version:
        L.append(f"- SWMM 版本：{data.version}")
    L.append("- 生成工具：swmm-report-cn（数值均取自 .rpt 原文）")
    L.append("")

    # ---------------- 一、工程概况与模拟设置 ----------------
    L.append("## 一、工程概况与模拟设置")
    L.append("")
    title = None
    if inp_info and inp_info.get("title"):
        title = inp_info["title"]
    elif data.title_lines:
        title = " ".join(data.title_lines)
    if title:
        L.append(f"- 模型标题：{title}")
    unit_note = (
        "SI 单位制（流量 LPS/CMS，长度 m，体积 10^6 ltr）"
        if data.unit_system == "SI"
        else "US 单位制（流量 CFS/GPM，长度 ft，体积 10^6 gal）"
    )
    L.append(f"- 单位制：{unit_note}")
    if inp_info and inp_info.get("counts"):
        labels = inp_info.get("labels", {})
        stats = "、".join(
            f"{labels.get(k, k)} {v} 个" for k, v in inp_info["counts"].items()
        )
        L.append(f"- 模型要素：{stats}")
        if inp_info.get("total_area"):
            L.append(f"- 子汇水区总面积：{inp_info['total_area']:.2f} ha")
    L.append("")
    L.append("| 模拟设置 | 取值 |")
    L.append("| --- | --- |")
    opt_rows = [
        ("流量单位", data.options.get("Flow Units")),
        ("径流计算", data.options.get("Rainfall/Runoff")),
        ("水流演算", data.options.get("Flow Routing")),
        ("演算方法", data.options.get("Flow Routing Method")),
        ("开始时间", data.start_datetime),
        ("结束时间", data.end_datetime),
        ("模拟时长", _fmt_duration(data.start_datetime, data.end_datetime)),
        ("报告步长", data.options.get("Report Time Step")),
        ("演算步长", data.options.get("Routing Time Step")),
        ("允许积水（Ponding）", data.options.get("Ponding Allowed")),
    ]
    for name, val in opt_rows:
        if val:
            L.append(f"| {name} | {val} |")
    L.append("")

    # ---------------- 二、连续性误差校核 ----------------
    L.append("## 二、连续性误差校核")
    L.append("")
    L.append(
        "连续性误差反映模型的质量守恒水平，是判断结果能不能用的第一道关。"
        "判定门槛：|误差| ≤1% 优秀、≤5% 合格、≤10% 警告、>10% 不合格。"
    )
    L.append("")
    if data.runoff_continuity is not None:
        L.extend(_continuity_table(data.runoff_continuity, checks_map))
    else:
        L.append("### 径流连续性（Runoff Continuity）")
        L.append("")
        L.append(_MISSING)
        L.append("")
    if data.routing_continuity is not None:
        L.extend(_continuity_table(data.routing_continuity, checks_map))
    else:
        L.append("### 水流演算连续性（Flow Routing Continuity）")
        L.append("")
        L.append(_MISSING)
        L.append("")

    # ---------------- 三、出口流量汇总 ----------------
    L.append("## 三、出口流量汇总")
    L.append("")
    if data.outfalls:
        L.append(
            f"| 排放口 | 排水频率（%） | 平均流量（{data.flow_units or ''}） "
            f"| 峰值流量（{data.flow_units or ''}） | 总出水量（{data.volume_unit}） |"
        )
        L.append("| --- | ---: | ---: | ---: | ---: |")
        for o in data.outfalls:
            L.append(
                f"| {o.name} | {o.raw[0]} | {o.raw[1]} | {o.raw[2]} | {o.raw[3]} |"
            )
        if data.outfall_system is not None:
            s = data.outfall_system
            L.append(
                f"| **系统合计** | **{s.raw[0]}** | **{s.raw[1]}** "
                f"| **{s.raw[2]}** | **{s.raw[3]}** |"
            )
        L.append("")
        if data.outfall_system is not None:
            L.append(
                f"全系统总出水量 {data.outfall_system.raw[3]} {data.volume_unit}，"
                f"峰值出流量 {data.outfall_system.raw[2]} {data.flow_units or ''}。"
            )
            L.append("")
    else:
        L.append(_MISSING)
        L.append("")

    # ---------------- 四、节点校核 ----------------
    L.append("## 四、节点校核")
    L.append("")
    L.append("### 4.1 节点水深（最深 5 个）")
    L.append("")
    if data.node_depth:
        top = sorted(data.node_depth, key=lambda n: n.max_depth, reverse=True)[:5]
        L.append(
            f"| 节点 | 类型 | 平均水深（{data.length_unit}） "
            f"| 最大水深（{data.length_unit}） | 最大水位 HGL（{data.length_unit}） "
            "| 出现时刻（天 时:分） |"
        )
        L.append("| --- | --- | ---: | ---: | ---: | --- |")
        for n in top:
            L.append(
                f"| {n.name} | {n.node_type} | {n.raw[0]} | {n.raw[1]} "
                f"| {n.raw[2]} | {n.day} {n.time} |"
            )
        L.append("")
        if checks.deepest_node is not None:
            d = checks.deepest_node
            L.append(
                f"全网最大水深出现在节点 {d.name}：{d.raw[1]} {data.length_unit}"
                f"（{d.day} 天 {d.time}）。"
            )
            L.append("")
    else:
        L.append(_MISSING)
        L.append("")

    L.append("### 4.2 节点溢流")
    L.append("")
    if data.node_flooding is None:
        L.append(_MISSING)
        L.append("")
    elif checks.flooded_nodes:
        L.append(
            f"| 节点 | 溢流历时（h） | 峰值溢流流量（{data.flow_units or ''}） "
            f"| 溢流总量（{data.volume_unit}） | 出现时刻（天 时:分） |"
        )
        L.append("| --- | ---: | ---: | ---: | --- |")
        for n in checks.flooded_nodes:
            L.append(
                f"| {n.name} | {n.raw[0]} | {n.raw[1]} "
                f"| {n.raw[2]} | {n.day} {n.time} |"
            )
        L.append("")
    else:
        L.append("无节点溢流。")
        L.append("")

    L.append("### 4.3 节点超载（水位超过管道顶）")
    L.append("")
    if data.node_surcharge is None:
        L.append(_MISSING)
        L.append("")
    elif data.node_surcharge:
        L.append(
            f"| 节点 | 超载历时（h） | 超出管顶高度（{data.length_unit}） "
            f"| 距井盖余量（{data.length_unit}） |"
        )
        L.append("| --- | ---: | ---: | ---: |")
        for n in data.node_surcharge:
            L.append(f"| {n.name} | {n.raw[0]} | {n.raw[1]} | {n.raw[2]} |")
        L.append("")
    else:
        L.append("无节点超载。")
        L.append("")

    # ---------------- 五、管道校核 ----------------
    L.append("## 五、管道校核")
    L.append("")
    L.append("### 5.1 超载管道（满流比 > 1.0）")
    L.append("")
    if data.link_flow is None:
        L.append(_MISSING)
        L.append("")
    elif checks.overloaded_links:
        L.append(
            f"| 管道 | 峰值流量（{data.flow_units or ''}） "
            f"| 峰值流速（{data.length_unit}/s） | 满流比 Max/Full Flow "
            "| 满水深比 Max/Full Depth | 出现时刻（天 时:分） |"
        )
        L.append("| --- | ---: | ---: | ---: | ---: | --- |")
        for l in checks.overloaded_links:
            L.append(
                f"| {l.name} | {l.raw[0]} | {l.raw[1]} | {l.raw[2]} "
                f"| {l.raw[3]} | {l.day} {l.time} |"
            )
        L.append("")
    else:
        L.append("无管道超载（全部管道满流比 ≤ 1.0）。")
        L.append("")

    L.append("### 5.2 接近满流管道（满流比 0.85 ~ 1.0）")
    L.append("")
    if data.link_flow is None:
        L.append(_MISSING)
        L.append("")
    elif checks.near_full_links:
        L.append(
            f"| 管道 | 峰值流量（{data.flow_units or ''}） "
            f"| 峰值流速（{data.length_unit}/s） | 满流比 Max/Full Flow "
            "| 满水深比 Max/Full Depth | 出现时刻（天 时:分） |"
        )
        L.append("| --- | ---: | ---: | ---: | ---: | --- |")
        for l in checks.near_full_links:
            L.append(
                f"| {l.name} | {l.raw[0]} | {l.raw[1]} | {l.raw[2]} "
                f"| {l.raw[3]} | {l.day} {l.time} |"
            )
        L.append("")
    else:
        L.append("无接近满流管道（满流比位于 0.85~1.0 区间的管道）。")
        L.append("")

    L.append("### 5.3 管道满流历时（Conduit Surcharge Summary）")
    L.append("")
    if data.conduit_surcharge is None:
        L.append(_MISSING)
        L.append("")
    elif data.conduit_surcharge:
        L.append("| 管道 | 两端满流（h） | 上端满流（h） | 下端满流（h） "
                 "| 超满流正常流量历时（h） | 能力受限历时（h） |")
        L.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for c in data.conduit_surcharge:
            L.append(
                f"| {c.name} | {c.raw[0]} | {c.raw[1]} | {c.raw[2]} "
                f"| {c.raw[3]} | {c.raw[4]} |"
            )
        L.append("")
    else:
        L.append("无管道满流历时记录（各管道均未达到满流）。")
        L.append("")

    L.append("### 5.4 流态分类提示（Flow Classification Summary）")
    L.append("")
    if data.flow_classification is None:
        L.append(_MISSING)
        L.append("")
    else:
        flagged = [
            r for r in data.flow_classification
            if len(r.fractions) >= 2 and (r.fractions[-1] > 0 or r.fractions[-2] > 0)
        ]
        if flagged:
            L.append("| 管道 | 长度修正比 | 正常流受限时间占比 | 入口控制时间占比 |")
            L.append("| --- | ---: | ---: | ---: |")
            for r in flagged:
                L.append(
                    f"| {r.name} | {r.adj_length_ratio:.2f} "
                    f"| {r.fractions[-2]:.2f} | {r.fractions[-1]:.2f} |"
                )
            L.append("")
            L.append("九类流态完整占比见 .rpt 原文 Flow Classification Summary。")
            L.append("")
        else:
            L.append("无管道受正常流或入口控制限制。九类流态完整占比见 .rpt 原文。")
            L.append("")

    # ---------------- 六、校核结论 ----------------
    L.append("## 六、校核结论")
    L.append("")
    if checks.items:
        L.append("| 校核项 | 判定 | 说明 |")
        L.append("| --- | --- | --- |")
        for it in checks.items:
            L.append(f"| {it.name} | **{it.verdict}** | {it.detail} |")
        L.append("")
    L.append(f"**一句话总结：{checks.summary}**")
    L.append("")
    missing = data.missing_sections
    if missing:
        L.append(
            "数据完整性说明：本 .rpt 未包含以下段落，相应校核未开展："
            + "、".join(missing)
            + "。"
        )
        L.append("")
    return "\n".join(L).rstrip() + "\n"
