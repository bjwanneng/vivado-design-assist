"""
VMC Web Server — 纯 stdlib HTTP + SSE 服务器

零外部依赖，用浏览器替代 pywebview。
提供 REST API 和 Server-Sent Events 状态推送。
"""

import http.server
import json
import queue
import threading
from pathlib import Path

FRONTEND_DIR = Path(__file__).parent / "frontend"


class VMCRequestHandler(http.server.BaseHTTPRequestHandler):
    """VMC HTTP 请求处理器"""

    backend = None       # 由 start_web_server 设置
    sse_clients = None   # list[queue.Queue]，由 start_web_server 设置

    def log_message(self, format, *args):
        """静默日志（避免 stderr 污染）"""
        pass

    # ── 路由 ──

    def do_GET(self):
        path = self.path.split("?")[0]
        routes = {
            "/": self._serve_index,
            "/api/initialize": self._handle_initialize,
            "/api/analysis_result": self._handle_analysis_result,
            "/api/state": self._handle_state,
            "/api/events": self._handle_sse,
        }
        handler = routes.get(path)
        if handler:
            handler()
        else:
            self._serve_static(path)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/run_now":
            self._handle_run_now()
        else:
            self._send_json(404, {"error": "not found"})

    # ── 静态文件 ──

    def _serve_index(self):
        html = (FRONTEND_DIR / "index.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _serve_static(self, path: str):
        """提供 frontend 目录下的静态文件"""
        rel = path.lstrip("/")
        file_path = FRONTEND_DIR / rel
        if file_path.is_file() and FRONTEND_DIR in file_path.resolve().parents:
            data = file_path.read_bytes()
            ct = self._guess_content_type(rel)
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._send_json(404, {"error": "not found"})

    @staticmethod
    def _guess_content_type(path: str) -> str:
        ext = Path(path).suffix.lower()
        types = {".html": "text/html", ".css": "text/css", ".js": "application/javascript",
                 ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}
        return types.get(ext, "application/octet-stream")

    # ── API 端点 ──

    def _handle_initialize(self):
        result = self.backend.initialize()
        self._send_json(200, result)

    def _handle_analysis_result(self):
        result = self.backend.analysis_result
        self._send_json(200, result)

    def _handle_state(self):
        self._send_json(200, {
            "state": self.backend.state,
            "project_info": self.backend.project_info,
        })

    def _handle_run_now(self):
        result = self.backend.run_now()
        self._send_json(200, result)

    # ── SSE ──

    def _handle_sse(self):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

        q = queue.Queue()
        self.sse_clients.append(q)

        # 立即发送当前状态
        try:
            initial = json.dumps({"state": self.backend.state})
            self._sse_write(initial)
        except (BrokenPipeError, ConnectionResetError, OSError):
            if q in self.sse_clients:
                self.sse_clients.remove(q)
            return

        try:
            while True:
                try:
                    payload = q.get(timeout=30)
                    self._sse_write(payload)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            if q in self.sse_clients:
                self.sse_clients.remove(q)

    def _sse_write(self, payload: str):
        self.wfile.write(f"data: {payload}\n\n".encode())
        self.wfile.flush()

    # ── 工具方法 ──

    def _send_json(self, status: int, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_web_server(backend, port: int = 19877):
    """启动 Web GUI 服务器"""

    sse_clients: list[queue.Queue] = []

    # 注册状态回调 → 广播给所有 SSE 客户端
    def on_state_change(new_state: str):
        payload = json.dumps({"state": new_state})
        dead = []
        for i, q in enumerate(sse_clients):
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(i)
        for i in reversed(dead):
            sse_clients.pop(i)

    backend.add_state_callback(on_state_change)

    # 注入共享状态
    VMCRequestHandler.backend = backend
    VMCRequestHandler.sse_clients = sse_clients

    # 端口冲突自动递增
    server = None
    actual_port = port
    for attempt in range(10):
        try:
            server = http.server.HTTPServer(
                ("0.0.0.0", actual_port), VMCRequestHandler,
            )
            break
        except OSError:
            actual_port = port + attempt + 1
    else:
        print(f"ERROR: No available port (tried {port}-{actual_port})")
        return

    print(f"\n  VMC Web GUI: http://localhost:{actual_port}\n")
    print("  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backend._polling = False
        server.shutdown()
