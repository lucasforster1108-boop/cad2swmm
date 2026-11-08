"""命令行入口（薄封装）：解析参数 -> parse_rpt -> generate_report -> 写文件/打印。

用法：
    swmm-report-cn model.rpt                 # 报告打到标准输出
    swmm-report-cn model.rpt -o report.md    # 写到文件
    swmm-report-cn model.rpt --inp model.inp # 附带 .inp 时概况里带要素统计
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .parser import parse_inp, parse_rpt
from .report import generate_report


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="swmm-report-cn",
        description="把 EPA SWMM 的 .rpt 报告转成中文校核报告（Markdown）。",
    )
    ap.add_argument("rpt", help=".rpt 报告文件路径")
    ap.add_argument("--inp", default=None, help="可选：对应的 .inp 模型文件，"
                                                "用于在工程概况中统计模型要素")
    ap.add_argument("-o", "--output", default=None,
                    help="输出的 Markdown 文件路径；不指定则打印到标准输出")
    ap.add_argument("--version", action="version",
                    version=f"swmm-report-cn {__version__}")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    rpt_path = Path(args.rpt)
    if not rpt_path.is_file():
        print(f"错误：找不到 .rpt 文件：{rpt_path}", file=sys.stderr)
        return 2

    data = parse_rpt(rpt_path)
    inp_info = parse_inp(args.inp) if args.inp else None
    report = generate_report(data, inp_info=inp_info)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"已生成校核报告：{args.output}")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
