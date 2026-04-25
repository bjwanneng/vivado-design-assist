#!/bin/bash
# VMC 开发调试启动脚本
# 启动 Python FastAPI 服务，浏览器访问 http://127.0.0.1:8000

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/src"

# 检查依赖
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "[INFO] 安装 fastapi + uvicorn..."
    python3 -m pip install fastapi uvicorn -q
fi

echo "========================================"
echo "  VMC 开发服务器启动中..."
echo "========================================"
echo ""
echo "  浏览器访问: http://127.0.0.1:8000"
echo "  按 Ctrl+C 停止"
echo ""

cd "${SCRIPT_DIR}"
python3 -m uvicorn vivado_ai.api.server:app \
    --host 127.0.0.1 \
    --port 8000 \
    --reload \
    --log-level info
