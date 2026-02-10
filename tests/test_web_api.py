"""Test cases for FastAPI Web Server.

测试 Mini Agent API 的各个接口，包括：
- 会话管理（创建、查询、更新、删除）
- 流式聊天
- 非流式聊天
- 聊天历史
- 健康检查
"""

import json
import tempfile
import uuid
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_db_path() -> Generator[str, None, None]:
    """创建临时数据库文件."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False, delete=True) as f:
        db_path = f.name
    
    yield db_path
    
    try:
        if Path(db_path).exists():
            Path(db_path).unlink()
    except Exception:
        pass


@pytest.fixture
def client(test_db_path) -> Generator[TestClient, None, None]:
    """创建测试客户端."""
    from mini_agent.web.database import init_database
    from mini_agent.web.server import app
    
    db = init_database(test_db_path)
    
    with TestClient(app) as c:
        yield c


class TestHealthCheck:
    """测试健康检查接口."""

    def test_health_check(self, client: TestClient):
        """测试健康检查接口返回正常状态."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "database_initialized" in data

    def test_root_endpoint(self, client: TestClient):
        """测试根端点返回 API 信息."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Mini Agent API Server"
        assert "docs" in data
        assert "redoc" in data


class TestSessionManagement:
    """测试会话管理接口."""

    def test_create_session_with_title(self, client: TestClient):
        """测试创建会话（带标题）."""
        response = client.post(
            "/api/sessions",
            json={"title": "我的测试会话"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["title"] == "我的测试会话"
        assert data["message_count"] == 0
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_session_without_title(self, client: TestClient):
        """测试创建会话（自动生成标题）."""
        response = client.post(
            "/api/sessions",
            json={},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["title"].startswith("新会话")

    def test_list_sessions_empty(self, client: TestClient):
        """测试获取空会话列表."""
        response = client.get("/api/sessions")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_sessions_with_pagination(self, client: TestClient):
        """测试获取会话列表（分页）."""
        response = client.get("/api/sessions?limit=5&offset=0")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    def test_get_session_not_found(self, client: TestClient):
        """测试获取不存在的会话."""
        response = client.get("/api/sessions/non-existent-id")
        
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_get_session_success(self, client: TestClient):
        """测试获取存在的会话."""
        create_response = client.post(
            "/api/sessions",
            json={"title": "测试会话"},
        )
        session_id = create_response.json()["session_id"]
        
        response = client.get(f"/api/sessions/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["title"] == "测试会话"
        assert "messages" in data

    def test_update_session_title(self, client: TestClient):
        """测试更新会话标题."""
        create_response = client.post(
            "/api/sessions",
            json={"title": "原标题"},
        )
        session_id = create_response.json()["session_id"]
        
        response = client.put(
            f"/api/sessions/{session_id}/title",
            json={"title": "新标题"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "新标题"

    def test_delete_session(self, client: TestClient):
        """测试删除会话."""
        create_response = client.post(
            "/api/sessions",
            json={"title": "待删除会话"},
        )
        session_id = create_response.json()["session_id"]
        
        delete_response = client.delete(f"/api/sessions/{session_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"
        
        get_response = client.get(f"/api/sessions/{session_id}")
        assert get_response.status_code == 404

    def test_delete_session_not_found(self, client: TestClient):
        """测试删除不存在的会话."""
        response = client.delete("/api/sessions/non-existent-id")
        
        assert response.status_code == 404


class TestChatHistory:
    """测试聊天历史接口."""

    def test_get_chat_history_not_found(self, client: TestClient):
        """测试获取不存在的聊天历史."""
        response = client.get("/api/chat/history/non-existent-id")
        
        assert response.status_code == 404

    def test_add_message_to_session(self, client: TestClient):
        """测试向会话添加消息."""
        create_response = client.post(
            "/api/sessions",
            json={"title": "历史测试"},
        )
        session_id = create_response.json()["session_id"]
        
        response = client.post(
            f"/api/chat/history/{session_id}/messages",
            json={"role": "user", "content": "你好！"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["message_count"] == 1

    def test_add_multiple_messages(self, client: TestClient):
        """测试向会话添加多条消息."""
        create_response = client.post(
            "/api/sessions",
            json={"title": "多消息测试"},
        )
        session_id = create_response.json()["session_id"]
        
        client.post(
            f"/api/chat/history/{session_id}/messages",
            json={"role": "user", "content": "第一条消息"},
        )
        client.post(
            f"/api/chat/history/{session_id}/messages",
            json={"role": "assistant", "content": "第一条回复"},
        )
        client.post(
            f"/api/chat/history/{session_id}/messages",
            json={"role": "user", "content": "第二条消息"},
        )
        
        history_response = client.get(f"/api/sessions/{session_id}")
        assert history_response.status_code == 200
        data = history_response.json()
        assert len(data["messages"]) == 3


class TestChatAPI:
    """测试聊天接口."""

    def test_chat_request_validation_empty_message(self, client: TestClient):
        """测试聊天请求验证（空消息）."""
        response = client.post(
            "/api/chat",
            json={},
        )
        
        assert response.status_code == 422

    def test_chat_with_new_session(self, client: TestClient):
        """测试创建新会话并聊天."""
        response = client.post(
            "/api/chat",
            json={"message": "你好，请介绍一下你自己"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "response" in data

    def test_chat_with_existing_session(self, client: TestClient):
        """测试在现有会话中聊天."""
        create_response = client.post(
            "/api/sessions",
            json={"title": "连续对话测试"},
        )
        session_id = create_response.json()["session_id"]
        
        response = client.post(
            "/api/chat",
            json={
                "message": "我的名字是张三",
                "session_id": session_id,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        
        response2 = client.post(
            "/api/chat",
            json={
                "message": "你知道我的名字吗？",
                "session_id": session_id,
            },
        )
        
        assert response2.status_code == 200


class TestStreamingChatAPI:
    """测试流式聊天接口."""

    def test_stream_chat_endpoint(self, client: TestClient):
        """测试流式聊天端点存在."""
        response = client.post(
            "/api/chat/stream",
            json={"message": "讲个笑话"},
            stream=True,
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    def test_stream_chat_format(self, client: TestClient):
        """测试流式聊天返回格式（SSE）."""
        response = client.post(
            "/api/chat/stream",
            json={"message": "你好"},
            stream=True,
        )
        
        assert response.status_code == 200
        
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line.decode("utf-8"))
        
        assert len(lines) > 0
        for line in lines:
            if line.startswith("data: "):
                data = json.loads(line[6:])
                assert "type" in data


class TestDatabaseOperations:
    """测试数据库操作."""

    def test_database_init(self, test_db_path: str):
        """测试数据库初始化."""
        from mini_agent.web.database import init_database, Database
        
        db = init_database(test_db_path)
        assert db is not None
        assert Path(test_db_path).exists()

    def test_session_model(self):
        """测试会话模型."""
        from mini_agent.web.database import SessionModel
        from datetime import datetime
        
        now = datetime.now().isoformat()
        session = SessionModel(
            session_id="test-001",
            title="测试",
            messages=[{"role": "user", "content": "测试"}],
            created_at=now,
            updated_at=now,
        )
        
        assert session.session_id == "test-001"
        assert session.title == "测试"
        assert len(session.messages) == 1
        
        json_str = session.to_json()
        assert "test-001" in json_str

    def test_database_session_crud(self, test_db_path: str):
        """测试数据库会话 CRUD."""
        from mini_agent.web.database import Database, SessionModel, init_database
        from datetime import datetime
        
        db = init_database(test_db_path)
        
        now = datetime.now().isoformat()
        session = SessionModel(
            session_id="crud-test-001",
            title="CRUD测试",
            messages=[],
            created_at=now,
            updated_at=now,
        )
        
        db.create_session(session)
        
        retrieved = db.get_session("crud-test-001")
        assert retrieved is not None
        assert retrieved.title == "CRUD测试"
        
        retrieved.messages.append({"role": "user", "content": "测试"})
        db.update_session(retrieved)
        
        updated = db.get_session("crud-test-001")
        assert len(updated.messages) == 1
        
        deleted = db.delete_session("crud-test-001")
        assert deleted is True
        
        not_found = db.get_session("crud-test-001")
        assert not_found is None

    def test_database_list_sessions(self, test_db_path: str):
        """测试数据库列出会话."""
        from mini_agent.web.database import Database, SessionModel, init_database
        from datetime import datetime
        
        db = init_database(test_db_path)
        
        sessions = db.list_sessions(limit=10, offset=0)
        assert isinstance(sessions, list)

    def test_database_add_message(self, test_db_path: str):
        """测试数据库添加消息."""
        from mini_agent.web.database import Database, SessionModel, init_database
        from datetime import datetime
        
        db = init_database(test_db_path)
        
        now = datetime.now().isoformat()
        session = SessionModel(
            session_id="msg-test-001",
            title="消息测试",
            messages=[],
            created_at=now,
            updated_at=now,
        )
        
        db.create_session(session)
        
        message = {"role": "user", "content": "测试消息"}
        updated = db.add_message("msg-test-001", message)
        
        assert updated is not None
        assert len(updated.messages) == 1

    def test_database_get_session_count(self, test_db_path: str):
        """测试获取会话数量."""
        from mini_agent.web.database import init_database
        
        db = init_database(test_db_path)
        
        count = db.get_session_count()
        assert isinstance(count, int)
        assert count >= 0


class TestRequestValidation:
    """测试请求验证."""

    def test_create_session_request(self, client: TestClient):
        """测试创建会话请求验证."""
        response = client.post("/api/sessions", json={})
        assert response.status_code == 200

    def test_list_sessions_query_params(self, client: TestClient):
        """测试列出会话查询参数."""
        response = client.get("/api/sessions?limit=10")
        assert response.status_code == 200
        
        response = client.get("/api/sessions?limit=1000")
        assert response.status_code == 422

    def test_update_title_request(self, client: TestClient):
        """测试更新标题请求."""
        create_response = client.post("/api/sessions", json={})
        session_id = create_response.json()["session_id"]
        
        response = client.put(
            f"/api/sessions/{session_id}/title",
            json={},
        )
        assert response.status_code == 200


class TestErrorHandling:
    """测试错误处理."""

    def test_invalid_session_id_format(self, client: TestClient):
        """测试无效的会话ID格式."""
        response = client.get("/api/sessions/../../../etc/passwd")
        assert response.status_code == 404

    def test_session_isolation(self, client: TestClient):
        """测试会话隔离（不同会话数据独立）."""
        session1 = client.post(
            "/api/sessions",
            json={"title": "会话1"},
        ).json()["session_id"]
        
        session2 = client.post(
            "/api/sessions",
            json={"title": "会话2"},
        ).json()["session_id"]
        
        assert session1 != session2
        
        client.post(
            f"/api/chat/history/{session1}/messages",
            json={"role": "user", "content": "会话1的消息"},
        )
        
        history1 = client.get(f"/api/sessions/{session1}").json()
        history2 = client.get(f"/api/sessions/{session2}").json()
        
        assert len(history1["messages"]) == 1
        assert len(history2["messages"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
