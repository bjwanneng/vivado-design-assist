"""VMC FastAPI 服务

将 Backend 的所有功能暴露为 HTTP API + WebSocket 状态推送。
"""

import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from vivado_ai.gui.app import Backend

logger = logging.getLogger(__name__)


class APIState:
    """全局状态管理"""
    backend: Optional[Backend] = None
    _shutdown_event = threading.Event()


state = APIState()


def _state_callback(new_state: str):
    """Backend 状态变化时广播到所有 WebSocket 客户端"""
    from vivado_ai.api.server import connection_manager
    connection_manager.broadcast({"type": "state", "state": new_state})
    # 当进入 results 状态时，同时推送结果数据
    if new_state == "results" and state.backend:
        result = state.backend.analysis_result
        if result:
            connection_manager.broadcast({"type": "result", "data": result})


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化 Backend
    logger.info("Starting VMC API server...")
    state.backend = Backend()
    state.backend.add_state_callback(_state_callback)
    init_result = state.backend.initialize()
    logger.info("Backend initialized: %s", init_result)

    yield

    # 关闭时清理
    logger.info("Shutting down VMC API server...")
    state._shutdown_event.set()
    if state.backend:
        state.backend.shutdown()


app = FastAPI(title="VMC API", lifespan=lifespan)

# CORS：允许 Wails 前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    """WebSocket 连接管理"""
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = threading.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        with self._lock:
            self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    def broadcast(self, message: dict):
        """广播消息到所有客户端"""
        with self._lock:
            connections = list(self.active_connections)

        # 使用 threading 避免阻塞主线程
        def _send():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            for ws in connections:
                try:
                    loop.run_until_complete(ws.send_json(message))
                except Exception:
                    pass
            loop.close()

        threading.Thread(target=_send, daemon=True).start()


connection_manager = ConnectionManager()


# ── REST API ──

@app.get("/api/health")
def health():
    """健康检查"""
    return {"status": "ok", "connected": state.backend.tcl_client is not None}


@app.get("/api/state")
def get_state():
    """获取当前状态"""
    if not state.backend:
        return {"state": "error", "error": "Backend not initialized"}
    return {
        "state": state.backend.state,
        "project_info": state.backend.project_info,
        "vivado_instances": state.backend.vivado_instances,
    }


@app.post("/api/select_vivado/{index}")
def select_vivado(index: int):
    """选择 Vivado 实例"""
    if not state.backend:
        return {"error": "Backend not initialized"}
    state.backend.select_vivado(index)
    return {"success": True}


@app.get("/api/run_status")
def get_run_status():
    """获取运行状态（实现阶段进度）"""
    if not state.backend:
        return {}
    return state.backend.run_status


@app.post("/api/analyze/{stage}")
def analyze_stage(stage: str):
    """触发指定阶段分析"""
    if not state.backend:
        return {"error": "Backend not initialized"}
    return state.backend.analyze_stage(stage)


@app.get("/api/analysis_result")
def get_analysis_result():
    """获取分析结果"""
    if not state.backend:
        return {"error": "Backend not initialized"}
    result = state.backend.analysis_result
    return result or {}


@app.post("/api/clear_reports")
def clear_reports(stage: str = "all"):
    """清理报告"""
    if not state.backend:
        return {"error": "Backend not initialized"}
    state.backend.clear_stage_reports(stage)
    return {"success": True}


@app.post("/api/uninstall")
def uninstall():
    """卸载 VMC 集成"""
    if not state.backend:
        return {"error": "Backend not initialized"}
    return state.backend.uninstall()


# ── LLM 配置 API ──

@app.get("/api/config/llm")
def get_llm_config():
    """获取 LLM 配置（不含 api_key）"""
    from vivado_ai.utils.config import get_llm_config_dict
    return get_llm_config_dict()


@app.post("/api/config/llm")
def update_llm_config_endpoint(data: dict):
    """更新 LLM 配置"""
    from vivado_ai.utils.config import update_llm_config
    try:
        update_llm_config(
            provider=data.get("provider"),
            model=data.get("model"),
            api_key=data.get("api_key"),
            base_url=data.get("base_url"),
            max_tokens=data.get("max_tokens"),
            temperature=data.get("temperature"),
        )
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


# ── WebSocket ──

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await connection_manager.connect(websocket)
    try:
        # 发送当前状态
        if state.backend:
            await websocket.send_json({
                "type": "state",
                "state": state.backend.state,
            })
        # 保持连接，接收前端心跳
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg.get("type") == "get_result":
                result = state.backend.analysis_result if state.backend else None
                await websocket.send_json({
                    "type": "result",
                    "data": result or {},
                })
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
        connection_manager.disconnect(websocket)


# ── 静态文件（可选，用于直接浏览器访问）──

frontend_dir = Path(__file__).parent.parent / "gui" / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(str(frontend_dir / "index.html"))
