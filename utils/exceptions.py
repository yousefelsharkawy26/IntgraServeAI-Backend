from fastapi import HTTPException, status
from typing import Optional, Dict, Any


class BaseAPIException(HTTPException):
    """Base exception for all API exceptions"""
    def __init__(
        self,
        status_code: int,
        message: str,
        errors: Optional[Dict[str, Any]] = None
    ):
        # إذا كان فيه validation errors، نرجع errors فقط
        if errors:
            detail = {"errors": errors}
        else:
            # باقي الأخطاء نرجع message فقط
            detail = {"message": message}
        super().__init__(status_code=status_code, detail=detail)


class ValidationException(BaseAPIException):
    """Exception for validation errors"""
    def __init__(self, errors: Dict[str, str]):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="Validation failed",
            errors=errors
        )


class AuthenticationException(BaseAPIException):
    """Exception for authentication errors"""
    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message
        )


class UnauthorizedException(BaseAPIException):
    """Exception for unauthorized access"""
    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message
        )


class NotFoundException(BaseAPIException):
    """Exception for resource not found"""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            message=message
        )


class BadRequestException(BaseAPIException):
    """Exception for bad requests"""
    def __init__(self, message: str = "Bad request"):
        super().__Init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=message
        )


class ConflictException(BaseAPIException):
    """Exception for conflicts (e.g., duplicate entries)"""
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            message=message
        )


class InvalidTokenException(BaseAPIException):
    """Exception for invalid or expired tokens"""
    def __init__(self, message: str = "Invalid Link."):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=message
        )


class ServerException(BaseAPIException):
    """Exception for server errors"""
    def __init__(self, message: str = "Internal server error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=message
        )