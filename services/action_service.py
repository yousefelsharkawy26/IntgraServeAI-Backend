# services/action_service.py
import logging
from typing import Any, Dict, List, Optional, Tuple

from models.action import Action
from repositories.action_repository import ActionNameConflict, ActionRepository
from utils.schemas.action_schemas import (
    ACTION_TYPE_CONFIG, ActionCreate, ActionResponse, ActionSummary, ActionType, ActionUpdate,
)
from utils.exceptions import (
    MissingFieldException, InvalidActionFieldException, UnsupportedActionTypeException,
    InvalidParamTypeException, InvalidParamValueTypeException, InvalidResponseModeException,
    BodyParamOnGetRequestException, RpcFieldInNonRpcActionException,
    InternalActionNotAllowedException, DuplicateActionNameException, ActionNotFoundException,
    NotFoundException,
)

logger = logging.getLogger(__name__)


class ActionService:
    """Action business rules. Persistence is delegated to ActionRepository."""

    def __init__(self, repository: ActionRepository):
        self.repository = repository

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

            from utils.exceptions import InvalidParamValueTypeException
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

    async def get_all_actions(
        self, action_type: Optional[str] = None, active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[ActionSummary], int]:
        rows = await self.repository.list(action_type, active, search)
        summaries = [
            ActionSummary(
                id=row.id, name=row.name, description=row.description, type=row.type,
                active=row.active, requires_confirmation=row.requires_confirmation,
            )
            for row in rows
        ]
        summaries.sort(key=lambda item: (item.type == ActionType.INTERNAL, item.id))
        return summaries, len(summaries)

    async def get_action_by_id(self, action_id: str) -> ActionResponse:
        action = await self.repository.get_by_id(action_id)
        if action is None:
            raise ActionNotFoundException(action_id)
        return self._response(action)

    async def get_action_by_name(self, name: str) -> ActionResponse:
        action = await self.repository.get_by_name(name)
        if action is None:
            raise NotFoundException(f"Action '{name}' not found")
        return self._response(action)

    async def create_action(self, action_data: ActionCreate) -> Tuple[str, str]:
        if action_data.type == ActionType.INTERNAL:
            raise InternalActionNotAllowedException("create")
        if await self.repository.get_by_name(action_data.name):
            raise DuplicateActionNameException(action_data.name)

        values = action_data.model_dump(mode="json", exclude_none=True)
        _, warnings = self.validate_action(values)
        action = Action(**values)
        try:
            await self.repository.create(action)
        except ActionNameConflict:
            raise DuplicateActionNameException(action_data.name)
        await self._refresh_cached_engine()
        logger.info("Action created: %s - %s", action.id, action.name)
        if warnings:
            logger.warning("Action '%s' created with warnings: %s", action.name, warnings)
        return action.id, action.name

    async def update_action(self, action_id: str, update_data: ActionUpdate) -> Tuple[str, str]:
        action = await self.repository.get_by_id(action_id)
        if action is None:
            raise ActionNotFoundException(action_id)
        if action.type == "internal":
            raise InternalActionNotAllowedException("update")

        if update_data.name and update_data.name != action.name:
            duplicate = await self.repository.get_by_name(update_data.name)
            if duplicate is not None and duplicate.id != action_id:
                raise DuplicateActionNameException(update_data.name)

        update_values = update_data.model_dump(mode="json", exclude_none=True)
        current = action.to_dict(include_id=False)
        merged = {**current, **update_values}
        if update_data.execution_config is not None:
            merged["execution_config"] = {
                **(current.get("execution_config") or {}),
                **update_values.get("execution_config", {}),
            }
            update_values["execution_config"] = merged["execution_config"]
        self.validate_action(merged, is_update=True)
        await self.repository.update(action, update_values)
        await self._refresh_cached_engine()
        logger.info("Action updated: %s", action_id)
        return action.id, action.name

    async def delete_action(self, action_id: str) -> Tuple[str, str]:
        action = await self.repository.get_by_id(action_id)
        if action is None:
            raise ActionNotFoundException(action_id)
        if action.type == "internal":
            raise InternalActionNotAllowedException("delete")
        name = action.name
        await self.repository.delete(action)
        await self._refresh_cached_engine()
        logger.info("Action deleted: %s - %s", action_id, name)
        return action_id, name

    async def toggle_action_status(self, action_id: str) -> Tuple[str, str, bool]:
        action = await self.repository.get_by_id(action_id)
        if action is None:
            raise ActionNotFoundException(action_id)
        await self.repository.update(action, {"active": not action.active})
        await self._refresh_cached_engine()
        return action.id, action.name, action.active

    async def validate_action_only(
        self, action_data: Dict[str, Any],
    ) -> Tuple[bool, str, List[str]]:
        for field in ("name", "description", "type"):
            if field not in action_data:
                raise MissingFieldException(field)
        if action_data.get("type") == "internal":
            raise InternalActionNotAllowedException("create")
        _, warnings = self.validate_action(action_data)
        return True, "Action structure is valid", warnings

    async def _refresh_cached_engine(self) -> None:
        # Keep a previously initialized engine coherent without making CRUD
        # depend on engine initialization or a second database transaction.
        from services.ai_gateway_service import AIGatewayService

        if AIGatewayService.has_cached_engine():
            rows = await self.repository.list()
            current_config = AIGatewayService.get_engine().agent_config.model_dump(mode="json")
            AIGatewayService.configure_engine(
                current_config,
                [
                    row.to_dict(include_id=False, include_engine_fields=True)
                    | {"_backend_id": row.id}
                    for row in rows
                ],
            )

    @staticmethod
    def _response(action: Action) -> ActionResponse:
        return ActionResponse(
            id=action.id, name=action.name, description=action.description, type=action.type,
            active=action.active, requires_confirmation=action.requires_confirmation,
            execution_config=action.execution_config, parameters=action.parameters,
            response_config=action.response_config,
        )
