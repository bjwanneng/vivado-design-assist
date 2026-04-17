# Vivado Methodology Checker (VMC) - 产品需求文档 (PRD)

> 版本: v2.0
> 日期: 2026-04-17
> 状态: Draft
> 替代: v1.0 (AI Timing Report 分析方向)

---

## 1. 项目概述

### 1.1 背景

Xilinx Vivado 的 UltraFast Design Methodology (UG949) 定义了一套经过验证的 FPGA 设计最佳实践，覆盖从 RTL 编码到时序收敛的全流程。然而：

- **UG949 文档 200+ 页，鲜有工程师完整阅读**
- **Vivado 内置了 80+ 个 methodology 检查**（`report_methodology`），但输出几百行，难以快速定位关键问题
- **UG1292 定义了完整的时序收敛决策树**，但大部分工程师只跑 `report_timing_summary` 就完事
- **各阶段 log 大量 WARNING/CRITICAL WARNING 被忽视**，其中很多是时序失败的早期信号
- **问题在后期（布线后）才发现，返工成本高**；如果按方法论在前端就检查，很多问题可以避免

### 1.2 产品愿景

> **把 UG949/UltraFast Methodology 从一本没人看的文档，变成一个自动化的检查流程。**

核心定位：**Vivado Design Methodology Compliance Checker**

- 不让 AI 去 "猜" 时序问题（准确性不可控）
- 基于 UG949/UG1292 的确定性规则做检查（准确、可信赖）
- AI 的角色是 "解释" 和 "关联"，不是 "判断"
- 覆盖设计全生命周期：RTL 编码 → 约束 → 综合 → 布局 → 布线 → 时序收敛

### 1.3 目标用户

| 用户类型 | 占比 | 特征 | 核心需求 |
|---------|------|------|---------|
| **新手工程师** | ~30% | 不了解 UG949，不知道 Vivado 有哪些检查命令 | "告诉我哪里不符合规范" |
| **普通工程师** | ~40% | 知道方法论但懒得按步骤走，忽略 WARNING | "一键检查，别让我手动跑 10 个 report" |
| **资深工程师** | ~25% | 精通方法论，做设计评审时需要工具辅助 | "自动化检查 + 评审报告" |
| **团队负责人** | ~5% | 负责设计规范、代码审查、质量把关 | "团队设计质量度量 + 合规报告" |

### 1.4 成功指标

| 指标 | 当前基线 | MVP 目标 | Phase 2 目标 |
|------|---------|---------|-------------|
| 约束问题发现时间 | 布线后（几小时~几天） | 综合前（秒级） | 编码时（实时） |
| WARNING 处理率 | ~10%（大部分被忽略） | >80%（工具自动分级+解读） | >95% |
| 方法论违规遗漏率 | 高（人工检查不完整） | <5%（规则全覆盖） | <1% |
| 时序收敛迭代轮数 | 5-15 轮 | 减少 30% | 减少 60% |
| 设计评审准备时间 | 2-4 小时 | 15 分钟（自动生成报告） | 5 分钟 |

---

## 2. 产品形态

### 2.1 三种使用模式

```
┌──────────────────────────────────────────────────────────────────┐
│                  Vivado Methodology Checker                      │
├──────────────┬───────────────────┬───────────────────────────────┤
│   Mode 1     │    Mode 2         │         Mode 3                │
│   Lint       │    Check          │         Analyze               │
│              │                   │                               │
│  RTL + XDC   │  Vivado Reports   │    Stage Logs                 │
│  静态分析     │  + DCP 解读       │    综合log/布局log/布线log     │
│              │                   │                               │
│  不需要Vivado │  不需要Vivado运行  │    不需要Vivado运行            │
│              │  (解析报告文件)    │    (解析log文件)               │
├──────────────┼───────────────────┼───────────────────────────────┤
│  编码阶段     │  综合后/实现后     │    编译完成后                  │
│  实时反馈     │  合规检查          │    问题定位                    │
└──────────────┴───────────────────┴───────────────────────────────┘
```

#### Mode 1: Lint（编码阶段，不需要 Vivado）

