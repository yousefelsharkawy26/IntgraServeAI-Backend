# utils/schemas/action_schemas.py
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, Dict, List, Any, Union
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class ActionType(str, Enum):
    """Supported action types"""
    API_REQUEST = "api_request"
    SQL_QUERY = "sql_query"
    VECTOR_QUERY = "vector_query"
    KNOWLEDGE_QUERY = "knowledge_query"
    RPC_REQUEST = "rpc_request"
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


class ConnectorType(str, Enum):
    """Database connector types"""
    SQLITE = "sqlite"
    POSTGRES = "postgres"


class ResponseMode(str, Enum):
    """Response modes"""
    JSON = "json"
    XML = "xml"
    HTML = "html"
    SQL = "sql"
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
        "forbidden_exec_fields": ["connector", "connection_string", "collection_name", 
                                   "max_results", "auth", "embedding_config", "host", 
                                   "service", "proto_file"],
    },
    ActionType.VECTOR_QUERY: {
        "required_exec_fields": ["connector", "connection_string", "collection_name"],
        "optional_exec_fields": ["max_results", "auth", "embedding_config"],
        "allowed_param_types": ["vector"],
        "allowed_response_modes": ["raw", "sql"],
        "forbidden_exec_fields": ["protocol", "url", "method", "host", "service", "proto_file"],
        "no_values_in_response": True,
        "required_topic_param": True,
    },
    ActionType.SQL_QUERY: {
        "required_exec_fields": ["connector", "connection_string"],
        "optional_exec_fields": ["max_results", "auth"],
        "allowed_param_types": ["query"],
        "allowed_response_modes": ["raw", "sql"],
        "forbidden_exec_fields": ["protocol", "url", "method", "host", "service", 
                                   "proto_file", "embedding_config"],
        "no_values_in_response": True,
    },
    ActionType.KNOWLEDGE_QUERY: {
        "required_exec_fields": ["connector", "connection_string"],
        "optional_exec_fields": ["max_results", "auth", "collection_name"],
        "allowed_param_types": ["query"],
        "allowed_response_modes": ["raw"],
        "forbidden_exec_fields": ["protocol", "url", "method", "host", "service", 
                                   "proto_file", "embedding_config"],
        "no_values_in_response": True,
    },
    ActionType.RPC_REQUEST: {
        "required_exec_fields": ["protocol", "host", "service", "method", "proto_file"],
        "optional_exec_fields": ["headers", "timeout"],
        "allowed_param_types": ["message_field"],
        "allowed_response_modes": ["json"],
        "forbidden_exec_fields": ["connector", "connection_string", "collection_name",
                                   "max_results", "auth", "embedding_config", "url"],
    },
    ActionType.INTERNAL: {
        "required_exec_fields": [],
        "optional_exec_fields": ["timeout"],
        "allowed_param_types": ["internal"],
        "allowed_response_modes": ["json", "raw"],
        "forbidden_exec_fields": ["protocol", "url", "method", "connector", "connection_string",
                                   "host", "service", "proto_file"],
    },
}


# ============================================================================
# Parameter Schema
# ============================================================================

class ActionParameter(BaseModel):
    """Schema for action parameter"""
    type: ParamValueType = Field(..., description="Data type of the parameter value")
    required: bool = Field(..., description="Whether the parameter is required")
    param_type: str = Field(..., description="Type of parameter (query, body, path, vector, message_field, etc.)")
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
# Embedding Config Schema (for vector_query)
# ============================================================================

class EmbeddingConfig(BaseModel):
    """Schema for embedding configuration in vector queries"""
    provider: str = Field(..., description="Embedding provider (e.g., openai, cohere)")
    model: str = Field(..., description="Embedding model name")
    api_key: str = Field(..., description="API key for the embedding provider")
    
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Auth Config Schema (for query actions)
# ============================================================================

class QueryAuthConfig(BaseModel):
    """Schema for database authentication"""
    user: str = Field(..., description="Database username")
    pass_: str = Field(..., alias="pass", description="Database password")
    
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


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
    
    # Query action fields
    connector: Optional[ConnectorType] = Field(None, description="Database connector type")
    connection_string: Optional[str] = Field(None, description="Database connection string")
    collection_name: Optional[str] = Field(None, description="Collection/table name")
    max_results: Optional[int] = Field(None, description="Maximum number of results")
    auth: Optional[QueryAuthConfig] = Field(None, description="Database authentication")
    embedding_config: Optional[EmbeddingConfig] = Field(None, description="Embedding configuration")
    
    # RPC Request fields
    host: Optional[str] = Field(None, description="gRPC host address")
    service: Optional[str] = Field(None, description="gRPC service name")
    proto_file: Optional[str] = Field(None, description="Path to .proto file")
    
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Main Action Schema - Create
# ============================================================================

class ActionCreate(BaseModel):
    """Schema for creating a new action"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r'^[a-z][a-z0-9_]*$',
        description="Unique action name (lowercase, underscores allowed)"
    )
    description: str = Field(..., min_length=1, max_length=500, description="Description of what the action does")
    type: ActionType = Field(..., description="Type of action")
    active: bool = Field(True, description="Whether the action is active")
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
    
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Main Action Schema - Update
# ============================================================================

class ActionUpdate(BaseModel):
    """Schema for updating an action (all fields optional)"""
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    type: Optional[ActionType] = Field(None)
    active: Optional[bool] = Field(None)
    execution_config: Optional[ExecutionConfig] = Field(None)
    parameters: Optional[Dict[str, ActionParameter]] = Field(None)
    response_config: Optional[ResponseConfig] = Field(None)
    
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Action Response Schemas
# ============================================================================

class ActionSummary(BaseModel):
    """Summary of an action for list views"""
    name: str
    description: str
    type: ActionType
    active: bool
    
    model_config = ConfigDict(from_attributes=True)


class ActionResponse(BaseModel):
    """Full action response"""
    name: str
    description: str
    type: ActionType
    active: bool
    execution_config: Dict[str, Any]
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
    name: str


class ActionUpdatedResponse(BaseModel):
    """Response after updating an action"""
    message: str
    name: str


class ActionDeletedResponse(BaseModel):
    """Response after deleting an action"""
    message: str
    name: str


class ActionToggleResponse(BaseModel):
    """Response after toggling action status"""
    message: str
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
    ActionType.SQL_QUERY: "SQL database queries",
    ActionType.VECTOR_QUERY: "Vector database queries with embeddings",
    ActionType.KNOWLEDGE_QUERY: "Knowledge base queries",
    ActionType.RPC_REQUEST: "gRPC remote procedure calls",
    ActionType.INTERNAL: "Internal system actions",
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
        )
        types_info.append(info)
    
    return types_info