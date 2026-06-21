# ai_engine/exceptions.py

import contextvars
import logging

class ActionEngineException(Exception):
    """Base class for all Action Engine errors."""
    pass

# --- Parsing Exceptions (Configuration Time) ---
class ParsingException(ActionEngineException):
    pass

class MissingField(ParsingException):
    pass

class InvalidActionStructure(ParsingException):
    pass

class InvalidActionField(ParsingException):
    pass

class UnsupportedActionType(ParsingException):
    pass

class InvalidParamValueType(ParsingException):
    pass

class InvalidParamType(ParsingException):
    pass

class InvalidResponseMode(ParsingException):
    pass

# --- Execution Exceptions (Runtime) ---
class ExecutionException(ActionEngineException):
    pass

class PathParamNotFound(ExecutionException):
    pass

class BodyParamOnGetRequest(ExecutionException):
    pass

class UserDeniedConfirmation(ExecutionException):
    pass

class ProtoNotFound(ExecutionException):
    pass

class ServiceNotFound(ExecutionException):
    pass

class MethodNotFound(ExecutionException):
    pass

class UnsupportedDatabaseDriver(ExecutionException):
    pass

class InvalidConnectorType(ParsingException):
    pass

class EmbeddingGenerationError(ExecutionException):
    pass

class VectorSearchError(ExecutionException):
    pass

class ActionRequiresConfirmationError(ActionEngineException):
    def __init__(self, message: str, action_name: str, params: dict):
        super().__init__(message)
        self.action_name = action_name
        self.params = params

# P5.4: New execution exceptions for standardized taxonomy
class ActionNotFound(ExecutionException):
    """Raised when a requested action does not exist in the engine."""
    pass

class ActionNotActive(ExecutionException):
    """Raised when a requested action exists but is not active."""
    pass

class ProviderConfigurationError(ExecutionException):
    """Raised when a provider is misconfigured (missing API key, invalid model, etc.)."""
    pass


# P5.1: Structured logging correlation ID utilities
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