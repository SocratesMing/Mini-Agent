"""Pydantic Models for API Request/Response.

定义所有 API 接口使用的数据模型.
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Agent 配置模型（用于动态创建 Agent 实例）.
    
    注意：这是轻量级配置对象，实际的 LLMClient 和 tools
    在启动时创建并缓存.
    """
    
    system_prompt: str = Field(default="你是一个有帮助的 AI 助手.", description="系统提示词")
    max_steps: int = Field(default=50, description="最大执行步数")
    workspace_dir: str = Field(default="./workspace", description="工作目录")


class CreateSessionRequest(BaseModel):
    """创建会话请求模型."""
    
    title: Optional[str] = Field(
        default=None,
        description="会话标题，如果不提供则自动生成"
    )


class CreateSessionResponse(BaseModel):
    """创建会话响应模型."""
    
    session_id: str = Field(..., description="会话唯一标识符")
    title: str = Field(..., description="会话标题")
    created_at: str = Field(..., description="创建时间 ISO 格式")
    updated_at: str = Field(..., description="更新时间 ISO 格式")
    message_count: int = Field(default=0, description="消息数量")


class SessionInfo(BaseModel):
    """会话信息模型（不含消息列表）."""
    
    session_id: str = Field(..., description="会话唯一标识符")
    title: str = Field(..., description="会话标题")
    created_at: str = Field(..., description="创建时间 ISO 格式")
    updated_at: str = Field(..., description="更新时间 ISO 格式")
    message_count: int = Field(default=0, description="消息数量")


class SessionDetail(BaseModel):
    """会话详情模型（包含消息列表）."""
    
    session_id: str = Field(..., description="会话唯一标识符")
    title: str = Field(..., description="会话标题")
    created_at: str = Field(..., description="创建时间 ISO 格式")
    updated_at: str = Field(..., description="更新时间 ISO 格式")
    messages: List[dict[str, Any]] = Field(default_factory=list, description="消息列表")


class MessageModel(BaseModel):
    """消息模型."""
    
    role: str = Field(..., description="消息角色: user, assistant, system")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[str] = Field(default=None, description="时间戳")
    thinking: Optional[str] = Field(default=None, description="思考内容")


class ChatRequest(BaseModel):
    """聊天请求模型."""
    
    message: str = Field(..., description="用户消息内容", min_length=1)
    session_id: Optional[str] = Field(default=None, description="会话ID，不提供则创建新会话")
    message_id: Optional[str] = Field(default=None, description="消息ID，用于追踪单条消息（可选）")
    enable_deep_think: bool = Field(default=False, description="是否启用深度思考模式")
    files: Optional[List[dict]] = Field(default=None, description="用户上传的文件列表")


class ChatResponse(BaseModel):
    """聊天响应模型."""
    
    session_id: str = Field(..., description="会话ID")
    response: str = Field(..., description="AI 响应内容")
    thinking: Optional[str] = Field(default=None, description="思考过程内容")
    tool_calls: Optional[List[dict]] = Field(default=None, description="工具调用列表")
    usage: Optional[dict] = Field(default=None, description="Token 使用统计")


class StreamChunk(BaseModel):
    """流式响应数据块模型."""
    
    type: str = Field(
        ...,
        description="数据类型: start, thinking_start, thinking, assistant_start, content, done, error"
    )
    content: str = Field(default="", description="数据内容")
    session_id: Optional[str] = Field(default=None, description="会话ID")


class ErrorResponse(BaseModel):
    """错误响应模型."""
    
    detail: str = Field(..., description="错误详情")


class HealthResponse(BaseModel):
    """健康检查响应模型."""
    
    status: str = Field(default="healthy", description="服务状态")
    agent_initialized: bool = Field(default=False, description="Agent 是否已初始化")
    database_initialized: bool = Field(default=False, description="数据库是否已初始化")


class ListSessionsQuery(BaseModel):
    """查询会话列表的请求参数."""
    
    limit: int = Field(default=50, ge=1, le=100, description="返回数量限制")
    offset: int = Field(default=0, ge=0, description="偏移量")


class UpdateTitleRequest(BaseModel):
    """更新标题请求模型."""
    
    title: Optional[str] = Field(default=None, description="新的会话标题")


class AddMessageRequest(BaseModel):
    """添加消息请求模型."""
    
    role: str = Field(..., description="消息角色: user, assistant, system")
    content: str = Field(..., description="消息内容")


class AddMessageResponse(BaseModel):
    """添加消息响应模型."""
    
    status: str = Field(default="success", description="状态")
    session_id: str = Field(..., description="会话ID")
    message_count: int = Field(..., description="当前消息数量")


class SessionCountResponse(BaseModel):
    """会话数量响应模型."""
    
    total_sessions: int = Field(..., description="会话总数")


class DeleteSessionResponse(BaseModel):
    """删除会话响应模型."""
    
    status: str = Field(default="deleted", description="状态")
    session_id: str = Field(..., description="被删除的会话ID")


class GetChatHistoryResponse(BaseModel):
    """获取聊天历史响应模型."""
    
    session_id: str = Field(..., description="会话ID")
    title: str = Field(..., description="会话标题")
    messages: List[dict[str, Any]] = Field(default_factory=list, description="消息列表")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")


class UserProfile(BaseModel):
    """用户资料模型."""
    
    user_id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    organization_id: str = Field(default="", description="机构ID")
    email: str = Field(default="", description="用户邮箱")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")


class UpdateUserProfileRequest(BaseModel):
    """更新用户资料请求模型."""
    
    username: Optional[str] = Field(default=None, description="用户名")
    organization_id: Optional[str] = Field(default=None, description="机构ID")
    email: Optional[str] = Field(default=None, description="用户邮箱")