```bash
# 检查 RTL 和 XDC 的方法论合规性
vivado-ai lint --rtl src/ --xdc constraints/ --part xc7z020clg400-2
```

直接扫描源文件，在运行 Vivado 之前发现问题。

#### Mode 2: Check（综合/实现后，解析 Vivado 报告）

```bash
# 解析 Vivado 生成的报告文件
vivado-ai check --reports-dir build/reports/

# 或解析单个报告
vivado-ai check --timing timing_summary.rpt --utilization utilization.rpt
```

解析 `report_methodology`、`report_failfast`、`report_timing_summary` 等的输出文件。

#### Mode 3: Analyze（编译完成后，分析各阶段 Log）

```bash
# 分析完整编译流程的所有 log
vivado-ai analyze --log-dir build/

# 分析单个阶段 log
vivado-ai analyze --synth-log build/runme.log
vivado-ai analyze --place-log build/place_design.log
vivado-ai analyze --route-log build/route_design.log
```

解析 Vivado 各阶段 log 中的 WARNING、CRITICAL WARNING、INFO，按方法论分类。

---

## 3. 检查规则体系

### 3.1 规则总览

基于 UG949（UltraFast Design Methodology）和 UG1292（Timing Closure Quick Reference），提取以下检查规则：

```
┌─────────────────────────────────────────────────────────┐
│              UG949 Methodology Rules                     │
├─────────────┬───────────────────────────────────────────┤
│ Group A     │ Group B       │ Group C    │ Group D      │
│ 约束方法论   │ RTL 编码规范   │ 实现流程    │ 时序根因分析  │
│ (Ch3, Ch5)  │ (Ch3)         │ (Ch4)      │ (UG1292)     │
├─────────────┼───────────────┼────────────┼──────────────┤
│ CONST-001~  │ RTL-001~      │ IMPL-001~  │ ROOT-001~    │
│ CONST-010   │ RTL-010       │ IMPL-008   │ ROOT-006     │
└─────────────┴───────────────┴────────────┴──────────────┘

┌─────────────────────────────────────────────────────────┐
│              Stage Log Analysis Rules                     │
├─────────────┬───────────────┬────────────┬──────────────┤
│ Group E     │ Group F       │ Group G    │ Group H      │
│ 综合 Log     │ 优化 Log      │ 布局 Log    │ 布线 Log      │
└─────────────┴───────────────┴────────────┴──────────────┘
```

### 3.2 Group A: 约束方法论（UG949 Ch3, Ch5）

**对应 UG949 流程**：Ch5 "建立基线约束"（Baselining）

| ID | 检查项 | 严重性 | 检测方式 | UG949 参考 |
|----|--------|--------|---------|-----------|
| CONST-001 | 所有时钟是否有 `create_clock` 周期约束 | **FAIL** | 解析 XDC 文件 + `report_clock_networks` | Ch5: 建立基线 |
| CONST-002 | MMCM/PLL 输出是否用 `create_generated_clock` | **WARN** | 解析 XDC 文件 | Ch3: 时钟约束 |
| CONST-003 | I/O 端口是否有 `set_input_delay`/`set_output_delay` | **WARN** | 解析 XDC + `check_timing` | Ch5: I/O 延迟 |
| CONST-004 | 时钟域交互是否声明（`set_clock_groups`/`set_false_path`） | **FAIL** | `report_clock_interaction` | Ch5: 时钟交互 |
| CONST-005 | CDC 路径是否正确约束 | **FAIL** | `report_cdc` | Ch3: CDC |
| CONST-006 | 是否存在 unconstrained endpoints | **FAIL** | `check_timing` | Ch5: Check Timing |
| CONST-007 | 约束是否冲突 | **FAIL** | `report_methodology` (XDC-*) | Ch5: DRC |
| CONST-008 | 是否过度使用 `set_false_path` 掩盖问题 | **WARN** | 统计 false_path 数量 vs 端点数 | Ch5: 约束质量 |
| CONST-009 | `set_clock_uncertainty` 是否合理 | **INFO** | 解析 XDC | Ch5: 不确定性 |
| CONST-010 | 是否缺少 `set_multicycle_path`（CE 控制路径） | **WARN** | 分析 CE 信号路径 | Ch5: 时序例外 |

