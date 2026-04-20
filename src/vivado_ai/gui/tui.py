"""
VMC TUI — 终端交互式界面

使用 Rich Live Display 显示实时状态，支持键盘快捷键。
零新依赖（Rich 已有）。
"""

import json
import time
import threading
from typing import Optional

from rich import console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.rule import Rule


class TUI:
    """VMC 终端 UI"""

    def __init__(self, backend, refresh_interval: float = 0.5):
        self.backend = backend
        self.refresh_interval = refresh_interval
        self._running = True
        self._lock = threading.Lock()
        self._console = console.Console()

    def run(self):
        """启动 TUI 主循环"""
        backend.add_state_callback(self._on_state_change)

        # 注册键盘监听
        import keyboard
        def listen_keys():
            while self._running:
                if keyboard.is_pressed("a") and backend.state == "ready":
                    backend.run_now()
                time.sleep(0.1)
        threading.Thread(target=listen_keys, daemon=True).start()

        # 创建 Live Display
        with Live(self._build_layout(), refresh_per_second=2) as live:
            while self._running:
                live.update(self._build_layout())
                time.sleep(self.refresh_interval)

    def _build_layout(self) -> Layout:
        """构建当前显示布局"""
        state = self.backend.state
        project = self.backend.project_info or {}

        # 状态面板
        state_lines = []
        if state == "waiting":
            state_lines = ["扫描 Vivado 中..."]
        elif state == "ready":
            state_lines = [
                "[green]Vivado 已连接[/green]",
                "按 [bright_cyan]A[/bright_cyan] 触发分析",
            ]
        elif state == "analyzing":
            state_lines = ["[[yellow]分析中...[/yellow]]"]

        state_text = "\n".join(state_lines)
        state_panel = Panel(
            Text(state_text),
            title="VMC 状态",
            border_style="blue",
        )

        # 项目信息面板
        project_lines = []
        if project:
            project_lines = [
                f"项目: {project.get('name', 'N/A')}",
                f"器件: {project.get('part', 'N/A')}",
            ]
        project_panel = Panel(
            Text("\n".join(project_lines)),
            title="项目信息",
            border_style="cyan",
        )

        # 分析结果面板
        result_panel = Panel("", title="分析结果", border_style="green")
        if state == "results" and self.backend.analysis_result:
            result = self.backend.analysis_result
            if result and not result.get("error"):
                score_color = "green" if result.get("score", 0) >= 80 else "red"
                result_panel = Panel(
                    f"[{score_color}]评分: {result.get('score', 0)}/100[/]\n"
                    f"问题数: {result.get('total_issues', 0)}\n\n",
                    title="分析结果",
                    border_style=score_color,
                )

        return Layout(state_panel, project_panel, result_panel)

    def _on_state_change(self, new_state: str):
        """状态变化回调"""
        with self._lock:
            if new_state == "results":
                self._show_results()
            else:
                self._last_state = new_state

    def _show_results(self):
        """显示分析结果详情"""
        result = self.backend.analysis_result
        if not result or result.get("error"):
            return

        self._console.print(Rule(style="bright_cyan"))
        self._console.print(f"[green]评分: {result.get('score', 0)}/100[/green]")
        self._console.print(f"问题数: {result.get('total_issues', 0)}")
        self._console.print()

        # 显示问题列表
        issues = result.get("issues", [])
        if issues:
            table = Table(show_header=True)
            table.add_column("严重性", style="bold")
            table.add_column("规则ID")
            table.add_column("消息")
            table.add_column("位置")

            for issue in issues:
                table.add_row(
                    issue.get("severity", ""),
                    issue.get("rule_id", ""),
                    issue.get("message", "")[:50],
                    issue.get("location", "")[:20],
                )
            self._console.print(table)
