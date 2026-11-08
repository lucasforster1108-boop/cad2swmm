"""校核规则：把解析出的模型结果按工程口径逐条判定。

判定档位：优秀 / 合格 / 警告 / 不合格 / 需关注 / 提示。
规则默认值就是排水模型校核里通用的经验门槛，README 里有对照表，
需要调整时改这里的常量即可。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .parser import RptData

# --- 连续性误差分档（|误差| %）：≤1 优秀，≤5 合格，≤10 警告，>10 不合格 ---
CONTINUITY_EXCELLENT = 1.0
CONTINUITY_PASS = 5.0
CONTINUITY_WARN = 10.0

# --- 管道满流比（Max/Full Flow）分档 ---
FULL_FLOW_OVERLOAD = 1.0  # >1.0 超载
FULL_FLOW_NEAR = 0.85  # 0.85~1.0 接近满流


def grade_continuity(error_pct: float) -> str:
    """连续性误差判定：返回 优秀/合格/警告/不合格。"""
    a = abs(error_pct)
    if a <= CONTINUITY_EXCELLENT:
        return "优秀"
    if a <= CONTINUITY_PASS:
        return "合格"
    if a <= CONTINUITY_WARN:
        return "警告"
    return "不合格"


@dataclass
class CheckItem:
    """结论段里的一条判定。"""

    name: str  # 校核项
    verdict: str  # 判定
    detail: str  # 依据说明


@dataclass
class CheckResults:
    items: list[CheckItem] = field(default_factory=list)
    flooded_nodes: list = field(default_factory=list)  # 溢流体积 > 0 的节点
    overloaded_links: list = field(default_factory=list)  # Max/Full Flow > 1.0
    near_full_links: list = field(default_factory=list)  # 0.85 ~ 1.0
    deepest_node: object = None  # 最大水深节点（NodeDepthRow）
    summary: str = ""  # 一句话总结


_VERDICT_RANK = {"不合格": 4, "警告": 3, "需关注": 2, "合格": 1, "优秀": 0, "提示": 0}


def run_checks(data: RptData) -> CheckResults:
    """对解析结果执行全部校核规则，返回结论所需的数据。"""
    res = CheckResults()

    # 1) 连续性误差
    for block, label in (
        (data.runoff_continuity, "径流连续性误差"),
        (data.routing_continuity, "水流演算连续性误差"),
    ):
        if block is not None and block.error_pct is not None:
            grade = grade_continuity(block.error_pct)
            res.items.append(
                CheckItem(
                    label,
                    grade,
                    f"连续性误差 {block.error_raw}%，"
                    f"门槛：|误差|≤1% 优秀、≤5% 合格、≤10% 警告、>10% 不合格。",
                )
            )

    # 2) 节点溢流：溢流体积 > 0 的逐个列入，有溢流即"需关注"
    if data.node_flooding is not None:
        res.flooded_nodes = [n for n in data.node_flooding if n.total_volume > 0]
        if res.flooded_nodes:
            names = "、".join(
                f"{n.name}（溢流 {n.raw[2]} {data.volume_unit}，历时 {n.raw[0]} h）"
                for n in res.flooded_nodes
            )
            res.items.append(
                CheckItem(
                    "节点溢流",
                    "需关注",
                    f"共 {len(res.flooded_nodes)} 个节点发生溢流：{names}。"
                    "溢流意味着该处水量已超出系统排水能力，需结合现场竖向与井盖标高复核。",
                )
            )
        else:
            res.items.append(
                CheckItem("节点溢流", "合格", "全网节点无溢流。")
            )

    # 3) 节点超载（水位超过管道顶）
    if data.node_surcharge is not None:
        if data.node_surcharge:
            names = "、".join(
                f"{n.name}（超载 {n.raw[0]} h）" for n in data.node_surcharge
            )
            res.items.append(
                CheckItem(
                    "节点超载",
                    "需关注",
                    f"共 {len(data.node_surcharge)} 个节点水位曾超过汇入管道顶：{names}。"
                    "超载本身不等于溢流，但说明管道已满流承压。",
                )
            )
        else:
            res.items.append(
                CheckItem("节点超载", "合格", "全网节点无超载。")
            )

    # 4) 管道满流比
    if data.link_flow is not None:
        res.overloaded_links = [
            l for l in data.link_flow if l.max_full_flow > FULL_FLOW_OVERLOAD
        ]
        res.near_full_links = [
            l
            for l in data.link_flow
            if FULL_FLOW_NEAR <= l.max_full_flow <= FULL_FLOW_OVERLOAD
        ]
        if res.overloaded_links:
            names = "、".join(
                f"{l.name}（满流比 {l.raw[2]}）" for l in res.overloaded_links
            )
            res.items.append(
                CheckItem(
                    "管道超载",
                    "需关注",
                    f"共 {len(res.overloaded_links)} 条管道峰值流量超过满流流量：{names}。"
                    "建议放大管径或调整坡度后复算。",
                )
            )
        elif res.near_full_links:
            names = "、".join(
                f"{l.name}（满流比 {l.raw[2]}）" for l in res.near_full_links
            )
            res.items.append(
                CheckItem(
                    "管道超载",
                    "合格",
                    f"无管道超载；{len(res.near_full_links)} 条管道接近满流"
                    f"（满流比 0.85~1.0）：{names}，余量有限，建议关注。",
                )
            )
        else:
            res.items.append(
                CheckItem("管道超载", "合格", "无管道超载，满流比均低于 0.85。")
            )

    # 5) 最深节点（信息项）
    if data.node_depth:
        res.deepest_node = max(data.node_depth, key=lambda n: n.max_depth)

    res.summary = _make_summary(res)
    return res


def _make_summary(res: CheckResults) -> str:
    if not res.items:
        return "未解析到可校核的汇总数据，请确认 .rpt 是否为完整的 SWMM 模拟报告。"
    worst = max(
        (it.verdict for it in res.items),
        key=lambda v: _VERDICT_RANK.get(v, 0),
    )
    if worst == "不合格":
        return (
            "本次模拟存在不合格项（见上表），模型结果不可直接采用，"
            "应先修正模型设置或参数后重新计算。"
        )
    if worst == "警告":
        return (
            "本次模拟连续性误差偏大，结果可信度打折，建议检查时步与模型参数后复算，"
            "其余校核项见上表。"
        )
    problems = []
    if res.flooded_nodes:
        problems.append(f"{len(res.flooded_nodes)} 个节点溢流")
    if res.overloaded_links:
        problems.append(f"{len(res.overloaded_links)} 条管道超载")
    if problems:
        return (
            "模型计算本身收敛可信，但排水能力不足："
            + "、".join(problems)
            + "，需针对上述薄弱环节调整设计后复算。"
        )
    if res.near_full_links:
        return (
            "模型计算收敛，连续性误差合格，无溢流、无管道超载；"
            f"仅 {len(res.near_full_links)} 条管道接近满流，整体可采用，建议留意余量。"
        )
    return "模型计算收敛，连续性误差合格，无溢流、无超载，模拟结果可采用。"
