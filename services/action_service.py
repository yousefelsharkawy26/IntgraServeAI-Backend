# services/action_service.py
import json
import shutil
import logging
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from filelock import FileLock

from core.config import settings
from utils.schemas.action_schemas import (
    ActionCreate,
    ActionUpdate,
    ActionType,
    ActionSummary,
    ActionResponse,
    ACTION_TYPE_CONFIG,
)
from utils.exceptions import (
    NotFoundException,
    ConflictException,
    MissingFieldException,
    InvalidActionStructureException,
    InvalidActionFieldException,
    UnsupportedActionTypeException,
    InvalidParamTypeException,
    InvalidParamValueTypeException,
    InvalidResponseModeException,
    BodyParamOnGetRequestException,
    PathParamNotInUrlException,
    RpcFieldInNonRpcActionException,
    InternalActionNotAllowedException,
    DuplicateActionNameException,
    ActionNotFoundException,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Default Internal Actions
# ============================================================================

DEFAULT_INTERNAL_ACTIONS = {
    "INT-001": {
        "name": "create_support_ticket",
        "description": "Creates a support ticket to connect the customer with a support employee.",
        "type": "internal",
        "active": True,
        "requires_confirmation": True,
    },
    "INT-002": {
        "name": "create_technical_ticket",
        "description": "Creates a technical ticket to report a bug, error or a failure in the system.",
        "type": "internal",
        "active": True,
        "requires_confirmation": True,
    },
    "INT-003": {
        "name": "check_ticket_status",
        "description": "Checks on the status for a specific reported ticket.",
        "type": "internal",
        "active": True,
        "requires_confirmation": False,
        "parameters": {
            "ticket_id": {
                "type": "string",
                "required": True,
                "param_type": "internal",
                "description": "The ID of the ticket to check status for"
            }
        }
    },
    "INT-004": {
        "name": "search_tickets",
        "description": "Searches reported tickets, used to avoid duplication.",
        "type": "internal",
        "active": True,
        "requires_confirmation": False,
        "parameters": {
            "query": {
                "type": "string",
                "required": True,
                "param_type": "internal",
                "description": "The query to search reported tickets with"
            }
        }
    },
    "INT-005": {
        "name": "request_confirmation",
        "description": "Requests confirmation from the user to execute an action.",
        "type": "internal",
        "active": True,
        "requires_confirmation": False,
    },
}


class ActionService:
    """Service for managing actions stored in JSON file"""
    
    def __init__(self):
        self.file_path = settings.ACTIONS_FILE_FULL_PATH
        self.backup_dir = settings.ACTIONS_BACKUP_DIR
        self.backup_enabled = settings.ACTIONS_BACKUP_ENABLED
        self.backup_count = settings.ACTIONS_BACKUP_COUNT
        self.lock_path = self.file_path.with_suffix('.lock')
        
        # Ensure data directory exists
        self._ensure_directories()
    
    # =========================================================================
    # File Operations
    # =========================================================================
    
    def _ensure_directories(self) -> None:
        """Ensure data and backup directories exist"""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if self.backup_enabled:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Create file if not exists with default internal actions
        if not self.file_path.exists():
            self._save_data({
                "version": "2.0",
                "last_updated": None,
                "actions": DEFAULT_INTERNAL_ACTIONS.copy()
            })
            logger.info(f"Created new actions file with default internal actions: {self.file_path}")
    
    def _load_data(self) -> Dict[str, Any]:
        """Load actions data from JSON file"""
        try:
            with FileLock(self.lock_path):
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Ensure internal actions exist
                    actions = data.get("actions", {})
                    for int_id, int_action in DEFAULT_INTERNAL_ACTIONS.items():
                        if int_id not in actions:
                            actions[int_id] = int_action.copy()
                    data["actions"] = actions
                    
                    return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in actions file: {e}")
            raise InvalidActionStructureException(f"Actions file contains invalid JSON: {e}")
        except FileNotFoundError:
            logger.warning("Actions file not found, creating new one")
            self._ensure_directories()
            return {"version": "2.0", "last_updated": None, "actions": DEFAULT_INTERNAL_ACTIONS.copy()}
        except Exception as e:
            logger.error(f"Error loading actions file: {e}")
            raise
    
    def _save_data(self, data: Dict[str, Any]) -> None:
        """Save actions data to JSON file"""
        try:
            # Create backup before saving
            if self.backup_enabled and self.file_path.exists():
                self._create_backup()
            
            # Update timestamp
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            
            with FileLock(self.lock_path):
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info("Actions file saved successfully")
        except Exception as e:
            logger.error(f"Error saving actions file: {e}")
            raise
    
    def _create_backup(self) -> None:
        """Create backup of current actions file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"actions_backup_{timestamp}.json"
            backup_path = self.backup_dir / backup_name
            
            shutil.copy2(self.file_path, backup_path)
            logger.info(f"Backup created: {backup_path}")
            
            # Clean old backups
            self._cleanup_old_backups()
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
    
    def _cleanup_old_backups(self) -> None:
        """Remove old backup files, keeping only the most recent ones"""
        try:
            backups = sorted(
                self.backup_dir.glob("actions_backup_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            
            for old_backup in backups[self.backup_count:]:
                old_backup.unlink()
                logger.info(f"Removed old backup: {old_backup}")
        except Exception as e:
            logger.warning(f"Failed to cleanup backups: {e}")
    
    # =========================================================================
    # ID Generation
    # =========================================================================
    
    def _generate_next_id(self, action_type: ActionType) -> str:
        """Generate next available ID for action type"""
        data = self._load_data()
        actions = data.get("actions", {})
        
        # Determine prefix based on type
        if action_type == ActionType.INTERNAL:
            prefix = "INT"
        else:
            prefix = "ACT"
        
        # Find max number for this prefix
        max_num = 0
        pattern = re.compile(rf'^{prefix}-(\d+)$')
        
        for action_id in actions.keys():
            match = pattern.match(action_id)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
        
        # Generate next ID
        next_num = max_num + 1
        return f"{prefix}-{next_num:03d}"
    
    def _is_internal_action(self, action_id: str) -> bool:
        """Check if action ID is for internal action"""
        return action_id.startswith("INT-")
    
    # =========================================================================
    # Validation Methods
    # =========================================================================
    
    def validate_action(
        self, 
        action_data: Dict[str, Any],
        is_update: bool = False
    ) -> Tuple[bool, List[str]]:
        """Validate action data structure and rules. Returns (is_valid, warnings_list)"""
        warnings = []
        
        # Get action type
        action_type_str = action_data.get("type")
        if not action_type_str:
            if not is_update:
                raise MissingFieldException("type")
            return True, warnings
        
        # Validate action type
        try:
            action_type = ActionType(action_type_str)
        except ValueError:
            raise UnsupportedActionTypeException(action_type_str)
        
        # Internal actions cannot be created/modified
        if action_type == ActionType.INTERNAL and not is_update:
            raise InternalActionNotAllowedException("create")
        
        # Get type config
        type_config = ACTION_TYPE_CONFIG.get(action_type)
        if not type_config:
            raise UnsupportedActionTypeException(action_type_str)
        
        # Skip validation for internal actions
        if action_type == ActionType.INTERNAL:
            return True, warnings
        
        # Validate execution_config
        exec_config = action_data.get("execution_config", {})
        if not exec_config and not is_update:
            raise MissingFieldException("execution_config")
        
        if exec_config:
            self._validate_execution_config(exec_config, action_type, type_config)
        
        # Validate parameters
        parameters = action_data.get("parameters", {})
        if parameters:
            self._validate_parameters(
                parameters, 
                action_type, 
                type_config, 
                exec_config
            )
        
        # Validate response_config
        response_config = action_data.get("response_config")
        if response_config:
            self._validate_response_config(response_config, action_type, type_config)
        
        # Check for path params in URL (warning only)
        if action_type == ActionType.API_REQUEST and parameters and exec_config:
            url = exec_config.get("url", "")
            for param_name, param_config in parameters.items():
                if param_config.get("param_type") == "path":
                    if f"{{{param_name}}}" not in url:
                        warnings.append(
                            f"Path parameter '{param_name}' not found in URL. "
                            f"URL should contain '{{{param_name}}}'"
                        )
        
        return True, warnings
    
    def _validate_execution_config(
        self,
        exec_config: Dict[str, Any],
        action_type: ActionType,
        type_config: Dict
    ) -> None:
        """Validate execution_config based on action type"""
        
        # Check required fields
        for field in type_config["required_exec_fields"]:
            if field not in exec_config or exec_config[field] is None:
                raise MissingFieldException(field, "execution_config")
        
        # Check for forbidden fields
        for field in type_config.get("forbidden_exec_fields", []):
            if field in exec_config and exec_config[field] is not None:
                raise RpcFieldInNonRpcActionException(field, action_type.value)
        
        # Validate protocol
        if "protocol" in exec_config and exec_config["protocol"]:
            protocol = exec_config["protocol"]
            if action_type == ActionType.API_REQUEST:
                if protocol not in ["http", "https"]:
                    raise InvalidActionFieldException(
                        f"protocol={protocol}",
                        "api_request (must be http or https)"
                    )
            elif action_type == ActionType.RPC_REQUEST:
                if protocol != "grpc":
                    raise InvalidActionFieldException(
                        f"protocol={protocol}",
                        "rpc_request (must be grpc)"
                    )
    
    def _validate_parameters(
        self,
        parameters: Dict[str, Any],
        action_type: ActionType,
        type_config: Dict,
        exec_config: Dict[str, Any]
    ) -> None:
        """Validate parameters based on action type"""
        
        allowed_param_types = type_config["allowed_param_types"]
        http_method = exec_config.get("method", "GET")
        if http_method:
            http_method = http_method.upper() if isinstance(http_method, str) else http_method.value.upper()
        else:
            http_method = "GET"
        
        for param_name, param_config in parameters.items():
            # Check param_type
            param_type = param_config.get("param_type")
            if not param_type:
                raise MissingFieldException("param_type", f"parameters.{param_name}")
            
            if param_type not in allowed_param_types:
                raise InvalidParamTypeException(
                    param_type, 
                    action_type.value, 
                    allowed_param_types
                )
            
            # Check value type
            value_type = param_config.get("type")
            if not value_type:
                raise MissingFieldException("type", f"parameters.{param_name}")
            
            from utils.schemas.action_schemas import InvalidParamValueTypeException
            if value_type not in InvalidParamValueTypeException.SUPPORTED_VALUE_TYPES:
                raise InvalidParamValueTypeException(value_type, param_name)
            
            # Check required field
            if "required" not in param_config:
                raise MissingFieldException("required", f"parameters.{param_name}")
            
            # Check description
            if "description" not in param_config:
                raise MissingFieldException("description", f"parameters.{param_name}")
            
            # Body param on GET request
            if (action_type == ActionType.API_REQUEST and 
                param_type == "body" and 
                http_method == "GET"):
                raise BodyParamOnGetRequestException(param_name)
    
    def _validate_response_config(
        self,
        response_config: Dict[str, Any],
        action_type: ActionType,
        type_config: Dict
    ) -> None:
        """Validate response_config based on action type"""
        
        # Check mode
        mode = response_config.get("mode")
        if not mode:
            raise MissingFieldException("mode", "response_config")
        
        allowed_modes = type_config["allowed_response_modes"]
        if mode not in allowed_modes:
            raise InvalidResponseModeException(mode, action_type.value, allowed_modes)
        
        # Check template
        if "template" not in response_config:
            raise MissingFieldException("template", "response_config")
        
        # Check on_error
        if "on_error" not in response_config:
            raise MissingFieldException("on_error", "response_config")
        
        # Validate values structure
        values = response_config.get("values", {})
        for value_key, value_config in values.items():
            if "type" not in value_config:
                raise MissingFieldException("type", f"response_config.values.{value_key}")
            if "path" not in value_config:
                raise MissingFieldException("path", f"response_config.values.{value_key}")
            
            if value_config["type"] not in ["string", "integer"]:
                raise InvalidParamValueTypeException(value_config["type"], value_key)
    
    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    async def get_all_actions(
        self,
        action_type: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None
    ) -> Tuple[List[ActionSummary], int]:
        """Get all actions with optional filters"""
        data = self._load_data()
        actions = data.get("actions", {})
        
        filtered_actions = []
        for action_id, action in actions.items():
            # Filter by type
            if action_type and action.get("type") != action_type:
                continue
            # Filter by active status
            if active is not None and action.get("active") != active:
                continue
            # Filter by search
            if search:
                search_lower = search.lower()
                name_match = search_lower in action.get("name", "").lower()
                desc_match = search_lower in action.get("description", "").lower()
                if not (name_match or desc_match):
                    continue
            
            filtered_actions.append(ActionSummary(
                id=action_id,
                name=action["name"],
                description=action["description"],
                type=action["type"],
                active=action.get("active", True),
                requires_confirmation=action.get("requires_confirmation", False)
            ))
        
        # Sort: internal actions last, then by ID
        filtered_actions.sort(key=lambda x: (x.type == ActionType.INTERNAL, x.id))
        
        return filtered_actions, len(filtered_actions)
    
    async def get_action_by_id(self, action_id: str) -> ActionResponse:
        """Get action by ID"""
        data = self._load_data()
        actions = data.get("actions", {})
        
        if action_id not in actions:
            raise ActionNotFoundException(action_id)
        
        action = actions[action_id]
        return ActionResponse(
            id=action_id,
            name=action["name"],
            description=action["description"],
            type=action["type"],
            active=action.get("active", True),
            requires_confirmation=action.get("requires_confirmation", False),
            execution_config=action.get("execution_config"),
            parameters=action.get("parameters"),
            response_config=action.get("response_config")
        )
    
    async def get_action_by_name(self, name: str) -> ActionResponse:
        """Get action by name"""
        data = self._load_data()
        actions = data.get("actions", {})
        
        for action_id, action in actions.items():
            if action["name"] == name:
                return ActionResponse(
                    id=action_id,
                    name=action["name"],
                    description=action["description"],
                    type=action["type"],
                    active=action.get("active", True),
                    requires_confirmation=action.get("requires_confirmation", False),
                    execution_config=action.get("execution_config"),
                    parameters=action.get("parameters"),
                    response_config=action.get("response_config")
                )
        
        raise NotFoundException(f"Action '{name}' not found")
    
    async def create_action(self, action_data: ActionCreate) -> Tuple[str, str]:
        """Create a new action. Returns (id, name)"""
        data = self._load_data()
        actions = data.get("actions", {})
        
        # Check if internal type (not allowed)
        if action_data.type == ActionType.INTERNAL:
            raise InternalActionNotAllowedException("create")
        
        # Check for duplicate name
        for existing_action in actions.values():
            if existing_action["name"] == action_data.name:
                raise DuplicateActionNameException(action_data.name)
        
        # Validate action
        action_dict = action_data.model_dump(mode="json", exclude_none=True)
        is_valid, warnings = self.validate_action(action_dict)
        
        # Generate ID
        action_id = self._generate_next_id(action_data.type)
        
        # Add action
        actions[action_id] = action_dict
        data["actions"] = actions
        self._save_data(data)
        
        logger.info(f"Action created: {action_id} - {action_data.name}")
        if warnings:
            logger.warning(f"Action '{action_data.name}' created with warnings: {warnings}")
        
        return action_id, action_data.name
    
    async def update_action(self, action_id: str, update_data: ActionUpdate) -> Tuple[str, str]:
        """Update an existing action. Returns (id, name)"""
        data = self._load_data()
        actions = data.get("actions", {})
        
        # Check if action exists
        if action_id not in actions:
            raise ActionNotFoundException(action_id)
        
        existing_action = actions[action_id]
        
        # Check if internal action (read-only, except toggle)
        if existing_action.get("type") == "internal":
            raise InternalActionNotAllowedException("update")
        
        # Check for duplicate name if name is being changed
        if update_data.name and update_data.name != existing_action["name"]:
            for aid, action in actions.items():
                if aid != action_id and action["name"] == update_data.name:
                    raise DuplicateActionNameException(update_data.name)
        
        # Merge update data
        update_dict = update_data.model_dump(mode="json", exclude_none=True)
        merged_action = {**existing_action, **update_dict}
        
        # Handle nested updates for execution_config
        if update_data.execution_config:
            existing_exec = existing_action.get("execution_config", {})
            update_exec = update_dict.get("execution_config", {})
            merged_action["execution_config"] = {**existing_exec, **update_exec}
        
        # Validate merged action
        is_valid, warnings = self.validate_action(merged_action, is_update=True)
        
        # Update action
        actions[action_id] = merged_action
        data["actions"] = actions
        self._save_data(data)
        
        logger.info(f"Action updated: {action_id}")
        return action_id, merged_action["name"]
    
    async def delete_action(self, action_id: str) -> Tuple[str, str]:
        """Delete an action. Returns (id, name)"""
        data = self._load_data()
        actions = data.get("actions", {})
        
        # Check if action exists
        if action_id not in actions:
            raise ActionNotFoundException(action_id)
        
        action = actions[action_id]
        
        # Check if internal action (cannot delete)
        if action.get("type") == "internal":
            raise InternalActionNotAllowedException("delete")
        
        # Delete action
        action_name = action["name"]
        del actions[action_id]
        data["actions"] = actions
        self._save_data(data)
        
        logger.info(f"Action deleted: {action_id} - {action_name}")
        return action_id, action_name
    
    async def toggle_action_status(self, action_id: str) -> Tuple[str, str, bool]:
        """Toggle action active status. Returns (id, name, new_status)"""
        data = self._load_data()
        actions = data.get("actions", {})
        
        # Check if action exists
        if action_id not in actions:
            raise ActionNotFoundException(action_id)
        
        action = actions[action_id]
        
        # Toggle status (allowed for all actions including internal)
        action["active"] = not action.get("active", True)
        new_status = action["active"]
        
        data["actions"] = actions
        self._save_data(data)
        
        logger.info(f"Action '{action_id}' status toggled to: {new_status}")
        return action_id, action["name"], new_status
    
    async def validate_action_only(
        self, 
        action_data: Dict[str, Any]
    ) -> Tuple[bool, str, List[str]]:
        """Validate action without saving. Returns (is_valid, message, warnings)"""
        if "name" not in action_data:
            raise MissingFieldException("name")
        if "description" not in action_data:
            raise MissingFieldException("description")
        if "type" not in action_data:
            raise MissingFieldException("type")
        
        # Check internal type
        if action_data.get("type") == "internal":
            raise InternalActionNotAllowedException("create")
        
        is_valid, warnings = self.validate_action(action_data)
        return True, "Action structure is valid", warnings
    
    # =========================================================================
    # Backup Operations
    # =========================================================================
    
    async def get_all_backups(self) -> List[Dict[str, Any]]:
        """Get list of all backup files"""
        backups = []
        
        if not self.backup_dir.exists():
            return backups
        
        backup_files = sorted(
            self.backup_dir.glob("actions_backup_*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        for backup_file in backup_files:
            stat = backup_file.stat()
            filename = backup_file.name
            
            try:
                timestamp_str = filename.replace("actions_backup_", "").replace(".json", "")
                created_at = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                created_at = created_at.replace(tzinfo=timezone.utc)
            except ValueError:
                created_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            
            backups.append({
                "filename": filename,
                "created_at": created_at.isoformat(),
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 2)
            })
        
        return backups
    
    async def get_backup_content(self, filename: str) -> Dict[str, Any]:
        """Get content of a specific backup file"""
        backup_path = self.backup_dir / filename
        
        if not filename.startswith("actions_backup_") or not filename.endswith(".json"):
            raise NotFoundException(f"Invalid backup filename: {filename}")
        
        if not backup_path.exists():
            raise NotFoundException(f"Backup '{filename}' not found")
        
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                actions = data.get("actions", {})
                return {
                    "filename": filename,
                    "content": data,
                    "actions_count": len(actions)
                }
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in backup file {filename}: {e}")
            raise InvalidActionStructureException(f"Backup file contains invalid JSON: {e}")
    
    async def restore_backup(self, filename: str) -> Dict[str, Any]:
        """Restore actions from a backup file"""
        backup_path = self.backup_dir / filename
        
        if not filename.startswith("actions_backup_") or not filename.endswith(".json"):
            raise NotFoundException(f"Invalid backup filename: {filename}")
        
        if not backup_path.exists():
            raise NotFoundException(f"Backup '{filename}' not found")
        
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            if "actions" not in backup_data:
                raise InvalidActionStructureException("Backup file missing 'actions' field")
            
            # Create backup of current state
            if self.file_path.exists():
                self._create_backup()
            
            # Ensure internal actions exist in restored data
            actions = backup_data.get("actions", {})
            for int_id, int_action in DEFAULT_INTERNAL_ACTIONS.items():
                if int_id not in actions:
                    actions[int_id] = int_action.copy()
            backup_data["actions"] = actions
            
            # Update metadata
            backup_data["last_updated"] = datetime.now(timezone.utc).isoformat()
            backup_data["restored_from"] = filename
            backup_data["restored_at"] = datetime.now(timezone.utc).isoformat()
            
            with FileLock(self.lock_path):
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
            actions_count = len(backup_data.get("actions", {}))
            logger.info(f"Backup restored: {filename} ({actions_count} actions)")
            
            return {
                "message": "Backup restored successfully",
                "restored_from": filename,
                "actions_count": actions_count
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in backup file {filename}: {e}")
            raise InvalidActionStructureException(f"Backup file contains invalid JSON: {e}")
    
    async def delete_backup(self, filename: str) -> Dict[str, str]:
        """Delete a specific backup file"""
        backup_path = self.backup_dir / filename
        
        if not filename.startswith("actions_backup_") or not filename.endswith(".json"):
            raise NotFoundException(f"Invalid backup filename: {filename}")
        
        if not backup_path.exists():
            raise NotFoundException(f"Backup '{filename}' not found")
        
        try:
            backup_path.unlink()
            logger.info(f"Backup deleted: {filename}")
            return {"message": "Backup deleted successfully", "filename": filename}
        except Exception as e:
            logger.error(f"Failed to delete backup {filename}: {e}")
            raise
    
    async def delete_all_backups(self) -> Dict[str, Any]:
        """Delete all backup files"""
        if not self.backup_dir.exists():
            return {"message": "No backups to delete", "deleted_count": 0}
        
        backup_files = list(self.backup_dir.glob("actions_backup_*.json"))
        deleted_count = 0
        
        for backup_file in backup_files:
            try:
                backup_file.unlink()
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete backup {backup_file.name}: {e}")
        
        logger.info(f"Deleted {deleted_count} backup files")
        return {"message": f"Deleted {deleted_count} backup(s)", "deleted_count": deleted_count}
    
    async def compare_with_backup(self, filename: str) -> Dict[str, Any]:
        """Compare current actions with a backup"""
        backup_data = await self.get_backup_content(filename)
        backup_actions = backup_data["content"].get("actions", {})
        
        current_data = self._load_data()
        current_actions = current_data.get("actions", {})
        
        backup_ids = set(backup_actions.keys())
        current_ids = set(current_actions.keys())
        
        added = list(current_ids - backup_ids)
        removed = list(backup_ids - current_ids)
        
        modified = []
        for action_id in backup_ids & current_ids:
            if backup_actions[action_id] != current_actions[action_id]:
                modified.append(action_id)
        
        return {
            "filename": filename,
            "backup_actions_count": len(backup_actions),
            "current_actions_count": len(current_actions),
            "added": added,
            "removed": removed,
            "modified": modified,
            "has_changes": bool(added or removed or modified)
        }