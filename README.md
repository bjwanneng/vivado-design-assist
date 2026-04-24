# Vivado Methodology Checker (VMC)

基于 Xilinx UltraFast Design Methodology (UG949) 和 Timing Closure Quick Reference (UG1292) 构建的 **Vivado 设计方法论合规检查工具**。

支持 CLI、Web 浏览器、终端 TUI、GUI 浮窗四种使用方式，覆盖从约束检查、报告解析到 Log 分析的全流程。

---

## 功能特性

- **49 条内置规则**：覆盖约束、RTL 编码、综合、优化、布局、布线、时序根因、全流程 9 大类别
- **多模式 GUI**：自动检测环境，支持 Native 浮窗 / Web 浏览器 / TUI 终端三种界面
- **AI 增强分析**：可选 LLM 为每个违规生成中文解释和修复建议，支持跨 issue 根因归纳
- **Vivado 集成**：自动注入 Tcl Server，实现编译阶段自动分析、实时状态推送
- **零依赖 Web/TUI**：纯标准库 HTTP + SSE，Rich Live Display，服务器环境无需桌面

---

## 安装

```bash
# 基础安装（CLI  only）
pip install -e .

# 完整安装（含 GUI）
pip install -e ".[gui]"

# 开发依赖
pip install -e ".[dev]"
```

需要 Python >= 3.10。

---

## 快速开始

### CLI 检查约束文件

```bash
vivado-ai lint --xdc constraints/*.xdc
```

### 解析 Vivado 报告

```bash
vivado-ai check --reports-dir build/reports/ --output report.md
```

### 分析编译 Log

```bash
vivado-ai analyze --log-dir build/logs/
```

### 启动 GUI（自动检测最佳模式）

```bash
vivado-ai gui
```

| 模式 | 适用场景 | 依赖 |
|------|---------|------|
| **Native** | Windows / macOS 本地桌面，需要浮窗体验 | `pywebview` |
| **Web** | Linux 服务器、远程桌面、NoMachine 等环境 | 零额外依赖 |
| **TUI** | SSH 远程终端、无桌面环境 | `rich`（已随基础安装） |

自动检测逻辑：有 TTY 终端 → TUI；有 `pywebview` → Native；否则 → Web。

### 列出所有规则

```bash
vivado-ai rules
```

---

## 项目结构

```
src/vivado_ai/
├── cli/              # 命令行入口
├── core/
│   ├── engine.py     # 规则引擎与评分
│   ├── parsers/      # report / log / xdc 解析器
│   └── rules/        # 9 组共 49 条规则
├── gui/
│   ├── app.py        # 后端状态机
│   ├── web_server.py # HTTP + SSE 服务器
│   ├── tui.py        # Rich 终端界面
│   └── frontend/     # 暗色主题 Web UI
├── models/           # Issue / Finding / Report 数据模型
└── utils/            # 配置管理
```

---

## 文档

- [USAGE.md](USAGE.md) — CLI 与 GUI 详细使用手册
- [readme_first.md](readme_first.md) — 项目当前状态与开发进度

---

## 许可证

MIT