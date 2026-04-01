"""Mini Agent - Minimal single agent with basic tools and MCP support."""

__version__ = "0.1.0"

# 延迟导入，避免启动时加载所有依赖
def get_agent():
    from .agent import Agent
    return Agent

def get_llm_client():
    from .llm import LLMClient
    return LLMClient

# 直接导出，方便 from mini_agent import LLMClient
from .llm import LLMClient
