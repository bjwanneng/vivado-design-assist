# Vivado Methodology Checker (VMC) - 项目当前状态

> 更新时间: 2026-04-20
> 版本: v2.3 多模式 GUI (Web + TUI + Native) — 22 项代码质量修复

---

## 项目简介

基于 Xilinx UltraFast Design Methodology (UG949) 和 Timing Closure Quick Reference (UG1292)，
构建一个 **Vivado 设计方法论合规检查工具**，支持 CLI、Web 浏览器、终端 TUI、GUI 浮窗四种使用方式。

---

## 完成状态

### 规则引擎 ✅ (49 rules)

| Group | 规则数 | 文件 |
|-------|--------|------|
| A: CONST-* 约束规则 | 5 | constraint_rules.py |
| B: RTL-* 编码规范 | 10 | rtl_rules.py (regex) |
| C: IMPL-* 实现流程 | 8 | impl_rules.py |
| D: ROOT-* 时序根因 | 3 | root_cause_rules.py |
| E: SYNTH-* 综合Log | 7 | synth_rules.py |
| F: OPT-* 优化Log | 5 | opt_rules.py |
| G: PLACE-* 布局Log | 3 | place_rules.py |
| H: ROUTE-* 布线Log | 3 | route_rules.py |
| I: FLOW-* 全流程汇总 | 5 | flow_rules.py |

### CLI ✅

```bash
vivado-ai lint --xdc <files>           # Pre-synthesis 检查
vivado-ai check --reports-dir <dir>     # 报告解析
vivado-ai analyze --log-dir <dir>       # Log 分析
vivado-ai rules                         # 列出 49 条规则
vivado-ai gui                            # 启动 GUI (auto 模式)
vivado-ai gui --mode web                # 浏览器模式
vivado-ai gui --mode tui                # 终端 TUI 模式
vivado-ai gui --mode native             # pywebview 浮窗模式
vivado-ai gui --uninstall               # 卸载 Vivado 集成
```

### GUI 组件 ✅

| 组件 | 文件 | 说明 |
|------|------|------|
| 自动安装器 | gui/installer.py | init.tcl 注入 Tcl Socket Server |
| Tcl 客户端 | gui/tcl_client.py | TCP 连接 Vivado |
| Hook 生成器 | gui/hooks.py | post_synth/place/route.tcl |
| 后端 | gui/app.py | VivadoProbe + BuildWatcher + 状态机 |
| Web 服务器 | gui/web_server.py | 纯 stdlib HTTP + SSE (零依赖) |
| TUI 终端界面 | gui/tui.py | Rich Live Display 实时面板 (零新依赖) |
| 前端 | gui/frontend/index.html | 暗色主题 UI (pywebview/web 双模式) |

### 代码质量修复 ✅ (v2.3)

22 项代码审查修复，全部通过 77 个单元测试：

| 类别 | 修复项 |
|------|--------|
| 高优先级 | #1 HTTP→ThreadingHTTPServer, #2 Tcl响应协议, #3 时长HH:MM:SS, #4 AI解释per-issue, #5 XDC多行续行, #6 TUI Layout |
| 中优先级 | #7 Backend线程安全Lock, #8 run_now异步分析, #9 重连资源清理, #10 SSE clients线程安全, #11 keyboard可选依赖, #12 Tcl路径引用, #13 Hook路径转义 |
| 低优先级 | #14 输入校验, #15 total_rules填充, #16 JSON/Markdown PASS一致性, #17 重复规则ID警告, #18 LLM重试仅限瞬态异常, #19 报告文件错误处理, #20 opt阶段检测, #21 XSS防护 |

### 文档 ✅

| 文件 | 说明 |
|------|------|
| [README.md](README.md) | 项目总览、功能特性、快速开始、项目结构 |
| [USAGE.md](USAGE.md) | CLI 命令详解、GUI 模式、Vivado 集成、AI 功能、典型工作流 |

### 基础设施 ✅

- pyproject.toml + pip install -e .
- 3 个解析器 (report/log/xdc)
- AI Interpreter (可选)
- YAML 规则配置
- 77 个单元测试全部通过

### AI 增强 ✅ (v2.1)

| 功能 | 说明 |
|------|------|
| Forum 搜索链接 | 每个 issue 自动生成 Xilinx Forum 搜索 URL |
| AI 跨 issue 根因分析 | LLM 归纳所有 FAIL/CRITICAL 的共同根因 |
| AI 单 issue 解读 | 为每个违规生成中文解释和修复建议 |
| `--no-ai` / `enable_ai=False` | 无 API key 时完全离线可用 |

### 多模式 GUI ✅ (v2.2)

| 模式 | 适用场景 | 依赖 |
|------|---------|------|
| `native` (pywebview) | Windows/macOS 桌面 | pywebview, Qt/GTK |
| `web` (浏览器) | Linux 服务器 (NoMachine/远程桌面) | 零额外依赖 (stdlib) |
| `tui` (终端) | SSH 远程 / 无桌面环境 | 零额外依赖 (Rich) |
| `auto` (自动) | 自动检测环境选择最佳模式 | — |

**默认模式**：`native`（桌面浮窗）。如需自动检测，显式使用 `--mode auto`：
- 有 TTY 终端 → TUI 模式
- 有 pywebview → Native 模式
- 其他 → Web 模式

**Web 模式特性**：SSE 实时状态推送、自动选端口、自动打开浏览器
**TUI 模式特性**：Rich Live Display 实时刷新、按 `A` 触发分析、Ctrl+C 退出

---

## 使用方式

### CLI 模式

```bash
vivado-ai lint --xdc constraints/*.xdc
vivado-ai check --reports-dir build/reports/ --output report.md
vivado-ai analyze --log-dir build/logs/
```

### GUI 模式

```bash
# 默认 Native 桌面浮窗模式
vivado-ai gui

# 指定模式
vivado-ai gui --mode native  # 浮窗 (Windows/macOS)
vivado-ai gui --mode web     # 浏览器 (Linux 服务器)
vivado-ai gui --mode tui     # 终端 (SSH 环境)
vivado-ai gui --mode auto    # 自动检测最佳模式

# 首次启动自动安装 init.tcl，重启 Vivado 后自动生效：
# - Vivado 启动时自动加载 Tcl Server (port 19876)
# - 自动探测 Vivado 进程
# - 自动注入 Hook 脚本
# - 每个编译阶段完成后自动生成报告并分析

# 卸载
vivado-ai gui --uninstall
```

---

## 项目结构

```
src/vivado_ai/
├── core/
│   ├── engine.py, scorer.py, ai_interpreter.py
│   ├── parsers/ (report, log, xdc)
│   └── rules/ (9 rule files, 49 rules)
├── models/ (issue, finding, report)
├── cli/main.py
├── gui/
│   ├── app.py, installer.py, tcl_client.py, hooks.py
│   ├── web_server.py          # HTTP + SSE 服务器
│   ├── tui.py                 # Rich 终端界面
│   └── frontend/index.html    # 暗色主题 UI
└── utils/config.py

tests/ (77 tests, all passing)
configs/rules/ (YAML)
```

---

## 可扩展方向

- RTL AST 分析 (pyverilog 替代 regex)
- UG1292 决策树编排
- 历史对比 + 趋势分析
- 修复脚本自动生成 (TCL/XDC)
- Xilinx Forum 知识库 (embedding 语义匹配)