### 3.3 Group B: RTL 编码规范（UG949 Ch3）

| ID | 检查项 | 严重性 | 检测方式 | UG949 参考 |
|----|--------|--------|---------|-----------|
| RTL-001 | 组合逻辑环路 | **FAIL** | Verilog AST 分析 | Ch3: RTL 编码 |
| RTL-002 | 意外 Latch 生成（不完整 case/if） | **WARN** | 检查 case/if 覆盖性 | Ch3: Latch |
| RTL-003 | CDC 无同步器（跨时钟域信号无 2-FF 同步） | **FAIL** | 时钟域追踪 | Ch3: CDC |
| RTL-004 | BRAM 输出无寄存器（DOA_REG/DOB_REG=0） | **WARN** | 模式匹配 | Ch3: RAM |
| RTL-005 | SRL 与异步 reset 冲突 | **WARN** | 检查 SRL+reset 组合 | Ch3: SRL |
| RTL-006 | DSP48 寄存器级数不足（影响时序） | **WARN** | 检查 AREG/BREG/MREG/PREG | Ch3: DSP |
| RTL-007 | 全局复位使用不当（GSR vs 同步复位） | **INFO** | 检查 reset 策略 | Ch3: 复位 |
| RTL-008 | 高 fanout 信号（>5000）未标记 `MAX_FANOUT` | **WARN** | 综合后报告 | Ch3: Fanout |
| RTL-009 | MUX 使用不当（应使用 MUXF7/MUXF8） | **INFO** | 检查宽 MUX 逻辑 | Ch3: LUT 优化 |
| RTL-010 | 未使用 XPM 宏（自行推断 RAM/FIFO） | **WARN** | 检查 RAM/FIFO 推断方式 | Ch3: XPM |

### 3.4 Group C: 实现流程方法论（UG949 Ch4 + UG1292）

| ID | 检查项 | 严重性 | 检测方式 | UG949 参考 |
|----|--------|--------|---------|-----------|
| IMPL-001 | 是否在综合后先做约束基线检查再实现 | **WARN** | 流程编排检查 | Ch5: Baseline |
| IMPL-002 | 是否运行了 `report_methodology` | **WARN** | 日志检查 | Ch4: DRC |
| IMPL-003 | 是否尝试过多个 `place_design` directive | **INFO** | 日志/策略记录 | Ch4: 实现 |
| IMPL-004 | 拥塞等级 ≥ 4（严重拥塞） | **FAIL** | `report_design_analysis -congestion` | UG1292 |
| IMPL-005 | SLR 利用率不均衡（差值 > 20%） | **WARN** | `report_failfast -by_slr` | UG1292: SSI |
| IMPL-006 | Control set 占比 > 7.5% | **WARN** | `report_failfast` | UG1292 |
| IMPL-007 | 是否使用了增量编译（相似度 > 95%） | **INFO** | 编译日志 | UG949: 增量 |
| IMPL-008 | 是否运行了 `report_qor_suggestions` | **INFO** | 日志检查 | Ch4: QoR |

### 3.5 Group D: 时序根因分析（UG1292 决策树）

当 WNS < 0 时，按 UG1292 决策树逐条检查：

| ID | 检查项 | 触发条件 | 建议动作 | UG1292 参考 |
|----|--------|---------|---------|-------------|
| ROOT-001 | 逻辑延迟 > 50% 数据路径延迟 | WNS < 0 | 减少逻辑级数、加流水线、LUT remap | "Reducing Logic Delay" |
| ROOT-002 | 布线延迟 > 50% 数据路径延迟 | WNS < 0 | 降低拥塞、高 fanout 处理、物理优化 | "Reducing Net Delay" |
| ROOT-003 | 时钟 skew > 0.5ns | Setup/Hold violation | 优化时钟树、CLOCK_DELAY_GROUP | "Improving Clock Skew" |
| ROOT-004 | 时钟 uncertainty > 0.1ns | Setup violation | 优化 MMCM/PLL、BUFGCE_DIV | "Improving Clock Uncertainty" |
| ROOT-005 | Hold detour > 0 | Fmax 受限 | 减少 hold fix 干扰 | "Fixing Setup Violations Due to Hold Detours" |
| ROOT-006 | 路径跨越 SLR 边界 | WNS < 0 | SLR 分区优化、USER_SLR_ASSIGNMENT | "Improving SLR Crossing Performance" |

