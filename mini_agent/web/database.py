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


class UserModel(BaseModel):
    """用户数据模型.
    
    Attributes:
        user_id: 用户唯一标识符
        username: 用户名
        organization_id: 机构ID
        email: 用户邮箱
        created_at: 创建时间
        updated_at: 更新时间
    """
    
    user_id: str
    username: str
    organization_id: str = ""
    email: str = ""
    created_at: str
    updated_at: str


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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tool_call_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_call_id TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    result TEXT,
                    success INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tool_call_session ON tool_call_records(session_id)
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("PRAGMA table_info(session_files)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'username' not in columns:
                cursor.execute("ALTER TABLE session_files ADD COLUMN username TEXT DEFAULT ''")
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_files_session ON session_files(session_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_files_username ON session_files(username)
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    organization_id TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
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

    def add_tool_call_record(
        self,
        session_id: str,
        message_id: str,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
        result: Optional[str] = None,
        success: bool = True
    ) -> int:
        """保存工具调用记录.

        Args:
            session_id: 会话ID
            message_id: 消息ID
            tool_name: 工具名称
            tool_call_id: 工具调用ID
            arguments: 工具参数
            result: 工具执行结果
            success: 是否执行成功

        Returns:
            记录ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tool_call_records 
                (session_id, message_id, tool_name, tool_call_id, arguments, result, success, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    message_id,
                    tool_name,
                    tool_call_id,
                    json.dumps(arguments, ensure_ascii=False),
                    result,
                    1 if success else 0,
                    datetime.now().isoformat(),
                )
            )
            return cursor.lastrowid

    def get_tool_call_records(
        self,
        session_id: str,
        message_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """获取工具调用记录列表.

        Args:
            session_id: 会话ID
            message_id: 消息ID（可选）

        Returns:
            工具调用记录列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if message_id:
                cursor.execute(
                    """
                    SELECT id, session_id, message_id, tool_name, tool_call_id, 
                           arguments, result, success, created_at
                    FROM tool_call_records 
                    WHERE session_id = ? AND message_id = ?
                    ORDER BY id ASC
                    """,
                    (session_id, message_id)
                )
            else:
                cursor.execute(
                    """
                    SELECT id, session_id, message_id, tool_name, tool_call_id, 
                           arguments, result, success, created_at
                    FROM tool_call_records 
                    WHERE session_id = ?
                    ORDER BY id ASC
                    """,
                    (session_id,)
                )
            
            rows = cursor.fetchall()
            records = []
            for row in rows:
                records.append({
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "message_id": row["message_id"],
                    "tool_name": row["tool_name"],
                    "tool_call_id": row["tool_call_id"],
                    "arguments": json.loads(row["arguments"]) if row["arguments"] else {},
                    "result": row["result"],
                    "success": bool(row["success"]),
                    "created_at": row["created_at"],
                })
            return records

    def update_tool_call_result(
        self,
        session_id: str,
        message_id: str,
        tool_call_id: str,
        result: str,
        success: bool = True
    ) -> bool:
        """更新工具调用结果.

        Args:
            session_id: 会话ID
            message_id: 消息ID
            tool_call_id: 工具调用ID
            result: 工具执行结果
            success: 是否执行成功

        Returns:
            是否更新成功
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tool_call_records 
                SET result = ?, success = ?
                WHERE session_id = ? AND message_id = ? AND tool_call_id = ?
                """,
                (result, 1 if success else 0, session_id, message_id, tool_call_id)
            )
            return cursor.rowcount > 0

    def add_session_file(
        self,
        session_id: str,
        filename: str,
        file_path: str,
        file_type: str,
        size: int,
        username: str = ""
    ) -> int:
        """添加会话文件记录.

        Args:
            session_id: 会话ID
            filename: 文件名
            file_path: 文件路径
            file_type: 文件类型
            size: 文件大小
            username: 用户名

        Returns:
            记录ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO session_files (session_id, filename, file_path, file_type, size, uploaded_at, username)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    filename,
                    file_path,
                    file_type,
                    size,
                    datetime.now().isoformat(),
                    username
                )
            )
            return cursor.lastrowid

    def get_session_files(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话文件列表.

        Args:
            session_id: 会话ID

        Returns:
            文件列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, session_id, filename, file_path, file_type, size, uploaded_at, username
                FROM session_files
                WHERE session_id = ?
                ORDER BY id DESC
                """,
                (session_id,)
            )
            
            rows = cursor.fetchall()
            files = []
            for row in rows:
                files.append({
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "filename": row["filename"],
                    "file_path": row["file_path"],
                    "file_type": row["file_type"],
                    "size": row["size"],
                    "uploaded_at": row["uploaded_at"],
                    "username": row["username"] or "",
                })
            return files

    def get_user_files(self, username: str) -> list[dict[str, Any]]:
        """获取用户上传的所有文件.

        Args:
            username: 用户名

        Returns:
            文件列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT sf.id, sf.session_id, sf.filename, sf.file_path, sf.file_type, 
                       sf.size, sf.uploaded_at, sf.username, s.title as session_title
                FROM session_files sf
                LEFT JOIN sessions s ON sf.session_id = s.session_id
                WHERE sf.username = ?
                ORDER BY sf.id DESC
                """,
                (username,)
            )
            
            rows = cursor.fetchall()
            files = []
            for row in rows:
                files.append({
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "filename": row["filename"],
                    "file_path": row["file_path"],
                    "file_type": row["file_type"],
                    "size": row["size"],
                    "uploaded_at": row["uploaded_at"],
                    "username": row["username"] or "",
                    "session_title": row["session_title"] or "",
                })
            return files

    def delete_session_file(self, file_id: int) -> bool:
        """删除会话文件记录.

        Args:
            file_id: 文件记录ID

        Returns:
            是否删除成功
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM session_files WHERE id = ?
                """,
                (file_id,)
            )
            return cursor.rowcount > 0

    def create_user(self, user_data: UserModel) -> UserModel:
        """创建用户.

        Args:
            user_data: 用户数据对象

        Returns:
            创建的用户数据对象
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (user_id, username, organization_id, email, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_data.user_id,
                    user_data.username,
                    user_data.organization_id,
                    user_data.email,
                    user_data.created_at,
                    user_data.updated_at,
                )
            )
        return user_data

    def get_user(self, user_id: str) -> Optional[UserModel]:
        """获取用户信息.

        Args:
            user_id: 用户ID

        Returns:
            用户数据对象，如果不存在则返回None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT user_id, username, organization_id, email, created_at, updated_at
                FROM users WHERE user_id = ?
                """,
                (user_id,)
            )
            row = cursor.fetchone()
        
        if row is None:
            return None
        
        return UserModel(
            user_id=row["user_id"],
            username=row["username"],
            organization_id=row["organization_id"] or "",
            email=row["email"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_user_by_username(self, username: str) -> Optional[UserModel]:
        """通过用户名获取用户信息.

        Args:
            username: 用户名

        Returns:
            用户数据对象，如果不存在则返回None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT user_id, username, organization_id, email, created_at, updated_at
                FROM users WHERE username = ?
                """,
                (username,)
            )
            row = cursor.fetchone()
        
        if row is None:
            return None
        
        return UserModel(
            user_id=row["user_id"],
            username=row["username"],
            organization_id=row["organization_id"] or "",
            email=row["email"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_user(self, user_data: UserModel) -> UserModel:
        """更新用户信息.

        Args:
            user_data: 用户数据对象

        Returns:
            更新后的用户数据对象
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT username FROM users WHERE user_id = ?", (user_data.user_id,))
            row = cursor.fetchone()
            old_username = row[0] if row else None
            
            cursor.execute(
                """
                UPDATE users
                SET username = ?,
                    organization_id = ?,
                    email = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (
                    user_data.username,
                    user_data.organization_id,
                    user_data.email,
                    user_data.updated_at,
                    user_data.user_id,
                )
            )
            
            if old_username and old_username != user_data.username:
                cursor.execute(
                    "UPDATE session_files SET username = ? WHERE username = ?",
                    (user_data.username, old_username)
                )
            
            conn.commit()
        return user_data

    def get_or_create_default_user(self) -> UserModel:
        """获取或创建默认用户.

        Returns:
            默认用户数据对象
        """
        import uuid
        
        default_user = self.get_user("default")
        if default_user:
            return default_user
        
        now = datetime.now().isoformat()
        user_data = UserModel(
            user_id="default",
            username="default_user",
            organization_id="",
            email="",
            created_at=now,
            updated_at=now,
        )
        return self.create_user(user_data)


_db_instance: Optional[Database] = None


def get_database() -> Database:
    """获取数据库单例.
    
    Returns:
        Database实例
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        _db_instance.init_tables()
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
