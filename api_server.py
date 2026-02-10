"""Mini Agent Web Server Entry Point.

启动 Mini Agent API 服务，支持会话管理和流式聊天功能.
"""

import os
import sys
from pathlib import Path


def setup_environment():
    """设置运行环境."""
    project_root = Path(__file__).parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.chdir(project_root)


def main():
    """主入口函数."""
    setup_environment()
    
    import uvicorn
    from mini_agent.web.server import app
    
    print("=" * 50)
    print("  Mini Agent API Server")
    print("=" * 50)
    print()
    print("  Swagger UI:  http://localhost:8000/docs")
    print("  ReDoc:      http://localhost:8000/redoc")
    print("  Health:     http://localhost:8000/health")
    print()
    print("=" * 50)
    print()
    
    uvicorn.run(
        "mini_agent.web.server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