---

## 4. Stage Log 分析规则

### 4.1 总体设计思路

Vivado 在综合、优化、布局、布线各阶段产生大量 log 输出，包含：
- **ERROR**：致命错误，设计无法继续
- **CRITICAL WARNING**：严重警告，通常影响 QoR 或时序
- **WARNING**：一般警告，部分可忽略
- **INFO**：信息性输出，包含性能数据

**痛点**：一个中等规模设计的完整编译 log 可能有 5000-20000 行，其中 WARNING 可能有几百条。工程师通常直接跳过 WARNING，但其中很多是时序失败的早期信号。

**工具做什么**：自动解析各阶段 log，按 UG949 方法论分类，过滤噪音，突出关键信息。

### 4.2 Group E: 综合 Log 分析

综合阶段是发现设计问题的第一道关卡。综合 log 包含大量关于 RTL 质量、资源推断、优化决策的信息。

| ID | 检查项 | 严重性 | Log 匹配模式 | 说明 |
|----|--------|--------|-------------|------|
| SYNTH-001 | 未推断为 Block RAM（使用了 LUTRAM） | **WARN** | `Synth 8-3936` / `Synth 8-5537` | UG949 Ch3: 建议使用 XPM 或 ram_style 属性 |
| SYNTH-002 | 推断了意外的 Latch | **FAIL** | `Synth 8-327` / `Synth 8-3352` | UG949 Ch3: 不完整的 if/case 语句 |
| SYNTH-003 | 多驱动信号 | **FAIL** | `Synth 8-3352` / `Netlist 29-58` | 严重的 RTL 错误 |
| SYNTH-004 | DSP 推断失败（回退到 LUT 实现） | **WARN** | `Synth 8-3936` (乘法器相关) | 检查 use_dsp48 属性 |
| SYNTH-005 | 端口未连接 | **WARN** | `Synth 8-3331` / `Synth 8-6014` | 可能是设计错误 |
| SYNTH-006 | 时钟驱动不正确（非专用时钟引脚） | **FAIL** | `Synth 8-524` / `CLOCK_DEDICATED_ROUTE` | UG949 Ch3: 时钟布线 |
| SYNTH-007 | DONT_TOUCH/KEEP 使用过多 | **WARN** | 统计 `DONT_TOUCH` / `MARK_DEBUG` 数量 | UG949 Ch4: 限制使用 |
| SYNTH-008 | 综合过程被 DONT_TOUCH 阻止优化 | **WARN** | `Synth 8-6416` | UG949 Ch4: 过度约束 |
| SYNTH-009 | case 语句未使用 full_case/parallel_case | **INFO** | `Synth 8-327` | 可能导致不必要逻辑 |
| SYNTH-010 | 资源利用率预估异常（某类资源 > 80%） | **WARN** | 综合后 utilization summary | UG949 Ch2: 资源规划 |
| SYNTH-011 | Retiming 未执行或效果不佳 | **INFO** | `Synth 8-XXXX` (retiming 相关) | UG949 Ch4: Retiming |
| SYNTH-012 | 存在 Gated Clock | **WARN** | `Synth 8-5543` / gated clock 相关 | UG949 Ch3: 使用 BUFGCE 替代 |

### 4.3 Group F: 优化 Log 分析（opt_design + power_opt_design）

| ID | 检查项 | 严重性 | Log 匹配模式 | 说明 |
|----|--------|--------|-------------|------|
| OPT-001 | 优化被 DONT_TOUCH 阻止 | **WARN** | `Opt 31-XX` (DONT_TOUCH 相关) | UG949 Ch4: 检查是否真的需要 DONT_TOUCH |
| OPT-002 | Control set 优化未执行 | **INFO** | opt_design summary | 考虑 `-control_set_merge` |
| OPT-003 | 高 fanout 网络未被 BUFG 缓冲 | **WARN** | `Opt 31-XX` (fanout 相关) | UG949 Ch3: CLOCK_BUFFER_TYPE |
| OPT-004 | LUT 合并导致拥塞 | **INFO** | `-no_lc` 相关建议 | UG949 Ch3: LUT 使用 |
| OPT-005 | 未执行 power_opt_design | **INFO** | 日志中无 power_opt_design 记录 | UG949 Ch4: 推荐流程 |

