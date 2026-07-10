from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserRead(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LeadRead(BaseModel):
    id: int
    name: str
    region_id: Optional[int] = None
    district: Optional[str] = None
    settlement: Optional[str] = None
    inn: Optional[str] = None
    level: Optional[str] = None
    priority: Optional[int] = None
    stage: str = "0"
    created_at: datetime

    class Config:
        from_attributes = True


class ContactRead(BaseModel):
    id: int
    lead_id: int
    name: Optional[str] = None
    position: Optional[str] = None
    phone: str
    email: Optional[str] = None
    is_decision_maker: bool = False

    class Config:
        from_attributes = True
