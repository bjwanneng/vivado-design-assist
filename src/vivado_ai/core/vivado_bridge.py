"""
Vivado Bridge 模块

提供与 Xilinx Vivado 的交互能力：
- 执行 TCL 命令/脚本
- 读取/解析报告文件
- 监听 Vivado 输出
- 管理设计检查点（DCP）
"""

import subprocess
import tempfile
import os
import re
import time
import threading
import queue
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, Generator, Any, Union
from contextlib import contextmanager
import json


@dataclass
class VivadoResult:
    """Vivado 执行结果"""
    returncode: int
    stdout: str
    stderr: str
    duration: float  # 执行耗时（秒）
    log_file: Optional[str] = None
    command: Optional[str] = None  # 执行的命令

    @property
    def success(self) -> bool:
        """是否执行成功"""
        return self.returncode == 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration": self.duration,
            "success": self.success,
            "command": self.command,
        }


@dataclass
class BuildStatus:
    """编译状态"""
    status: str  # "idle" | "running" | "completed" | "failed"
    stage: Optional[str] = None  # "synthesis" | "optimization" | "placement" | "routing"
    progress: float = 0.0  # 0-100
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    message: str = ""
    error: Optional[str] = None

    @property
    def duration(self) -> Optional[float]:
        """运行时长"""
        if self.start_time:
            end = self.end_time or time.time()
            return end - self.start_time
        return None


