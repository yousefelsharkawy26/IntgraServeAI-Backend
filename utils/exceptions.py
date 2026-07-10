"""Unified system exceptions.

This module consolidates all exceptions used across the system.
They are organized into two primary layers:

1. **Internal Engine Exceptions** (inherit from ``Exception``)
   Used within the AI Engine for internal logic, parsing, and execution.
   These are NOT HTTP-specific and can be raised in any context.

2. **HTTP API Exceptions** (inherit from ``fastapi.HTTPException``)
   Used by the API layer to return structured error responses to clients.
   These are further divided into general API errors and action-parsing errors.
"""

from fastapi import HTTPException, status
from typing import Optional, Dict, Any
import contextvars
import logging
from typing import Optional, Set
from uuid import UUID


# =============================================================================
# INTERNAL ENGINE EXCEPTIONS
# =============================================================================

class ActionEngineException(Exception):
    """Base class for all Action Engine errors."""
    pass


# --- Internal Parsing Errors ---

class ParsingException(ActionEngineException):
    """Base exception for internal action parsing errors."""
    pass


class MissingField(ParsingException):
    """Exception when a required field is missing during internal parsing."""
    pass


class InvalidActionStructure(ParsingException):
    """Exception for invalid or incomplete action structure during internal parsing."""
    pass

class InvalidActionField(ParsingException):
    """Exception for unknown/foreign fields in action during internal parsing."""
    pass


class UnsupportedActionType(ParsingException):
    """Exception for unsupported action types during internal parsing."""
    pass


class InvalidParamType(ParsingException):
    """Exception for invalid parameter types during internal parsing."""
    pass


class InvalidParamValueType(ParsingException):
    """Exception for invalid parameter value types during internal parsing."""
    pass


class InvalidResponseMode(ParsingException):
    """Exception for invalid response modes during internal parsing."""
    pass


class InvalidConnectorType(ParsingException):
    """Exception for invalid connector types during internal parsing."""
    pass


# --- Internal Execution Errors ---

class ExecutionException(ActionEngineException):
    """Base exception for action execution errors."""
    pass


class SSRFVulnerabilityError(ExecutionException):
    """Raised when an API URL fails Server-Side Request Forgery (SSRF) safety checks."""
    pass


class PathParamNotFound(ExecutionException):
    """Exception when path parameter is not found during execution."""
    pass


class BodyParamOnGetRequest(ExecutionException):
    """Exception when body parameter is used with GET request during execution."""
    pass


class UserDeniedConfirmation(ExecutionException):
    """Exception when user denies a confirmation prompt."""
    pass


class ProtoNotFound(ExecutionException):
    """Exception when protobuf definition is not found."""
    pass


class ServiceNotFound(ExecutionException):
    """Exception when gRPC service is not found."""
    pass


class MethodNotFound(ExecutionException):
    """Exception when gRPC method is not found."""
    pass


class UnsupportedDatabaseDriver(ExecutionException):
    """Exception when database driver is not supported."""
    pass


class EmbeddingGenerationError(ExecutionException):
    """Exception when embedding generation fails."""
    pass


class VectorSearchError(ExecutionException):
    """Exception when vector search fails."""
    pass


class ActionNotFound(ExecutionException):
    """Raised when a requested action does not exist in the engine."""
    pass


class ActionNotActive(ExecutionException):
    """Raised when a requested action exists but is not active."""
    pass


class ProviderConfigurationError(ExecutionException):
    """Raised when a provider is misconfigured (missing API key, invalid model, etc.)."""
    pass


class ActionRequiresConfirmationError(ActionEngineException):
    """Raised when an action requires user confirmation before execution."""
    def __init__(self, message: str, action_name: str, params: dict):
        super().__init__(message)
        self.action_name = action_name
        self.params = params


# =============================================================================
# HTTP API EXCEPTIONS
# =============================================================================

class BaseAPIException(HTTPException):
    """Base exception for all API exceptions.

    Response format: ``{"message": "..."}`` or ``{"errors": {...}}``
    """
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


# --- General HTTP Errors ---

class ValidationException(BaseAPIException):
    """Exception for validation errors (HTTP 422)."""
    def __init__(self, errors: Dict[str, str]):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message="Validation failed",
            errors=errors
        )


class AuthenticationException(BaseAPIException):
    """Exception for authentication errors (HTTP 401)."""
    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message
        )