### 4.4 Group G: 布局 Log 分析（place_design + phys_opt_design）

| ID | 检查项 | 严重性 | Log 匹配模式 | 说明 |
|----|--------|--------|-------------|------|
| PLACE-001 | 布局拥塞（Level ≥ 3） | **FAIL** | `Place 30-XXX` congestion summary | UG1292: 拥塞处理 |
| PLACE-002 | 布局拥塞（Level ≥ 4，严重） | **CRITICAL** | `Place 30-XXX` (Level 4+) | UG1292: 必须处理 |
| PLACE-003 | SLR 分区不均衡 | **WARN** | `Place 30-XXX` SLR utilization | UG949 Ch2: SSI 设计 |
| PLACE-004 | 物理优化未执行 | **INFO** | 无 `phys_opt_design` 记录 | UG1292: 推荐 phys_opt 循环 |
| PLACE-005 | 物理优化效果不佳（WNS 未改善） | **WARN** | `Physopt 32-XX` WNS 前后对比 | UG1292: 尝试不同 directive |
| PLACE-006 | 物理优化被 DONT_TOUCH 阻止 | **WARN** | `Physopt 32-XX` DONT_TOUCH | UG949 Ch4: 限制 DONT_TOUCH |
| PLACE-007 | 高 fanout 复制不充分 | **WARN** | `Physopt 32-XX` replication summary | UG1292: Fanout 优化 |
| PLACE-008 | 关键路径跨越 SLR 边界 | **WARN** | 路径分析中包含 SLR crossing | UG1292: SLR 优化 |
| PLACE-009 | RAMB/DSP 放置冲突 | **WARN** | `Place 30-XXX` RAMB/DSP 相关 | UG949 Ch3: RAM/DSP 放置 |

### 4.5 Group H: 布线 Log 分析（route_design + post-route phys_opt）

| ID | 检查项 | 严重性 | Log 匹配模式 | 说明 |
|----|--------|--------|-------------|------|
| ROUTE-001 | 存在 Unrouted Nets | **CRITICAL** | `Route 35-XX` unrouted | 设计未完成布线 |
| ROUTE-002 | 布线拥塞导致 Detour | **FAIL** | `Route 35-XX` congestion detour | UG1292: 布线优化 |
| ROUTE-003 | Hold violation 严重（WHS < -0.5ns） | **FAIL** | `Route 35-XX` / timing summary | UG1292: Hold 修复 |
| ROUTE-004 | 布线后 WNS 恶化（比布局后更差） | **WARN** | 对比 place/route 后 WNS | UG1292: 过度约束建议 |
| ROUTE-005 | Post-route phys_opt 效果 | **INFO** | `Physopt 32-XX` post-route | UG1292: 仅建议 WNS > -0.2ns 时使用 |
| ROUTE-006 | 布线运行时间异常长（> 2x 预期） | **WARN** | 运行时间记录 | 可能存在严重拥塞 |
| ROUTE-007 | DRC 违例（布线后） | **FAIL** | `DRC XX-XX` | UG949 Ch4: DRC |
| ROUTE-008 | 时序收敛未达标（WNS < 0） | **FAIL** | 最终 timing summary | 触发 ROOT-* 根因分析 |
| ROUTE-009 | Clock skew 异常 | **WARN** | `Route 35-XX` / timing report | UG1292: Clock 优化 |

### 4.6 Group I: 全流程 Log 汇总分析

