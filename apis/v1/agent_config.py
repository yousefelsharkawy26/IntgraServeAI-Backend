import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.user import User
from repositories.agent_config_repository import AgentConfigRepository
from services.agent_config_service import AgentConfigService
from utils.dependencies import require_admin
from utils.schemas.agent_config_schemas import AgentConfigResponse, AgentConfigUpdateResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def get_config_service(db: AsyncSession = Depends(get_db)) -> AgentConfigService:
    return AgentConfigService(AgentConfigRepository(db))


@router.get("", response_model=AgentConfigResponse, summary="Get Active Agent Configuration")
async def get_full_config(
    service: AgentConfigService = Depends(get_config_service),
    _: User = Depends(require_admin),
):
    return await service.get_full_config()


@router.put("", response_model=AgentConfigUpdateResponse, summary="Replace Active Agent Configuration")
async def update_full_config(
    config_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    service: AgentConfigService = Depends(get_config_service),
):
    await service.update_full_config(config_data, current_user.id)
    logger.info("Full agent config updated by admin: %s", current_user.email)
    return {"message": "Full configuration updated successfully"}
