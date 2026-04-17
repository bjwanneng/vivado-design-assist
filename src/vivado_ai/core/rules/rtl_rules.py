"""
Group B: RTL 编码规范规则 (RTL-*)

Phase 2: 基于 regex 的静态检查。
Phase 3 将升级为 pyverilog AST 分析。
"""

import re
from pathlib import Path

from vivado_ai.core.rules.base import Rule, RuleResult
from vivado_ai.core.rules.registry import RuleRegistry
from vivado_ai.models.finding import Findings
from vivado_ai.models.issue import Severity


@RuleRegistry.register
class CombinationalLoop(Rule):
    """RTL-001: 组合逻辑环路"""
    id = "RTL-001"
    name = "Combinational Logic Loop"
    group = "B"
    severity = Severity.FAIL
    ug949_ref = "Ch3: RTL Coding"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if "combinational loop" in msg.text.lower():
                issues.append(self._create_issue(
                    message=f"Combinational loop detected: {msg.text}",
                    detail="Combinational loops cause timing analysis issues "
                           "and can lead to oscillation.",
                    fix_suggestion=(
                        "Break the combinational loop by:\n"
                        "1. Adding a register in the feedback path\n"
                        "2. Restructuring the combinational logic"
                    ),
                    location=msg.source,
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class LatchFromIncompleteCase(Rule):
    """RTL-002: case/if 不完整导致 Latch"""
    id = "RTL-002"
    name = "Latch from Incomplete Case/If"
    group = "B"
    severity = Severity.WARN
    ug949_ref = "Ch3: Latch"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if msg.code == "Synth 8-327":
                issues.append(self._create_issue(
                    message=f"Latch inferred (RTL coding issue): {msg.text}",
                    detail="Incomplete if/case branch — signal not assigned in all paths.",
                    fix_suggestion=(
                        "Ensure all branches assign the signal:\n"
                        "- Add 'default:' with full assignments in case\n"
                        "- Add 'else' clause in if statements\n"
                        "- Assign signal before the case/if block"
                    ),
                    location=msg.source,
                    severity=Severity.WARN,
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class CDCNoSynchronizer(Rule):
    """RTL-003: CDC 无同步器"""
    id = "RTL-003"
    name = "CDC Without Synchronizer"
    group = "B"
    severity = Severity.FAIL
    ug949_ref = "Ch3: CDC"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        # 检查 methodology_checks 中的 CDC 相关问题
        if findings.methodology_checks:
            for check in findings.methodology_checks:
                if "CDC" in check.check_id or "cdc" in check.message.lower():
                    issues.append(self._create_issue(
                        message=f"CDC issue: {check.message}",
                        detail=f"Check ID: {check.check_id}",
                        fix_suggestion=(
                            "Add proper CDC synchronization:\n"
                            "1. Use 2-FF synchronizer for single-bit signals\n"
                            "2. Use async FIFO or handshake for multi-bit buses\n"
                            "3. Add set_clock_groups for async clock domains\n"
                            "4. Consider using XPM_CDC macros"
                        ),
                    ))

        # 检查 clock_interactions 中的 unsafe/no
        if findings.clock_interactions:
            unsafe = [
                i for i in findings.clock_interactions
                if i.inter_class in ("unsafe", "no")
            ]
            if unsafe and not any("CDC" in i.rule_id for i in issues):
                issues.append(self._create_issue(
                    message=f"{len(unsafe)} unsafe clock domain crossing(s) "
                            f"without proper constraints",
                    detail="Unsafe inter-clock paths found",
                    fix_suggestion=(
                        "1. Add set_clock_groups -asynchronous for async domains\n"
                        "2. Implement proper CDC synchronizers in RTL\n"
                        "3. Use XPM_CDC macros for safe crossing"
                    ),
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class BRAMOutputUnregistered(Rule):
    """RTL-004: BRAM 输出无寄存器"""
    id = "RTL-004"
    name = "BRAM Output Unregistered"
    group = "B"
    severity = Severity.WARN
    ug949_ref = "Ch3: RAM"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if msg.code == "Synth 8-3936" and "ram" in msg.text.lower():
                issues.append(self._create_issue(
                    message=f"RAM may not use block RAM optimally: {msg.text}",
                    fix_suggestion=(
                        "Ensure block RAM inference:\n"
                        "1. Use synchronous read (clocked read)\n"
                        "2. Register the output: add output register stage\n"
                        "3. Set RAM primitive: (* ram_style = \"block\" *)\n"
                        "4. Or use XPM_MEMORY macro"
                    ),
                    location=msg.source,
                    severity=Severity.WARN,
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class SRLAsyncResetConflict(Rule):
    """RTL-005: SRL 异步复位冲突"""
    id = "RTL-005"
    name = "SRL with Async Reset Conflict"
    group = "B"
    severity = Severity.WARN
    ug949_ref = "Ch3: SRL"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if "SRL" in msg.text and (
                "reset" in msg.text.lower() or "async" in msg.text.lower()
            ):
                issues.append(self._create_issue(
                    message=f"SRL with async reset: {msg.text}",
                    fix_suggestion=(
                        "SRL primitives don't support async reset natively.\n"
                        "1. Use synchronous reset instead\n"
                        "2. Or set: (* srl_style = \"register\" *)\n"
                        "3. Use XPM_SRL macro for portability"
                    ),
                    location=msg.source,
                    severity=Severity.WARN,
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class DSP48RegisterStages(Rule):
    """RTL-006: DSP48 寄存器级不足"""
    id = "RTL-006"
    name = "DSP48 Register Stages Insufficient"
    group = "B"
    severity = Severity.WARN
    ug949_ref = "Ch3: DSP"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if msg.code == "Synth 8-3936" and "dsp" in msg.text.lower():
                issues.append(self._create_issue(
                    message=f"DSP not fully pipelined: {msg.text}",
                    fix_suggestion=(
                        "Enable all DSP48 pipeline registers:\n"
                        "(* use_dsp48 = \"yes\" *)\n"
                        "Set AREG=1, BREG=1, MREG=1, PREG=1 in XDC:\n"
                        "set_property AREG 1 [get_cells ...]\n"
                        "Or use XPM_DSP macro"
                    ),
                    location=msg.source,
                    severity=Severity.WARN,
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class GlobalResetMisuse(Rule):
    """RTL-007: 全局复位使用不当"""
    id = "RTL-007"
    name = "Global Reset Misuse"
    group = "B"
    severity = Severity.INFO
    ug949_ref = "Ch3: Reset"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        # 检查是否有大量同步复位（可能导致控制集问题）
        reset_msgs = [
            m for m in findings.synth_log.messages
            if "reset" in m.text.lower() and m.level == "WARNING"
        ]
        if len(reset_msgs) > 3:
            issues.append(self._create_issue(
                message=f"Multiple reset-related warnings: {len(reset_msgs)}",
                detail="UG949 Ch3: Consider reset strategy carefully.",
                fix_suggestion=(
                    "UG949 reset guidelines:\n"
                    "1. Use synchronous reset for FPGA (not async)\n"
                    "2. Only reset functional registers, not datapath\n"
                    "3. Let BRAM/DSP initialize via GSR\n"
                    "4. Avoid global reset trees — use local resets"
                ),
                severity=Severity.INFO,
            ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class HighFanoutUnmarked(Rule):
    """RTL-008: 高扇出信号未标记 MAX_FANOUT"""
    id = "RTL-008"
    name = "High Fanout Signal Unmarked"
    group = "B"
    severity = Severity.WARN
    ug949_ref = "Ch3: Fanout"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if "high fanout" in msg.text.lower():
                issues.append(self._create_issue(
                    message=f"High fanout signal: {msg.text}",
                    fix_suggestion=(
                        "Add MAX_FANOUT attribute:\n"
                        "(* MAX_FANOUT = 32 *) reg signal;\n"
                        "Or in XDC:\n"
                        "set_property MAX_FANOUT 32 [get_nets signal]"
                    ),
                    location=msg.source,
                    severity=Severity.WARN,
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class MUXMisuse(Rule):
    """RTL-009: 大 MUX 应使用 MUXF7/MUXF8"""
    id = "RTL-009"
    name = "Wide MUX Should Use MUXF7/MUXF8"
    group = "B"
    severity = Severity.INFO
    ug949_ref = "Ch3: LUT Optimization"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        for msg in findings.synth_log.messages:
            if "mux" in msg.text.lower() and "lut" in msg.text.lower():
                issues.append(self._create_issue(
                    message=f"Wide MUX using LUTs: {msg.text}",
                    fix_suggestion=(
                        "For wide MUX operations:\n"
                        "1. Use MUXF7/MUXF8 primitives\n"
                        "2. Use case statement for clean MUX inference\n"
                        "3. Consider pipelining the MUX select logic"
                    ),
                    location=msg.source,
                    severity=Severity.INFO,
                ))
        return RuleResult(rule_id=self.id, issues=issues)


@RuleRegistry.register
class NotUsingXPM(Rule):
    """RTL-010: 未使用 XPM 宏"""
    id = "RTL-010"
    name = "Not Using XPM Macros for RAM/FIFO"
    group = "B"
    severity = Severity.WARN
    ug949_ref = "Ch3: XPM"
    applicable_modes = ["analyze"]

    def check(self, findings: Findings) -> RuleResult:
        issues = []
        if not findings.synth_log:
            return RuleResult(rule_id=self.id)

        # 检查是否手动推断了 RAM/FIFO 而非使用 XPM
        ram_msgs = [
            m for m in findings.synth_log.messages
            if m.code in ("Synth 8-3936", "Synth 8-5537")
        ]
        if ram_msgs:
            issues.append(self._create_issue(
                message=f"RAM/FIFO inferred manually ({len(ram_msgs)} instances) "
                        f"— consider using XPM macros",
                detail="\n".join(m.text[:80] for m in ram_msgs[:3]),
                fix_suggestion=(
                    "Use XPM macros for portable, optimized inference:\n"
                    "1. xpm_memory_sdpram (Simple Dual Port RAM)\n"
                    "2. xpm_fifo_sync / xpm_fifo_async (FIFO)\n"
                    "3. xpm_memory_sprom (ROM)\n"
                    "XPM handles all device-specific optimizations automatically."
                ),
                severity=Severity.WARN,
            ))
        return RuleResult(rule_id=self.id, issues=issues)
