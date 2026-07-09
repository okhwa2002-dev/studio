from sqlmodel import Field

from app.models.base import BaseEntity


class ErrorCode(BaseEntity, table=True):
    __tablename__ = "error_codes"

    code: str = Field(unique=True, index=True)
    message: str
    http_status: int = 400
    is_default: bool = False
    is_active: bool = True
