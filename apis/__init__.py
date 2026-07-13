# apis/__init__.py

from fastapi import APIRouter
from apis.v1 import auth, users, tickets, roles, agent_config, actions, chat, llm_configs

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(tickets.router, prefix="/tickets", tags=["Tickets"])
api_router.include_router(roles.router, prefix="/roles", tags=["Roles"])
api_router.include_router(agent_config.router, prefix="/agent-config", tags=["Agent Config"])
api_router.include_router(llm_configs.router, prefix="/llm-configs", tags=["LLM Configurations"])
api_router.include_router(actions.router, prefix="/actions", tags=["Actions"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])