"""
VMC TUI — 终端交互式界面

使用 Rich Live Display 显示实时状态，支持键盘快捷键交互菜单。
"""

import os
import select
import sys
import time
import threading
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.rule import Rule
from rich.console import Group


class TUI:
    """VMC 终端 UI — 三阶段交互式界面"""

    PHASES = [
        ("1", "OPT 后", "opt"),
        ("2", "布局后", "place"),
        ("3", "布线后", "route"),
    ]

    def __init__(self, backend, refresh_interval: float = 0.5):
        self.backend = backend
        self.refresh_interval = refresh_interval
        self._running = True
        self._lock = threading.Lock()
        self._console = Console()
        self._input_queue = []
        self._stdin_fd = sys.stdin.fileno() if sys.stdin.isatty() else None

    def run(self):
        """启动 TUI 主循环"""
        backend = self.backend
        backend.add_state_callback(self._on_state_change)

        self._start_input_listener()

        try:
            with Live(self._build_display(), refresh_per_second=2, console=self._console) as live:
                while self._running:
                    self._process_input()
                    live.update(self._build_display())
                    time.sleep(self.refresh_interval)
        finally:
            self._running = False
            backend.shutdown()

    def _start_input_listener(self):
        """启动键盘输入监听线程"""
        def read_stdin():
            while self._running:
                if self._stdin_fd is not None:
                    try:
                        r, _, _ = select.select([sys.stdin], [], [], 0.1)
                        if r:
                            ch = sys.stdin.read(1)
                            if ch:
                                with self._lock:
                                    self._input_queue.append(ch.lower())
                    except Exception:
                        pass
                else:
                    time.sleep(0.1)

        try:
            import tty
            import termios
            old_settings = termios.tcgetattr(self._stdin_fd)
            tty.setcbreak(self._stdin_fd)
            def restore():
                try:
                    termios.tcsetattr(self._stdin_fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass
            threading.Thread(target=read_stdin, daemon=True).start()
        except Exception:
            try:
                import keyboard
                def listen_keys():
                    while self._running:
                        for num, _, _ in self.PHASES:
                            if keyboard.is_pressed(num):
                                with self._lock:
                                    self._input_queue.append(num)
                                time.sleep(0.3)
                        if keyboard.is_pressed("r"):
                            with self._lock:
                                self._input_queue.append("r")
                            time.sleep(0.3)
                        time.sleep(0.05)
                threading.Thread(target=listen_keys, daemon=True).start()
            except ImportError:
                pass

    def _process_input(self):
        """处理输入队列"""
        with self._lock:
            queue = list(self._input_queue)
            self._input_queue.clear()

        for ch in queue:
            state = self.backend.state
            if state == "select_vivado":
                instances = self.backend.vivado_instances
                for i in range(len(instances)):
                    if ch == str(i + 1):
                        self.backend.select_vivado(i)
                        break
            elif state == "ready":
                for num, _, phase_key in self.PHASES:
                    if ch == num:
                        self._trigger_stage_analysis(phase_key)
                        break
                else:
                    if ch == "r":
                        self._trigger_stage_analysis("current")
                    elif ch == "c":
                        self.backend.clear_stage_reports("all")

    def _trigger_stage_analysis(self, stage: str):
        """触发指定阶段的分析"""
        self.backend.analyze_stage(stage)

    def _build_display(self):
        state = self.backend.state
        project = self.backend.project_info or {}
        run_status = self.backend.run_status or {}

        state_panel = self._build_state_panel(state, run_status)
        phases_panel = self._build_phases_panel(run_status)
        project_panel = self._build_project_panel(project)
        guide_panel = self._build_guide_panel(state)
        result_panel = self._build_result_panel(state)

        return Group(state_panel, phases_panel, project_panel, guide_panel, result_panel)

    def _build_state_panel(self, state: str, run_status: dict) -> Panel:
        if state == "waiting":
            content = "扫描 Vivado 中...\n\n提示：首次使用需重启 Vivado 以加载 Tcl Server"
            border = "blue"
        elif state == "select_vivado":
            instances = self.backend.vivado_instances
            lines = [f"检测到 {len(instances)} 个 Vivado 实例，请选择要连接的实例：", ""]
            for i, inst in enumerate(instances):
                proj_name = inst.get("project_name", "")
                part = inst.get("part", "")
                port = inst.get("port", "")
                if proj_name and proj_name != "未知项目":
                    desc = f"[bold]{proj_name}[/bold]"
                    if part:
                        desc += f"  ({part})"
                    if port:
                        desc += f"  [dim]端口:{port}[/dim]"
                else:
                    desc = inst.get("cmdline", f"PID:{inst.get('pid', '?')}")[:80]
                lines.append(f"  [bright_cyan]{i + 1}[/bright_cyan]  {desc}")
            lines.append("")
            lines.append("[dim]按数字键选择对应的 Vivado 实例[/dim]")
            content = "\n".join(lines)
            border = "yellow"
        elif state == "ready":
            opt_stage = run_status.get("opt", {}).get("stage", "")
            place_stage = run_status.get("place", {}).get("stage", "")
            route_stage = run_status.get("route", {}).get("stage", "")
            border = "green"
            if route_stage == "complete":
                content = "Vivado 已连接 — 布线已完成，可选择任意阶段分析"
            elif place_stage == "complete":
                content = "Vivado 已连接 — 布局已完成，按 2 分析"
            elif opt_stage == "complete":
                content = "Vivado 已连接 — OPT 已完成，按 1 分析"
            else:
                impl_stage = run_status.get("impl_overall", {}).get("stage", "")
                if impl_stage == "running":
                    content = "Vivado 已连接 — 编译运行中..."
                else:
                    content = "Vivado 已连接 — 等待实现完成..."
        elif state == "analyzing":
            content = "分析中..."
            border = "yellow"
        elif state == "results":
            content = "分析完成，查看下方结果"
            border = "green"
        else:
            content = "未知状态"
            border = "blue"

        return Panel(content, title="VMC 状态", border_style=border)

    def _build_phases_panel(self, run_status: dict) -> Panel:
        table = Table(show_header=True, header_style="bold magenta", expand=False)
        table.add_column("#", style="bold", width=3)
        table.add_column("阶段", width=8)
        table.add_column("状态", width=10)
        table.add_column("进度", width=8)
        table.add_column("报告", width=6)
        table.add_column("操作", width=14)

        reports_dir = self._get_reports_dir()

        for num, name, phase_key in self.PHASES:
            info = run_status.get(phase_key, {})
            stage = info.get("stage", "unknown")
            progress = info.get("progress", "")

            if stage == "complete":
                status_str = "已完成"
                progress_str = "100%"
                status_style = "green"
            elif stage == "running":
                status_str = "运行中"
                progress_str = progress or "..."
                status_style = "yellow"
            elif stage == "failed":
                status_str = "失败"
                progress_str = "-"
                status_style = "red"
            else:
                status_str = "未开始"
                progress_str = "-"
                status_style = "dim"

            has_report = self._check_phase_report(reports_dir, phase_key)
            if has_report is True:
                report_str = "有"
                report_style = "green"
            elif has_report is False:
                report_str = "无"
                report_style = "red"
            else:
                report_str = "?"
                report_style = "dim"

            if stage == "complete":
                action_str = f"按 {num} 分析"
                action_style = "bright_cyan"
            elif stage == "running":
                action_str = "等待中"
                action_style = "yellow"
            else:
                action_str = "不可用"
                action_style = "dim"

            table.add_row(
                num,
                name,
                f"[{status_style}]{status_str}[/{status_style}]",
                progress_str,
                f"[{report_style}]{report_str}[/{report_style}]",
                f"[{action_style}]{action_str}[/{action_style}]",
            )

        return Panel(table, title="实现阶段 & 报告状态", border_style="magenta")

    def _get_reports_dir(self) -> Optional[Path]:
        hooks = getattr(self.backend, "hooks", None)
        if hooks:
            return getattr(hooks, "reports_dir", None)
        project_info = self.backend.project_info or {}
        runs_dir = project_info.get("runs_dir")
        if runs_dir:
            return Path(runs_dir) / "vmc_reports"
        return None

    def _check_phase_report(self, reports_dir: Optional[Path], phase: str) -> Optional[bool]:
        if not reports_dir:
            return None
        phase_files = {
            "opt":   ["vm_timing_opt.rpt", "vm_methodology_opt.rpt"],
            "place": ["vm_timing_place.rpt", "vm_methodology_place.rpt"],
            "route": ["vm_timing_route.rpt", "vm_methodology_route.rpt"],
        }
        files = phase_files.get(phase, [])
        return any((reports_dir / f).exists() for f in files)

    def _build_project_panel(self, project: dict) -> Panel:
        lines = []
        if project:
            lines = [
                f"项目: {project.get('name', 'N/A')}",
                f"器件: {project.get('part', 'N/A')}",
            ]
        return Panel("\n".join(lines), title="项目信息", border_style="cyan")

    def _build_guide_panel(self, state: str) -> Panel:
        if state != "ready":
            return Panel("", title="操作指南", border_style="yellow")

        content = (
            "[bold]快捷键操作：[/bold]\n\n"
            "  [bright_cyan]1[/bright_cyan]  分析 OPT 后（全面分析）\n"
            "  [bright_cyan]2[/bright_cyan]  分析布局后（增量分析）\n"
            "  [bright_cyan]3[/bright_cyan]  分析布线后（增量分析）\n"
            "  [bright_cyan]R[/bright_cyan]  重新生成报告并分析\n"
            "  [bright_cyan]C[/bright_cyan]  清理所有报告文件\n\n"
            "[dim]提示：只有已完成的阶段才能进行分析[/dim]"
        )
        return Panel(content, title="操作指南", border_style="yellow")

    def _build_result_panel(self, state: str) -> Panel:
        if state != "results":
            return Panel("", title="分析结果", border_style="green")

        result = self.backend.analysis_result
        if not result:
            return Panel("", title="分析结果", border_style="green")

        if result.get("error"):
            return Panel(
                f"[red]{result['error']}[/red]",
                title="分析结果",
                border_style="red",
            )

        score = result.get("score", 0)
        total = result.get("total_issues", 0)
        issues = result.get("issues", [])

        if score == 0 and total == 0 and not issues:
            return Panel(
                "[yellow]分析完成但未找到报告数据[/yellow]\n"
                "[dim]可能原因：DCP 未打开、报告生成失败[/dim]",
                title="分析结果",
                border_style="yellow",
            )

        score_color = "green" if score >= 80 else "red"

        lines = [f"[{score_color}]评分: {score}/100[/{score_color}]"]
        lines.append(f"问题总数: {total}")
        lines.append("")

        for idx, issue in enumerate(issues[:10], 1):
            sev = issue.get("severity", "")
            sev_style = "red" if sev in ("CRITICAL", "FAIL") else "yellow" if sev == "WARN" else "green"
            rule = issue.get("rule_id", "")
            msg = issue.get("message", "")
            loc = issue.get("location", "")

            lines.append(f"[{sev_style}]{idx}. [{sev}] {rule}[/{sev_style}]")
            if msg:
                lines.append(f"   {msg}")
            if loc:
                lines.append(f"   [dim]位置: {loc}[/dim]")
            lines.append("")

        if len(issues) > 10:
            lines.append(f"[dim]... 还有 {len(issues) - 10} 个问题[/dim]")

        ai_summary = result.get("ai_summary", "")
        if ai_summary:
            lines.append("")
            lines.append("─" * 50)
            lines.append("[bold bright_cyan]AI 分析总结[/bold bright_cyan]")
            lines.append("")
            for summary_line in ai_summary.splitlines():
                lines.append(summary_line)

        stage_names = {"opt": "OPT 后", "place": "布局后", "route": "布线后"}
        stage_label = stage_names.get(result.get("stage", ""), result.get("stage", "未知阶段"))

        return Panel(
            "\n".join(lines),
            title=f"分析结果 — {stage_label}",
            border_style=score_color,
        )

    def _on_state_change(self, new_state: str):
        with self._lock:
            if new_state == "results":
                self._show_results()

    def _show_results(self):
        result = self.backend.analysis_result
        if not result or result.get("error"):
            return

        self._console.print(Rule(style="bright_cyan"))
        score = result.get("score", 0)
        score_color = "green" if score >= 80 else "red"
        self._console.print(f"[{score_color}]评分: {score}/100[/{score_color}]")
        self._console.print(f"问题数: {result.get('total_issues', 0)}")
        self._console.print()

        issues = result.get("issues", [])
        if issues:
            table = Table(show_header=True)
            table.add_column("#", width=3)
            table.add_column("严重性", style="bold")
            table.add_column("规则ID")
            table.add_column("消息")
            table.add_column("位置")
            table.add_column("建议")

            for idx, issue in enumerate(issues, 1):
                sev = issue.get("severity", "")
                sev_style = "red" if sev in ("CRITICAL", "FAIL") else "yellow" if sev == "WARN" else "green"
                fix = issue.get("fix_suggestion", "")
                table.add_row(
                    str(idx),
                    f"[{sev_style}]{sev}[/{sev_style}]",
                    issue.get("rule_id", ""),
                    issue.get("message", "")[:60],
                    issue.get("location", "")[:30],
                    fix[:40] if fix else "",
                )
            self._console.print(table)
