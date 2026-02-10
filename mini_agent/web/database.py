"""数据库模型和连接管理.

使用 SQLite3 提供轻量级数据持久化.
"""

import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional

import sqlite3
from pydantic import BaseModel


DATABASE_PATH = "./data/mini_agent.db"


class DatabaseConfig(BaseModel):
    """数据库配置."""
    
    path: str = "./data/mini_agent.db"
    
    @property
    def connection_string(self) -> str:
        """获取数据库连接路径."""
        return self.path


def ensure_database_dir():
    """确保数据库目录存在."""
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)


class SessionModel(BaseModel):
    """会话数据模型.
    
    Attributes:
        session_id: 会话唯一标识符
        title: 会话标题
        messages: 消息列表，存储为JSON格式
        created_at: 创建时间
        updated_at: 更新时间
    """
    
    session_id: str
    title: str
    messages: list[dict[str, Any]]
    created_at: str
    updated_at: str
    
    def to_json(self) -> str:
        """转换为JSON字符串."""
        return json.dumps(self.model_dump(), ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> "SessionModel":
        """从JSON字符串解析."""
        data = json.loads(json_str)
        return cls(**data)


class Database:
    """SQLite3 数据库管理类.
    
    提供数据库连接、初始化和会话操作的方法.
    """
    
    def __init__(self, db_path: str = None):
        """初始化数据库连接.
        
        Args:
            db_path: 数据库文件路径，如果为None则使用默认路径
        """
        if db_path is None:
            ensure_database_dir()
            db_path = DATABASE_PATH
        
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def close(self):
        """关闭数据库连接."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """获取数据库连接的上下文管理器.
        
        Yields:
            SQLite3 Connection对象
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def init_tables(self):
        """初始化数据库表结构."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_updated_at ON sessions(updated_at)
            """)
            conn.commit()
    
    def create_session(self, session_data: SessionModel) -> SessionModel:
        """创建新会话.
        
        Args:
            session_data: 会话数据对象
            
        Returns:
            创建的会话数据对象
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sessions (session_id, title, messages, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_data.session_id,
                    session_data.title,
                    json.dumps(session_data.messages, ensure_ascii=False),
                    session_data.created_at,
                    session_data.updated_at,
                )
            )
        return session_data
    
    def get_session(self, session_id: str) -> Optional[SessionModel]:
        """获取会话信息.
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话数据对象，如果不存在则返回None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, title, messages, created_at, updated_at
                FROM sessions WHERE session_id = ?
                """,
                (session_id,)
            )
            row = cursor.fetchone()
        
        if row is None:
            return None
        
        return SessionModel(
            session_id=row["session_id"],
            title=row["title"],
            messages=json.loads(row["messages"]) if row["messages"] else [],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    
    def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> list[SessionModel]:
        """获取会话列表.
        
        Args:
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            会话数据对象列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, title, messages, created_at, updated_at
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
            rows = cursor.fetchall()
        
        sessions = []
        for row in rows:
            sessions.append(SessionModel(
                session_id=row["session_id"],
                title=row["title"],
                messages=json.loads(row["messages"]) if row["messages"] else [],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            ))
        return sessions
    
    def update_session(self, session_data: SessionModel) -> SessionModel:
        """更新会话.
        
        Args:
            session_data: 会话数据对象
            
        Returns:
            更新后的会话数据对象
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET title = ?,
                    messages = ?,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    session_data.title,
                    json.dumps(session_data.messages, ensure_ascii=False),
                    session_data.updated_at,
                    session_data.session_id,
                )
            )
        return session_data
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话.
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否删除成功
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,)
            )
        return cursor.rowcount > 0
    
    def add_message(
        self,
        session_id: str,
        message: dict[str, Any]
    ) -> Optional[SessionModel]:
        """向会话添加消息.
        
        Args:
            session_id: 会话ID
            message: 消息数据
            
        Returns:
            更新后的会话对象，如果会话不存在则返回None
        """
        session = self.get_session(session_id)
        if session is None:
            return None
        
        session.messages.append(message)
        session.updated_at = datetime.now().isoformat()
        self.update_session(session)
        return session
    
    def get_session_count(self) -> int:
        """获取会话总数."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sessions")
            return cursor.fetchone()[0]


_db_instance: Optional[Database] = None


def get_database() -> Database:
    """获取数据库单例.
    
    Returns:
        Database实例
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


def init_database(db_path: str = None) -> Database:
    """初始化数据库.
    
    Args:
        db_path: 可选的数据库路径
        
    Returns:
        Database实例
    """
    global _db_instance
    _db_instance = Database(db_path)
    _db_instance.init_tables()
    return _db_instance
