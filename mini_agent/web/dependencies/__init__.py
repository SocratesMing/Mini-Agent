"""FastAPI 依赖模块."""

from mini_agent.web.dependencies.auth import get_current_username, get_optional_username

__all__ = ["get_current_username", "get_optional_username"]
