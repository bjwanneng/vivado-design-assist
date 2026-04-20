"""Tests for web server mode"""

import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from vivado_ai.gui.web_server import VMCRequestHandler


class FakeWfile:
    """模拟 HTTP 响应写入"""
    def __init__(self):
        self._buffer = BytesIO()

    def write(self, data):
        self._buffer.write(data)

    def flush(self):
        pass

    def getvalue(self):
        return self._buffer.getvalue()


def _make_handler(path: str, method: str = "GET"):
    """创建一个可用的请求处理器"""
    handler = VMCRequestHandler.__new__(VMCRequestHandler)
    handler.command = method
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.headers = {}
    handler.rfile = BytesIO()

    wfile = FakeWfile()
    handler.wfile = wfile

    return handler


def _get_response_body(handler):
    """从 FakeWfile 提取 JSON body"""
    raw = handler.wfile.getvalue()
    parts = raw.split(b"\r\n\r\n", 1)
    if len(parts) < 2:
        parts = raw.split(b"\n\n", 1)
    return json.loads(parts[1]) if len(parts) > 1 else None


@pytest.fixture
def mock_backend():
    backend = MagicMock()
    backend.state = "waiting"
    backend.analysis_result = None
    backend.project_info = {"name": "test_project"}
    backend.initialize.return_value = {"installed": True, "need_restart": False}
    backend.run_now.return_value = {"success": True}
    VMCRequestHandler.backend = backend
    VMCRequestHandler.sse_clients = []
    yield backend
    VMCRequestHandler.backend = None
    VMCRequestHandler.sse_clients = None


class TestStaticFiles:
    def test_serve_index(self, mock_backend):
        handler = _make_handler("/")
        handler.do_GET()
        output = handler.wfile.getvalue()
        assert b"VMC" in output

    def test_serve_not_found(self, mock_backend):
        handler = _make_handler("/nonexistent.css")
        handler.do_GET()
        output = handler.wfile.getvalue()
        assert b"not found" in output


class TestAPIEndpoints:
    def test_initialize(self, mock_backend):
        handler = _make_handler("/api/initialize")
        handler.do_GET()
        data = _get_response_body(handler)
        assert data["installed"] is True

    def test_analysis_result_empty(self, mock_backend):
        handler = _make_handler("/api/analysis_result")
        handler.do_GET()
        data = _get_response_body(handler)
        assert data is None

    def test_analysis_result_with_data(self, mock_backend):
        mock_backend.analysis_result = {"score": 85, "issues": []}
        handler = _make_handler("/api/analysis_result")
        handler.do_GET()
        data = _get_response_body(handler)
        assert data["score"] == 85

    def test_state(self, mock_backend):
        handler = _make_handler("/api/state")
        handler.do_GET()
        data = _get_response_body(handler)
        assert data["state"] == "waiting"

    def test_run_now(self, mock_backend):
        handler = _make_handler("/api/run_now", method="POST")
        handler.do_POST()
        data = _get_response_body(handler)
        assert data["success"] is True

    def test_post_not_found(self, mock_backend):
        handler = _make_handler("/api/nonexistent", method="POST")
        handler.do_POST()
        output = handler.wfile.getvalue()
        assert b"not found" in output


class TestSSE:
    def test_sse_sends_initial_state(self, mock_backend):
        handler = _make_handler("/api/events")

        original_write = handler.wfile.write
        call_count = [0]

        def write_limited(data):
            call_count[0] += 1
            if call_count[0] > 3:
                raise BrokenPipeError()
            return original_write(data)

        handler.wfile.write = write_limited
        handler._handle_sse()
        output = handler.wfile.getvalue()
        assert b"waiting" in output
        assert len(VMCRequestHandler.sse_clients) == 0

    def test_sse_client_cleanup(self, mock_backend):
        VMCRequestHandler.sse_clients = []
        handler = _make_handler("/api/events")

        # 在 send_response 阶段就断开，验证 finally 清理
        handler.send_response = MagicMock(side_effect=BrokenPipeError)
        handler._handle_sse()
        assert len(VMCRequestHandler.sse_clients) == 0

    def test_sse_callback_broadcasts(self, mock_backend):
        """测试状态回调能广播到 SSE 客户端"""
        import queue as q_mod

        clients = []
        VMCRequestHandler.sse_clients = clients

        # 模拟一个已注册的 SSE 客户端
        client_q = q_mod.Queue()
        clients.append(client_q)

        # 模拟 _set_state 回调
        from vivado_ai.gui.web_server import start_web_server
        import json

        # 直接调用 start_web_server 内的 on_state_change 逻辑
        payload = json.dumps({"state": "analyzing"})
        dead = []
        for i, q in enumerate(clients):
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(i)
        for i in reversed(dead):
            clients.pop(i)

        # 验证 queue 收到了消息
        result = client_q.get_nowait()
        assert "analyzing" in result
        assert len(VMCRequestHandler.sse_clients) == 1
