"""
VMC CLI 入口

vivado-ai lint/check/analyze/rules
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from vivado_ai.core.engine import MethodologyEngine, CheckConfig, CheckMode
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.issue import Severity
from vivado_ai.models.report import CheckReport

# 确保规则注册
import vivado_ai.core.rules.constraint_rules   # noqa: F401
import vivado_ai.core.rules.synth_rules         # noqa: F401
import vivado_ai.core.rules.place_rules         # noqa: F401
import vivado_ai.core.rules.route_rules         # noqa: F401
import vivado_ai.core.rules.root_cause_rules    # noqa: F401
import vivado_ai.core.rules.impl_rules          # noqa: F401
import vivado_ai.core.rules.opt_rules           # noqa: F401
import vivado_ai.core.rules.flow_rules          # noqa: F401
import vivado_ai.core.rules.rtl_rules           # noqa: F401

console = Console()


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vivado-ai",
        description="Vivado Methodology Checker - "
                    "UG949/UltraFast Design Methodology Compliance Tool",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ── lint ──
    lint_p = subparsers.add_parser("lint", help="Pre-synthesis RTL + XDC static check")
    lint_p.add_argument("--xdc", type=Path, nargs="+", required=True, help="XDC constraint files")
    lint_p.add_argument("--rtl", type=Path, help="RTL source directory")
    lint_p.add_argument("--groups", nargs="+", default=["all"], help="Rule groups")
    lint_p.add_argument("--no-ai", action="store_true", help="Disable AI explanations")
    lint_p.add_argument("--output", type=Path, help="Output report file (.md or .json)")

    # ── check ──
    check_p = subparsers.add_parser("check", help="Parse Vivado report files")
    check_p.add_argument("--reports-dir", type=Path, required=True, help="Directory with .rpt files")
    check_p.add_argument("--groups", nargs="+", default=["all"], help="Rule groups")
    check_p.add_argument("--no-ai", action="store_true")
    check_p.add_argument("--output", type=Path, help="Output report file")

    # ── analyze ──
    analyze_p = subparsers.add_parser("analyze", help="Parse Vivado stage log files")
    analyze_p.add_argument("--log-dir", type=Path, required=True, help="Directory with .log files")
    analyze_p.add_argument("--groups", nargs="+", default=["all"], help="Rule groups")
    analyze_p.add_argument("--no-ai", action="store_true")
    analyze_p.add_argument("--output", type=Path, help="Output report file")

    # ── rules ──
    subparsers.add_parser("rules", help="List all available rules")

    # ── gui ──
    gui_p = subparsers.add_parser("gui", help="Launch GUI (auto-detect Vivado)")
    gui_p.add_argument("--uninstall", action="store_true", help="Remove VMC integration from Vivado init.tcl")
    gui_p.add_argument("--mode", choices=["native", "web", "auto"], default="auto",
                       help="GUI mode: native=pywebview, web=browser, auto=try native first (default: auto)")
    gui_p.add_argument("--port", type=int, default=19877, help="Web server port (default: 19877)")

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "rules":
        _cmd_list_rules()
        return

    if args.command == "gui":
        _cmd_gui(args)
        return

    config = _build_config(args)
    engine = MethodologyEngine(config)
    result = engine.run()

    report = _build_report(result, config)
    _print_report(report)

    if args.output:
        _save_report(report, args.output)


def _build_config(args) -> CheckConfig:
    mode_map = {
        "lint": CheckMode.LINT,
        "check": CheckMode.CHECK,
        "analyze": CheckMode.ANALYZE,
    }
    return CheckConfig(
        mode=mode_map[args.command],
        rtl_dir=getattr(args, "rtl", None),
        xdc_files=getattr(args, "xdc", []) or [],
        reports_dir=getattr(args, "reports_dir", None),
        log_dir=getattr(args, "log_dir", None),
        enable_ai=not getattr(args, "no_ai", False),
        rule_groups=getattr(args, "groups", ["all"]),
    )


def _build_report(result, config: CheckConfig) -> CheckReport:
    issues = result.issues
    by_severity = {}
    by_group = {}
    for issue in issues:
        by_severity[issue.severity.value] = by_severity.get(issue.severity.value, 0) + 1
        group = issue.rule_id.split("-")[0]
        by_group.setdefault(group, []).append(issue)

    return CheckReport(
        mode=config.mode.value,
        total_rules=0,
        total_issues=len(issues),
        by_severity=by_severity,
        by_group=by_group,
        score=result.score,
        issues=issues,
        root_cause_summary=result.root_cause_summary,
    )


def _print_report(report: CheckReport):
    console.print()
    score_color = "green" if report.score >= 80 else ("yellow" if report.score >= 50 else "red")
    console.print(Panel(
        f"[{score_color}]{report.score}[/{score_color}]/100",
        title="Methodology Compliance Score",
    ))
    console.print(f"Mode: {report.mode} | Issues: {report.total_issues}")

    if report.root_cause_summary:
        console.print(Panel(
            report.root_cause_summary,
            title="Root Cause Analysis",
            border_style="cyan",
        ))

    if report.by_severity:
        for sev, count in report.by_severity.items():
            color = {"CRITICAL": "red", "FAIL": "red", "WARN": "yellow", "INFO": "blue"}.get(sev, "white")
            console.print(f"  [{color}]{sev}[/{color}]: {count}")

    if report.issues:
        table = Table(title="Issues", show_lines=True)
        table.add_column("Severity", width=10)
        table.add_column("Rule", width=12)
        table.add_column("Message", max_width=60)
        table.add_column("Fix", max_width=40)

        for issue in report.issues:
            if issue.severity == Severity.PASS:
                continue
            sev_color = {"CRITICAL": "red", "FAIL": "red", "WARN": "yellow", "INFO": "blue"}.get(
                issue.severity.value, "white"
            )
            fix = issue.fix_suggestion[:80] + "..." if len(issue.fix_suggestion) > 80 else issue.fix_suggestion
            table.add_row(
                f"[{sev_color}]{issue.severity.value}[/{sev_color}]",
                issue.rule_id,
                issue.message,
                fix,
            )

        console.print(table)

    console.print()


def _save_report(report: CheckReport, output: Path):
    output = Path(output)
    if output.suffix == ".json":
        output.write_text(report.to_json(), encoding="utf-8")
    else:
        output.write_text(report.to_markdown(), encoding="utf-8")
    console.print(f"Report saved to: {output}")


def _cmd_list_rules():
    registry = RuleRegistry()
    rules = registry.list_rules()

    table = Table(title="Available Rules")
    table.add_column("ID", width=14)
    table.add_column("Name", max_width=40)
    table.add_column("Group", width=6)
    table.add_column("Severity", width=10)
    table.add_column("Modes", width=20)

    for rule in sorted(rules, key=lambda r: r["id"]):
        table.add_row(
            rule["id"],
            rule["name"],
            rule["group"],
            rule["severity"],
            ", ".join(rule["modes"]),
        )

    console.print(table)
    console.print(f"\nTotal: {len(rules)} rules")


def _cmd_gui(args):
    """启动 GUI"""
    if args.uninstall:
        from vivado_ai.gui.installer import VivadoAutoInstaller
        installer = VivadoAutoInstaller()
        installer.uninstall()
        console.print("[green]VMC integration removed from Vivado init.tcl[/green]")
        return

    mode = args.mode

    if mode == "auto":
        try:
            import webview  # noqa: F401
            mode = "native"
        except ImportError:
            mode = "web"

    if mode == "native":
        try:
            from vivado_ai.gui.app import start_gui
            start_gui()
            return
        except ImportError as e:
            console.print(f"[yellow]pywebview not available:[/yellow] {e}")
            console.print("Falling back to web server mode...")
            mode = "web"

    # web mode
    try:
        from vivado_ai.gui.app import Backend
        from vivado_ai.gui.web_server import start_web_server
    except ImportError as e:
        console.print(f"[red]GUI dependencies not installed:[/red] {e}")
        console.print("Install with: pip install vivado-ai[gui]")
        sys.exit(1)

    backend = Backend()
    backend.initialize()
    start_web_server(backend, port=args.port)


if __name__ == "__main__":
    main()
