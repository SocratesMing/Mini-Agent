"""数据库模型和连接管理.

支持 SQLite3 (本地) 和 MySQL (远程) 数据库.
"""

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional

import sqlite3
import pymysql
from pydantic import BaseModel
from dbutils.pooled_db import PooledDB
from queue import Queue
import threading


DATABASE_PATH = "./data/mini_agent.db"
logger = logging.getLogger(__name__)


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


class ScheduledTaskModel(BaseModel):
    """定时任务数据模型."""
    task_id: str
    username: str
    name: str
    description: str
    cron_expression: str
    enabled: bool = True
    created_at: str
    updated_at: str


class TaskExecutionModel(BaseModel):
    """任务执行记录模型."""
    execution_id: str
    task_id: str
    username: str
    status: str
    result: str = ""
    error_message: str = ""
    started_at: str
    completed_at: str = ""


class Database:
    """数据库管理类.
    
    支持 SQLite3 (本地) 和 MySQL (远程) 数据库.
    """
    
    def __init__(self, db_config: dict = None):
        """初始化数据库连接.
        
        Args:
            db_config: 数据库配置字典，支持以下格式:
                - SQLite: {"type": "sqlite", "path": "./data/mini_agent.db"}
                - MySQL: {"type": "mysql", "host": "localhost", "port": 3306, "user": "root", "password": "xxx", "database": "mini_agent", ...}
        """
        self.db_type = "sqlite"
        self._connection: Optional[sqlite3.Connection] = None
        self._pool: Optional[PooledDB] = None
    
        if db_config:
            self.db_type = db_config.get("type", "sqlite")
            
            if self.db_type == "sqlite":
                self.db_path = db_config.get("path", DATABASE_PATH)
                ensure_database_dir()
                logger.info(f"数据库类型: SQLite | 路径: {self.db_path}")
            elif self.db_type == "mysql":
                self._mysql_config = db_config.get("mysql", {})
                self._init_mysql_pool()
                logger.info(f"数据库类型: MySQL | 主机: {self._mysql_config.get('host')}:{self._mysql_config.get('port')} | 数据库: {self._mysql_config.get('database')} | 用户: {self._mysql_config.get('user')}")
        else:
            self.db_path = DATABASE_PATH
            ensure_database_dir()
            logger.info(f"数据库类型: SQLite | 路径: {self.db_path}")
    
    def _init_mysql_pool(self):
        """初始化MySQL连接池."""
        pool_config = self._mysql_config.get("pool", {})
        self._pool = PooledDB(
            creator=pymysql,
            maxconnections=pool_config.get("pool_size", 5) + pool_config.get("max_overflow", 10),
            mincached=1,
            maxcached=pool_config.get("pool_size", 5),
            blocking=True,
            maxusage=pool_config.get("pool_recycle", 3600),
            host=self._mysql_config.get("host", "localhost"),
            port=self._mysql_config.get("port", 3306),
            user=self._mysql_config.get("user", "root"),
            password=self._mysql_config.get("password", ""),
            database=self._mysql_config.get("database", "mini_agent"),
            charset=self._mysql_config.get("charset", "utf8mb4"),
            connect_timeout=self._mysql_config.get("connect_timeout", 10),
            read_timeout=self._mysql_config.get("read_timeout", 30),
            write_timeout=self._mysql_config.get("write_timeout", 30),
            cursorclass=pymysql.cursors.DictCursor,
        )
        
        try:
            conn = self._pool.connection()
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            cursor.close()
            conn.close()
            logger.info(f"MySQL连接成功 | 版本: {version['VERSION()'] if version else '未知'}")
        except Exception as e:
            logger.error(f"MySQL连接失败: {e}")
            raise
    
    def _get_sqlite_connection(self) -> sqlite3.Connection:
        """获取SQLite数据库连接."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def _get_mysql_connection(self):
        """获取MySQL数据库连接."""
        if self._pool is None:
            self._init_mysql_pool()
        return self._pool.connection()
    
    def _get_connection(self):
        """获取数据库连接."""
        if self.db_type == "mysql":
            return self._get_mysql_connection()
        return self._get_sqlite_connection()
    
    def close(self):
        """关闭数据库连接."""
        if self.db_type == "mysql":
            if self._pool:
                self._pool.close()
                self._pool = None
        else:
            if self._connection:
                self._connection.close()
                self._connection = None
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器.
        
        Yields:
            数据库连接对象
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _execute(self, cursor, sql: str, params: tuple = None):
        """执行SQL语句，自动处理占位符差异.
        
        SQLite 使用 ? 占位符，MySQL 使用 %s 占位符.
        """
        if self.db_type == "mysql":
            import re
            sql = re.sub(r'\?', '%s', sql)
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
    
    def _create_index(self, cursor, index_name: str, table_name: str, columns: str):
        """创建索引，兼容SQLite和MySQL."""
        if self.db_type == "sqlite":
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({columns})")
        else:
            try:
                cursor.execute(f"CREATE INDEX {index_name} ON {table_name}({columns})")
            except Exception as e:
                if "Duplicate key name" in str(e) or "already exists" in str(e):
                    pass
                else:
                    raise
    
    def init_tables(self):
        """初始化数据库表结构."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if self.db_type == "mysql":
                auto_inc = "AUTO_INCREMENT"
            else:
                auto_inc = "AUTOINCREMENT"
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id VARCHAR(255) PRIMARY KEY,
                    title TEXT NOT NULL,
                    messages TEXT NOT NULL,
                    created_at VARCHAR(50) NOT NULL,
                    updated_at VARCHAR(50) NOT NULL
                )
            """)
            self._create_index(cursor, "idx_updated_at", "sessions", "updated_at")
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS tool_call_records (
                    id INTEGER PRIMARY KEY {auto_inc},
                    session_id VARCHAR(255) NOT NULL,
                    message_id VARCHAR(255) NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_call_id VARCHAR(255) NOT NULL,
                    arguments TEXT NOT NULL,
                    result TEXT,
                    success INTEGER NOT NULL DEFAULT 1,
                    created_at VARCHAR(50) NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            """)
            self._create_index(cursor, "idx_tool_call_session", "tool_call_records", "session_id")
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS session_files (
                    id INTEGER PRIMARY KEY {auto_inc},
                    session_id VARCHAR(255) NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type VARCHAR(50) NOT NULL,
                    size INTEGER NOT NULL,
                    uploaded_at VARCHAR(50) NOT NULL,
                    username VARCHAR(255) DEFAULT '',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            """)
            
            if self.db_type == "sqlite":
                cursor.execute("PRAGMA table_info(session_files)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'username' not in columns:
                    cursor.execute("ALTER TABLE session_files ADD COLUMN username TEXT DEFAULT ''")
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS generated_files (
                    id INTEGER PRIMARY KEY {auto_inc},
                    session_id VARCHAR(255) NOT NULL,
                    message_id VARCHAR(255) NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type VARCHAR(50) NOT NULL,
                    size INTEGER NOT NULL,
                    created_at VARCHAR(50) NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            """)
            self._create_index(cursor, "idx_generated_files_session", "generated_files", "session_id")
            self._create_index(cursor, "idx_generated_files_message", "generated_files", "session_id, message_id")
            self._create_index(cursor, "idx_session_files_session", "session_files", "session_id")
            self._create_index(cursor, "idx_session_files_username", "session_files", "username")
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(255) PRIMARY KEY,
                    username VARCHAR(255) NOT NULL UNIQUE,
                    organization_id VARCHAR(255) DEFAULT '',
                    email VARCHAR(255) DEFAULT '',
                    created_at VARCHAR(50) NOT NULL,
                    updated_at VARCHAR(50) NOT NULL
                )
            """)
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    task_id VARCHAR(255) PRIMARY KEY,
                    username VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description VARCHAR(255) DEFAULT '',
                    cron_expression VARCHAR(100) NOT NULL,
                    enabled BOOLEAN DEFAULT 1,
                    created_at VARCHAR(50) NOT NULL,
                    updated_at VARCHAR(50) NOT NULL
                )
            """)
            self._create_index(cursor, "idx_scheduled_tasks_username", "scheduled_tasks", "username")
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS task_executions (
                    execution_id VARCHAR(255) PRIMARY KEY,
                    task_id VARCHAR(255) NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    result VARCHAR(255) DEFAULT '',
                    error_message VARCHAR(255) DEFAULT '',
                    started_at VARCHAR(50) NOT NULL,
                    completed_at VARCHAR(50) DEFAULT '',
                    FOREIGN KEY (task_id) REFERENCES scheduled_tasks(task_id) ON DELETE CASCADE
                )
            """)
            self._create_index(cursor, "idx_task_executions_task", "task_executions", "task_id")
            self._create_index(cursor, "idx_task_executions_started", "task_executions", "started_at")
            
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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            self._execute(cursor, "SELECT COUNT(*) FROM sessions")
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
            self._execute(
                cursor,
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
                self._execute(
                    cursor,
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
                self._execute(
                    cursor,
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
            self._execute(
                cursor,
                """
                UPDATE tool_call_records 
                SET result = ?, success = ?
                WHERE session_id = ? AND message_id = ? AND tool_call_id = ?
                """,
                (result, 1 if success else 0, session_id, message_id, tool_call_id)
            )
            return cursor.rowcount > 0

    def add_generated_file(
        self,
        session_id: str,
        message_id: str,
        filename: str,
        file_path: str,
        file_type: str,
        size: int,
    ) -> int:
        """添加生成的文件记录.

        Args:
            session_id: 会话ID
            message_id: 消息ID
            filename: 文件名
            file_path: 文件路径
            file_type: 文件类型
            size: 文件大小

        Returns:
            记录ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute(
                cursor,
                """
                INSERT INTO generated_files 
                (session_id, message_id, filename, file_path, file_type, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    message_id,
                    filename,
                    file_path,
                    file_type,
                    size,
                    datetime.now().isoformat(),
                )
            )
            return cursor.lastrowid

    def get_generated_files(
        self,
        session_id: str,
        message_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """获取生成的文件列表.

        Args:
            session_id: 会话ID
            message_id: 消息ID（可选）

        Returns:
            文件列表
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if message_id:
                self._execute(
                    cursor,
                    """
                    SELECT id, session_id, message_id, filename, file_path, file_type, size, created_at
                    FROM generated_files
                    WHERE session_id = ? AND message_id = ?
                    ORDER BY created_at DESC
                    """,
                    (session_id, message_id)
                )
            else:
                self._execute(
                    cursor,
                    """
                    SELECT id, session_id, message_id, filename, file_path, file_type, size, created_at
                    FROM generated_files
                    WHERE session_id = ?
                    ORDER BY created_at DESC
                    """,
                    (session_id,)
                )
            
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "message_id": row["message_id"],
                    "filename": row["filename"],
                    "file_path": row["file_path"],
                    "file_type": row["file_type"],
                    "size": row["size"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            self._execute(
                cursor,
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
            
            self._execute(cursor, "SELECT username FROM users WHERE user_id = ?", (user_data.user_id,))
            row = cursor.fetchone()
            old_username = row["username"] if row else None
            
            self._execute(
                cursor,
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
                self._execute(
                    cursor,
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

    def create_scheduled_task(self, task: ScheduledTaskModel) -> ScheduledTaskModel:
        """创建定时任务."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute(
                cursor,
                """
                INSERT INTO scheduled_tasks (task_id, username, name, description, cron_expression, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.username,
                    task.name,
                    task.description,
                    task.cron_expression,
                    1 if task.enabled else 0,
                    task.created_at,
                    task.updated_at,
                )
            )
            conn.commit()
        return task

    def get_scheduled_tasks(self, username: str) -> list[ScheduledTaskModel]:
        """获取用户的所有定时任务."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute(
                cursor,
                "SELECT task_id, username, name, description, cron_expression, enabled, created_at, updated_at FROM scheduled_tasks WHERE username = ? ORDER BY created_at DESC",
                (username,),
            )
            rows = cursor.fetchall()
            tasks = []
            for row in rows:
                tasks.append(ScheduledTaskModel(
                    task_id=row["task_id"],
                    username=row["username"],
                    name=row["name"],
                    description=row["description"],
                    cron_expression=row["cron_expression"],
                    enabled=bool(row["enabled"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                ))
            return tasks

    def get_scheduled_task(self, task_id: str) -> Optional[ScheduledTaskModel]:
        """获取定时任务详情."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute(
                cursor,
                "SELECT task_id, username, name, description, cron_expression, enabled, created_at, updated_at FROM scheduled_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ScheduledTaskModel(
                task_id=row["task_id"],
                username=row["username"],
                name=row["name"],
                description=row["description"],
                cron_expression=row["cron_expression"],
                enabled=bool(row["enabled"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def update_scheduled_task(self, task: ScheduledTaskModel) -> ScheduledTaskModel:
        """更新定时任务."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute(
                cursor,
                """
                UPDATE scheduled_tasks SET name = ?, description = ?, cron_expression = ?, enabled = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (task.name, task.description, task.cron_expression, 1 if task.enabled else 0, task.updated_at, task.task_id),
            )
            conn.commit()
        return task

    def delete_scheduled_task(self, task_id: str) -> bool:
        """删除定时任务."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute(cursor, "DELETE FROM scheduled_tasks WHERE task_id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def create_task_execution(self, execution: TaskExecutionModel) -> TaskExecutionModel:
        """创建任务执行记录."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute(
                cursor,
                """
                INSERT INTO task_executions (execution_id, task_id, username, status, result, error_message, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.execution_id,
                    execution.task_id,
                    execution.username,
                    execution.status,
                    execution.result,
                    execution.error_message,
                    execution.started_at,
                    execution.completed_at,
                )
            )
            conn.commit()
        return execution

    def get_task_executions(self, task_id: str, limit: int = 50) -> list[TaskExecutionModel]:
        """获取任务的执行记录."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute(
                cursor,
                "SELECT execution_id, task_id, username, status, result, error_message, started_at, completed_at FROM task_executions WHERE task_id = ? ORDER BY started_at DESC LIMIT ?",
                (task_id, limit),
            )
            rows = cursor.fetchall()
            executions = []
            for row in rows:
                executions.append(TaskExecutionModel(
                    execution_id=row["execution_id"],
                    task_id=row["task_id"],
                    username=row["username"],
                    status=row["status"],
                    result=row["result"],
                    error_message=row["error_message"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                ))
            return executions

    def update_task_execution(self, execution: TaskExecutionModel) -> TaskExecutionModel:
        """更新任务执行记录."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._execute(
                cursor,
                """
                UPDATE task_executions SET status = ?, result = ?, error_message = ?, completed_at = ?
                WHERE execution_id = ?
                """,
                (execution.status, execution.result, execution.error_message, execution.completed_at, execution.execution_id),
            )
            conn.commit()
        return execution


_db_instance: Optional[Database] = None


def _load_db_config_from_app_config() -> dict:
    """从应用配置加载数据库配置."""
    try:
        from mini_agent.config import Config
        config_path = Config.get_default_config_path()
        logger.info(f"加载配置文件: {config_path}")
        app_config = Config.load()
        db_config = app_config.database
        
        if db_config.type == "mysql":
            mysql_cfg = db_config.mysql
            pool_cfg = mysql_cfg.pool
            return {
                "type": "mysql",
                "mysql": {
                    "host": mysql_cfg.host,
                    "port": mysql_cfg.port,
                    "user": mysql_cfg.user,
                    "password": mysql_cfg.password,
                    "database": mysql_cfg.database,
                    "charset": mysql_cfg.charset,
                    "pool": {
                        "pool_size": pool_cfg.pool_size,
                        "max_overflow": pool_cfg.max_overflow,
                        "pool_timeout": pool_cfg.pool_timeout,
                        "pool_recycle": pool_cfg.pool_recycle,
                    },
                    "connect_timeout": mysql_cfg.connect_timeout,
                    "read_timeout": mysql_cfg.read_timeout,
                    "write_timeout": mysql_cfg.write_timeout,
                }
            }
        else:
            return {
                "type": "sqlite",
                "path": db_config.sqlite.path,
            }
    except Exception as e:
        logger.warning(f"加载数据库配置失败，使用默认SQLite配置: {e}")
        return {"type": "sqlite", "path": DATABASE_PATH}


def get_database() -> Database:
    """获取数据库单例.
    
    Returns:
        Database实例
    """
    global _db_instance
    if _db_instance is None:
        db_config = _load_db_config_from_app_config()
        _db_instance = Database(db_config)
        _db_instance.init_tables()
    return _db_instance


def init_database(db_config: dict = None) -> Database:
    """初始化数据库.
    
    Args:
        db_config: 可选的数据库配置字典
        
    Returns:
        Database实例
    """
    global _db_instance
    if db_config is None:
        db_config = _load_db_config_from_app_config()
    _db_instance = Database(db_config)
    _db_instance.init_tables()
    return _db_instance