| ID | 检查项 | 严重性 | 检测方式 | 说明 |
|----|--------|--------|---------|------|
| FLOW-001 | 各阶段 CRITICAL WARNING 统计及趋势 | **WARN** | 跨阶段汇总 | 关注 CRITICAL WARNING 数量变化 |
| FLOW-002 | WNS 在各阶段的演变趋势 | **INFO** | 提取各阶段 timing summary | WNS 从综合到布线的变化 |
| FLOW-003 | 资源利用率在各阶段的变化 | **INFO** | 提取各阶段 utilization | 关注资源增长异常 |
| FLOW-004 | 被重复报告的问题（多阶段同现） | **WARN** | 跨阶段去重+关联 | 同一个问题在多个阶段出现 |
| FLOW-005 | 总编译时间及各阶段占比 | **INFO** | 提取时间戳 | 识别瓶颈阶段 |

---

## 5. 详细交互设计

### 5.1 Mode 1: Lint

```bash
$ vivado-ai lint --rtl src/ --xdc constraints/ --part xc7z020clg400-2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Vivado Methodology Checker — Lint Mode (Pre-Synthesis)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scanning 47 Verilog files, 3 XDC files...

━━━ Clock Constraints (Group A) ━━━

  [PASS] CONST-001: All 5 clocks have period constraints
  [FAIL] CONST-004: 2 clock pairs without interaction constraints
    → clk_spi and clk_sys: no set_clock_groups or set_false_path
    → clk_adc and clk_sys: no set_clock_groups or set_false_path
    → Fix: set_clock_groups -asynchronous -group [get_clocks clk_spi] \
           -group [get_clocks clk_sys]
    → Ref: UG949 Ch5 "CDC Constraints"

  [WARN] CONST-003: 12 ports missing I/O delay constraints
    → data_in[7:0], valid, ready, spi_miso, ...
    → Ref: UG949 Ch5 "Input/Output Delays"

━━━ RTL Coding (Group B) ━━━

  [FAIL] RTL-003: Async signal without synchronizer
    → uart_rx.v:47 — rx_data crosses from clk_rx to clk_sys
    → Suggested: XPM_CDC_ARRAY_SINGLE (width=8)
    → Ref: UG949 Ch3 "CDC Figure 3-62"

  [WARN] RTL-002: Potential latch in arbiter.v
    → arbiter.v:35 — case statement missing default
    → Ref: UG949 Ch3 "Latch"

  [WARN] RTL-010: RAM inferred without XPM
    → dsp_core.v:89 — Block RAM inferred directly
    → Suggested: Use XPM_MEMORY for better portability
    → Ref: UG949 Ch3 "XPM"

  [PASS] RTL-001: No combinational loops
  [PASS] RTL-005: No SRL+reset conflicts

━━━ Summary ━━━

  PASS: 12   WARN: 4   FAIL: 2
  Methodology Compliance Score: 68/100

  Priority Actions:
  1. [CRITICAL] Add CDC synchronizers (RTL-003) — will cause metastability
  2. [CRITICAL] Add clock interaction constraints (CONST-004)
  3. [IMPORTANT] Add I/O delay constraints (CONST-003)
  4. [SUGGESTED] Migrate RAM to XPM (RTL-010)
```

### 5.2 Mode 2: Check

```bash
$ vivado-ai check --reports-dir build/reports/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Vivado Methodology Checker — Check Mode (Post-Implementation)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Parsing 8 report files...

━━━ report_methodology Summary ━━━

  Total Checks: 86   Passed: 71   Failed: 15

  [FAIL] TIMING-14: 3480 paths with no clock (CRITICAL)
    → 3480 endpoints in module "clk_domain_b" lack clock definition
    → Root cause: Missing create_clock on port clk_b_in
    → Fix: create_clock -period 10 -name clk_b [get_ports clk_b_in]
    → Ref: UG949 Ch5 "Check Timing / no_clock"

  [FAIL] TIMING-6: Clock groups needed for asynchronous clocks
    → clk_adc and clk_sys interact without constraint
    → Ref: UG949 Ch5 "CDC Constraints"

  [WARN] TIMING-17: Large positive hold requirement on 2 paths
    → May need set_multicycle_path
    → Ref: UG949 Ch5 "Multicycle Paths"

━━━ report_timing_summary ━━━

  Setup:  WNS = -0.342 ns (VIOLATED)   TNS = -12.5 ns
  Hold:   WHS =  0.015 ns (MET)        THS =  0.0 ns
  Pulse:  WPWS =  2.1 ns (MET)

  ━━ Root Cause Analysis (UG1292 Decision Tree) ━━

  Top violating path: inst_dsp/data_pipe|reg_out
  → Logic delay: 62% of datapath (> 50%)  [ROOT-001]
  → Logic levels: 8 (target for 250MHz: ≤ 6) [ROOT-001]
  → Suggestion: Add pipeline register, reduce logic levels
  → Ref: UG1292 "Optimizing Regular Fabric Paths"

━━━ Summary ━━━

  Methodology Compliance Score: 55/100
  UG1292 Stage: Pre-Placement (WNS < 0)

  Recommended Next Steps:
  1. Fix TIMING-14 (missing clock) → re-run synthesis
  2. Add CDC constraints (TIMING-6) → re-baseline
  3. Reduce logic levels on top 3 paths → RTL change
  4. Try place_design -directive ExploreAltThinWireLoop
```

