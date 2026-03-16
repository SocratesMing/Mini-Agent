"""定时任务路由."""

import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException

from mini_agent.web.database import Database, get_database
from mini_agent.web.models import ScheduledTaskModel, TaskExecutionModel


router = APIRouter(prefix="/api/tasks", tags=["scheduled_tasks"])


@router.get("")
async def list_scheduled_tasks(
    db: Annotated[Database, Depends(get_database)],
):
    """获取当前用户的所有定时任务."""
    user = db.get_or_create_default_user()
    tasks = db.get_scheduled_tasks(user.username)
    
    result = []
    for task in tasks:
        executions = db.get_task_executions(task.task_id, limit=10)
        result.append({
            "task": task.model_dump(),
            "recent_executions": [e.model_dump() for e in executions],
        })
    
    return result


@router.post("")
async def create_scheduled_task(
    name: str,
    description: str,
    cron_expression: str,
    db: Annotated[Database, Depends(get_database)],
):
    """创建新的定时任务."""
    user = db.get_or_create_default_user()
    now = datetime.now().isoformat()
    
    task = ScheduledTaskModel(
        task_id=str(uuid.uuid4()),
        username=user.username,
        name=name,
        description=description,
        cron_expression=cron_expression,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    
    db.create_scheduled_task(task)
    return task.model_dump()


@router.get("/{task_id}")
async def get_scheduled_task(
    task_id: str,
    db: Annotated[Database, Depends(get_database)],
):
    """获取定时任务详情和执行记录."""
    task = db.get_scheduled_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    executions = db.get_task_executions(task_id)
    
    return {
        "task": task.model_dump(),
        "executions": [e.model_dump() for e in executions],
    }


@router.put("/{task_id}")
async def update_scheduled_task(
    task_id: str,
    name: str,
    description: str,
    cron_expression: str,
    enabled: bool,
    db: Annotated[Database, Depends(get_database)],
):
    """更新定时任务."""
    task = db.get_scheduled_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task.name = name
    task.description = description
    task.cron_expression = cron_expression
    task.enabled = enabled
    task.updated_at = datetime.now().isoformat()
    
    db.update_scheduled_task(task)
    return task.model_dump()


@router.delete("/{task_id}")
async def delete_scheduled_task(
    task_id: str,
    db: Annotated[Database, Depends(get_database)],
):
    """删除定时任务."""
    success = db.delete_scheduled_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return {"message": "删除成功"}


@router.get("/{task_id}/executions")
async def get_task_executions(
    db: Annotated[Database, Depends(get_database)],
    task_id: str,
    limit: int = 50,
):
    """获取任务的执行记录."""
    task = db.get_scheduled_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    executions = db.get_task_executions(task_id, limit)
    return [e.model_dump() for e in executions]
