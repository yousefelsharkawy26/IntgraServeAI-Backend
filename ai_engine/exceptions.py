# ai_engine/exceptions.py

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