### 5.3 Mode 3: Analyze（Log 分析）

```bash
$ vivado-ai analyze --log-dir build/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Vivado Methodology Checker — Log Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scanning 3 log files (28,450 lines total)...

━━━ Synthesis Log (12,340 lines) ━━━

  Messages: 0 ERROR, 3 CRITICAL WARNING, 47 WARNING, 832 INFO

  [CRITICAL] SYNTH-006: Non-dedicated clock route detected
    → "clk_spi" driven by regular I/O instead of GCIO pin
    → Impact: Increased clock skew, degraded timing
    → Fix: Use Global Clock I/O (GCIO) pin or add CLOCK_DEDICATED_ROUTE constraint
    → Ref: UG949 Ch3 "CLOCK_DEDICATED_ROUTE"

  [WARN] SYNTH-001: 3 RAMs inferred as LUTRAM (not Block RAM)
    → data_buffer.v:78 — 64x32 RAM too small for BRAM
    → Suggested: Use XPM_MEMORY_SP with MEMORY_PRIMITIVE="distributed"
    → Ref: UG949 Ch3 "RAM/LUTRAM Threshold"

  [WARN] SYNTH-008: Optimization blocked by DONT_TOUCH on 5 instances
    → dsp_core_inst, fft_engine_inst, ...
    → Impact: LUT optimization, retiming not applied
    → Ref: UG949 Ch4 "DONT_TOUCH Guidelines"

  [INFO] SYNTH-010: Resource utilization estimate
    → LUT: 45%  FF: 38%  BRAM: 62%  DSP: 71%
    → Note: DSP utilization high, consider resource sharing

━━━ Placement Log (8,920 lines) ━━━

  [WARN] PLACE-001: Congestion Level 3 detected in region X12Y5:W16xH16
    → Top contributors: dsp_core/fft_engine overlapping
    → Fix: Add Pblock constraints to separate modules
    → Ref: UG1292 "Reducing Congestion"

  [WARN] PLACE-005: phys_opt improved WNS from -0.542 to -0.342
    → Improvement: 0.200 ns, but still negative
    → Suggestion: Try phys_opt_design -directive AggressiveExplore
    → Ref: UG1292 "Post-Place Physical Optimization"

━━━ Routing Log (7,190 lines) ━━━

  [FAIL] ROUTE-008: Final timing not met
    → WNS = -0.342 ns (48 failing endpoints)
    → TNS = -12.5 ns

  [WARN] ROUTE-004: WNS degraded from -0.342 (post-place) to -0.342 (post-route)
    → Router did not further degrade timing (stable)
    → WNS is largely a placement issue, not routing

━━━ Flow Summary (Group I) ━━━

  Stage         | Duration  | CRITICAL WARN | WARNING | WNS
  ──────────────┼──────────┼───────────────┼─────────┼────────
  Synthesis     | 12 min    | 3             | 47      | -0.542
  opt_design    | 2 min     | 0             | 2       | —
  place_design  | 28 min    | 0             | 15      | -0.542
  phys_opt      | 8 min     | 0             | 3       | -0.342
  route_design  | 45 min    | 0             | 8       | -0.342
  ──────────────┼──────────┼───────────────┼─────────┼────────
  Total         | 95 min    | 3             | 75      | -0.342

  Key Observations:
  1. Synthesis CRITICAL WARNING (SYNTH-006) → Clock routing issue
  2. WNS improved by phys_opt but not enough
  3. Placement is the bottleneck (not routing)
  4. DSP utilization 71% — approaching limit

  Methodology Compliance Score: 55/100
```

