# utils/schemas/action_schemas.py
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, Dict, List, Any, Union
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class ActionType(str, Enum):
    API_REQUEST = "api_request"
    RPC_REQUEST = "rpc_request"
    VECTOR_QUERY = "vector_query"
    INTERNAL = "internal"


class HttpMethod(str, Enum):
    """HTTP methods"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ParamValueType(str, Enum):
    """Parameter value types"""
    STRING = "string"
    INTEGER = "integer"


class ResponseMode(str, Enum):
    JSON = "json"
    XML = "xml"
    HTML = "html"
    RAW = "raw"


class Protocol(str, Enum):
    """Protocols"""
    HTTP = "http"
    HTTPS = "https"
    GRPC = "grpc"


# ============================================================================
# Helper: Allowed values per action type
# ============================================================================

ACTION_TYPE_CONFIG = {
    ActionType.API_REQUEST: {
        "required_exec_fields": ["protocol", "url"],
        "optional_exec_fields": ["method", "headers", "timeout"],
        "allowed_param_types": ["query", "body", "path"],
        "allowed_response_modes": ["json", "xml", "html"],
        "forbidden_exec_fields": ["host", "service", "proto_file"],
    },
    ActionType.RPC_REQUEST: {
        "required_exec_fields": ["protocol", "host", "service", "method", "proto_file"],
        "optional_exec_fields": ["headers", "timeout"],
        "allowed_param_types": ["message_field"],
        "allowed_response_modes": ["json"],
        "forbidden_exec_fields": ["url"],
    },
    ActionType.VECTOR_QUERY: {
        "required_exec_fields": ["connector", "connection_string", "collection_name"],
        "optional_exec_fields": ["max_results", "auth", "embedding_config"],
        "allowed_param_types": ["vector"],
        "allowed_response_modes": ["json", "raw"],
        "forbidden_exec_fields": ["protocol", "url", "method", "host", "service", "proto_file", "headers", "timeout"],
    },
    ActionType.INTERNAL: {
        "required_exec_fields": [],
        "optional_exec_fields": [],
        "allowed_param_types": ["internal"],
        "allowed_response_modes": ["json"],
        "forbidden_exec_fields": ["protocol", "url", "method", "host", "service", "proto_file", "headers", "timeout"],
        "read_only": True,
    },
}


# ============================================================================
# Parameter Schema
# ============================================================================

class ActionParameter(BaseModel):
    """Schema for action parameter"""
    type: ParamValueType = Field(..., description="Data type of the parameter value")
    required: bool = Field(..., description="Whether the parameter is required")
    param_type: str = Field(..., description="Type of parameter (query, body, path, message_field, internal)")
    description: str = Field(..., description="Description of the parameter")
    default: Optional[Union[str, int]] = Field(None, description="Default value for the parameter")
    enum: Optional[List[Union[str, int]]] = Field(None, description="Allowed values for the parameter")
    
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Response Value Schema
# ============================================================================

class ResponseValue(BaseModel):
    """Schema for response value mapping"""
    type: ParamValueType = Field(..., description="Data type of the response value")
    path: str = Field(..., description="JSON path to extract the value")
    
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Response Config Schema
# ============================================================================

class ResponseConfig(BaseModel):
    """Schema for response configuration"""
    mode: ResponseMode = Field(..., description="Response format mode")
    values: Optional[Dict[str, ResponseValue]] = Field(None, description="Value mappings for response parsing")
    template: str = Field(..., description="Template for successful response")
    on_error: str = Field(..., description="Message template for error responses")
    
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Execution Config Schema
# ============================================================================

class ExecutionConfig(BaseModel):
    """Schema for execution configuration. Fields vary based on action type."""
    # API Request fields
    protocol: Optional[Protocol] = Field(None, description="Protocol (http, https, grpc)")
    method: Optional[HttpMethod] = Field(None, description="HTTP method")
    url: Optional[str] = Field(None, description="API URL")
    headers: Optional[Dict[str, str]] = Field(None, description="HTTP headers")
    timeout: Optional[int] = Field(None, description="Timeout in milliseconds")
    
    # RPC Request fields
    host: Optional[str] = Field(None, description="gRPC host address")
    service: Optional[str] = Field(None, description="gRPC service name")
    proto_file: Optional[str] = Field(None, description="Path to .proto file")

    connector: Optional[str] = Field(None, description="Vector DB connector")
    connection_string: Optional[str] = Field(None, description="Vector DB connection string")
    collection_name: Optional[str] = Field(None, description="Collection/table name")
    max_results: Optional[int] = Field(None, description="Max search results")
    auth: Optional[Dict[str, str]] = Field(None, description="Auth credentials")
    embedding_config: Optional[Dict[str, Any]] = Field(None, description="Embedding model config")

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Main Action Schema - Create (for API/RPC only)
# ============================================================================

class ActionCreate(BaseModel):
    """Schema for creating a new action (API/RPC only, not internal)"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r'^[a-z][a-z0-9_]*$',
        description="Unique action name (lowercase, underscores allowed)"
    )
    description: str = Field(..., min_length=1, max_length=500, description="Description of what the action does")
    type: ActionType = Field(..., description="Type of action (api_request or rpc_request)")
    active: bool = Field(True, description="Whether the action is active")
    requires_confirmation: bool = Field(False, description="Whether action requires user confirmation")
    execution_config: ExecutionConfig = Field(..., description="Execution configuration")
    parameters: Optional[Dict[str, ActionParameter]] = Field(None, description="Action parameters")
    response_config: Optional[ResponseConfig] = Field(None, description="Response configuration")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate action name format"""
        v = v.strip().lower()
        if not v:
            raise ValueError("Action name cannot be empty")
        if not v[0].isalpha():
            raise ValueError("Action name must start with a letter")
        return v
    
    @field_validator('type')
    @classmethod
    def validate_type_not_internal(cls, v: ActionType) -> ActionType:
        """Prevent creating internal actions"""
        if v == ActionType.INTERNAL:
            raise ValueError("Cannot create internal actions. They are system-defined.")
        return v
    
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Main Action Schema - Update (for API/RPC only)
# ============================================================================

class ActionUpdate(BaseModel):
    """Schema for updating an action (all fields optional, not for internal actions)"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, pattern=r'^[a-z][a-z0-9_]*$')
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    active: Optional[bool] = Field(None)
    requires_confirmation: Optional[bool] = Field(None)
    execution_config: Optional[ExecutionConfig] = Field(None)
    parameters: Optional[Dict[str, ActionParameter]] = Field(None)
    response_config: Optional[ResponseConfig] = Field(None)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate action name format"""
        if v is not None:
            v = v.strip().lower()
            if not v:
                raise ValueError("Action name cannot be empty")
            if not v[0].isalpha():
                raise ValueError("Action name must start with a letter")
        return v
    
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Action Response Schemas
# ============================================================================

class ActionSummary(BaseModel):
    """Summary of an action for list views"""
    id: str
    name: str
    description: str
    type: ActionType
    active: bool
    requires_confirmation: bool = False
    
    model_config = ConfigDict(from_attributes=True)


class ActionResponse(BaseModel):
    """Full action response"""
    id: str
    name: str
    description: str
    type: ActionType
    active: bool
    requires_confirmation: bool = False
    execution_config: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    response_config: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


class ActionListResponse(BaseModel):
    """Response for listing actions"""
    total: int
    actions: List[ActionSummary]


class ActionCreatedResponse(BaseModel):
    """Response after creating an action"""
    message: str
    id: str
    name: str


class ActionUpdatedResponse(BaseModel):
    """Response after updating an action"""
    message: str
    id: str
    name: str


class ActionDeletedResponse(BaseModel):
    """Response after deleting an action"""
    message: str
    id: str
    name: str


class ActionToggleResponse(BaseModel):
    """Response after toggling action status"""
    message: str
    id: str
    name: str
    active: bool


class ActionValidateResponse(BaseModel):
    """Response for action validation"""
    valid: bool
    message: str
    warnings: Optional[List[str]] = None


# ============================================================================
# Action Types Info Response
# ============================================================================

class ActionTypeInfo(BaseModel):
    """Information about an action type"""
    type: str
    description: str
    required_config: List[str]
    optional_config: List[str]
    allowed_param_types: List[str]
    allowed_response_modes: List[str]
    read_only: bool = False


class ActionTypesResponse(BaseModel):
    """Response for listing action types"""
    types: List[ActionTypeInfo]


# ============================================================================
# Backup Schemas
# ============================================================================

class BackupInfo(BaseModel):
    """Information about a backup file"""
    filename: str
    created_at: str
    size_bytes: int
    size_kb: float


class BackupListResponse(BaseModel):
    """Response for listing backups"""
    total: int
    backups: List[BackupInfo]


class BackupContentResponse(BaseModel):
    """Response for backup content"""
    filename: str
    content: Dict[str, Any]
    actions_count: int


class BackupRestoreResponse(BaseModel):
    """Response after restoring a backup"""
    message: str
    restored_from: str
    actions_count: int


class BackupDeleteResponse(BaseModel):
    """Response after deleting a backup"""
    message: str
    filename: str


class BackupDeleteAllResponse(BaseModel):
    """Response after deleting all backups"""
    message: str
    deleted_count: int


class BackupCompareResponse(BaseModel):
    """Response for comparing current state with backup"""
    filename: str
    backup_actions_count: int
    current_actions_count: int
    added: List[str]
    removed: List[str]
    modified: List[str]
    has_changes: bool


# ============================================================================
# Helper function to get action type descriptions
# ============================================================================

ACTION_TYPE_DESCRIPTIONS = {
    ActionType.API_REQUEST: "HTTP/HTTPS API calls",
    ActionType.RPC_REQUEST: "gRPC remote procedure calls",
    ActionType.INTERNAL: "Internal system actions (read-only)",
}


def get_action_types_info() -> List[ActionTypeInfo]:
    """Get information about all supported action types"""
    types_info = []
    
    for action_type, config in ACTION_TYPE_CONFIG.items():
        info = ActionTypeInfo(
            type=action_type.value,
            description=ACTION_TYPE_DESCRIPTIONS.get(action_type, ""),
            required_config=config["required_exec_fields"],
            optional_config=config["optional_exec_fields"],
            allowed_param_types=config["allowed_param_types"],
            allowed_response_modes=config["allowed_response_modes"],
            read_only=config.get("read_only", False),
        )
        types_info.append(info)
    
    return types_info