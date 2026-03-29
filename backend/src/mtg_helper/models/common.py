"""Shared response envelope models."""

from pydantic import BaseModel


class PaginationMeta(BaseModel):
    """Pagination metadata included with list responses."""

    total: int
    limit: int
    offset: int


class DataResponse[T](BaseModel):
    """Standard response envelope wrapping all API responses."""

    data: T
    meta: PaginationMeta | None = None


class ErrorDetail(BaseModel):
    """Details of an API error."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    error: ErrorDetail
