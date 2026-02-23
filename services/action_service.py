# services/action_service.py
import json
import shutil
import logging
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
    InvalidConnectorTypeException,
    BodyParamOnGetRequestException,
    PathParamNotInUrlException,
    VectorParamNotTopicException,
    ValuesNotAllowedInQueryException,
    RpcFieldInNonRpcActionException,
)

logger = logging.getLogger(__name__)


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
        
        # Create file if not exists
        if not self.file_path.exists():
            self._save_data({
                "version": "2.0",
                "last_updated": None,
                "actions": []
            })
            logger.info(f"Created new actions file: {self.file_path}")
    
    def _load_data(self) -> Dict[str, Any]:
        """Load actions data from JSON file"""
        try:
            with FileLock(self.lock_path):
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in actions file: {e}")
            raise InvalidActionStructureException(f"Actions file contains invalid JSON: {e}")
        except FileNotFoundError:
            logger.warning("Actions file not found, creating new one")
            self._ensure_directories()
            return {"version": "2.0", "last_updated": None, "actions": []}
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
        
        # Get type config
        type_config = ACTION_TYPE_CONFIG.get(action_type)
        if not type_config:
            raise UnsupportedActionTypeException(action_type_str)
        
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
                if action_type == ActionType.RPC_REQUEST:
                    continue
                raise RpcFieldInNonRpcActionException(field, action_type.value)
        
        # Validate connector type for query actions
        if "connector" in exec_config and exec_config["connector"]:
            connector = exec_config["connector"]
            if connector not in ["sqlite", "postgres"]:
                raise InvalidConnectorTypeException(connector)
        
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
            
            if value_type not in ["string", "integer"]:
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
            
            # Vector param only for 'topic'
            if param_type == "vector" and param_name != "topic":
                raise VectorParamNotTopicException(param_name)
    
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
        
        # Check values not allowed in query actions
        if type_config.get("no_values_in_response") and response_config.get("values"):
            raise ValuesNotAllowedInQueryException(action_type.value)
        
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
        actions = data.get("actions", [])
        
        filtered_actions = []
        for action in actions:
            if action_type and action.get("type") != action_type:
                continue
            if active is not None and action.get("active") != active:
                continue
            if search:
                search_lower = search.lower()
                name_match = search_lower in action.get("name", "").lower()
                desc_match = search_lower in action.get("description", "").lower()
                if not (name_match or desc_match):
                    continue
            
            filtered_actions.append(ActionSummary(
                name=action["name"],
                description=action["description"],
                type=action["type"],
                active=action["active"]
            ))
        
        return filtered_actions, len(filtered_actions)
    
    async def get_action_by_name(self, name: str) -> ActionResponse:
        """Get action by name"""
        data = self._load_data()
        actions = data.get("actions", [])
        
        for action in actions:
            if action["name"] == name:
                return ActionResponse(
                    name=action["name"],
                    description=action["description"],
                    type=action["type"],
                    active=action["active"],
                    execution_config=action["execution_config"],
                    parameters=action.get("parameters"),
                    response_config=action.get("response_config")
                )
        
        raise NotFoundException(f"Action '{name}' not found")
    
    async def create_action(self, action_data: ActionCreate) -> str:
        """Create a new action"""
        data = self._load_data()
        actions = data.get("actions", [])
        
        for action in actions:
            if action["name"] == action_data.name:
                raise ConflictException(f"Action '{action_data.name}' already exists")
        
        action_dict = action_data.model_dump(mode="json", exclude_none=True)
        is_valid, warnings = self.validate_action(action_dict)
        
        actions.append(action_dict)
        data["actions"] = actions
        self._save_data(data)
        
        logger.info(f"Action created: {action_data.name}")
        if warnings:
            logger.warning(f"Action '{action_data.name}' created with warnings: {warnings}")
        
        return action_data.name
    
    async def update_action(self, name: str, update_data: ActionUpdate) -> str:
        """Update an existing action"""
        data = self._load_data()
        actions = data.get("actions", [])
        
        action_index = None
        existing_action = None
        for i, action in enumerate(actions):
            if action["name"] == name:
                action_index = i
                existing_action = action.copy()
                break
        
        if action_index is None:
            raise NotFoundException(f"Action '{name}' not found")
        
        update_dict = update_data.model_dump(mode="json", exclude_none=True)
        merged_action = {**existing_action, **update_dict}
        
        is_valid, warnings = self.validate_action(merged_action, is_update=True)
        
        actions[action_index] = merged_action
        data["actions"] = actions
        self._save_data(data)
        
        logger.info(f"Action updated: {name}")
        return name
    
    async def delete_action(self, name: str) -> str:
        """Delete an action"""
        data = self._load_data()
        actions = data.get("actions", [])
        
        action_found = False
        new_actions = []
        for action in actions:
            if action["name"] == name:
                action_found = True
            else:
                new_actions.append(action)
        
        if not action_found:
            raise NotFoundException(f"Action '{name}' not found")
        
        data["actions"] = new_actions
        self._save_data(data)
        
        logger.info(f"Action deleted: {name}")
        return name
    
    async def toggle_action_status(self, name: str) -> Tuple[str, bool]:
        """Toggle action active status"""
        data = self._load_data()
        actions = data.get("actions", [])
        
        action_found = False
        new_status = False
        for action in actions:
            if action["name"] == name:
                action_found = True
                action["active"] = not action.get("active", True)
                new_status = action["active"]
                break
        
        if not action_found:
            raise NotFoundException(f"Action '{name}' not found")
        
        data["actions"] = actions
        self._save_data(data)
        
        logger.info(f"Action '{name}' status toggled to: {new_status}")
        return name, new_status
    
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
                return {
                    "filename": filename,
                    "content": data,
                    "actions_count": len(data.get("actions", []))
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
            
            if self.file_path.exists():
                self._create_backup()
            
            backup_data["last_updated"] = datetime.now(timezone.utc).isoformat()
            backup_data["restored_from"] = filename
            backup_data["restored_at"] = datetime.now(timezone.utc).isoformat()
            
            with FileLock(self.lock_path):
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
            actions_count = len(backup_data.get("actions", []))
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
        backup_actions = {a["name"]: a for a in backup_data["content"].get("actions", [])}
        
        current_data = self._load_data()
        current_actions = {a["name"]: a for a in current_data.get("actions", [])}
        
        backup_names = set(backup_actions.keys())
        current_names = set(current_actions.keys())
        
        added = list(current_names - backup_names)
        removed = list(backup_names - current_names)
        
        modified = []
        for name in backup_names & current_names:
            if backup_actions[name] != current_actions[name]:
                modified.append(name)
        
        return {
            "filename": filename,
            "backup_actions_count": len(backup_actions),
            "current_actions_count": len(current_actions),
            "added": added,
            "removed": removed,
            "modified": modified,
            "has_changes": bool(added or removed or modified)
        }