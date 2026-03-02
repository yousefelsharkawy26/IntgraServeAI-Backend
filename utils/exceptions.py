# utils/exceptions.py
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
        if errors:
            detail = {"errors": errors}
        else:
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
        super().__init__(
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


# ============================================================================
# Action Parsing Exceptions
# ============================================================================

class ParsingException(HTTPException):
    """Base exception for all action parsing errors"""
    def __init__(self, error_type: str, message: str):
        detail = {
            "error": error_type,
            "message": message
        }
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )


class MissingFieldException(ParsingException):
    """Exception when a required field is missing"""
    def __init__(self, field: str, context: str = None):
        if context:
            message = f"Missing required field: '{field}' in {context}"
        else:
            message = f"Missing required field: '{field}'"
        super().__init__(
            error_type="MissingField",
            message=message
        )


class InvalidActionStructureException(ParsingException):
    """Exception for invalid or incomplete action structure"""
    def __init__(self, message: str = "Invalid or incomplete action structure"):
        super().__init__(
            error_type="InvalidActionStructure",
            message=message
        )


class InvalidActionFieldException(ParsingException):
    """Exception for unknown/foreign fields in action"""
    def __init__(self, field: str, context: str = None):
        if context:
            message = f"Unknown field '{field}' is not allowed in {context}"
        else:
            message = f"Unknown field '{field}' is not allowed"
        super().__init__(
            error_type="InvalidActionField",
            message=message
        )


class UnsupportedActionTypeException(ParsingException):
    """Exception for unsupported action types"""
    SUPPORTED_TYPES = ["api_request", "rpc_request", "internal"]
    
    def __init__(self, action_type: str):
        message = (
            f"Action type '{action_type}' is not supported. "
            f"Supported types: {', '.join(self.SUPPORTED_TYPES)}"
        )
        super().__init__(
            error_type="UnsupportedActionType",
            message=message
        )


class InvalidParamTypeException(ParsingException):
    """Exception for invalid parameter types"""
    def __init__(self, param_type: str, action_type: str, allowed_types: list):
        message = (
            f"Parameter type '{param_type}' is not valid for '{action_type}' actions. "
            f"Allowed types: {', '.join(allowed_types)}"
        )
        super().__init__(
            error_type="InvalidParamType",
            message=message
        )


class InvalidParamValueTypeException(ParsingException):
    """Exception for invalid parameter value types"""
    SUPPORTED_VALUE_TYPES = ["string", "integer"]
    
    def __init__(self, value_type: str, param_name: str):
        message = (
            f"Parameter '{param_name}' has invalid value type '{value_type}'. "
            f"Supported types: {', '.join(self.SUPPORTED_VALUE_TYPES)}"
        )
        super().__init__(
            error_type="InvalidParamValueType",
            message=message
        )


class InvalidResponseModeException(ParsingException):
    """Exception for invalid response modes"""
    def __init__(self, mode: str, action_type: str, allowed_modes: list):
        message = (
            f"Response mode '{mode}' is not valid for '{action_type}' actions. "
            f"Allowed modes: {', '.join(allowed_modes)}"
        )
        super().__init__(
            error_type="InvalidResponseMode",
            message=message
        )


class BodyParamOnGetRequestException(ParsingException):
    """Exception when body parameter is used with GET request"""
    def __init__(self, param_name: str):
        message = f"Body parameter '{param_name}' is not allowed on GET requests"
        super().__init__(
            error_type="BodyParamOnGetRequest",
            message=message
        )


class PathParamNotInUrlException(ParsingException):
    """Exception when path parameter is not found in URL"""
    def __init__(self, param_name: str, url: str):
        message = (
            f"Path parameter '{param_name}' not found in URL. "
            f"URL should contain '{{{param_name}}}'. Current URL: {url}"
        )
        super().__init__(
            error_type="PathParamNotInUrl",
            message=message
        )


class RpcFieldInNonRpcActionException(ParsingException):
    """Exception when RPC-specific fields are used in non-RPC actions"""
    def __init__(self, field: str, action_type: str):
        message = f"Field '{field}' is only allowed in 'rpc_request' actions, not in '{action_type}'"
        super().__init__(
            error_type="InvalidActionStructure",
            message=message
        )


class InternalActionNotAllowedException(ParsingException):
    """Exception when trying to create/update/delete internal actions"""
    def __init__(self, operation: str = "modify"):
        message = f"Cannot {operation} internal actions. They are system-defined and read-only."
        super().__init__(
            error_type="InternalActionNotAllowed",
            message=message
        )


class DuplicateActionNameException(ParsingException):
    """Exception when action name already exists"""
    def __init__(self, name: str):
        message = f"Action with name '{name}' already exists"
        super().__init__(
            error_type="DuplicateActionName",
            message=message
        )


class ActionNotFoundException(ParsingException):
    """Exception when action is not found"""
    def __init__(self, action_id: str):
        message = f"Action with ID '{action_id}' not found"
        super().__init__(
            error_type="ActionNotFound",
            message=message
        )