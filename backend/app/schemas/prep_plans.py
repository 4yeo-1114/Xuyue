from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PrepPlanBase(BaseModel):
    date: str
    subject: str
    content: str
    completed: bool = False

class PrepPlanCreate(PrepPlanBase):
    pass

class PrepPlanUpdate(BaseModel):
    date: Optional[str] = None
    subject: Optional[str] = None
    content: Optional[str] = None
    completed: Optional[bool] = None

class PrepPlanResponse(PrepPlanBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