class VivadoBridge:
    """
    Vivado TCL 桥接类

    提供与 Vivado 的交互能力，支持：
    1. 执行 TCL 命令/脚本
    2. 读取/解析报告文件
    3. 监听 Vivado 输出
    4. 管理设计检查点（DCP）

    示例：
        # 基本使用
        bridge = VivadoBridge(vivado_path="/tools/vivado/bin/vivado")
        result = bridge.execute_tcl("puts hello")

        # 上下文管理器
        with VivadoBridge() as bridge:
            result = bridge.execute_tcl("synth_design -top my_design")
    """

    # 编译阶段标识符
    STAGE_MARKERS = {
        "synthesis": ["Starting synthesis", "synth_design"],
        "optimization": ["Starting optimization", "opt_design"],
        "placement": ["Starting placement", "place_design"],
        "routing": ["Starting routing", "route_design"],
        "bitstream": ["Writing bitstream", "write_bitstream"],
    }

    def __init__(
        self,
        vivado_path: str = "vivado",
        work_dir: str = "./vivado_work",
        mode: str = "batch",
        timeout: int = 3600,
        logger: Optional[Any] = None,
    ):
        """
        初始化 Vivado Bridge

        Args:
            vivado_path: Vivado 可执行文件路径
            work_dir: 工作目录
            mode: 运行模式 (batch / tcl)
            timeout: 默认超时时间（秒）
            logger: 日志记录器
        """
        self.vivado_path = vivado_path
        self.work_dir = Path(work_dir)
        self.mode = mode
        self.default_timeout = timeout
        self.logger = logger

        # 创建工作目录
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # 进程管理
        self._process: Optional[subprocess.Popen] = None
        self._output_queue: queue.Queue = queue.Queue()
        self._watch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 状态
        self._last_result: Optional[VivadoResult] = None
        self._build_status = BuildStatus(status="idle")

        # 缓存
        self._cache: Dict[str, Any] = {}

    def _log(self, level: str, message: str) -> None:
        """记录日志"""
        if self.logger:
            getattr(self.logger, level, print)(message)
        else:
            print(f"[{level.upper()}] {message}")

    def check_vivado(self) -> bool:
        """
        检查 Vivado 是否可用

        Returns:
            bool: Vivado 是否可用
        """
        try:
            result = subprocess.run(
                [self.vivado_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                self._log("info", f"Vivado found: {result.stdout.split(chr(10))[0]}")
                return True
        except FileNotFoundError:
            self._log("error", f"Vivado not found at: {self.vivado_path}")
        except Exception as e:
            self._log("error", f"Error checking Vivado: {e}")
        return False

    def execute_tcl(
        self,
        tcl_code: str,
        timeout: Optional[int] = None,
        capture_output: bool = True,
        env: Optional[Dict[str, str]] = None,
    ) -> VivadoResult:
        """
        执行 TCL 代码

        Args:
            tcl_code: TCL 代码字符串
            timeout: 超时时间（秒），None 表示使用默认值
            capture_output: 是否捕获输出
            env: 环境变量

        Returns:
            VivadoResult: 执行结果

        Example:
            >>> bridge = VivadoBridge()
            >>> result = bridge.execute_tcl("puts hello")
            >>> if result.success:
            ...     print(result.stdout)
        """
        timeout = timeout or self.default_timeout
        start_time = time.time()

        # 创建临时 TCL 文件
        tcl_file = self.work_dir / f"tmp_{os.getpid()}_{threading.current_thread().ident}_{int(start_time*1000)}.tcl"
        tcl_file.write_text(tcl_code, encoding="utf-8")

        try:
            # 构建命令
            cmd = [
                self.vivado_path,
                "-mode", self.mode,
                "-source", str(tcl_file),
                "-nolog",
                "-nojournal",
            ]

            self._log("debug", f"Executing: {' '.join(cmd)}")

            # 执行
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                env={**os.environ, **(env or {})},
            )

            duration = time.time() - start_time

            vivado_result = VivadoResult(
                returncode=result.returncode,
                stdout=result.stdout if capture_output else "",
                stderr=result.stderr if capture_output else "",
                duration=duration,
                command=tcl_code[:200] + "..." if len(tcl_code) > 200 else tcl_code,
            )

            self._last_result = vivado_result

            if not vivado_result.success:
                self._log("warning", f"TCL execution failed: {vivado_result.stderr[:500]}")

            return vivado_result

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            self._log("error", f"TCL execution timed out after {timeout}s")
            return VivadoResult(
                returncode=-1,
                stdout="",
                stderr=f"Timeout after {timeout} seconds",
                duration=duration,
                command=tcl_code[:200],
            )

        except Exception as e:
            duration = time.time() - start_time
            self._log("error", f"Error executing TCL: {e}")
            return VivadoResult(
                returncode=-1,
                stdout="",
                stderr=str(e),
                duration=duration,
                command=tcl_code[:200],
            )

        finally:
            # 清理临时文件
            try:
                tcl_file.unlink(missing_ok=True)
            except Exception as e:
                self._log("warning", f"Failed to cleanup temp file: {e}")

    def execute_script(
        self,
        script_path: Union[str, Path],
        args: Optional[List[str]] = None,
        timeout: Optional[int] = None,
    ) -> VivadoResult:
        """
        执行 TCL 脚本文件

        Args:
            script_path: TCL 脚本路径
            args: 传递给脚本的参数
            timeout: 超时时间

        Returns:
            VivadoResult: 执行结果
        """
        script_path = Path(script_path)
        if not script_path.exists():
            return VivadoResult(
                returncode=-1,
                stdout="",
                stderr=f"Script not found: {script_path}",
                duration=0.0,
            )

        cmd = [
            self.vivado_path,
            "-mode", "batch",
            "-source", str(script_path),
        ]

        if args:
            cmd.extend(["-tclargs"] + args)

        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self.default_timeout,
            )
            duration = time.time() - start_time

            return VivadoResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration=duration,
                command=str(script_path),
            )

        except subprocess.TimeoutExpired:
            return VivadoResult(
                returncode=-1,
                stdout="",
                stderr="Timeout",
                duration=time.time() - start_time,
            )

    def watch_directory(
        self,
        directory: Union[str, Path],
        callback: Optional[Callable[[Dict], None]] = None,
        patterns: Optional[List[str]] = None,
        interval: float = 2.0,
    ) -> None:
        """
        监听目录变化

        Args:
            directory: 要监听的目录
            callback: 检测到变化时的回调函数
            patterns: 要监听的文件模式列表（如 ['*.rpt', '*.dcp']）
            interval: 检查间隔（秒）
        """
        directory = Path(directory)
        if not directory.exists():
            self._log("warning", f"Watch directory does not exist: {directory}")
            return

        patterns = patterns or ["*.rpt", "*.dcp"]
        self._stop_event.clear()

        def watcher():
            last_mtime: Dict[Path, float] = {}

            # 初始化文件状态
            for pattern in patterns:
                for filepath in directory.rglob(pattern):
                    if filepath.is_file():
                        last_mtime[filepath] = filepath.stat().st_mtime

            self._log("info", f"Started watching {directory} for patterns: {patterns}")

            while not self._stop_event.is_set():
                try:
                    changes = []

                    for pattern in patterns:
                        for filepath in directory.rglob(pattern):
                            if not filepath.is_file():
                                continue

                            current_mtime = filepath.stat().st_mtime

                            if filepath not in last_mtime:
                                # 新文件
                                last_mtime[filepath] = current_mtime
                                changes.append({
                                    "type": "created",
                                    "path": str(filepath),
                                    "filename": filepath.name,
                                })
                            elif last_mtime[filepath] != current_mtime:
                                # 文件修改
                                last_mtime[filepath] = current_mtime
                                changes.append({
                                    "type": "modified",
                                    "path": str(filepath),
                                    "filename": filepath.name,
                                })

                    # 检查删除的文件
                    current_files = set()
                    for pattern in patterns:
                        for filepath in directory.rglob(pattern):
                            if filepath.is_file():
                                current_files.add(filepath)

                    removed = set(last_mtime.keys()) - current_files
                    for filepath in removed:
                        del last_mtime[filepath]
                        changes.append({
                            "type": "deleted",
                            "path": str(filepath),
                            "filename": filepath.name,
                        })

                    # 调用回调
                    if changes and callback:
                        for change in changes:
                            try:
                                callback(change)
                            except Exception as e:
                                self._log("error", f"Callback error: {e}")

                    self._stop_event.wait(interval)

                except Exception as e:
                    self._log("error", f"Watcher error: {e}")
                    self._stop_event.wait(5)

        self._watch_thread = threading.Thread(target=watcher, daemon=True)
        self._watch_thread.start()

    def stop_watch(self) -> None:
        """停止监听"""
        self._stop_event.set()
        if self._watch_thread and self._watch_thread.is_alive():
            self._watch_thread.join(timeout=5)
        self._log("info", "Stopped watching")

    def get_build_status(self) -> BuildStatus:
        """获取当前编译状态"""
        return self._build_status

    def read_checkpoint(
        self,
        dcp_path: Union[str, Path],
        extract_details: bool = False,
    ) -> Dict[str, Any]:
        """
        读取设计检查点（DCP）信息

        Args:
            dcp_path: DCP 文件路径
            extract_details: 是否提取详细信息（需要更多时间）

        Returns:
            Dict: DCP 中包含的关键信息
        """
        dcp_path = Path(dcp_path)
        if not dcp_path.exists():
            return {"error": f"DCP file not found: {dcp_path}"}

        tcl_code = f"""
set dcp_path "{dcp_path}"
open_checkpoint $dcp_path

# 基本信息
set part [get_property PART [current_design]]
set top [get_property TOP [current_design]]
set cells [get_cells -hierarchical]
set nets [get_nets -hierarchical]

puts "DCP_INFO_START"
puts "file: $dcp_path"
puts "part: $part"
puts "top: $top"
puts "cell_count: [llength $cells]"
puts "net_count: [llength $nets]"
"""

        if extract_details:
            tcl_code += """
# 资源统计
set lut_count 0
set ff_count 0
set bram_count 0
set dsp_count 0

foreach cell $cells {
    set ref_name [get_property REF_NAME $cell]
    if {[string match "LUT*" $ref_name]} {
        incr lut_count
    } elseif {[string match "FD*" $ref_name] || [string match "FDRE" $ref_name]} {
        incr ff_count
    } elseif {[string match "RAMB*" $ref_name]} {
        incr bram_count
    } elseif {[string match "DSP*" $ref_name]} {
        incr dsp_count
    }
}

puts "lut_count: $lut_count"
puts "ff_count: $ff_count"
puts "bram_count: $bram_count"
puts "dsp_count: $dsp_count"

# 时钟信息
set clocks [get_clocks]
puts "clock_count: [llength $clocks]"
foreach clk $clocks {
    set period [get_property PERIOD $clk]
    puts "clock: [get_property NAME $clk] period: $period"
}
"""

        tcl_code += """
puts "DCP_INFO_END"
close_design
"""

        result = self.execute_tcl(tcl_code)

        if not result.success:
            return {
                "error": "Failed to read DCP",
                "stderr": result.stderr,
            }

        # 解析输出
        dcp_info: Dict[str, Any] = {}
        in_info_block = False

        for line in result.stdout.split('\n'):
            line = line.strip()

            if line == "DCP_INFO_START":
                in_info_block = True
                continue
            elif line == "DCP_INFO_END":
                in_info_block = False
                continue

            if in_info_block and ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()

                # 尝试转换为数字
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass

                dcp_info[key] = value

        return dcp_info

    def create_project_tcl(
        self,
        project_name: str,
        part: str,
        top_module: str,
        sources: List[Union[str, Path]],
        constraints: Optional[List[Union[str, Path]]] = None,
        ip_files: Optional[List[Union[str, Path]]] = None,
    ) -> str:
        """
        生成创建 Vivado 项目的 TCL 脚本

        Args:
            project_name: 项目名称
            part: FPGA 器件型号
            top_module: 顶层模块名
            sources: RTL 源文件列表
            constraints: 约束文件列表
            ip_files: IP 文件列表

        Returns:
            str: TCL 脚本内容
        """
        tcl_lines = [
            f"# Auto-generated by Vivado AI Design Assist",
            f"# Created at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"# Create project",
            f"create_project {project_name} ./ -part {part} -force",
            f"",
            f"# Set top module",
            f"set_property top {top_module} [current_fileset]",
            f"",
            f"# Add sources",
        ]

        # 添加源文件
        for src in sources:
            src_path = Path(src).resolve()
            tcl_lines.append(f'add_files "{src_path}"')

        # 添加约束文件
        if constraints:
            tcl_lines.extend([
                f"",
                f"# Add constraints",
            ])
            for constr in constraints:
                constr_path = Path(constr).resolve()
                tcl_lines.append(f'add_files -fileset constrs_1 "{constr_path}"')

        # 添加 IP
        if ip_files:
            tcl_lines.extend([
                f"",
                f"# Add IPs",
            ])
            for ip in ip_files:
                ip_path = Path(ip).resolve()
                tcl_lines.append(f'add_files "{ip_path}"')

        tcl_lines.extend([
            f"",
            f"# Refresh hierarchy",
            f"update_compile_order -fileset sources_1",
            f"",
            f"puts \"Project created successfully: {project_name}\"",
        ])

        return "\n".join(tcl_lines)

    def build_tcl(
        self,
        top_module: str,
        part: str,
        steps: Optional[List[str]] = None,
        jobs: int = 4,
        directives: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        生成完整构建流程的 TCL 脚本

        Args:
            top_module: 顶层模块名
            part: FPGA 器件型号
            steps: 构建步骤（默认全部）
            jobs: 并行任务数
            directives: 各阶段的 directive

        Returns:
            str: TCL 脚本内容
        """
        steps = steps or ["synthesis", "optimization", "placement", "routing", "bitstream"]
        directives = directives or {}

        tcl_lines = [
            f"# Build script for {top_module}",
            f"set top_module {top_module}",
            f"set part {part}",
            f"",
        ]

        if "synthesis" in steps:
            synth_directive = directives.get("synthesis", "")
            directive_str = f" -directive {synth_directive}" if synth_directive else ""
            tcl_lines.extend([
                f"# Synthesis",
                f"synth_design -top $top_module -part $part{directive_str}",
                f"write_checkpoint -force ./post_synth.dcp",
                f"",
            ])

        if "optimization" in steps:
            tcl_lines.extend([
                f"# Optimization",
                f"opt_design",
                f"power_opt_design",
                f"",
            ])

        if "placement" in steps:
            place_directive = directives.get("placement", "")
            directive_str = f" -directive {place_directive}" if place_directive else ""
            tcl_lines.extend([
                f"# Placement",
                f"place_design{directive_str}",
                f"phys_opt_design",
                f"",
            ])

        if "routing" in steps:
            route_directive = directives.get("routing", "")
            directive_str = f" -directive {route_directive}" if route_directive else ""
            tcl_lines.extend([
                f"# Routing",
                f"route_design{directive_str}",
                f"phys_opt_design",
                f"write_checkpoint -force ./post_route.dcp",
                f"",
            ])

        if "bitstream" in steps:
            tcl_lines.extend([
                f"# Bitstream",
                f"write_bitstream -force ./{top_module}.bit",
                f"",
            ])

        # 生成报告
        tcl_lines.extend([
            f"# Reports",
            f"report_timing_summary -file ./timing_summary.rpt",
            f"report_utilization -file ./utilization.rpt",
            f"report_power -file ./power.rpt",
            f"",
            f"puts \"Build completed successfully\"",
        ])

        return "\n".join(tcl_lines)

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.stop_watch()
        return False

    def __repr__(self) -> str:
        return f"VivadoBridge(path={self.vivado_path}, work_dir={self.work_dir})"
