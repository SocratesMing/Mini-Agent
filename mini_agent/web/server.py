"""FastAPI Web Server for Mini Agent.

提供会话管理和流式聊天的 REST API 接口.
支持多用户并发访问，会话级别Agent复用.
"""

import asyncio
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mini_agent.web.database import Database, init_database as init_db


agent_config = None
db_instance = None


def setup_logging():
    """配置日志：同时输出到控制台和文件."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / "mini_agent.log"
    
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    
    return log_file


def load_system_prompt(path: str) -> str:
    """加载系统提示词."""
    prompt_path = Path(path)
    if prompt_path.exists():
        with open(prompt_path, encoding="utf-8") as f:
            return f.read()
    return "你是一个有帮助的 AI 助手."


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理."""
    global agent_config, db_instance
    
    project_root = Path(__file__).parent.parent.parent
    
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    os.chdir(project_root)
    
    log_file = setup_logging()
    logger = logging.getLogger(__name__)
    logger.info(f"日志文件: {log_file}")
    
    def get_tools(enable_file_tools: bool, enable_bash: bool, enable_note: bool) -> list:
        """获取基础工具列表."""
        from mini_agent.tools import BashTool, ReadTool, WriteTool, EditTool, SessionNoteTool
        tools = []
        
        if enable_bash:
            tools.append(BashTool())
        
        if enable_file_tools:
            tools.extend([
                ReadTool(workspace_dir=str(project_root / "workspace")),
                WriteTool(workspace_dir=str(project_root / "workspace")),
                EditTool(workspace_dir=str(project_root / "workspace")),
            ])
        
        if enable_note:
            tools.append(SessionNoteTool(memory_file=str(project_root / "workspace" / ".agent_memory.json")))
        
        return tools
    
    try:
        from mini_agent.config import Config as AppConfig
        from mini_agent.llm import LLMClient
        from mini_agent.schema import LLMProvider
        
        app_config = AppConfig.load()
        
        provider = LLMProvider.ANTHROPIC if app_config.llm.provider == "anthropic" else LLMProvider.OPENAI
        llm_client = LLMClient(
            api_key=app_config.llm.api_key,
            provider=provider,
            api_base=app_config.llm.api_base,
            model=app_config.llm.model,
            retry_config=app_config.llm.retry,
        )
        tools = get_tools(
            enable_file_tools=app_config.tools.enable_file_tools,
            enable_bash=app_config.tools.enable_bash,
            enable_note=app_config.tools.enable_note,
        )
        system_prompt = load_system_prompt(app_config.agent.system_prompt_path)
        
        agent_config = {
            "llm_client": llm_client,
            "tools": tools,
            "system_prompt": system_prompt,
            "max_steps": app_config.agent.max_steps,
            "workspace_dir": app_config.agent.workspace_dir,
        }
        
        logger.info("Agent 配置加载成功")
        
    except Exception as e:
        logger.warning(f"加载配置失败: {e}")
        agent_config = None
    
    db_instance = init_db()
    logger.info("数据库初始化完成")
    
    yield
    
    if db_instance:
        db_instance.close()
    logger.info("服务器关闭")


app = FastAPI(
    title="Mini Agent API",
    description="REST API for Mini Agent with session management and streaming chat. Supports multi-user concurrency with session-level Agent reuse.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from mini_agent.web.routes.sessions import router as sessions_router
from mini_agent.web.routes.chat import router as chat_router

app.include_router(sessions_router)
app.include_router(chat_router)


@app.get("/", tags=["System"])
async def root():
    """API 信息."""
    return {
        "message": "Mini Agent API Server",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["System"])
async def health_check():
    """健康检查."""
    return {
        "status": "healthy",
        "agent_configured": agent_config is not None,
        "database_initialized": db_instance is not None,
    }


if __name__ == "__main__":
    print("=" * 50)
    print("  Mini Agent API Server")
    print("=" * 50)
    print()
    print("  Swagger UI:  http://localhost:8000/docs")
    print("  ReDoc:      http://localhost:8000/redoc")
    print("  Health:     http://localhost:8000/health")
    print()
    print("  Session-level Agent reuse: Enabled")
    print("=" * 50)
    print()
    
    import uvicorn
    uvicorn.run(
        "mini_agent.web.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1,
    )
