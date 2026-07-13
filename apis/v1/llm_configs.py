from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.user import User
from repositories.llm_config_repository import LLMConfigRepository
from services.llm_config_service import LLMConfigService
from utils.dependencies import require_admin
from utils.schemas.llm_config_schemas import (
    LLMConfigurationCreate,
    LLMConfigurationDeletedResponse,
    LLMConfigurationReplace,
    LLMConfigurationResponse,
    LLMConfigurationUpdate,
    ProviderInfo,
)

router = APIRouter()


def get_llm_config_service(db: AsyncSession = Depends(get_db)) -> LLMConfigService:
    return LLMConfigService(LLMConfigRepository(db))


@router.get("/providers", response_model=list[ProviderInfo])
async def list_supported_providers(_: User = Depends(require_admin)):
    return LLMConfigService.providers()


@router.get("", response_model=list[LLMConfigurationResponse])
async def list_llm_configurations(
    service: LLMConfigService = Depends(get_llm_config_service),
    _: User = Depends(require_admin),
):
    return await service.list()


@router.get("/{config_id}", response_model=LLMConfigurationResponse)
async def get_llm_configuration(
    config_id: UUID,
    service: LLMConfigService = Depends(get_llm_config_service),
    _: User = Depends(require_admin),
):
    return await service.get(config_id)


@router.post("", response_model=LLMConfigurationResponse, status_code=status.HTTP_201_CREATED)
async def create_llm_configuration(
    payload: LLMConfigurationCreate,
    service: LLMConfigService = Depends(get_llm_config_service),
    _: User = Depends(require_admin),
):
    return await service.create(payload)


@router.put("/{config_id}", response_model=LLMConfigurationResponse)
async def replace_llm_configuration(
    config_id: UUID,
    payload: LLMConfigurationReplace,
    service: LLMConfigService = Depends(get_llm_config_service),
    _: User = Depends(require_admin),
):
    return await service.replace(config_id, payload)


@router.patch("/{config_id}", response_model=LLMConfigurationResponse)
async def update_llm_configuration(
    config_id: UUID,
    payload: LLMConfigurationUpdate,
    service: LLMConfigService = Depends(get_llm_config_service),
    _: User = Depends(require_admin),
):
    return await service.patch(config_id, payload)


@router.delete("/{config_id}", response_model=LLMConfigurationDeletedResponse)
async def delete_llm_configuration(
    config_id: UUID,
    service: LLMConfigService = Depends(get_llm_config_service),
    _: User = Depends(require_admin),
):
    await service.delete(config_id)
    return {"message": "LLM configuration deleted successfully", "id": config_id}
