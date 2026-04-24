# VMC 使用手册

本文档详细介绍 Vivado Methodology Checker (VMC) 的所有 CLI 命令、GUI 模式、Vivado 集成配置及使用场景。

---

## 目录

1. [CLI 命令](#cli-命令)
2. [GUI 模式](#gui-模式)
3. [Vivado 集成](#vivado-集成)
4. [AI 功能](#ai-功能)
5. [输出格式](#输出格式)
6. [规则分组](#规则分组)

---

## CLI 命令

### `vivado-ai lint` — 预综合静态检查

在综合前检查 XDC 约束和 RTL 源码的合规性。

```bash
vivado-ai lint --xdc constraints/top.xdc [constraints/io.xdc ...]
               [--rtl src/]
               [--groups all|CONST|RTL ...]
               [--no-ai]
               [--output report.md|report.json]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--xdc` | 是 | 一个或多个 XDC 约束文件 |
| `--rtl` | 否 | RTL 源码目录（用于编码规范检查） |
| `--groups` | 否 | 指定规则组，默认 `all` |
| `--no-ai` | 否 | 禁用 AI 解释 |
| `--output` | 否 | 输出报告文件（`.md` 或 `.json`） |

**示例**：

```bash
vivado-ai lint --xdc xdc/top.xdc xdc/io.xdc --rtl src/ --output lint_report.md
```

---

### `vivado-ai check` — 报告解析

解析 Vivado 生成的 `.rpt` 报告文件，检查时序、资源、DRC 等合规项。

```bash
vivado-ai check --reports-dir build/reports/
                [--groups all|IMPL|ROOT ...]
                [--no-ai]
                [--output report.md|report.json]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--reports-dir` | 是 | 存放 `.rpt` 文件的目录 |
| `--groups` | 否 | 指定规则组，默认 `all` |
| `--no-ai` | 否 | 禁用 AI 解释 |
| `--output` | 否 | 输出报告文件 |

**示例**：

```bash
vivado-ai check --reports-dir ./build/reports --output check_report.md
```

---

### `vivado-ai analyze` — Log 分析

分析 Vivado 各阶段（synth、opt、place、route）的 `.log` 文件，提取警告、错误和时序信息。

```bash
vivado-ai analyze --log-dir build/logs/
                  [--groups all|SYNTH|OPT|PLACE|ROUTE ...]
                  [--no-ai]
                  [--output report.md|report.json]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--log-dir` | 是 | 存放 `.log` 文件的目录 |
| `--groups` | 否 | 指定规则组，默认 `all` |
| `--no-ai` | 否 | 禁用 AI 解释 |
| `--output` | 否 | 输出报告文件 |

**示例**：

```bash
vivado-ai analyze --log-dir ./build/logs --groups SYNTH OPT --no-ai
```

---

### `vivado-ai rules` — 列出规则

打印所有 49 条规则的 ID、名称、所属组和适用的模式。

```bash
vivado-ai rules
```

---

### `vivado-ai gui` — 启动 GUI

启动图形界面，支持自动检测最佳模式。

```bash
vivado-ai gui [--mode native|web|tui|auto]
vivado-ai gui --uninstall
```

| 参数 | 说明 |
|------|------|
| `--mode auto` | 自动检测（默认）：有 TTY → TUI；有 pywebview → Native；否则 Web |
| `--mode native` | 桌面浮窗（pywebview），适合 Windows/macOS |
| `--mode web` | 浏览器模式，适合 Linux 服务器 / 远程桌面 |
| `--mode tui` | 终端实时面板，适合 SSH 环境 |
| `--uninstall` | 从 Vivado `init.tcl` 中移除 VMC 集成 |

---

## GUI 模式

### Native 模式

依赖 `pywebview`，启动一个桌面浮窗。

```bash
pip install vivado-ai[gui]   # 确保安装 pywebview
vivado-ai gui --mode native
```

特性：
- 与 Vivado 实时联动（Tcl Socket Server）
- 编译完成后自动刷新分析报告
- 暗色主题 UI

### Web 模式

纯标准库 HTTP + SSE，零额外依赖。

```bash
vivado-ai gui --mode web
```

特性：
- 自动选择可用端口
- 自动打开系统默认浏览器
- SSE 实时状态推送
- 支持远程访问

### TUI 模式

基于 Rich 的终端实时面板。

```bash
vivado-ai gui --mode tui
```

特性：
- Live Display 实时刷新
- 按 `A` 键手动触发分析
- Ctrl+C 退出
- 无需桌面环境，纯 SSH 可用

---

## Vivado 集成

VMC 可自动注入 Tcl Socket Server 到 Vivado 的 `init.tcl`，实现编译阶段自动分析和实时状态监控。

### 自动安装

首次运行 `vivado-ai gui` 时会自动检测并提示安装。安装内容：

- 在 Vivado `init.tcl` 中注入 Tcl Server（默认端口 19876）
- Vivado 启动时自动加载 Server
- 自动探测 Vivado 进程
- 自动注入 `post_synth.tcl`、`post_place.tcl`、`post_route.tcl` Hook 脚本

### 手动卸载

```bash
vivado-ai gui --uninstall
```

这会从 `init.tcl` 中移除所有 VMC 相关配置，不影响 Vivado 正常使用。

### 工作流程

1. 启动 VMC GUI（任意模式）
2. 启动 Vivado（自动连接 Tcl Server）
3. 在 Vivado 中运行综合/布局/布线
4. 每个阶段完成后 Hook 自动触发报告生成
5. VMC 自动拉取报告并执行规则检查
6. GUI 实时显示合规评分和 issue 列表

---

## AI 功能

VMC 可选接入 LLM（Claude / OpenAI），为检查结果提供智能分析。

### 单 Issue 解读

每个 FAIL/CRITICAL/WARN 级别的违规都会自动生成：
- 中文问题解释
- 具体修复建议
- Xilinx Forum 搜索链接

### 跨 Issue 根因分析

汇总所有问题，由 LLM 归纳可能的共同根因，例如：
- 时序约束缺失导致多处 setup 违例
- 跨时钟域处理不当引发 CDC 警告

### 关闭 AI

无需 API Key 时完全离线可用：

```bash
vivado-ai lint --xdc top.xdc --no-ai
```

或在配置文件中设置 `enable_ai = false`。

### API Key 配置

复制 `.env.example` 为 `.env`，填入对应 Key：

```bash
cp .env.example .env
```

```
ANTHROPIC_API_KEY=sk-...
OPENAI_API_KEY=sk-...
```

---

## 输出格式

### Markdown（默认）

适合人工阅读和归档，包含评分面板、根因分析、详细 issue 表格。

```bash
vivado-ai check --reports-dir reports/ --output report.md
```

### JSON

适合下游工具集成或 CI/CD 流水线解析。

```bash
vivado-ai check --reports-dir reports/ --output report.json
```

JSON 结构：

```json
{
  "mode": "check",
  "total_rules": 49,
  "total_issues": 3,
  "by_severity": {"FAIL": 2, "WARN": 1},
  "by_group": {"CONST": [...], "IMPL": [...]},
  "score": 78,
  "issues": [...],
  "root_cause_summary": "..."
}
```

---

## 规则分组

| 组 | 前缀 | 规则数 | 适用模式 | 说明 |
|----|------|--------|----------|------|
| A | CONST-* | 5 | lint | 约束规则（时钟、IO、时序约束） |
| B | RTL-* | 10 | lint | RTL 编码规范 |
| C | IMPL-* | 8 | check | 实现流程检查 |
| D | ROOT-* | 3 | check | 时序根因分析 |
| E | SYNTH-* | 7 | analyze | 综合 Log 检查 |
| F | OPT-* | 5 | analyze | 优化 Log 检查 |
| G | PLACE-* | 3 | analyze | 布局 Log 检查 |
| H | ROUTE-* | 3 | analyze | 布线 Log 检查 |
| I | FLOW-* | 5 | check/analyze | 全流程汇总 |

使用 `--groups` 参数可指定只运行特定组的规则：

```bash
vivado-ai lint --xdc top.xdc --groups CONST RTL
vivado-ai analyze --log-dir logs/ --groups SYNTH OPT PLACE ROUTE
```

---

## 典型工作流

### 工作流 1：CI/CD 集成

```bash
# 1. 约束预检
vivado-ai lint --xdc constraints/*.xdc --output lint.json
# 2. 解析编译报告
vivado-ai check --reports-dir build/reports/ --output check.json
# 3. 分析 Log
vivado-ai analyze --log-dir build/logs/ --output analyze.json
```

在 CI 中根据 `score` 或 `by_severity` 中的 FAIL/CRITICAL 数量决定构建是否通过。

### 工作流 2：交互式开发

```bash
# 启动 TUI，与 Vivado 实时联动
vivado-ai gui --mode tui
```

在 Vivado 中执行综合/布局/布线，TUI 自动刷新检查结果。

### 工作流 3：离线审计

```bash
vivado-ai check --reports-dir archived/reports/ --no-ai --output audit.md
```

无网络环境、无 API Key 时完全可用。