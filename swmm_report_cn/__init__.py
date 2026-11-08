"""swmm-report-cn：SWMM 中文校核报告生成器。

对外 API（供 cad2swmm 等上层工具嵌入）：
    parse_rpt(path) -> RptData          解析 .rpt 为结构化数据
    parse_inp(path) -> dict             .inp 概要（可选，工程概况用）
    run_checks(data) -> CheckResults    执行校核规则
    generate_report(data, inp_info=None, checks=None) -> str   生成中文 Markdown 报告
"""

from .checks import CheckItem, CheckResults, grade_continuity, run_checks
from .parser import RptData, parse_inp, parse_rpt
from .report import generate_report

__version__ = "0.1.0"

__all__ = [
    "parse_rpt",
    "parse_inp",
    "run_checks",
    "grade_continuity",
    "generate_report",
    "RptData",
    "CheckResults",
    "CheckItem",
    "__version__",
]
