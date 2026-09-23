from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TodoItemOut(BaseModel):
    id: str
    title: str
    content: Optional[str] = None
    remind_at: Optional[str] = None
    notified_at: Optional[str] = None
    is_done: bool = False
    created_at: str
    updated_at: str


class CreateTodoRequest(BaseModel):
    title: str
    content: Optional[str] = None
    remind_at: Optional[datetime] = None


class UpdateTodoRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    remind_at: Optional[datetime] = None
    is_done: Optional[bool] = None