---

## 6. AI 的角色定义

AI 在本工具中的角色是**严格限定**的，不做不可靠的推断：

| 场景 | AI 负责 | AI 不负责 |
|------|---------|----------|
| 规则判断 | 不负责，由规则引擎判断 pass/fail | — |
| 修复建议 | 关联 UG949 章节，提供模板化修复代码 | 不自动应用修改 |
| Log 解读 | 用自然语言解释 WARNING 的含义和影响 | 不猜测原因 |
| 根因分析 | 按 UG1292 决策树逐步推理 | 不跳过决策树直接给结论 |
| 约束生成 | 基于模板生成 XDC 代码片段 | 不凭空生成约束 |

### AI 使用策略

| 任务类型 | 模型 | 原因 |
|---------|------|------|
| Log/Report 解析 | 规则引擎（正则匹配） | 结构化数据，不需要 AI |
| 规则匹配 | 规则引擎 | 确定性判断，不需要 AI |
| 问题解释 + 修复建议 | Claude Haiku / Sonnet | 需要自然语言理解 |
| 根因分析推理 | Claude Sonnet | 需要多步推理 |

**关键设计原则**：能用规则引擎解决的，不用 AI。AI 只用于 "最后一公里" 的解释和推理。

---

## 7. 非功能需求

### 7.1 性能

| 场景 | 响应时间 |
|------|---------|
| Lint 模式（50 个 Verilog 文件） | < 10 秒 |
| Check 模式（解析 10 个 .rpt 文件） | < 5 秒 |
| Analyze 模式（解析 30000 行 log） | < 10 秒 |
| AI 增强解读（单条问题） | < 5 秒 |

### 7.2 兼容性

| 项目 | 要求 |
|------|------|
| Vivado 版本 | 2017.1+（UG949 v2017.1 起支持 report_methodology） |
| 操作系统 | Windows 10/11, Linux |
| Python | 3.10+ |
| FPGA 器件 | 7 Series, UltraScale, UltraScale+, Versal |

### 7.3 安全

- 设计文件仅在本地处理
- AI 调用可选择本地模型（Ollama）满足离线需求
- 不自动修改任何设计文件
- 所有建议需要用户确认后手动应用

---

## 8. 里程碑

| 里程碑 | 时间 | 交付物 |
|--------|------|--------|
| **MVP** | Week 1-3 | Mode 2 (Check)：解析 report_methodology + report_timing_summary，输出合规报告 |
| **Alpha** | Week 4-6 | Mode 3 (Analyze)：综合/布局/布线 log 解析，AI 增强解读 |
| **Beta** | Week 7-9 | Mode 1 (Lint)：RTL + XDC 静态检查，不依赖 Vivado |
| **RC** | Week 10-12 | 全模式整合，UG1292 决策树编排，报告生成 |
| **GA** | Week 13-14 | 规则库完善，文档，用户测试 |

---

## 9. 与 v1.0 PRD 的对比

| 维度 | v1.0（AI 分析 timing report） | v2.0（Methodology Checker） |
|------|---------------------------|---------------------------|
| 核心理念 | AI 推理分析时序报告 | UG949 规则合规检查 |
| 准确性 | 依赖 LLM，可能不准确 | 基于确定性规则，准确 |
| 介入时机 | 时序违例后（事后） | 编码 → 综合 → 实现（全流程） |
| AI 角色 | 分析师（主角） | 解释器（辅助） |
| 输入 | timing.rpt | RTL + XDC + Vivado Reports + Stage Logs |
| 输出 | AI 生成的分析文本 | 规则化合规报告 + AI 解释 |
| 信任度 | 中（用户可能不信任 AI） | 高（基于 UG949 官方方法论） |
| 技术壁垒 | 低（谁都能调 LLM） | 高（规则库 + 流程编排 + Log 解析） |
