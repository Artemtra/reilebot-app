from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class UserCreate(BaseModel):
    telegram_id: int
    role: str
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    telegram_id: int
    role: str
    full_name: Optional[str]
    created_at: datetime


class RequestCreate(BaseModel):
    client_telegram_id: int
    description: str


class RequestAssign(BaseModel):
    request_id: int
    executor_telegram_id: int


class RequestUpdateStatus(BaseModel):
    status: str


class RequestResponse(BaseModel):
    id: int
    client_id: int
    executor_id: Optional[int] = None
    description: str
    status: str
    created_at: datetime
    deadline: Optional[datetime] = None
    client_name: Optional[str] = None
    executor_name: Optional[str] = None
    client_telegram_id: Optional[int] = None
    executor_telegram_id: Optional[int] = None


class MediaCreate(BaseModel):
    request_id: int
    file_path: str
    media_type: str


class MediaResponse(BaseModel):
    id: int
    request_id: int
    file_path: str
    media_type: str


class ReportCreate(BaseModel):
    request_id: int
    executor_telegram_id: int
    text_report: str


class ReportResponse(BaseModel):
    id: int
    request_id: int
    executor_id: int
    text_report: Optional[str]
    created_at: datetime


class ExtensionCreate(BaseModel):
    request_id: int
    executor_telegram_id: int
    days: int


class ExtensionUpdate(BaseModel):
    status: str


class ExtensionResponse(BaseModel):
    id: int
    request_id: int
    requested_days: int
    status: str
    created_at: datetime


class MessageResponse(BaseModel):
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    error: str
    success: bool = False
    detail: Optional[str] = None


class RequestFilters(BaseModel):
    status: Optional[str] = None
    client_telegram_id: Optional[int] = None
    executor_telegram_id: Optional[int] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20


class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int