class UnauthorizedException(BaseAPIException):
    """Exception for unauthorized access (HTTP 401)."""
    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message
        )


class NotFoundException(BaseAPIException):
    """Exception for resource not found (HTTP 404)."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            message=message
        )


class BadRequestException(BaseAPIException):
    """Exception for bad requests (HTTP 400)."""
    def __init__(self, message: str = "Bad request"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=message
        )


class ConflictException(BaseAPIException):
    """Exception for conflicts, e.g. duplicate entries (HTTP 409)."""
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            message=message
        )


class InvalidTokenException(BaseAPIException):
    """Exception for invalid or expired tokens (HTTP 401)."""
    def __init__(self, message: str = "Invalid Link."):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=message
        )


class ServerException(BaseAPIException):
    """Exception for server errors (HTTP 500)."""
    def __init__(self, message: str = "Internal server error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=message
        )

class ChatNotFoundException(NotFoundException):
    def __init__(self, message: str = "Conversation not found"):
        super().__init__(message=message)

class MessageNotFoundException(NotFoundException):
    def __init__(self, message: str = "Message not found"):
        super().__init__(message=message)

class MessageNotEditableException(BadRequestException):
    def __init__(self, message: str = "Only customer messages can be edited or deleted"):
        super().__init__(message=message)


# --- HTTP Action Parsing Errors (HTTP 422) ---

class HTTPActionParsingException(HTTPException):
    """Base exception for HTTP action parsing errors.

    Response format: ``{"error": "ErrorType", "message": "..."}``

    .. note::
        This was formerly ``ParsingException`` in ``utils/exceptions.py``.
        Renamed to avoid collision with the internal ``ParsingException``.
    """
    def __init__(self, error_type: str, message: str):
        detail = {
            "error": error_type,
            "message": message
        }
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail
        )


class MissingFieldException(HTTPActionParsingException):
    """Exception when a required field is missing in an HTTP request."""
    def __init__(self, field: str, context: str = None):
        if context:
            message = f"Missing required field: '{field}' in {context}"
        else:
            message = f"Missing required field: '{field}'"
        super().__init__(
            error_type="MissingField",
            message=message
        )


class InvalidActionStructureException(HTTPActionParsingException):
    """Exception for invalid or incomplete action structure in an HTTP request."""
    def __init__(self, message: str = "Invalid or incomplete action structure"):
        super().__init__(
            error_type="InvalidActionStructure",
            message=message
        )


class InvalidActionFieldException(HTTPActionParsingException):
    """Exception for unknown/foreign fields in action in an HTTP request."""
    def __init__(self, field: str, context: str = None):
        if context:
            message = f"Unknown field '{field}' is not allowed in {context}"
        else:
            message = f"Unknown field '{field}' is not allowed"
        super().__init__(
            error_type="InvalidActionField",
            message=message
        )


class UnsupportedActionTypeException(HTTPActionParsingException):
    """Exception for unsupported action types in an HTTP request."""
    SUPPORTED_TYPES = ["api_request", "rpc_request", "vector_query", "sql_query", "knowledge_query", "internal"]

    def __init__(self, action_type: str):
        message = (
            f"Action type '{action_type}' is not supported. "
            f"Supported types: {', '.join(self.SUPPORTED_TYPES)}"
        )
        super().__init__(
            error_type="UnsupportedActionType",
            message=message
        )


class InvalidParamTypeException(HTTPActionParsingException):
    """Exception for invalid parameter types in an HTTP request."""
    def __init__(self, param_type: str, action_type: str, allowed_types: list):
        message = (
            f"Parameter type '{param_type}' is not valid for '{action_type}' actions. "
            f"Allowed types: {', '.join(allowed_types)}"
        )
        super().__init__(
            error_type="InvalidParamType",
            message=message
        )


class InvalidParamValueTypeException(HTTPActionParsingException):
    """Exception for invalid parameter value types in an HTTP request."""
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


class InvalidResponseModeException(HTTPActionParsingException):
    """Exception for invalid response modes in an HTTP request."""
    def __init__(self, mode: str, action_type: str, allowed_modes: list):
        message = (
            f"Response mode '{mode}' is not valid for '{action_type}' actions. "
            f"Allowed modes: {', '.join(allowed_modes)}"
        )
        super().__init__(
            error_type="InvalidResponseMode",
            message=message
        )


class BodyParamOnGetRequestException(HTTPActionParsingException):
    """Exception when body parameter is used with GET request."""
    def __init__(self, param_name: str):
        message = f"Body parameter '{param_name}' is not allowed on GET requests"
        super().__init__(
            error_type="BodyParamOnGetRequest",
            message=message
        )


class PathParamNotInUrlException(HTTPActionParsingException):
    """Exception when path parameter is not found in URL."""
    def __init__(self, param_name: str, url: str):
        message = (
            f"Path parameter '{param_name}' not found in URL. "
            f"URL should contain '{{{param_name}}}'. Current URL: {url}"
        )
        super().__init__(
            error_type="PathParamNotInUrl",
            message=message
        )


class RpcFieldInNonRpcActionException(HTTPActionParsingException):
    """Exception when RPC-specific fields are used in non-RPC actions."""
    def __init__(self, field: str, action_type: str):
        message = f"Field '{field}' is only allowed in 'rpc_request' actions, not in '{action_type}'"
        super().__init__(
            error_type="InvalidActionStructure",
            message=message
        )


class InternalActionNotAllowedException(HTTPActionParsingException):
    """Exception when trying to create/update/delete internal actions."""
    def __init__(self, operation: str = "modify"):
        message = f"Cannot {operation} internal actions. They are system-defined and read-only."
        super().__init__(
            error_type="InternalActionNotAllowed",
            message=message
        )


class DuplicateActionNameException(HTTPActionParsingException):
    """Exception when action name already exists."""
    def __init__(self, name: str):
        message = f"Action with name '{name}' already exists"
        super().__init__(
            error_type="DuplicateActionName",
            message=message
        )


class ActionNotFoundException(HTTPActionParsingException):
    """Exception when action is not found during HTTP request parsing."""
    def __init__(self, action_id: str):
        message = f"Action with ID '{action_id}' not found"
        super().__init__(
            error_type="ActionNotFound",
            message=message
        )

class ConversationNotFoundException(Exception):
    """Raised when a chat conversation cannot be found."""

    def __init__(self, conversation_id: Optional[UUID] = None):
        self.conversation_id = conversation_id
        msg = f"Conversation '{conversation_id}' not found" if conversation_id else "Conversation not found"
        super().__init__(msg)

class AttachmentNotFoundException(Exception):
    """Raised when a chat attachment cannot be found."""

    def __init__(self, attachment_id: Optional[UUID] = None):
        self.attachment_id = attachment_id
        msg = f"Attachment '{attachment_id}' not found" if attachment_id else "Attachment not found"
        super().__init__(msg)

class InvalidFileTypeException(Exception):
    """Raised when an uploaded file has a disallowed content type."""

    def __init__(self, content_type: str, allowed: Optional[Set[str]] = None):
        self.content_type = content_type
        self.allowed = allowed
        msg = f"File type '{content_type}' is not allowed"
        if allowed:
            msg += f". Allowed types: {sorted(allowed)}"
        super().__init__(msg)

class FileTooLargeException(Exception):
    """Raised when an uploaded file exceeds the size limit."""

    def __init__(self, size: int, max_size: int):
        self.size = size
        self.max_size = max_size
        super().__init__(f"File too large: {size} bytes (max {max_size} bytes)")

class InvalidRatingException(Exception):
    """Raised when a rating is outside the allowed range."""

    def __init__(self, rating: int):
        self.rating = rating
        super().__init__(f"Invalid rating '{rating}', must be between 1 and 5")

# =============================================================================
# Correlation ID Utilities
# =============================================================================

_correlation_id_var = contextvars.ContextVar('ai_engine_correlation_id', default=None)


class CorrelationIdAdapter(logging.LoggerAdapter):
    """Logger adapter that injects the current correlation_id into log messages.

    Works seamlessly with async contexts via contextvars.
    """
    def process(self, msg, kwargs):
        cid = _correlation_id_var.get()
        if cid:
            msg = f"[correlation_id={cid}] {msg}"
        return msg, kwargs


def get_correlation_id() -> str:
    """Get the current correlation ID from the async context."""
    return _correlation_id_var.get()


def set_correlation_id(cid: str):
    """Set the correlation ID for the current async context."""
    return _correlation_id_var.set(cid)
